from __future__ import annotations

from decimal import Decimal


VALID_CHARGING_TYPES = {
    "AC",
    "DC",
    "Level 1",
    "Level 2",
    "Fast Charging",
}


def validate_station_payload(data: dict[str, str]) -> list[str]:
    errors: list[str] = []

    station_name = data.get("station_name", "").strip()
    address = data.get("address", "").strip()
    city = data.get("city", "").strip()
    state = data.get("state", "").strip()
    charging_type = data.get("charging_type", "").strip()

    try:
        latitude = Decimal(data.get("latitude", ""))
        longitude = Decimal(data.get("longitude", ""))
        total_slots = int(data.get("total_slots", ""))
    except Exception:
        errors.append("Latitude, longitude, and total slots must be valid numbers.")
        return errors

    if not station_name:
        errors.append("Station name is required.")
    if not address:
        errors.append("Address is required.")
    if not city:
        errors.append("City is required.")
    if not state:
        errors.append("State is required.")

    if latitude < Decimal("-90") or latitude > Decimal("90"):
        errors.append("Latitude must be between -90 and 90.")
    if longitude < Decimal("-180") or longitude > Decimal("180"):
        errors.append("Longitude must be between -180 and 180.")
    if total_slots <= 0:
        errors.append("Total slots must be greater than zero.")
    if not charging_type:
        errors.append("Charging type is required.")
    elif charging_type not in VALID_CHARGING_TYPES:
        errors.append("Select a valid charging type.")

    return errors
