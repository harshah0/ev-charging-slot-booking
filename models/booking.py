from __future__ import annotations

from datetime import datetime

from sqlalchemy import CheckConstraint, func, text
from sqlalchemy.orm import validates

from extensions import db


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
        default="confirmed",
        server_default=text("'confirmed'"),
    )
    created_at = db.Column(
        db.DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )

    user = db.relationship("User", back_populates="bookings")
    station = db.relationship("ChargingStation", back_populates="bookings")

    @property
    def is_active(self) -> bool:
        return self.booking_status == "confirmed"

    @validates("booking_status")
    def validate_booking_status(self, key: str, value: str) -> str:
        value = value.strip().lower()
        valid_statuses = {"confirmed", "cancelled"}
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
        return value

    def __repr__(self) -> str:
        return (
            f"Booking(id={self.id!r}, user_id={self.user_id!r}, "
            f"station_id={self.station_id!r}, booking_status={self.booking_status!r})"
        )
