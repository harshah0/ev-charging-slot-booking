from __future__ import annotations

from decimal import Decimal

from sqlalchemy import func
from sqlalchemy.orm import validates

from extensions import db


class ChargingStation(db.Model):
    __tablename__ = "charging_stations"

    id = db.Column(db.Integer, primary_key=True)
    station_name = db.Column(db.String(120), nullable=False, unique=True, index=True)
    address = db.Column(db.String(255), nullable=False)
    city = db.Column(db.String(80), nullable=False, index=True)
    state = db.Column(db.String(80), nullable=False, index=True)
    latitude = db.Column(db.Numeric(10, 7), nullable=False)
    longitude = db.Column(db.Numeric(10, 7), nullable=False)
    total_slots = db.Column(db.Integer, nullable=False)
    available_slots = db.Column(db.Integer, nullable=False)
    charging_type = db.Column(db.String(50), nullable=False)
    created_at = db.Column(
        db.DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )

    bookings = db.relationship("Booking", back_populates="station")

    @validates("station_name")
    def validate_station_name(self, key: str, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("Station name is required.")
        if len(value) > 120:
            raise ValueError("Station name must not exceed 120 characters.")
        return value

    @validates("address", "city", "state", "charging_type")
    def validate_text_fields(self, key: str, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError(f"{key.replace('_', ' ').title()} is required.")
        limits = {
            "address": 255,
            "city": 80,
            "state": 80,
            "charging_type": 50,
        }
        if len(value) > limits[key]:
            raise ValueError(f"{key.replace('_', ' ').title()} is too long.")
        return value

    @validates("latitude", "longitude")
    def validate_coordinates(self, key: str, value) -> Decimal:
        decimal_value = Decimal(str(value))
        if key == "latitude" and not Decimal("-90") <= decimal_value <= Decimal("90"):
            raise ValueError("Latitude must be between -90 and 90.")
        if key == "longitude" and not Decimal("-180") <= decimal_value <= Decimal("180"):
            raise ValueError("Longitude must be between -180 and 180.")
        return decimal_value

    @validates("total_slots", "available_slots")
    def validate_slots(self, key: str, value: int) -> int:
        value = int(value)
        if value < 0:
            raise ValueError(f"{key.replace('_', ' ').title()} cannot be negative.")
        return value

    def __repr__(self) -> str:
        return f"ChargingStation(id={self.id!r}, station_name={self.station_name!r})"
