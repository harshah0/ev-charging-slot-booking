from __future__ import annotations

from flask_login import current_user
from flask_socketio import emit, join_room

from extensions import socketio
from services.admin_analytics import build_admin_analytics_snapshot
from utils.datetime_utils import utc_now


_socketio_events_registered = False


def register_socketio_events() -> None:
    global _socketio_events_registered
    if _socketio_events_registered:
        return

    @socketio.on("connect")
    def handle_connect(auth=None):
        if current_user.is_authenticated:
            join_room(f"user:{current_user.id}")
            if current_user.is_admin():
                join_room("admins")
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

    _socketio_events_registered = True


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
    socketio.emit("wallet:update", payload, room=f"user:{user.id}")
    socketio.emit("notification:new", payload, room=f"user:{user.id}")
    emit_admin_analytics_snapshot(reason="wallet")


def emit_admin_analytics_snapshot(*, reason: str) -> None:
    snapshot = build_admin_analytics_snapshot()
    snapshot["reason"] = reason
    socketio.emit("analytics:update", snapshot, room="admins")
