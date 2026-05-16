from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import json
import os
from typing import Any
from urllib.parse import urlencode
from urllib.request import Request, urlopen
from urllib.error import URLError, HTTPError

from flask import current_app

from utils.geospatial import haversine_distance_km


@dataclass(slots=True)
class _CacheEntry:
    created_at: datetime
    payload: list[dict[str, Any]]


_CACHE: dict[str, _CacheEntry] = {}


def _cache_key(latitude: float, longitude: float, radius_km: float, max_results: int) -> str:
    return f"{latitude:.3f}:{longitude:.3f}:{radius_km:.1f}:{max_results}"


def _cache_ttl_seconds() -> int:
    return int(current_app.config.get("OPENCHARGEMAP_CACHE_TTL_SECONDS", 300))


def _max_results() -> int:
    return int(current_app.config.get("OPENCHARGEMAP_MAX_RESULTS", 25))


def _timeout_seconds() -> int:
    return int(current_app.config.get("OPENCHARGEMAP_TIMEOUT_SECONDS", 6))


def _api_key() -> str | None:
    api_key = current_app.config.get("OPENCHARGEMAP_API_KEY")
    if api_key:
        return str(api_key)
    return os.getenv("OPENCHARGEMAP_API_KEY")


def _endpoint() -> str:
    return str(current_app.config.get("OPENCHARGEMAP_ENDPOINT", "https://api.openchargemap.io/v3/poi/"))


def _build_query(latitude: float, longitude: float, radius_km: float, max_results: int) -> str:
    params: dict[str, Any] = {
        "output": "json",
        "latitude": latitude,
        "longitude": longitude,
        "distance": radius_km,
        "distanceunit": "KM",
        "maxresults": max_results,
        "compact": "true",
        "verbose": "false",
    }
    api_key = _api_key()
    if api_key:
        params["key"] = api_key
    return urlencode(params)


def _normalise_station(item: dict[str, Any], *, user_lat: float, user_lon: float) -> dict[str, Any] | None:
    address_info = item.get("AddressInfo") or {}
    latitude = address_info.get("Latitude")
    longitude = address_info.get("Longitude")
    if latitude is None or longitude is None:
        return None

    latitude = float(latitude)
    longitude = float(longitude)
    distance_km = address_info.get("Distance")
    if distance_km is None:
        distance_km = haversine_distance_km(user_lat, user_lon, latitude, longitude)

    operator_info = item.get("OperatorInfo") or {}
    connections = item.get("Connections") or []
    connection_labels: list[str] = []
    for connection in connections:
        connection_type = connection.get("ConnectionType") or {}
        label_parts: list[str] = []
        title = connection_type.get("Title") or connection_type.get("FormalName")
        if title:
            label_parts.append(str(title))
        current_type = connection.get("CurrentType") or {}
        current_type_title = current_type.get("Title")
        if current_type_title:
            label_parts.append(str(current_type_title))
        power_kw = connection.get("PowerKW")
        if power_kw:
            label_parts.append(f"{power_kw} kW")
        if label_parts:
            connection_labels.append(" • ".join(label_parts))

    address_parts = [
        address_info.get("AddressLine1"),
        address_info.get("AddressLine2"),
        address_info.get("Town"),
        address_info.get("StateOrProvince"),
        address_info.get("Postcode"),
        (address_info.get("Country") or {}).get("Title"),
    ]
    formatted_address = ", ".join(str(part) for part in address_parts if part)

    station_name = address_info.get("Title") or item.get("ChargePointName") or "OpenChargeMap Station"
    return {
        "id": f"ocm-{item.get('ID')}",
        "external_id": item.get("ID"),
        "station_name": station_name,
        "location": formatted_address or station_name,
        "address": formatted_address or station_name,
        "operator": operator_info.get("Title") or "OpenChargeMap",
        "charging_type": ", ".join(connection_labels) if connection_labels else "Public EV charging",
        "latitude": latitude,
        "longitude": longitude,
        "distance_km": round(float(distance_km), 2),
        "source": "public",
        "bookable": False,
        "available_slots": None,
        "total_slots": None,
        "status": (item.get("StatusType") or {}).get("Title"),
    }


def _cached_payload(latitude: float, longitude: float, radius_km: float, max_results: int) -> list[dict[str, Any]] | None:
    entry = _CACHE.get(_cache_key(latitude, longitude, radius_km, max_results))
    if not entry:
        return None

    age_seconds = (datetime.now(timezone.utc) - entry.created_at).total_seconds()
    if age_seconds > _cache_ttl_seconds():
        _CACHE.pop(_cache_key(latitude, longitude, radius_km, max_results), None)
        return None
    return entry.payload


def _store_cache(latitude: float, longitude: float, radius_km: float, max_results: int, payload: list[dict[str, Any]]) -> None:
    _CACHE[_cache_key(latitude, longitude, radius_km, max_results)] = _CacheEntry(
        created_at=datetime.now(timezone.utc),
        payload=payload,
    )


def fetch_nearby_public_stations(*, latitude: float, longitude: float, radius_km: float) -> tuple[list[dict[str, Any]], str | None]:
    if not current_app.config.get("OPENCHARGEMAP_ENABLED", True):
        return [], None

    max_results = _max_results()
    cached_payload = _cached_payload(latitude, longitude, radius_km, max_results)
    if cached_payload is not None:
        return cached_payload, None

    url = f"{_endpoint()}?{_build_query(latitude, longitude, radius_km, max_results)}"
    request = Request(
        url,
        headers={
            "Accept": "application/json",
            "User-Agent": "ev-charging-slot-booking/1.0",
        },
        method="GET",
    )

    try:
        with urlopen(request, timeout=_timeout_seconds()) as response:
            raw_body = response.read().decode("utf-8")
        payload = json.loads(raw_body)
    except (HTTPError, URLError, TimeoutError, ValueError, json.JSONDecodeError, OSError):
        return [], "Public station discovery is temporarily unavailable."

    if not isinstance(payload, list):
        return [], "Public station discovery is temporarily unavailable."

    stations: list[dict[str, Any]] = []
    for item in payload:
        if not isinstance(item, dict):
            continue
        station = _normalise_station(item, user_lat=latitude, user_lon=longitude)
        if station is not None:
            stations.append(station)

    stations.sort(key=lambda station: station.get("distance_km") or 0)
    _store_cache(latitude, longitude, radius_km, max_results, stations)
    return stations, None
