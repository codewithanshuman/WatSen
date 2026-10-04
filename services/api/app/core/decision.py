"""Decision-support views built from the same evidence used by the dashboard.

These functions are intentionally deterministic.  They explain model output and
run labelled counterfactual simulations; they do not pretend to be causal proof
or regulatory advice.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from statistics import mean


INTERVENTIONS = {
    "aeration": {
        "name": "Temporary aeration",
        "description": "Simulates temporary oxygen support during the forecast event.",
        "disruption": 2,
        "stress_reduction": 0.18,
        "do_gain": 2.0,
    },
    "retention": {
        "name": "Stormwater retention",
        "description": "Simulates reduced runoff, suspended solids and nutrient loading.",
        "disruption": 3,
        "stress_reduction": 0.22,
        "do_gain": 0.8,
    },
    "retention_aeration": {
        "name": "Retention + temporary aeration",
        "description": "Combines runoff control with short-term oxygen support.",
        "disruption": 4,
        "stress_reduction": 0.36,
        "do_gain": 2.4,
    },
    "runoff_diversion": {
        "name": "Runoff diversion",
        "description": "Simulates diverting the first flush away from the monitored reach.",
        "disruption": 4,
        "stress_reduction": 0.28,
        "do_gain": 1.0,
    },
    "discharge_restriction": {
        "name": "Temporary discharge restriction",
        "description": "Simulates limiting organic and nutrient loading during the risk window.",
        "disruption": 5,
        "stress_reduction": 0.30,
        "do_gain": 1.5,
    },
    "citizen_sampling": {
        "name": "Citizen sampling surge",
        "description": "Improves evidence coverage; it does not directly change stream conditions.",
        "disruption": 1,
        "stress_reduction": 0.0,
        "do_gain": 0.0,
    },
}


def _avg(values: list[float]) -> float:
    return float(mean(values)) if values else 0.0


def failure_chain(summary: dict, history: dict, forecast: dict) -> dict:
    rain24 = sum(history["rain_mm"][-24:])
    rain_prev = sum(history["rain_mm"][-48:-24])
    turb_now = _avg(history["turbidity_ntu"][-12:])
    turb_prev = max(_avg(history["turbidity_ntu"][-36:-12]), 0.1)
    nitrate_now = _avg(history["nitrate_mgl"][-12:])
    nitrate_prev = max(_avg(history["nitrate_mgl"][-36:-12]), 0.1)
    do_now = _avg(history["do_mgl"][-12:])
    do_prev = _avg(history["do_mgl"][-36:-12])
    peak = max(forecast["points"], key=lambda p: p["value"])
    threshold = next((p for p in forecast["points"] if p["value"] >= 50), peak)
    issued = datetime.fromisoformat(forecast["issued_at"])
    onset_h = max(1, round((datetime.fromisoformat(threshold["valid_at"]) - issued).total_seconds() / 3600))

    runoff_pct = min(250, round(max(0.0, (rain24 - rain_prev) / max(rain_prev, 1.0) * 100)))
    turb_pct = round((turb_now - turb_prev) / turb_prev * 100)
    nitrate_pct = round((nitrate_now - nitrate_prev) / nitrate_prev * 100)
    do_delta = round(do_now - do_prev, 2)
    width = peak["upper"] - peak["lower"]
    confidence = round(max(35, min(94, 92 - width * 2.1)))

    if rain24 > 8 or turb_pct > 25:
        driver = "Runoff-driven oxygen depletion"
    elif do_delta < -0.7:
        driver = "Dissolved-oxygen decline"
    elif nitrate_pct > 25:
        driver = "Nutrient loading"
    else:
        driver = "Combined urban stream pressure"

    nodes = [
        _node("rain", "Heavy rainfall" if rain24 > 8 else "Rainfall signal", "observed", f"{rain24:.1f} mm / 24 h", 0.96, "MEAS-RAIN"),
        _node("runoff", f"Runoff response +{runoff_pct}%" if runoff_pct else "Urban runoff pressure", "inferred", "Derived from rainfall and urbanisation", 0.78, "INFER-RUNOFF"),
        _node("turbidity", f"Turbidity {'+' if turb_pct >= 0 else ''}{turb_pct}%", "observed", f"{turb_now:.1f} NTU", 0.93, "MEAS-TURB"),
        _node("nutrient", f"Nutrient pulse {'+' if nitrate_pct >= 0 else ''}{nitrate_pct}%", "observed", f"{nitrate_now:.2f} mg/L nitrate", 0.89, "MEAS-NITRATE"),
        _node("oxygen", f"Dissolved oxygen {do_delta:+.2f} mg/L", "observed", f"Current mean {do_now:.2f} mg/L", 0.94, "MEAS-DO"),
        _node("biology", "Sensitive taxa pressure", "inferred", f"ASPT {summary.get('aspt') or 'unavailable'}", 0.74, "BIO-ASPT"),
        _node("stress", f"Peak stress {peak['value']:.0f}", "forecast", f"Likely range {peak['lower']:.0f}–{peak['upper']:.0f}", confidence / 100, "FCST-PEAK"),
    ]
    return {
        "segment_code": summary["code"],
        "scenario": summary.get("scenario", "none"),
        "label": "Decision-support inference — not causal proof",
        "primary_driver": driver,
        "estimated_onset_h": onset_h,
        "onset_window_h": [max(1, onset_h - 4), min(72, onset_h + 4)],
        "confidence": confidence,
        "nodes": nodes,
        "edges": [[nodes[i]["id"], nodes[i + 1]["id"]] for i in range(len(nodes) - 1)],
    }


def _node(node_id: str, label: str, kind: str, evidence: str, confidence: float, source: str) -> dict:
    return {"id": node_id, "label": label, "kind": kind, "evidence": evidence,
            "confidence": round(confidence, 2), "source": source}


def intervention_search(summary: dict, history: dict, forecast: dict) -> dict:
    base_points = forecast["points"]
    base_min_do = min(history["do_mgl"][-24:])
    baseline = _metrics(base_points, base_min_do)
    results = []
    for key, spec in INTERVENTIONS.items():
        transformed = []
        for i, p in enumerate(base_points):
            ramp = min(1.0, (i + 1) / 12)
            reduction = spec["stress_reduction"] * ramp
            transformed.append({**p, "value": round(max(0, p["value"] * (1 - reduction)), 2)})
        metrics = _metrics(transformed, base_min_do + spec["do_gain"])
        avoided = baseline["critical_stress_hours"] - metrics["critical_stress_hours"]
        improvement = round(100 * (baseline["peak_stress"] - metrics["peak_stress"]) / max(baseline["peak_stress"], 1))
        results.append({
            "key": key, **spec, **metrics,
            "critical_failures_avoided": avoided,
            "ecological_improvement_pct": improvement,
            "confidence": "medium-high" if key in {"aeration", "retention"} else "medium",
            "points": transformed,
        })
    beneficial = [r for r in results if r["ecological_improvement_pct"] > 0]
    recommended = min(
        beneficial or results,
        key=lambda r: (r["critical_stress_hours"], r["elevated_stress_hours"],
                       r["disruption"], r["peak_stress"]),
    )
    return {
        "segment_code": summary["code"],
        "scenario": summary.get("scenario", "none"),
        "label": "Simulation recommendation — not authoritative environmental advice",
        "baseline": baseline,
        "interventions": results,
        "recommended": recommended["key"],
    }


def _metrics(points: list[dict], min_do: float) -> dict:
    values = [p["value"] for p in points]
    critical = sum(v >= 75 for v in values)
    poor = sum(v >= 50 for v in values)
    last_bad = max((i for i, v in enumerate(values) if v >= 50), default=-1)
    return {
        "critical_stress_hours": critical,
        "elevated_stress_hours": poor,
        "minimum_do_mgl": round(max(0, min_do), 2),
        "peak_stress": round(max(values), 1),
        "recovery_time_h": last_bad + 1 if last_bad >= 0 else 0,
    }


def data_sufficiency(summary: dict, history: dict, forecast: dict, observations: list[dict]) -> dict:
    widths = [p["upper"] - p["lower"] for p in forecast["points"]]
    accepted = [o for o in observations if o.get("state") in {"auto_accepted", "expert_confirmed"}]
    score = 88 - _avg(widths) * 1.8 - max(0, 5 - len(accepted)) * 4
    score = round(max(25, min(95, score)))
    latest = {k: history[k][-1] for k in ("do_mgl", "nitrate_mgl", "turbidity_ntu")}
    needs = [
        {"rank": 1, "measurement": "Dissolved oxygen", "impact": "high", "reason": "Most influential short-term mortality and stress signal."},
        {"rank": 2, "measurement": "Macroinvertebrate sample", "impact": "medium", "reason": f"{len(accepted)} accepted biological observations are available."},
        {"rank": 3, "measurement": "Nitrate", "impact": "medium", "reason": "Constrains runoff and eutrophication uncertainty."},
    ]
    return {
        "confidence_pct": score,
        "level": "high" if score >= 75 else "moderate" if score >= 50 else "low",
        "why_uncertain": [
            "Forecast interval widens with horizon",
            "Synthetic-development model has not been field-calibrated",
            "Recent biodiversity coverage is limited" if len(accepted) < 8 else "Biodiversity evidence is recent",
        ],
        "next_measurements": needs,
        "latest_values": latest,
        "mission": {
            "title": f"Verify dissolved oxygen at {summary['code']}",
            "needed": ["2 dissolved-oxygen readings", "3 macroinvertebrate samples", "1 stream photograph"],
            "due_at": (datetime.now(timezone.utc) + timedelta(hours=8)).replace(microsecond=0).isoformat(),
            "volunteers_nearby": 7,
        },
    }


def one_health_bridge(summary: dict, history: dict, observations: list[dict]) -> dict:
    do_now = _avg(history["do_mgl"][-24:])
    aspt = summary.get("aspt")
    stress = summary.get("stress") or 0
    sensitive = sum((o.get("bmwp_contribution") or 0) >= 8 for o in observations)
    level = "high" if stress >= 65 else "moderate" if stress >= 40 else "low"
    return {
        "attention_level": level,
        "disclaimer": "Environmental early-warning indicator, not a clinical diagnosis.",
        "reason": "Environmental conditions have deteriorated and the site has meaningful human interaction." if level != "low" else "Current environmental evidence does not indicate elevated One Health attention.",
        "domains": {
            "ecosystem": {"stress": stress, "aspt": aspt, "do_mgl": round(do_now, 2), "biodiversity": "declining" if stress >= 50 else "stable"},
            "animal_biodiversity": {"sensitive_taxa_observed": sensitive, "habitat_pressure": "high" if stress >= 65 else "moderate" if stress >= 40 else "low", "indicator_species": "under pressure" if stress >= 50 else "stable"},
            "human_exposure": {"recreation": "high" if summary.get("urban_index", 0) > .65 else "medium", "flood_exposure": "medium", "water_contact": "medium", "public_health_evidence": "unavailable"},
        },
    }


def model_card() -> dict:
    return {
        "name": "WatForecast Ridge v3",
        "purpose": "Short-range stream stress forecasting for decision support.",
        "inputs": ["dissolved oxygen", "water temperature", "turbidity", "nitrate", "precipitation", "ASPT", "time features"],
        "training_set": "Mechanistically inspired synthetic development data across six European urban reaches.",
        "evaluation": {"overall_mae": 2.757, "skill_0_24h": 0.421, "skill_24_48h": 0.237, "skill_48_72h": 0.227, "interval_coverage": 0.696},
        "known_limitations": ["Not validated for regulatory decision-making", "Synthetic-development data", "Interval coverage is below the nominal 80% and is labelled accordingly", "Accuracy varies with sensor availability"],
        "intended_use": "Research, citizen-science coordination and scenario exploration.",
    }
