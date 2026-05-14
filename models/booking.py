from __future__ import annotations

from datetime import datetime
from enum import Enum

from sqlalchemy import CheckConstraint, func, text
from sqlalchemy.orm import validates

from extensions import db
from utils.datetime_utils import ensure_utc_datetime, utc_now


class BookingLifecycleStatus(str, Enum):
    ACTIVE = "active"
    COMPLETED = "completed"
    EXPIRED = "expired"
    CANCELLED = "cancelled"


class Booking(db.Model):
    __tablename__ = "bookings"
    __table_args__ = (
        CheckConstraint("charging_duration > 0", name="ck_bookings_charging_duration_positive"),
        db.Index("ix_bookings_user_station_status", "user_id", "station_id", "booking_status"),
        db.Index("ix_bookings_station_time_status", "station_id", "booking_time", "booking_status"),
    )

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False, index=True)
    station_id = db.Column(
        db.Integer,
        db.ForeignKey("charging_stations.id"),
        nullable=False,
        index=True,
    )
    booking_time = db.Column(db.DateTime(timezone=True), nullable=False)
    charging_duration = db.Column(db.Integer, nullable=False)
    booking_status = db.Column(
        db.String(20),
        nullable=False,
        default=BookingLifecycleStatus.ACTIVE.value,
        server_default=text("'active'"),
    )
    activated_at = db.Column(db.DateTime(timezone=True), nullable=False, server_default=func.now())
    expires_at = db.Column(db.DateTime(timezone=True), nullable=False)
    completed_at = db.Column(db.DateTime(timezone=True), nullable=True)
    expired_at = db.Column(db.DateTime(timezone=True), nullable=True)
    cancelled_at = db.Column(db.DateTime(timezone=True), nullable=True)
    slot_released_at = db.Column(db.DateTime(timezone=True), nullable=True)
    created_at = db.Column(
        db.DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )

    user = db.relationship("User", back_populates="bookings")
    station = db.relationship("ChargingStation", back_populates="bookings")

    @property
    def is_active(self) -> bool:
        return self.booking_status == BookingLifecycleStatus.ACTIVE.value and not self.is_expired

    @property
    def is_expired(self) -> bool:
        if self.booking_status == BookingLifecycleStatus.EXPIRED.value:
            return True

        expires_at = ensure_utc_datetime(self.expires_at)
        return (
            self.booking_status == BookingLifecycleStatus.ACTIVE.value
            and expires_at is not None
            and expires_at <= utc_now()
        )

    @property
    def lifecycle_state(self) -> str:
        if self.booking_status == BookingLifecycleStatus.ACTIVE.value and self.is_expired:
            return BookingLifecycleStatus.EXPIRED.value
        return self.booking_status

    @property
    def seconds_remaining(self) -> int:
        expires_at = ensure_utc_datetime(self.expires_at)
        if expires_at is None:
            return 0
        return max(int((expires_at - utc_now()).total_seconds()), 0)

    @validates("booking_status")
    def validate_booking_status(self, key: str, value: str) -> str:
        value = value.strip().lower()
        if value == "confirmed":
            value = BookingLifecycleStatus.ACTIVE.value
        valid_statuses = {
            BookingLifecycleStatus.ACTIVE.value,
            BookingLifecycleStatus.COMPLETED.value,
            BookingLifecycleStatus.EXPIRED.value,
            BookingLifecycleStatus.CANCELLED.value,
        }
        if value not in valid_statuses:
            raise ValueError("Invalid booking status.")
        return value

    @validates("charging_duration")
    def validate_charging_duration(self, key: str, value: int) -> int:
        value = int(value)
        if value <= 0:
            raise ValueError("Charging duration must be greater than zero.")
        return value

    @validates("booking_time")
    def validate_booking_time(self, key: str, value: datetime) -> datetime:
        if not isinstance(value, datetime):
            raise ValueError("Booking time must be a valid datetime value.")
        normalized_value = ensure_utc_datetime(value)
        if normalized_value is None:
            raise ValueError("Booking time must be a valid datetime value.")
        return normalized_value

    @validates("activated_at", "expires_at", "completed_at", "expired_at", "cancelled_at", "slot_released_at")
    def validate_lifecycle_timestamp(self, key: str, value: datetime | None) -> datetime | None:
        return ensure_utc_datetime(value)

    def __repr__(self) -> str:
        return (
            f"Booking(id={self.id!r}, user_id={self.user_id!r}, "
            f"station_id={self.station_id!r}, booking_status={self.booking_status!r})"
        )
