from __future__ import annotations

from math import asin, cos, radians, sin, sqrt
from typing import Iterable

EARTH_RADIUS_KM = 6371.0088
SUPPORTED_RADIUS_KM = (5, 10, 25)


def haversine_distance_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Return great-circle distance in kilometers between two coordinates."""
    lat1_rad, lon1_rad = radians(lat1), radians(lon1)
    lat2_rad, lon2_rad = radians(lat2), radians(lon2)

    delta_lat = lat2_rad - lat1_rad
    delta_lon = lon2_rad - lon1_rad

    a = (
        sin(delta_lat / 2) ** 2
        + cos(lat1_rad) * cos(lat2_rad) * sin(delta_lon / 2) ** 2
    )
    c = 2 * asin(sqrt(a))
    return EARTH_RADIUS_KM * c


def parse_coordinate(value: str | float | None, name: str) -> float:
    if value is None or str(value).strip() == "":
        raise ValueError(f"{name} is required")

    parsed = float(value)
    if name == "latitude" and not -90.0 <= parsed <= 90.0:
        raise ValueError("latitude must be between -90 and 90")
    if name == "longitude" and not -180.0 <= parsed <= 180.0:
        raise ValueError("longitude must be between -180 and 180")
    return parsed


def parse_radius_km(value: str | int | None, default: int = 10) -> int:
    if value is None or str(value).strip() == "":
        return default

    radius = int(value)
    if radius not in SUPPORTED_RADIUS_KM:
        raise ValueError(f"radius_km must be one of {SUPPORTED_RADIUS_KM}")
    return radius


def with_distance(
    stations: Iterable[dict],
    *,
    user_lat: float,
    user_lon: float,
    radius_km: int | None = None,
) -> list[dict]:
    enriched: list[dict] = []
    for station in stations:
        distance_km = haversine_distance_km(
            user_lat,
            user_lon,
            float(station["latitude"]),
            float(station["longitude"]),
        )

        if radius_km is not None and distance_km > radius_km:
            continue

        enriched_station = dict(station)
        enriched_station["distance_km"] = round(distance_km, 2)
        enriched.append(enriched_station)

    enriched.sort(key=lambda item: item["distance_km"])
    return enriched
