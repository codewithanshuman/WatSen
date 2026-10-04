"""
Reproducible demo scenarios.

The problem: on a calm week every stream reads 'good' and the forecast is flat.
That is the correct output and a terrible demo. Judges need to see the alert
path fire.

The wrong fix is to quietly bias the generator so everything looks alarming.
The right fix is this: an explicitly labelled perturbation applied to a copy of
the data, with the label surfaced in the API response and in the UI banner.

    GET /v1/segments/IT-BLG-01/forecast?scenario=storm

Every response carries `scenario` so nothing is ever presented as observed data
when it is not. Say this on camera during the demo — showing that you separated
a scenario from a measurement is itself a credibility point.
"""
from __future__ import annotations

import numpy as np

SCENARIOS = {
    "none": "Observed data, unmodified.",
    "storm": "Convective storm: 38 mm over 6 hours, arriving 12 hours ago. "
             "Turbidity and nitrate respond immediately; the oxygen sag follows "
             "on the documented 8-30 hour lag.",
    "heatwave": "Five-day heat event: +6 degC on water temperature, reduced "
                "reaeration. Tests the oxygen-saturation pathway with no rain.",
    "spill": "Point-source organic discharge 18 hours ago: oxygen demand spike "
             "with no rainfall signal. Tests whether the index separates a "
             "pollution event from a weather event.",
}


def apply(frame: dict, scenario: str) -> dict:
    """Return a modified copy. Never mutates the stored frame."""
    if scenario in (None, "", "none"):
        return frame
    if scenario not in SCENARIOS:
        raise ValueError(f"unknown scenario {scenario!r}; one of {sorted(SCENARIOS)}")

    out = {k: (v.copy() if isinstance(v, np.ndarray) else list(v)) for k, v in frame.items()}
    n = len(out["t"])

    if scenario == "storm":
        start = n - 18
        depth = np.array([2.0, 5.5, 9.0, 11.0, 7.0, 3.5])
        out["rain_mm"][start : start + 6] += depth
        # immediate: suspended solids and washed-in nitrate
        for i in range(6, 18):
            decay = np.exp(-(i - 6) / 9.0)
            out["turbidity_ntu"][start + i] += 95.0 * decay
            out["nitrate_mgl"][start + i] += 3.1 * decay
        # lagged: oxygen demand from the organic load
        for i in range(10, 18):
            out["do_mgl"][start + i] -= 1.9 * (1 - np.exp(-(i - 10) / 4.0))

    elif scenario == "heatwave":
        span = min(120, n)
        ramp = np.linspace(0.2, 1.0, span)
        out["temp_c"][-span:] += 6.0 * ramp
        out["do_mgl"][-span:] -= 2.4 * ramp
        out["rain_mm"][-span:] *= 0.05

    elif scenario == "spill":
        start = n - 18
        for i in range(18):
            shape = np.exp(-((i - 4) ** 2) / 26.0)
            out["do_mgl"][start + i] -= 3.4 * shape
            out["nitrate_mgl"][start + i] += 2.2 * shape
            out["turbidity_ntu"][start + i] += 12.0 * shape

    out["do_mgl"] = np.clip(out["do_mgl"], 0.3, None)
    out["turbidity_ntu"] = np.clip(out["turbidity_ntu"], 0.5, None)
    out["nitrate_mgl"] = np.clip(out["nitrate_mgl"], 0.0, None)
    return out


def apply_forecast(points: list, scenario: str) -> list:
    """Apply a labelled future response curve to forecast point objects.

    The history perturbation describes the event already observed. This curve
    represents the scenario's documented lagged pathway (runoff/BOD/oxygen)
    over the following 72 hours so the counterfactual is visible to users.
    """
    if scenario in (None, "", "none"):
        return points
    out = []
    for i, point in enumerate(points):
        hour = i + 1
        if scenario == "storm":
            delta = 45 * np.exp(-((hour - 28) ** 2) / (2 * 15 ** 2))
        elif scenario == "heatwave":
            delta = 30 * (1 - np.exp(-hour / 20))
        elif scenario == "spill":
            delta = 45 * np.exp(-((hour - 13) ** 2) / (2 * 11 ** 2))
        else:
            delta = 0
        clone = type(point)(
            valid_at=point.valid_at,
            value=round(float(np.clip(point.value + delta, 0, 100)), 2),
            lower=round(float(np.clip(point.lower + delta * .8, 0, 100)), 2),
            upper=round(float(np.clip(point.upper + delta * 1.2, 0, 100)), 2),
        )
        clone.lower = min(clone.lower, clone.value)
        clone.upper = max(clone.upper, clone.value)
        out.append(clone)
    return out
