from __future__ import annotations

from datetime import datetime
from enum import Enum

from extensions import db
from models.booking import Booking
from models.charging_station import ChargingStation
from utils.datetime_utils import add_minutes, ensure_utc_datetime, utc_now


class BookingLifecycleStatus(str, Enum):
    ACTIVE = "active"
    COMPLETED = "completed"
    EXPIRED = "expired"
    CANCELLED = "cancelled"


TERMINAL_STATUSES = {
    BookingLifecycleStatus.COMPLETED.value,
    BookingLifecycleStatus.EXPIRED.value,
    BookingLifecycleStatus.CANCELLED.value,
}

BADGE_CLASS_MAP = {
    BookingLifecycleStatus.ACTIVE.value: "text-bg-primary",
    BookingLifecycleStatus.COMPLETED.value: "text-bg-success",
    BookingLifecycleStatus.EXPIRED.value: "text-bg-warning",
    BookingLifecycleStatus.CANCELLED.value: "text-bg-secondary",
}


def booking_expires_at(booking_time: datetime, charging_duration: int) -> datetime:
    return add_minutes(booking_time, charging_duration)


def booking_countdown_seconds(booking: Booking, reference_time: datetime | None = None) -> int:
    now = ensure_utc_datetime(reference_time) or utc_now()
    expires_at = ensure_utc_datetime(booking.expires_at)
    if expires_at is None:
        return 0
    return max(int((expires_at - now).total_seconds()), 0)


def lifecycle_label(status: str) -> str:
    return status.replace("_", " ").title()


def lifecycle_badge_class(status: str) -> str:
    return BADGE_CLASS_MAP.get(status, "text-bg-secondary")


def release_booking_slot(booking: Booking, reference_time: datetime | None = None) -> bool:
    now = ensure_utc_datetime(reference_time) or utc_now()
    station = (
        db.session.query(ChargingStation)
        .filter(ChargingStation.id == booking.station_id)
        .with_for_update()
        .one_or_none()
    )
    if station is None or booking.slot_released_at is not None:
        return False

    station.available_slots = min(station.available_slots + 1, station.total_slots)
    booking.slot_released_at = now
    booking.station = station
    return True


def expire_booking(booking: Booking, reference_time: datetime | None = None) -> bool:
    now = ensure_utc_datetime(reference_time) or utc_now()
    if booking.booking_status != BookingLifecycleStatus.ACTIVE.value:
        return False

    expires_at = ensure_utc_datetime(booking.expires_at)
    if expires_at is not None and expires_at > now:
        return False

    booking.booking_status = BookingLifecycleStatus.EXPIRED.value
    booking.expired_at = now
    release_booking_slot(booking, now)
    return True


def complete_booking(booking: Booking, reference_time: datetime | None = None) -> bool:
    now = ensure_utc_datetime(reference_time) or utc_now()
    if booking.booking_status != BookingLifecycleStatus.ACTIVE.value:
        return False

    booking.booking_status = BookingLifecycleStatus.COMPLETED.value
    booking.completed_at = now
    release_booking_slot(booking, now)
    return True


def cancel_booking(booking: Booking, reference_time: datetime | None = None) -> bool:
    now = ensure_utc_datetime(reference_time) or utc_now()
    if booking.booking_status != BookingLifecycleStatus.ACTIVE.value:
        return False

    booking.booking_status = BookingLifecycleStatus.CANCELLED.value
    booking.cancelled_at = now
    release_booking_slot(booking, now)
    return True


def sync_booking_lifecycle(booking: Booking, reference_time: datetime | None = None) -> bool:
    if booking.booking_status != BookingLifecycleStatus.ACTIVE.value:
        return False

    return expire_booking(booking, reference_time)


def expire_due_bookings(reference_time: datetime | None = None) -> int:
    now = ensure_utc_datetime(reference_time) or utc_now()
    due_bookings = (
        Booking.query
        .filter(
            Booking.booking_status == BookingLifecycleStatus.ACTIVE.value,
            Booking.expires_at.isnot(None),
            Booking.expires_at <= now,
            Booking.slot_released_at.is_(None),
        )
        .with_for_update(skip_locked=True)
        .all()
    )

    expired_count = 0
    for booking in due_bookings:
        if expire_booking(booking, now):
            expired_count += 1

    return expired_count
