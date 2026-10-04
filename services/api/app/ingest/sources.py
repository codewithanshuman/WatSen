"""
External data connectors.  [Person 2]

Every connector obeys three rules, because all three will save you during the
demo:

  1. Cache to disk on success. A cached response is indistinguishable from a
     live one to everything downstream, and it means a rate limit at 2am does
     not take the demo down.
  2. Never raise into the caller. Return an empty result and log. One dead API
     must not stop the other five.
  3. Normalise to the `measurement` schema at the edge. Nothing downstream
     should ever know an API's field names.

Run them:  python -m app.ingest.sources --all
"""
from __future__ import annotations

import hashlib
import json
import logging
import os
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

import httpx

log = logging.getLogger("ingest")
CACHE = Path(os.getenv("INGEST_CACHE", ".cache/ingest"))
CACHE_TTL_S = int(os.getenv("INGEST_CACHE_TTL", 60 * 60 * 6))


def _cache_path(key: str) -> Path:
    return CACHE / f"{hashlib.sha1(key.encode()).hexdigest()}.json"


def cached_get(url: str, params: dict | None = None, headers: dict | None = None,
               ttl: int = CACHE_TTL_S) -> dict | None:
    key = f"{url}?{json.dumps(params or {}, sort_keys=True)}"
    path = _cache_path(key)
    if path.exists() and (time.time() - path.stat().st_mtime) < ttl:
        try:
            return json.loads(path.read_text())
        except json.JSONDecodeError:
            pass
    try:
        r = httpx.get(url, params=params, headers=headers, timeout=25.0)
        r.raise_for_status()
        data = r.json()
        CACHE.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(data))
        return data
    except Exception as exc:
        log.warning("fetch failed %s: %s", url, exc)
        if path.exists():                       # stale beats nothing
            log.warning("serving stale cache for %s", url)
            return json.loads(path.read_text())
        return None


def _m(segment_code, variable, value, unit, observed_at, source, quality=1.0) -> dict:
    return {
        "segment_code": segment_code, "variable": variable, "value": float(value),
        "unit": unit, "observed_at": observed_at, "source": source, "quality": quality,
    }


# ── OpenAQ ─────────────────────────────────────────────────────────
# v3 requires an API key (free). Header: X-API-Key.
# OpenAQ temperature is an atmospheric/environmental station measurement, not
# water temperature. Keep the distinction explicit so it cannot silently feed
# aquatic stress scoring.
OPENAQ_PARAM_MAP = {"pm25": None, "temperature": "air_temp_c", "relativehumidity": None}


def openaq_nearby(segment_code: str, lat: float, lon: float, radius_m: int = 12000,
                  api_key: str | None = None) -> list[dict]:
    key = api_key or os.getenv("OPENAQ_API_KEY")
    if not key:
        log.info("OPENAQ_API_KEY unset; skipping OpenAQ")
        return []
    data = cached_get(
        "https://api.openaq.org/v3/locations",
        params={"coordinates": f"{lat},{lon}", "radius": min(radius_m, 25000), "limit": 20},
        headers={"X-API-Key": key},
    )
    if not data:
        return []
    out = []
    for loc in data.get("results", []):
        for sensor in loc.get("sensors", []):
            pname = (sensor.get("parameter") or {}).get("name")
            mapped = OPENAQ_PARAM_MAP.get(pname)
            if not mapped:
                continue
            latest = cached_get(
                f"https://api.openaq.org/v3/sensors/{sensor['id']}/measurements",
                params={"limit": 168},
                headers={"X-API-Key": key},
            )
            for row in (latest or {}).get("results", []):
                period = (row.get("period") or {}).get("datetimeFrom", {})
                ts = period.get("utc")
                if ts and row.get("value") is not None:
                    out.append(_m(segment_code, mapped, row["value"],
                                  sensor.get("parameter", {}).get("units", ""), ts, "openaq"))
    return out


# ── OpenWeatherMap ─────────────────────────────────────────────────
def openweather(segment_code: str, lat: float, lon: float,
                api_key: str | None = None) -> list[dict]:
    key = api_key or os.getenv("OPENWEATHER_API_KEY")
    if not key:
        log.info("OPENWEATHER_API_KEY unset; skipping OpenWeatherMap")
        return []
    data = cached_get(
        "https://api.openweathermap.org/data/2.5/forecast",
        params={"lat": lat, "lon": lon, "appid": key, "units": "metric"},
        ttl=60 * 60,
    )
    if not data:
        return []
    out = []
    for row in data.get("list", []):
        ts = datetime.fromtimestamp(row["dt"], tz=timezone.utc).isoformat()
        rain = (row.get("rain") or {}).get("3h", 0.0)
        out.append(_m(segment_code, "rain_mm", rain / 3.0, "mm", ts, "openweather"))
        out.append(_m(segment_code, "air_temp_c", row["main"]["temp"], "degC", ts, "openweather"))
    return out


# ── GBIF ───────────────────────────────────────────────────────────
# No key required. Used to sanity-check whether a predicted family has ever
# been recorded near this location — the 'out_of_range' check in anomaly.py.
def gbif_family_nearby(family: str, lat: float, lon: float, radius_km: int = 40) -> dict:
    d = radius_km / 111.0
    data = cached_get(
        "https://api.gbif.org/v1/occurrence/search",
        params={
            "family": family, "hasCoordinate": "true", "limit": 0,
            "decimalLatitude": f"{lat - d},{lat + d}",
            "decimalLongitude": f"{lon - d},{lon + d}",
        },
        ttl=60 * 60 * 24 * 14,
    )
    if data is None:
        return {"family": family, "count": None, "known": None, "source": "unavailable"}
    n = data.get("count", 0)
    return {"family": family, "count": n, "known": n > 0, "source": "gbif"}


def gbif_families_for_area(lat: float, lon: float, radius_km: int = 40,
                           families: list[str] | None = None) -> dict:
    from app.ml.classifier import DEFAULT_CLASSES
    return {f: gbif_family_nearby(f, lat, lon, radius_km)
            for f in (families or DEFAULT_CLASSES)}


# ── Open-Meteo (no key — use this if OpenWeather quota is a problem) ──
def open_meteo_history(segment_code: str, lat: float, lon: float, days: int = 92) -> list[dict]:
    """
    Free, no key, hourly history. This is the fastest route to real training
    data for the forecaster — start here on day 1, add the keyed sources later.
    """
    end = datetime.now(timezone.utc).date()
    start = end - timedelta(days=days)
    data = cached_get(
        "https://archive-api.open-meteo.com/v1/archive",
        params={
            "latitude": lat, "longitude": lon,
            "start_date": str(start), "end_date": str(end),
            "hourly": "temperature_2m,precipitation,soil_temperature_7_to_28cm",
            "timezone": "UTC",
        },
        ttl=60 * 60 * 24,
    )
    if not data or "hourly" not in data:
        return []
    h = data["hourly"]
    out = []
    for i, ts in enumerate(h["time"]):
        iso = f"{ts}:00+00:00" if len(ts) == 16 else ts
        if h["precipitation"][i] is not None:
            out.append(_m(segment_code, "rain_mm", h["precipitation"][i], "mm", iso, "open-meteo"))
        soil = h.get("soil_temperature_7_to_28cm", [None] * len(h["time"]))[i]
        if soil is not None:
            # Shallow soil temperature is a decent proxy for base-flow water
            # temperature. Document this substitution; do not hide it.
            out.append(_m(segment_code, "temp_c", soil, "degC", iso, "open-meteo", quality=0.6))
    return out


# ── OpenStreetMap / Overpass ───────────────────────────────────────
def osm_catchment_context(lat: float, lon: float, radius_m: int = 1000) -> dict:
    """Industrial sites and impervious land use near the reach. No key needed."""
    q = f"""
    [out:json][timeout:25];
    (
      way["landuse"="industrial"](around:{radius_m},{lat},{lon});
      way["landuse"="retail"](around:{radius_m},{lat},{lon});
      way["man_made"="wastewater_plant"](around:{radius_m},{lat},{lon});
      way["landuse"="residential"](around:{radius_m},{lat},{lon});
    );
    out count;
    """
    data = cached_get("https://overpass-api.de/api/interpreter",
                      params={"data": q}, ttl=60 * 60 * 24 * 30)
    if not data:
        return {"industry_within_1km": None, "source": "unavailable"}
    count = 0
    for el in data.get("elements", []):
        if el.get("type") == "count":
            count = int(el.get("tags", {}).get("total", 0))
    return {"industry_within_1km": count, "radius_m": radius_m, "source": "overpass"}


# ── runner ─────────────────────────────────────────────────────────
def ingest_all(segments: list[dict]) -> dict:
    """segments: [{'code','lat','lon'}]. Returns a per-source report."""
    report = {}
    rows: list[dict] = []
    for seg in segments:
        code, lat, lon = seg["code"], seg["lat"], seg["lon"]
        for name, fn in (
            ("open-meteo", lambda: open_meteo_history(code, lat, lon)),
            ("openweather", lambda: openweather(code, lat, lon)),
            ("openaq", lambda: openaq_nearby(code, lat, lon)),
        ):
            got = fn()
            report[f"{code}:{name}"] = len(got)
            rows.extend(got)
    report["_total_rows"] = len(rows)
    return {"report": report, "measurements": rows}


if __name__ == "__main__":
    import argparse

    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s %(message)s")
    ap = argparse.ArgumentParser(description="Pull external data into the measurement schema")
    ap.add_argument("--all", action="store_true")
    ap.add_argument("--out", default="data/ingested.json")
    args = ap.parse_args()

    from app.core.synthetic import SEGMENTS

    segs = [{"code": s.code, "lat": s.lat, "lon": s.lon} for s in SEGMENTS]
    result = ingest_all(segs)
    Path(args.out).parent.mkdir(parents=True, exist_ok=True)
    Path(args.out).write_text(json.dumps(result["measurements"], indent=1))
    print(json.dumps(result["report"], indent=1))
    print(f"wrote {len(result['measurements'])} rows -> {args.out}")
