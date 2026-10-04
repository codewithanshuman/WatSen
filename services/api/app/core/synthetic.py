"""
Physically-plausible synthetic stream data.

Two jobs:
  1. Mock mode — the whole platform runs with zero external API keys, so the
     frontend is never blocked and the demo never depends on someone's rate limit.
  2. Pre-training — the forecaster needs thousands of hours of history before the
     sprint. Copernicus/ERA5 backfill replaces this, but this gets the model
     architecture validated on day 2 instead of day 6.

The generator is deterministic given a seed, so every teammate and every CI run
sees the same numbers.

Behaviour encoded (from standard stream ecology, keep these if you swap in real data):
  - diurnal temperature cycle, warmest ~16:00
  - dissolved oxygen is inversely related to temperature (saturation curve)
  - rain arrives as Poisson-spaced storms; turbidity spikes within ~2h
  - DO sags 8-30h AFTER a storm as washed-in organic load is respired
  - nitrate rises with runoff and decays slowly
"""
from __future__ import annotations

import math
import os
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone

import numpy as np

VARIABLES = ["do_mgl", "ph", "turbidity_ntu", "temp_c", "rain_mm", "nitrate_mgl"]

UNITS = {
    "do_mgl": "mg/L",
    "ph": "pH",
    "turbidity_ntu": "NTU",
    "temp_c": "degC",
    "rain_mm": "mm",
    "nitrate_mgl": "mg/L",
}


@dataclass
class SegmentProfile:
    """Per-segment character. Urban segments are flashier and more polluted."""

    code: str
    name: str
    city: str
    country_iso2: str
    lat: float
    lon: float
    urban: float = 0.5          # 0 rural .. 1 heavily urbanised
    base_temp_c: float = 14.0
    shade: float = 0.5          # canopy cover, damps the diurnal swing
    seed: int = 0
    path: list = field(default_factory=list)   # [(lon, lat), ...] LineString


def do_saturation(temp_c: np.ndarray) -> np.ndarray:
    """Benson & Krause approximation of DO saturation in fresh water (mg/L)."""
    t = np.asarray(temp_c, dtype=float)
    tk = t + 273.15
    ln_c = (
        -139.34411
        + 1.575701e5 / tk
        - 6.642308e7 / tk**2
        + 1.243800e10 / tk**3
        - 8.621949e11 / tk**4
    )
    return np.exp(ln_c)


def generate_series(
    profile: SegmentProfile,
    hours: int = 24 * 180,
    end: datetime | None = None,
) -> dict:
    """Return {'t': [datetime], 'do_mgl': np.ndarray, ...} at hourly resolution."""
    rng = np.random.default_rng(profile.seed)
    if end is None:
        raw_end = os.getenv("DEMO_END", "2026-09-30T12:00:00+00:00")
        end = datetime.fromisoformat(raw_end.replace("Z", "+00:00"))
        if end.tzinfo is None:
            end = end.replace(tzinfo=timezone.utc)
        end = end.astimezone(timezone.utc).replace(minute=0, second=0, microsecond=0)
    t0 = end - timedelta(hours=hours - 1)
    t = [t0 + timedelta(hours=i) for i in range(hours)]
    idx = np.arange(hours, dtype=float)

    doy = np.array([x.timetuple().tm_yday for x in t], dtype=float)
    hod = np.array([x.hour for x in t], dtype=float)

    # ── temperature ────────────────────────────────────────────────
    seasonal = 7.5 * np.sin(2 * math.pi * (doy - 110) / 365.0)
    diurnal = (2.6 * (1.0 - 0.6 * profile.shade)) * np.sin(2 * math.pi * (hod - 9) / 24.0)
    urban_heat = 1.8 * profile.urban
    temp = profile.base_temp_c + seasonal + diurnal + urban_heat
    temp += _ar1(rng, hours, sigma=0.35, phi=0.9)

    # ── rainfall: Poisson storms, gamma depths ─────────────────────
    rain = np.zeros(hours)
    # Storm occurrence is climatic, not caused by urbanisation. Urbanisation
    # instead amplifies runoff, turbidity and oxygen-demand responses below.
    storm_rate = 1.0 / 52.0   # storms per hour in the development generator
    n_storms = rng.poisson(storm_rate * hours)
    starts = rng.integers(0, hours, size=max(n_storms, 0))
    for s in starts:
        dur = int(rng.integers(2, 10))
        depth = rng.gamma(2.0, 3.2)
        shape = np.exp(-0.5 * ((np.arange(dur) - dur / 3) / (dur / 3.5)) ** 2)
        shape = shape / shape.sum()
        end_i = min(s + dur, hours)
        rain[s:end_i] += depth * shape[: end_i - s]

    # ── turbidity: fast response to rain + slow settling ───────────
    runoff = _convolve_kernel(rain, _gamma_kernel(peak=2, length=14, shape=1.7))
    base_turb = 3.0 + 9.0 * profile.urban
    turbidity = base_turb + 14.0 * runoff * (0.55 + profile.urban)
    turbidity += np.abs(_ar1(rng, hours, sigma=0.8, phi=0.85))
    turbidity = np.clip(turbidity, 0.6, None)

    # ── dissolved oxygen ───────────────────────────────────────────
    sat = do_saturation(temp)
    # lagged BOD pulse: organic load respired 8-30h after the storm
    bod = _convolve_kernel(rain, _gamma_kernel(peak=18, length=54, shape=2.6))
    deficit = 0.9 * profile.urban + 2.9 * bod * (0.5 + profile.urban)
    photosynthesis = 0.55 * np.clip(np.sin(2 * math.pi * (hod - 8) / 24.0), 0, None)
    do = sat - deficit + photosynthesis + _ar1(rng, hours, sigma=0.18, phi=0.88)
    do = np.clip(do, 0.4, None)

    # ── nitrate and pH ─────────────────────────────────────────────
    nitrate = 0.4 + 2.4 * profile.urban * _convolve_kernel(
        rain, _gamma_kernel(peak=10, length=90, shape=2.0)
    )
    nitrate += 0.12 * np.abs(_ar1(rng, hours, sigma=0.5, phi=0.95))
    ph = 7.8 - 0.35 * profile.urban - 0.06 * bod * 4 + _ar1(rng, hours, sigma=0.05, phi=0.9)
    ph = np.clip(ph, 5.8, 9.2)

    return {
        "t": t,
        "do_mgl": do,
        "ph": ph,
        "turbidity_ntu": turbidity,
        "temp_c": temp,
        "rain_mm": rain,
        "nitrate_mgl": nitrate,
    }


# ── helpers ────────────────────────────────────────────────────────

def _ar1(rng: np.random.Generator, n: int, sigma: float, phi: float) -> np.ndarray:
    """Autocorrelated noise — white noise looks obviously fake on a chart."""
    out = np.zeros(n)
    eps = rng.normal(0.0, sigma, n)
    for i in range(1, n):
        out[i] = phi * out[i - 1] + eps[i]
    return out


def _gamma_kernel(peak: int, length: int, shape: float) -> np.ndarray:
    """Unit-sum impulse response peaking `peak` hours after the input."""
    x = np.arange(1, length + 1, dtype=float)
    scale = max(peak, 1) / shape
    k = (x ** (shape - 1)) * np.exp(-x / scale)
    return k / k.sum()


def _convolve_kernel(signal: np.ndarray, kernel: np.ndarray) -> np.ndarray:
    return np.convolve(signal, kernel, mode="full")[: len(signal)]


# ── the demo catchment ─────────────────────────────────────────────
# Real coordinates on real urban streams in OneAquaHealth pilot cities.
# Swap `path` for geometry pulled from OSM when the ingest job is wired up.

SEGMENTS: list[SegmentProfile] = [
    SegmentProfile(
        code="PT-CBR-01", name="Ribeira de Coselhas", city="Coimbra", country_iso2="PT",
        lat=40.2320, lon=-8.4180, urban=0.78, base_temp_c=15.2, shade=0.35, seed=11,
        path=[(-8.4232, 40.2288), (-8.4196, 40.2311), (-8.4151, 40.2337), (-8.4108, 40.2352)],
    ),
    SegmentProfile(
        code="PT-CBR-02", name="Rio Mondego — margem norte", city="Coimbra", country_iso2="PT",
        lat=40.2075, lon=-8.4290, urban=0.55, base_temp_c=15.6, shade=0.25, seed=12,
        path=[(-8.4405, 40.2052), (-8.4321, 40.2068), (-8.4238, 40.2081), (-8.4154, 40.2090)],
    ),
    SegmentProfile(
        code="IT-BLG-01", name="Torrente Ravone", city="Bologna", country_iso2="IT",
        lat=44.4870, lon=11.3210, urban=0.86, base_temp_c=15.9, shade=0.20, seed=13,
        path=[(11.3138, 44.4842), (11.3181, 44.4861), (11.3229, 44.4879), (11.3277, 44.4894)],
    ),
    SegmentProfile(
        code="RO-BUC-01", name="Râul Colentina", city="Bucharest", country_iso2="RO",
        lat=44.4790, lon=26.0850, urban=0.72, base_temp_c=13.8, shade=0.40, seed=14,
        path=[(26.0762, 44.4771), (26.0818, 44.4784), (26.0879, 44.4796), (26.0941, 44.4805)],
    ),
    SegmentProfile(
        code="ES-VLC-01", name="Barranc del Carraixet", city="Valencia", country_iso2="ES",
        lat=39.5340, lon=-0.3610, urban=0.64, base_temp_c=17.1, shade=0.18, seed=15,
        path=[(-0.3702, 39.5318), (-0.3651, 39.5330), (-0.3598, 39.5344), (-0.3541, 39.5356)],
    ),
    SegmentProfile(
        code="NL-UTR-01", name="Kromme Rijn", city="Utrecht", country_iso2="NL",
        lat=52.0790, lon=5.1420, urban=0.41, base_temp_c=12.4, shade=0.62, seed=16,
        path=[(5.1338, 52.0771), (5.1389, 52.0782), (5.1443, 52.0793), (5.1498, 52.0801)],
    ),
]

BY_CODE = {s.code: s for s in SEGMENTS}
