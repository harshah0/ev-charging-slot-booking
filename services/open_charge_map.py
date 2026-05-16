from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
import json
import os
import time
from typing import Any
from urllib.parse import urlencode
from urllib.request import Request, urlopen
from urllib.error import URLError, HTTPError

from flask import current_app

from utils.geospatial import haversine_distance_km


# Optional Redis support: used when OPENCHARGEMAP_REDIS_URL is configured.
try:
    import redis as _redis  # type: ignore
    _HAS_REDIS = True
except Exception:
    _HAS_REDIS = False


_REDIS_CLIENT: "_redis.Redis" | None = None
_REDIS_PREFIX = "ocm:"


@dataclass(slots=True)
class _CacheEntry:
    created_at: datetime
    payload: list[dict[str, Any]]


_CACHE: dict[str, _CacheEntry] = {}
_RATE_LIMITED_UNTIL: datetime | None = None
_LAST_UPSTREAM_ERROR: str | None = None
_LAST_SUCCESS_AT: datetime | None = None
_METRICS = {
    "requests_total": 0,
    "api_calls_total": 0,
    "cache_hits": 0,
    "stale_cache_hits": 0,
    "rate_limited_short_circuit": 0,
    "upstream_errors": 0,
}


def _cache_key(latitude: float, longitude: float, radius_km: float, max_results: int) -> str:
    return f"{latitude:.3f}:{longitude:.3f}:{radius_km:.1f}:{max_results}"


def _cache_ttl_seconds() -> int:
    return int(current_app.config.get("OPENCHARGEMAP_CACHE_TTL_SECONDS", 300))


def _max_results() -> int:
    return int(current_app.config.get("OPENCHARGEMAP_MAX_RESULTS", 25))


def _timeout_seconds() -> int:
    return int(current_app.config.get("OPENCHARGEMAP_TIMEOUT_SECONDS", 6))


def _retry_attempts() -> int:
    return int(current_app.config.get("OPENCHARGEMAP_RETRY_ATTEMPTS", 2))


def _retry_backoff_seconds() -> float:
    return float(current_app.config.get("OPENCHARGEMAP_RETRY_BACKOFF_SECONDS", 0.35))


def _rate_limit_cooldown_seconds() -> int:
    return int(current_app.config.get("OPENCHARGEMAP_RATE_LIMIT_COOLDOWN_SECONDS", 60))


def _cache_max_entries() -> int:
    return int(current_app.config.get("OPENCHARGEMAP_CACHE_MAX_ENTRIES", 500))


def _api_key() -> str | None:
    api_key = current_app.config.get("OPENCHARGEMAP_API_KEY")
    if api_key:
        return str(api_key)
    return os.getenv("OPENCHARGEMAP_API_KEY")


def _endpoint() -> str:
    return str(current_app.config.get("OPENCHARGEMAP_ENDPOINT", "https://api.openchargemap.io/v3/poi/"))


def _redis_url() -> str | None:
    return current_app.config.get("OPENCHARGEMAP_REDIS_URL")


def _redis_prefix() -> str:
    return str(current_app.config.get("OPENCHARGEMAP_REDIS_PREFIX", _REDIS_PREFIX))


def _use_redis() -> bool:
    return _HAS_REDIS and bool(_redis_url())


def _redis_client() -> "_redis.Redis" | None:
    global _REDIS_CLIENT
    if not _use_redis():
        return None
    if _REDIS_CLIENT is not None:
        return _REDIS_CLIENT
    url = _redis_url()
    try:
        _REDIS_CLIENT = _redis.from_url(url, decode_responses=True)
        return _REDIS_CLIENT
    except Exception:
        return None


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
    # Prefer Redis-backed cache when configured; fall back to in-process cache.
    if _use_redis():
        client = _redis_client()
        if client:
            key = _redis_prefix() + _cache_key(latitude, longitude, radius_km, max_results)
            try:
                raw = client.get(key)
                if raw:
                    return json.loads(raw)
            except Exception:
                # Redis hiccup; continue to in-process cache
                pass

    entry = _CACHE.get(_cache_key(latitude, longitude, radius_km, max_results))
    if not entry:
        return None

    age_seconds = (datetime.now(timezone.utc) - entry.created_at).total_seconds()
    if age_seconds > _cache_ttl_seconds():
        _CACHE.pop(_cache_key(latitude, longitude, radius_km, max_results), None)
        return None
    return entry.payload


def _stale_cached_payload(latitude: float, longitude: float, radius_km: float, max_results: int) -> list[dict[str, Any]] | None:
    # Prefer an in-memory stale copy if available. Redis keys expire and won't
    # provide a stale fallback once TTL elapses, so we keep using the in-process
    # `_CACHE` for stale fallback to avoid returning nothing when upstream fails.
    entry = _CACHE.get(_cache_key(latitude, longitude, radius_km, max_results))
    if not entry:
        return None
    return entry.payload


def _mark_upstream_error(message: str) -> None:
    global _LAST_UPSTREAM_ERROR
    _LAST_UPSTREAM_ERROR = message
    _METRICS["upstream_errors"] += 1


def _mark_upstream_success() -> None:
    global _LAST_SUCCESS_AT, _LAST_UPSTREAM_ERROR
    _LAST_SUCCESS_AT = datetime.now(timezone.utc)
    _LAST_UPSTREAM_ERROR = None


def get_open_charge_map_diagnostics() -> dict[str, Any]:
    requests_total = max(0, int(_METRICS.get("requests_total", 0)))
    cache_hits = max(0, int(_METRICS.get("cache_hits", 0)))
    stale_cache_hits = max(0, int(_METRICS.get("stale_cache_hits", 0)))
    hit_ratio = round(((cache_hits + stale_cache_hits) / requests_total) * 100, 2) if requests_total else 0.0

    cooldown_remaining_seconds = 0
    if _RATE_LIMITED_UNTIL is not None:
        cooldown_remaining_seconds = max(
            0,
            int((_RATE_LIMITED_UNTIL - datetime.now(timezone.utc)).total_seconds()),
        )
    using_redis = _use_redis()
    redis_cache_entries = None
    if using_redis:
        client = _redis_client()
        if client:
            try:
                redis_cache_entries = int(client.zcard(_redis_prefix() + "keys"))
            except Exception:
                redis_cache_entries = None

    return {
        "enabled": bool(current_app.config.get("OPENCHARGEMAP_ENABLED", True)),
        "cache_entries": len(_CACHE) if not using_redis else (redis_cache_entries if redis_cache_entries is not None else len(_CACHE)),
        "cache_max_entries": _cache_max_entries(),
        "cache_ttl_seconds": _cache_ttl_seconds(),
        "using_redis": using_redis,
        "requests_total": requests_total,
        "api_calls_total": int(_METRICS.get("api_calls_total", 0)),
        "cache_hits": cache_hits,
        "stale_cache_hits": stale_cache_hits,
        "upstream_errors": int(_METRICS.get("upstream_errors", 0)),
        "hit_ratio": hit_ratio,
        "is_rate_limited": _is_rate_limited_now(),
        "cooldown_remaining_seconds": cooldown_remaining_seconds,
        "last_upstream_error": _LAST_UPSTREAM_ERROR,
        "last_success_at": _LAST_SUCCESS_AT.isoformat() if _LAST_SUCCESS_AT else None,
    }


def _prune_cache_if_needed() -> None:
    # When running without Redis, prune the in-process cache as before.
    if not _use_redis():
        max_entries = _cache_max_entries()
        overflow = len(_CACHE) - max_entries
        if overflow <= 0:
            return

        for key, _ in sorted(_CACHE.items(), key=lambda item: item[1].created_at)[:overflow]:
            _CACHE.pop(key, None)
        return

    # With Redis enabled, maintain a small ZSET of keys to allow trimming
    # to `_cache_max_entries()` without needing to load keys in-process.
    client = _redis_client()
    if not client:
        return
    zkey = _redis_prefix() + "keys"
    try:
        max_entries = _cache_max_entries()
        current_size = client.zcard(zkey)
        if current_size <= max_entries:
            return
        # remove oldest entries
        client.zremrangebyrank(zkey, 0, current_size - max_entries - 1)
    except Exception:
        pass


def _store_cache(latitude: float, longitude: float, radius_km: float, max_results: int, payload: list[dict[str, Any]]) -> None:
    key = _cache_key(latitude, longitude, radius_km, max_results)
    _CACHE[key] = _CacheEntry(
        created_at=datetime.now(timezone.utc),
        payload=payload,
    )
    if _use_redis():
        client = _redis_client()
        if client:
            rkey = _redis_prefix() + key
            zkey = _redis_prefix() + "keys"
            try:
                client.set(rkey, json.dumps(payload), ex=_cache_ttl_seconds())
                # score by created timestamp for eviction ordering
                client.zadd(zkey, {rkey: time.time()})
                # prune zset if needed
                _prune_cache_if_needed()
            except Exception:
                pass
    else:
        _prune_cache_if_needed()


def _should_retry_http_error(error: HTTPError) -> bool:
    return error.code in {408, 425, 429, 500, 502, 503, 504}


def _activate_rate_limit_cooldown() -> None:
    global _RATE_LIMITED_UNTIL
    until = datetime.now(timezone.utc) + timedelta(seconds=_rate_limit_cooldown_seconds())
    _RATE_LIMITED_UNTIL = until
    # Persist rate-limit state to Redis so all instances short-circuit.
    if _use_redis():
        client = _redis_client()
        if client:
            try:
                key = _redis_prefix() + "rate_limited_until"
                client.set(key, until.isoformat(), ex=_rate_limit_cooldown_seconds())
            except Exception:
                pass


def _is_rate_limited_now() -> bool:
    # First check Redis-shared cooldown when available.
    if _use_redis():
        client = _redis_client()
        if client:
            try:
                key = _redis_prefix() + "rate_limited_until"
                val = client.get(key)
                if val:
                    try:
                        until = datetime.fromisoformat(val)
                        return datetime.now(timezone.utc) < until
                    except Exception:
                        pass
            except Exception:
                pass
    return _RATE_LIMITED_UNTIL is not None and datetime.now(timezone.utc) < _RATE_LIMITED_UNTIL


def fetch_nearby_public_stations(*, latitude: float, longitude: float, radius_km: float) -> tuple[list[dict[str, Any]], str | None]:
    _METRICS["requests_total"] += 1

    if not current_app.config.get("OPENCHARGEMAP_ENABLED", True):
        return [], None

    max_results = _max_results()

    if _is_rate_limited_now():
        _METRICS["rate_limited_short_circuit"] += 1
        stale = _stale_cached_payload(latitude, longitude, radius_km, max_results)
        if stale is not None:
            _METRICS["stale_cache_hits"] += 1
            return stale, "Public station API is rate limited. Showing recently cached public stations."
        return [], "Public station API is rate limited. Please try again shortly."

    cached_payload = _cached_payload(latitude, longitude, radius_km, max_results)
    if cached_payload is not None:
        _METRICS["cache_hits"] += 1
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

    payload: Any = None
    total_attempts = max(1, _retry_attempts() + 1)
    backoff_seconds = max(0.05, _retry_backoff_seconds())

    for attempt in range(total_attempts):
        _METRICS["api_calls_total"] += 1
        try:
            with urlopen(request, timeout=_timeout_seconds()) as response:
                raw_body = response.read().decode("utf-8")
            payload = json.loads(raw_body)
            _mark_upstream_success()
            break
        except HTTPError as error:
            if error.code == 429:
                _activate_rate_limit_cooldown()
            if attempt < total_attempts - 1 and _should_retry_http_error(error):
                time.sleep(backoff_seconds * (attempt + 1))
                continue
            _mark_upstream_error(f"HTTP {error.code}")
            stale = _stale_cached_payload(latitude, longitude, radius_km, max_results)
            if stale is not None:
                _METRICS["stale_cache_hits"] += 1
                return stale, "Public station API is unavailable right now. Showing cached public stations."
            return [], "Public station discovery is temporarily unavailable."
        except (URLError, TimeoutError, ValueError, json.JSONDecodeError, OSError):
            if attempt < total_attempts - 1:
                time.sleep(backoff_seconds * (attempt + 1))
                continue
            _mark_upstream_error("Network/parse failure")
            stale = _stale_cached_payload(latitude, longitude, radius_km, max_results)
            if stale is not None:
                _METRICS["stale_cache_hits"] += 1
                return stale, "Public station API is unavailable right now. Showing cached public stations."
            return [], "Public station discovery is temporarily unavailable."

    if not isinstance(payload, list):
        _mark_upstream_error("Invalid response payload")
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
