"""
The composite stress index.

One number, 0 (healthy) to 100 (severe), that the map colours, the forecaster
predicts and the brief explains. Everything downstream depends on this being
stable, so it is defined here once and nowhere else.

Design notes for the write-up — judges ask about this:
  - Sub-scores are piecewise-linear against published thresholds, not z-scores.
    A z-score is relative to your own dataset, so it silently changes meaning
    when you add a city. Absolute thresholds do not.
  - DO is weighted heaviest because it is the variable that actually kills fish.
  - Biology (BMWP) is folded in when recent observations exist, and the weights
    renormalise when it is missing. No imputation, no silent zero.

Thresholds: dissolved oxygen from the EU Freshwater Fish Directive (78/659/EEC)
and standard salmonid/cyprinid guidance; BMWP/ASPT bands from the UK
Biological Monitoring Working Party scheme.
"""
from __future__ import annotations

import numpy as np

# variable -> weight when everything is present
WEIGHTS = {
    "do_mgl": 0.38,
    "turbidity_ntu": 0.18,
    "temp_c": 0.14,
    "nitrate_mgl": 0.12,
    "bmwp_aspt": 0.18,
}

BANDS = [(25.0, "good"), (50.0, "fair"), (75.0, "poor"), (float("inf"), "severe")]


def _piecewise(x: float, points: list[tuple[float, float]]) -> float:
    """Interpolate a stress sub-score from (value, stress) breakpoints."""
    xs = [p[0] for p in points]
    ys = [p[1] for p in points]
    return float(np.interp(x, xs, ys))


def score_do(mgl: float) -> float:
    # 9+ mg/L is healthy; below 4 is acutely lethal to most fish.
    return _piecewise(mgl, [(2.0, 100), (4.0, 85), (6.0, 55), (8.0, 20), (10.0, 0), (14.0, 0)])


def score_turbidity(ntu: float) -> float:
    return _piecewise(ntu, [(0.0, 0), (10.0, 12), (25.0, 38), (50.0, 62), (100.0, 85), (250.0, 100)])


def score_temp(c: float) -> float:
    # Both tails matter, but heat is the one that drives blooms and DO loss.
    return _piecewise(c, [(0.0, 30), (6.0, 5), (14.0, 0), (20.0, 22), (25.0, 58), (30.0, 88), (35.0, 100)])


def score_nitrate(mgl: float) -> float:
    return _piecewise(mgl, [(0.0, 0), (1.0, 10), (3.0, 35), (6.0, 62), (11.3, 88), (20.0, 100)])


def score_aspt(aspt: float) -> float:
    """ASPT = BMWP / number of scoring taxa. Above ~6 is clean water."""
    return _piecewise(aspt, [(2.0, 100), (3.5, 78), (4.5, 55), (5.5, 30), (6.5, 8), (8.0, 0)])


SCORERS = {
    "do_mgl": score_do,
    "turbidity_ntu": score_turbidity,
    "temp_c": score_temp,
    "nitrate_mgl": score_nitrate,
    "bmwp_aspt": score_aspt,
}


def band_for(value: float) -> str:
    for cutoff, name in BANDS:
        if value < cutoff:
            return name
    return "severe"


def composite(values: dict[str, float]) -> dict:
    """
    values: any subset of WEIGHTS keys, already averaged over the window.
    Returns {'value', 'band', 'components', 'n_inputs', 'missing'}.
    """
    components: dict[str, float] = {}
    total_w = 0.0
    acc = 0.0
    for key, weight in WEIGHTS.items():
        raw = values.get(key)
        if raw is None or (isinstance(raw, float) and np.isnan(raw)):
            continue
        sub = SCORERS[key](float(raw))
        components[key] = round(sub, 1)
        acc += weight * sub
        total_w += weight

    if total_w == 0:
        return {"value": None, "band": "unknown", "components": {}, "n_inputs": 0,
                "missing": list(WEIGHTS)}

    value = acc / total_w                      # renormalise over what we have
    return {
        "value": round(float(value), 1),
        "band": band_for(value),
        "components": components,
        "n_inputs": len(components),
        "missing": [k for k in WEIGHTS if k not in components],
    }


def series_from_measurements(
    hourly: dict[str, np.ndarray], aspt: float | None = None, window: int = 24
) -> np.ndarray:
    """
    Rolling daily stress index over an hourly frame — this is the training
    target for the forecaster. `hourly` maps variable -> array, equal length.
    """
    n = len(next(iter(hourly.values())))
    out = np.full(n, np.nan)
    keys = [k for k in ("do_mgl", "turbidity_ntu", "temp_c", "nitrate_mgl") if k in hourly]
    for i in range(n):
        lo = max(0, i - window + 1)
        vals = {k: float(np.mean(hourly[k][lo : i + 1])) for k in keys}
        if aspt is not None:
            vals["bmwp_aspt"] = aspt
        out[i] = composite(vals)["value"]
    return out


# ── BMWP from identified taxa ──────────────────────────────────────
# Family -> BMWP score. Abbreviated table; extend from the full BMWP list
# once the classifier's label set is final.
BMWP_FAMILY = {
    "Siphlonuridae": 10, "Heptageniidae": 10, "Leptophlebiidae": 10,
    "Ephemerellidae": 10, "Potamanthidae": 10, "Ephemeridae": 10,
    "Taeniopterygidae": 10, "Leuctridae": 10, "Capniidae": 10,
    "Perlodidae": 10, "Perlidae": 10, "Chloroperlidae": 10,
    "Aphelocheiridae": 10, "Phryganeidae": 10, "Molannidae": 10,
    "Beraeidae": 10, "Odontoceridae": 10, "Leptoceridae": 10,
    "Goeridae": 10, "Lepidostomatidae": 10, "Brachycentridae": 10,
    "Sericostomatidae": 10,
    "Astacidae": 8, "Lestidae": 8, "Agriidae": 8, "Gomphidae": 8,
    "Cordulegasteridae": 8, "Aeshnidae": 8, "Corduliidae": 8, "Libellulidae": 8,
    "Psychomyiidae": 8, "Philopotamidae": 8,
    "Caenidae": 7, "Nemouridae": 7, "Rhyacophilidae": 7, "Polycentropodidae": 7,
    "Limnephilidae": 7,
    "Neritidae": 6, "Viviparidae": 6, "Ancylidae": 6, "Hydroptilidae": 6,
    "Unionidae": 6, "Corophiidae": 6, "Gammaridae": 6, "Platycnemididae": 6,
    "Coenagriidae": 6,
    "Mesovelidae": 5, "Hydrometridae": 5, "Gerridae": 5, "Nepidae": 5,
    "Naucoridae": 5, "Notonectidae": 5, "Pleidae": 5, "Corixidae": 5,
    "Haliplidae": 5, "Hygrobiidae": 5, "Dytiscidae": 5, "Gyrinidae": 5,
    "Hydrophilidae": 5, "Clambidae": 5, "Helodidae": 5, "Dryopidae": 5,
    "Elminthidae": 5, "Chrysomelidae": 5, "Curculionidae": 5,
    "Hydropsychidae": 5, "Tipulidae": 5, "Simuliidae": 5,
    "Planariidae": 5, "Dendrocoelidae": 5,
    "Baetidae": 4, "Sialidae": 4, "Piscicolidae": 4,
    "Valvatidae": 3, "Hydrobiidae": 3, "Lymnaeidae": 3, "Physidae": 3,
    "Planorbidae": 3, "Sphaeriidae": 3, "Glossiphoniidae": 3, "Hirudidae": 3,
    "Erpobdellidae": 3, "Asellidae": 3,
    "Chironomidae": 2,
    "Oligochaeta": 1,
}


def bmwp_from_taxa(families: list[str]) -> dict:
    """BMWP total, number of scoring taxa, and ASPT from a family list."""
    scored = [BMWP_FAMILY[f] for f in set(families) if f in BMWP_FAMILY]
    if not scored:
        return {"bmwp": 0, "n_taxa": 0, "aspt": None, "unscored": sorted(set(families))}
    total = sum(scored)
    return {
        "bmwp": total,
        "n_taxa": len(scored),
        "aspt": round(total / len(scored), 2),
        "unscored": sorted(f for f in set(families) if f not in BMWP_FAMILY),
    }
