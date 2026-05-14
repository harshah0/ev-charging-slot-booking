from __future__ import annotations

from datetime import datetime, timedelta, timezone


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def ensure_utc_datetime(value: datetime | None) -> datetime | None:
    if value is None:
        return None

    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)

    return value.astimezone(timezone.utc)


def add_minutes(value: datetime, minutes: int) -> datetime:
    normalized_value = ensure_utc_datetime(value)
    if normalized_value is None:
        raise ValueError("A valid datetime value is required.")
    return normalized_value + timedelta(minutes=minutes)
