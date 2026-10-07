"""Live environmental context with explicit provenance and graceful failure.

The weather grid is context for a monitored reach; it is not a water-quality
measurement.  A provider outage returns an honest ``unavailable`` payload
instead of silently substituting synthetic values.
"""
from __future__ import annotations

from copy import deepcopy
from datetime import datetime, timedelta, timezone
from threading import Lock
from typing import Any

import httpx


OPEN_METEO_URL = "https://api.open-meteo.com/v1/forecast"
SUCCESS_TTL = timedelta(minutes=10)
FAILURE_TTL = timedelta(minutes=2)

_cache: dict[str, tuple[datetime, dict[str, Any]]] = {}
_cache_lock = Lock()


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _source() -> dict[str, str]:
    return {
        "name": "Open-Meteo Forecast API",
        "url": "https://open-meteo.com/en/docs",
        "license": "CC BY 4.0",
        "kind": "weather-model-grid",
    }


def _timestamp_with_offset(value: str | None, offset_seconds: int | None) -> str | None:
    if not value:
        return None
    try:
        offset = timezone(timedelta(seconds=int(offset_seconds or 0)))
        return datetime.fromisoformat(value).replace(tzinfo=offset).isoformat()
    except (TypeError, ValueError, OverflowError):
        return value


def _unavailable(segment: Any, message: str) -> dict[str, Any]:
    now = _now().isoformat()
    return {
        "segment_code": segment.code,
        "mode": "unavailable",
        "status": "unavailable",
        "retrieved_at": now,
        "observed_at": None,
        "timezone": None,
        "location": {"lat": segment.lat, "lon": segment.lon},
        "source": _source(),
        "current": [],
        "next_24h": {},
        "limitations": [
            "Live weather context is temporarily unavailable; WatSen has not substituted demo values.",
            "Weather is model-grid context and is not an in-stream water-quality measurement.",
        ],
        "message": message,
    }


def _parse(segment: Any, payload: dict[str, Any]) -> dict[str, Any]:
    current = payload.get("current") or {}
    units = payload.get("current_units") or {}
    hourly = payload.get("hourly") or {}
    times = hourly.get("time") or []
    probabilities = hourly.get("precipitation_probability") or []
    precipitation = hourly.get("precipitation") or []

    observed_at = current.get("time")
    start = next((index for index, value in enumerate(times) if observed_at and value >= observed_at), 0)
    end = min(len(times), start + 24)
    probs = [value for value in probabilities[start:end] if value is not None]
    rain = [value for value in precipitation[start:end] if value is not None]

    fields = (
        ("temperature_2m", "Air temperature"),
        ("precipitation", "Current precipitation"),
        ("wind_speed_10m", "Wind speed"),
    )
    values = [
        {
            "key": key,
            "label": label,
            "value": current[key],
            "unit": units.get(key, ""),
            "observed_at": _timestamp_with_offset(observed_at, payload.get("utc_offset_seconds")),
        }
        for key, label in fields
        if current.get(key) is not None
    ]

    return {
        "segment_code": segment.code,
        "mode": "live",
        "status": "fresh",
        "retrieved_at": _now().isoformat(),
        "observed_at": _timestamp_with_offset(observed_at, payload.get("utc_offset_seconds")),
        "timezone": payload.get("timezone"),
        "location": {
            "lat": payload.get("latitude", segment.lat),
            "lon": payload.get("longitude", segment.lon),
            "grid_elevation_m": payload.get("elevation"),
        },
        "source": _source(),
        "current": values,
        "next_24h": {
            "precipitation_probability_max_pct": max(probs) if probs else None,
            "precipitation_sum_mm": round(sum(rain), 1) if rain else None,
        },
        "limitations": [
            "Weather is model-grid context and is not an in-stream water-quality measurement.",
            "Forecast-grid values may differ from a gauge at the selected reach.",
        ],
        "message": "Live weather context loaded with source, time, unit, and spatial provenance.",
    }


def live_context(segment: Any, *, force: bool = False) -> dict[str, Any]:
    """Return a cached live weather context for one reach.

    Network errors are represented as data so a temporary third-party outage
    cannot take down the catchment dashboard.
    """
    now = _now()
    with _cache_lock:
        cached = _cache.get(segment.code)
        if cached and not force and cached[0] > now:
            result = deepcopy(cached[1])
            result["cache"] = "hit"
            return result

    params = {
        "latitude": segment.lat,
        "longitude": segment.lon,
        "current": "temperature_2m,precipitation,wind_speed_10m",
        "hourly": "precipitation_probability,precipitation",
        "forecast_days": 3,
        "timezone": "auto",
    }
    try:
        with httpx.Client(timeout=6.0, follow_redirects=True) as client:
            response = client.get(OPEN_METEO_URL, params=params)
            response.raise_for_status()
            result = _parse(segment, response.json())
        ttl = SUCCESS_TTL
    except (httpx.HTTPError, ValueError, KeyError, TypeError) as exc:
        result = _unavailable(segment, f"Provider request failed: {type(exc).__name__}")
        ttl = FAILURE_TTL

    result["cache"] = "miss"
    with _cache_lock:
        _cache[segment.code] = (now + ttl, deepcopy(result))
    return result
