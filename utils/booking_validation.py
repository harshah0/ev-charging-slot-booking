from __future__ import annotations

from datetime import datetime, timezone

MIN_CHARGING_DURATION_MINUTES = 15
MAX_CHARGING_DURATION_MINUTES = 24 * 60


def parse_booking_time(raw_value: str | None) -> datetime | None:
    if not raw_value:
        return None

    try:
        parsed_value = datetime.fromisoformat(raw_value)
    except ValueError:
        try:
            parsed_value = datetime.strptime(raw_value, "%Y-%m-%dT%H:%M")
        except ValueError:
            return None

    if parsed_value.tzinfo is None:
        parsed_value = parsed_value.replace(tzinfo=timezone.utc)
    return parsed_value.astimezone(timezone.utc)


def validate_booking_payload(data) -> tuple[list[str], datetime | None, int | None]:
    errors: list[str] = []

    booking_time = parse_booking_time(data.get("booking_time"))
    if booking_time is None:
        errors.append("Booking time is required and must be valid.")

    try:
        charging_duration = int(data.get("charging_duration", ""))
    except (TypeError, ValueError):
        charging_duration = None
        errors.append("Charging duration must be a valid number.")
    else:
        if charging_duration < MIN_CHARGING_DURATION_MINUTES:
            errors.append("Charging duration must be at least 15 minutes.")
        elif charging_duration > MAX_CHARGING_DURATION_MINUTES:
            errors.append("Charging duration is too long.")

    if booking_time is not None and booking_time <= datetime.now(timezone.utc):
        errors.append("Booking time must be in the future.")

    return errors, booking_time, charging_duration
