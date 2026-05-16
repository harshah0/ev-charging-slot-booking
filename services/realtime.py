from __future__ import annotations

from flask import current_app, request
from flask_login import current_user
from flask_socketio import emit, join_room
from sqlalchemy import func

from extensions import db
from extensions import socketio
from models import ChargingStation
from services.admin_analytics import build_admin_analytics_snapshot
from utils.datetime_utils import utc_now


_socketio_events_registered = False

def _log_socket(message: str, **details) -> None:
    try:
        current_app.logger.debug("socketio %s %s", message, details)
    except Exception:
        pass


def register_socketio_events() -> None:
    global _socketio_events_registered
    if _socketio_events_registered:
        return

    @socketio.on("connect")
    def handle_connect(auth=None):
        _log_socket(
            "connect",
            sid=getattr(request, "sid", None),
            user_id=current_user.id if current_user.is_authenticated else None,
            role=getattr(current_user, "role", None) if current_user.is_authenticated else None,
            auth_present=bool(auth),
        )
        _emit_station_bulk_update()
        if current_user.is_authenticated:
            join_room(f"user:{current_user.id}")
            if current_user.is_admin():
                # Admin sockets listen in a dedicated room so analytics can be
                # broadcast without leaking to regular users.
                join_room("admins")
                # Do not emit analytics snapshot on connect to avoid duplicate
                # broadcasts during reconnect/connect storms. Admin clients will
                # request a sync via `sync:request` on connect.

            emit(
                "wallet:update",
                {
                    "user_id": current_user.id,
                    "wallet_balance": float(current_user.wallet_balance),
                    "server_time": utc_now().isoformat(),
                },
            )

            emit(
                "socket:ready",
                {
                    "user_id": current_user.id,
                    "role": getattr(current_user, "role", "user"),
                    "server_time": utc_now().isoformat(),
                },
            )
        else:
            emit("socket:ready", {"server_time": utc_now().isoformat()})

    @socketio.on("disconnect")
    def handle_disconnect():
        _log_socket(
            "disconnect",
            sid=getattr(request, "sid", None),
            user_id=current_user.id if current_user.is_authenticated else None,
        )

    @socketio.on("sync:request")
    def handle_sync_request(payload=None):
        _log_socket(
            "sync:request",
            sid=getattr(request, "sid", None),
            user_id=current_user.id if current_user.is_authenticated else None,
            payload=payload,
        )
        _emit_station_bulk_update()
        if current_user.is_authenticated:
            emit(
                "wallet:update",
                {
                    "user_id": current_user.id,
                    "wallet_balance": float(current_user.wallet_balance),
                    "server_time": utc_now().isoformat(),
                },
            )
            # Do not automatically emit analytics snapshot on sync requests.
            # This prevents rapid analytics echoes during reconnects/page reloads.
            # Admin clients should only receive analytics updates triggered by
            # actual business events (bookings/recharges).

    _socketio_events_registered = True


def _emit_station_bulk_update() -> None:
    rows = (
        db.session.query(
            ChargingStation.id,
            ChargingStation.available_slots,
            ChargingStation.total_slots,
            func.now(),
        )
        .order_by(ChargingStation.id.asc())
        .all()
    )
    payload = {
        "stations": [
            {
                "station_id": int(row[0]),
                "available_slots": int(row[1]),
                "total_slots": int(row[2]),
            }
            for row in rows
        ],
        "server_time": utc_now().isoformat(),
    }
    _log_socket("emit station:bulk_update", station_count=len(payload["stations"]))
    emit(
        "station:bulk_update",
        payload,
    )


def emit_live_booking_event(*, action: str, booking, station=None, message: str | None = None) -> None:
    station_obj = station or getattr(booking, "station", None)
    payload = {
        "action": action,
        "message": message,
        "server_time": utc_now().isoformat(),
        "booking": {
            "id": booking.id,
            "user_id": booking.user_id,
            "station_id": booking.station_id,
            "booking_status": booking.lifecycle_state,
            "booking_time": booking.booking_time.isoformat() if booking.booking_time else None,
            "expires_at": booking.expires_at.isoformat() if getattr(booking, "expires_at", None) else None,
            "available_slots": station_obj.available_slots if station_obj else None,
            "total_slots": station_obj.total_slots if station_obj else None,
        },
    }
    _log_socket(
        "emit booking:update",
        action=action,
        booking_id=booking.id,
        user_id=booking.user_id,
        station_id=booking.station_id,
    )
    socketio.emit("booking:update", payload)
    socketio.emit(
        "station:update",
        {
            "station_id": station_obj.id if station_obj else booking.station_id,
            "available_slots": station_obj.available_slots if station_obj else None,
            "total_slots": station_obj.total_slots if station_obj else None,
            "action": action,
            "server_time": payload["server_time"],
        },
    )
    socketio.emit("notification:new", payload, room=f"user:{booking.user_id}")
    emit_admin_analytics_snapshot(reason=action)


def emit_wallet_update(*, user, transaction, message: str | None = None) -> None:
    payload = {
        "message": message,
        "server_time": utc_now().isoformat(),
        "user_id": user.id,
        "wallet_balance": float(user.wallet_balance),
        "transaction": {
            "id": transaction.id,
            "type": transaction.transaction_type,
            "amount": float(transaction.amount),
            "status": transaction.status,
            "balance_after": float(transaction.balance_after),
            "description": transaction.description,
        },
    }
    _log_socket(
        "emit wallet:update",
        user_id=user.id,
        transaction_id=transaction.id,
        amount=float(transaction.amount),
    )
    socketio.emit("wallet:update", payload, room=f"user:{user.id}")
    socketio.emit("notification:new", payload, room=f"user:{user.id}")
    # Wallet updates are frequent and not considered primary analytics triggers.
    # Do not emit admin analytics snapshot here to avoid noisy dashboard updates.


def emit_recharge_analytics_update(*, user, amount) -> None:
    """Broadcast a recharge-specific analytics update to admin dashboards.

    This is a business-event emission only. It is intentionally not tied to
    connect, reconnect, or sync flows so we avoid recursive websocket loops.
    """
    payload = {
        "type": "recharge",
        "user_id": user.id,
        "amount": float(amount),
        "wallet_balance": float(user.wallet_balance),
    }
    _log_socket(
        "emit analytics:update",
        reason="recharge",
        user_id=user.id,
        amount=float(amount),
        wallet_balance=float(user.wallet_balance),
    )
    socketio.emit("analytics:update", payload, room="admins")


def emit_admin_analytics_snapshot(*, reason: str) -> None:
    snapshot = build_admin_analytics_snapshot()
    snapshot["reason"] = reason
    _log_socket(
        "emit analytics:update",
        reason=reason,
        total_bookings=snapshot.get("total_bookings"),
        active_bookings=snapshot.get("active_bookings"),
    )
    try:
        socketio.emit("analytics:update", snapshot, room="admins")
    except Exception:
        _log_socket("emit analytics:update failed", reason=reason)
