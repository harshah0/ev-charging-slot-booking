from __future__ import annotations

import json
import os
import sys
import tempfile
from datetime import timedelta
from decimal import Decimal
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


def _configure_ci_test_database() -> None:
    """Set a writable sqlite path for CI smoke tests before app import.

    The app module creates a global Flask app at import time. In GitHub Actions,
    relative sqlite paths can fail when intermediate directories do not exist,
    causing db.create_all() to raise "unable to open database file".
    """
    if os.getenv("DATABASE_URL"):
        return

    temp_db = Path(tempfile.gettempdir()) / "ev-charging-slot-booking" / "realtime-smoke.db"
    temp_db.parent.mkdir(parents=True, exist_ok=True)
    os.environ["CI_SMOKE_TEST"] = "true"
    os.environ["DATABASE_URL"] = f"sqlite:///{temp_db.as_posix()}"


def _ensure_sqlite_directory(database_uri: str) -> None:
    if not database_uri.startswith("sqlite:///"):
        return

    target = database_uri.replace("sqlite:///", "", 1)
    if target in {":memory:", ""} or target.startswith("file:"):
        return

    Path(target).parent.mkdir(parents=True, exist_ok=True)


_configure_ci_test_database()

from app import app as flask_app
from extensions import db, socketio
from models import Booking, ChargingStation, User
from models.booking import BookingLifecycleStatus
from models.user import UserRole
from utils.datetime_utils import utc_now

USER_EMAIL = "realtime.user@ev.local"
USER_PASSWORD = "RealtimeUser123"
ADMIN_EMAIL = "admin@ev.com"
ADMIN_PASSWORD = "Admin123"


def ensure_user(email: str, username: str, password: str, role: str) -> User:
    user = User.query.filter_by(email=email).one_or_none()
    if user is None:
        user = User(
            email=email,
            username=username,
            role=role,
            wallet_balance=Decimal("0.00"),
        )
        user.set_password(password)
        db.session.add(user)
        db.session.commit()
        return user

    user.username = username
    user.role = role
    user.set_password(password)
    db.session.commit()
    return user


def ensure_station() -> ChargingStation:
    station = ChargingStation.query.filter_by(station_name="Realtime Verification Station").one_or_none()
    if station is None:
        station = ChargingStation(
            station_name="Realtime Verification Station",
            address="100 Realtime Street",
            city="Bengaluru",
            state="Karnataka",
            latitude="12.9716",
            longitude="77.5946",
            total_slots=5,
            available_slots=5,
            charging_type="DC Fast Charging",
        )
        db.session.add(station)
        db.session.commit()
    return station


def get_csrf_token(client, path: str) -> str:
    response = client.get(path, follow_redirects=True)
    if response.status_code >= 400:
        raise RuntimeError(f"Unable to load CSRF path {path}: status={response.status_code}")

    with client.session_transaction() as session:
        token = session.get("csrf_token")

    if not token:
        raise RuntimeError(f"CSRF token not generated for path {path}")
    return str(token)


def login(client, email: str, password: str) -> None:
    csrf_token = get_csrf_token(client, "/auth/login")
    response = client.post(
        "/auth/login",
        data={
            "csrf_token": csrf_token,
            "email": email,
            "password": password,
        },
        follow_redirects=False,
    )
    if response.status_code not in (302, 303):
        raise RuntimeError(f"Login failed for {email}: status={response.status_code}")


def pretty_events(tab_name: str, events: list[dict]) -> None:
    for event in events:
        payload = event.get("args", [])
        payload_obj = payload[0] if payload else None
        print(
            f"[browser:{tab_name}] event={event.get('name')} payload="
            f"{json.dumps(payload_obj, default=str, ensure_ascii=True)}"
        )


def names(events: list[dict]) -> list[str]:
    return [event.get("name", "") for event in events]


def assert_event(event_names: list[str], expected_name: str, step: str) -> None:
    if expected_name not in event_names:
        raise AssertionError(f"Missing event '{expected_name}' during {step}. Seen={event_names}")


def assert_station_bulk_payload(events: list[dict], step: str) -> None:
    bulk_events = [event for event in events if event.get("name") == "station:bulk_update"]
    if not bulk_events:
        raise AssertionError(f"Missing 'station:bulk_update' payload during {step}.")

    payload = (bulk_events[-1].get("args") or [None])[0] or {}
    stations = payload.get("stations") if isinstance(payload, dict) else None
    if not isinstance(stations, list) or not stations:
        raise AssertionError(f"Invalid station:bulk_update payload during {step}: {payload}")


def collect(socket_client, tab_name: str, step: str) -> list[dict]:
    socketio.sleep(0)
    events = socket_client.get_received()
    pretty_events(tab_name, events)
    print(f"[verify] {step} tab={tab_name} events={len(events)}")
    return events


def run() -> None:
    app = flask_app
    app.config["TESTING"] = True
    _ensure_sqlite_directory(str(app.config.get("SQLALCHEMY_DATABASE_URI", "")))

    with app.app_context():
        db.create_all()

        admin_user = ensure_user(
            email=ADMIN_EMAIL,
            username="admin",
            password=ADMIN_PASSWORD,
            role=UserRole.ADMIN.value,
        )
        verify_user = ensure_user(
            email=USER_EMAIL,
            username="realtime_user",
            password=USER_PASSWORD,
            role=UserRole.USER.value,
        )
        station = ensure_station()

        # Reset to known balances/state.
        verify_user.wallet_balance = Decimal("0.00")
        station.available_slots = station.total_slots
        db.session.query(Booking).filter(
            Booking.user_id == verify_user.id,
            Booking.booking_status == BookingLifecycleStatus.ACTIVE.value,
        ).delete(synchronize_session=False)
        db.session.commit()

    user_http = app.test_client()
    admin_http = app.test_client()

    login(user_http, USER_EMAIL, USER_PASSWORD)
    login(admin_http, ADMIN_EMAIL, ADMIN_PASSWORD)

    user_socket = socketio.test_client(app, flask_test_client=user_http)
    admin_socket = socketio.test_client(app, flask_test_client=admin_http)

    if not user_socket.is_connected() or not admin_socket.is_connected():
        raise RuntimeError(
            f"Socket connection failed: user_connected={user_socket.is_connected()} admin_connected={admin_socket.is_connected()}"
        )

    # Drain initial connect/sync events.
    collect(user_socket, "user", "initial-connect")
    collect(admin_socket, "admin", "initial-connect")

    # Step 1: recharge wallet
    recharge_csrf = get_csrf_token(user_http, "/payment/recharge")
    recharge_response = user_http.post(
        "/payment/recharge",
        data={"csrf_token": recharge_csrf, "amount": "250"},
        follow_redirects=False,
    )
    if recharge_response.status_code not in (302, 303):
        raise RuntimeError(f"Recharge failed: status={recharge_response.status_code}")

    user_events = collect(user_socket, "user", "recharge")
    admin_events = collect(admin_socket, "admin", "recharge")

    user_names = names(user_events)
    admin_names = names(admin_events)
    assert_event(user_names, "wallet:update", "recharge")
    assert_event(user_names, "notification:new", "recharge")
    assert_event(admin_names, "analytics:update", "recharge")
    recharge_admin_event = next(
        (event for event in admin_events if event.get("name") == "analytics:update"),
        None,
    )
    if not recharge_admin_event:
        raise RuntimeError("Missing recharge analytics event payload")
    recharge_payload = recharge_admin_event.get("args", [{}])[0]
    if recharge_payload.get("type") != "recharge":
        raise RuntimeError(f"Unexpected recharge analytics payload: {recharge_payload}")

    # Step 2: create booking
    with app.app_context():
        station_id = ChargingStation.query.filter_by(station_name="Realtime Verification Station").one().id

    booking_time = (utc_now() + timedelta(minutes=20)).strftime("%Y-%m-%dT%H:%M")
    booking_csrf = get_csrf_token(user_http, f"/bookings/new/{station_id}")
    create_response = user_http.post(
        "/bookings",
        data={
            "csrf_token": booking_csrf,
            "station_id": station_id,
            "booking_time": booking_time,
            "charging_duration": "30",
        },
        follow_redirects=False,
    )
    if create_response.status_code not in (302, 303):
        raise RuntimeError(f"Booking create failed: status={create_response.status_code}")

    user_events = collect(user_socket, "user", "booking-create")
    admin_events = collect(admin_socket, "admin", "booking-create")
    user_names = names(user_events)
    admin_names = names(admin_events)

    assert_event(user_names, "booking:update", "booking-create")
    assert_event(user_names, "station:update", "booking-create")
    assert_event(user_names, "notification:new", "booking-create")
    assert_event(admin_names, "analytics:update", "booking-create")

    # Step 3: complete booking
    with app.app_context():
        booking = (
            Booking.query.filter(
                Booking.user_id == User.query.filter_by(email=USER_EMAIL).one().id,
                Booking.booking_status == BookingLifecycleStatus.ACTIVE.value,
            )
            .order_by(Booking.created_at.desc())
            .first()
        )
        if booking is None:
            raise RuntimeError("No active booking found for completion step")
        booking_id = booking.id

    complete_csrf = get_csrf_token(user_http, "/bookings")
    complete_response = user_http.post(
        f"/bookings/{booking_id}/complete",
        data={"csrf_token": complete_csrf},
        follow_redirects=False,
    )
    if complete_response.status_code not in (302, 303):
        raise RuntimeError(f"Booking complete failed: status={complete_response.status_code}")

    user_events = collect(user_socket, "user", "booking-complete")
    admin_events = collect(admin_socket, "admin", "booking-complete")
    user_names = names(user_events)
    admin_names = names(admin_events)

    assert_event(user_names, "booking:update", "booking-complete")
    assert_event(user_names, "station:update", "booking-complete")
    assert_event(user_names, "notification:new", "booking-complete")
    assert_event(admin_names, "analytics:update", "booking-complete")

    # Step 4: explicit reconnect + sync request verification
    user_socket.disconnect()
    user_socket = socketio.test_client(app, flask_test_client=user_http)
    if not user_socket.is_connected():
        raise RuntimeError("User socket failed to reconnect")

    reconnect_events = collect(user_socket, "user", "reconnect-initial")
    reconnect_names = names(reconnect_events)
    assert_event(reconnect_names, "station:bulk_update", "reconnect-initial")
    assert_event(reconnect_names, "socket:ready", "reconnect-initial")
    assert_station_bulk_payload(reconnect_events, "reconnect-initial")

    user_socket.emit("sync:request", {"reason": "harness-reconnect-check"})
    sync_events = collect(user_socket, "user", "sync-request")
    sync_names = names(sync_events)
    assert_event(sync_names, "station:bulk_update", "sync-request")
    assert_event(sync_names, "wallet:update", "sync-request")
    assert_station_bulk_payload(sync_events, "sync-request")

    admin_socket.emit("sync:request", {"reason": "harness-admin-sync-check"})
    admin_sync_events = collect(admin_socket, "admin", "admin-sync-request")
    admin_sync_names = names(admin_sync_events)
    assert_event(admin_sync_names, "station:bulk_update", "admin-sync-request")
    assert_station_bulk_payload(admin_sync_events, "admin-sync-request")

    user_socket.disconnect()
    admin_socket.disconnect()

    print("[verify] PASS realtime event flow verified for recharge/create/complete/reconnect")


if __name__ == "__main__":
    run()
