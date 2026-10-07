"""Decision-support views built from the same evidence used by the dashboard.

These functions are intentionally deterministic.  They explain model output and
run labelled counterfactual simulations; they do not pretend to be causal proof
or regulatory advice.
"""
from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
from statistics import mean


INTERVENTIONS = {
    "aeration": {
        "name": "Temporary aeration",
        "description": "Simulates temporary oxygen support during the forecast event.",
        "disruption": 2,
        "stress_reduction": 0.18,
        "do_gain": 2.0,
        "cost_band": "medium", "cost_score": 68, "time_to_effect_h": 2,
        "feasibility": 86, "reversibility": 96, "co_benefit": 42,
        "one_health": 76, "evidence_strength": 82, "space_sensitivity": 2,
        "constraints": ["Requires power and safe equipment access", "Temporary measure; does not remove the pollution source"],
    },
    "retention": {
        "name": "Stormwater retention",
        "description": "Simulates reduced runoff, suspended solids and nutrient loading.",
        "disruption": 3,
        "stress_reduction": 0.22,
        "do_gain": 0.8,
        "cost_band": "high", "cost_score": 42, "time_to_effect_h": 24,
        "feasibility": 64, "reversibility": 70, "co_benefit": 94,
        "one_health": 91, "evidence_strength": 80, "space_sensitivity": 18,
        "constraints": ["Needs upstream storage or blue-green space", "Performance depends on storm volume and maintenance"],
    },
    "retention_aeration": {
        "name": "Retention + temporary aeration",
        "description": "Combines runoff control with short-term oxygen support.",
        "disruption": 4,
        "stress_reduction": 0.36,
        "do_gain": 2.4,
        "cost_band": "very high", "cost_score": 28, "time_to_effect_h": 6,
        "feasibility": 53, "reversibility": 66, "co_benefit": 83,
        "one_health": 92, "evidence_strength": 76, "space_sensitivity": 18,
        "constraints": ["Coordinates two operational teams", "Requires both suitable storage and powered access"],
    },
    "runoff_diversion": {
        "name": "Runoff diversion",
        "description": "Simulates diverting the first flush away from the monitored reach.",
        "disruption": 4,
        "stress_reduction": 0.28,
        "do_gain": 1.0,
        "cost_band": "high", "cost_score": 38, "time_to_effect_h": 12,
        "feasibility": 57, "reversibility": 72, "co_benefit": 74,
        "one_health": 82, "evidence_strength": 68, "space_sensitivity": 14,
        "constraints": ["Needs a safe receiving or storage pathway", "Must avoid transferring risk downstream"],
    },
    "discharge_restriction": {
        "name": "Temporary discharge restriction",
        "description": "Simulates limiting organic and nutrient loading during the risk window.",
        "disruption": 5,
        "stress_reduction": 0.30,
        "do_gain": 1.5,
        "cost_band": "medium", "cost_score": 62, "time_to_effect_h": 4,
        "feasibility": 48, "reversibility": 92, "co_benefit": 62,
        "one_health": 87, "evidence_strength": 72, "space_sensitivity": 0,
        "constraints": ["Requires a known controllable source and legal authority", "Potential operational burden for the discharger"],
    },
    "citizen_sampling": {
        "name": "Citizen sampling surge",
        "description": "Improves evidence coverage; it does not directly change stream conditions.",
        "disruption": 1,
        "stress_reduction": 0.0,
        "do_gain": 0.0,
        "cost_band": "low", "cost_score": 94, "time_to_effect_h": 3,
        "feasibility": 92, "reversibility": 100, "co_benefit": 67,
        "one_health": 65, "evidence_strength": 86, "space_sensitivity": 0,
        "decision_role": "verification",
        "constraints": ["Does not directly reduce ecological stress", "Needs training, review and safe site access"],
    },
}

CATALOGUE_URL = "https://www.oneaquahealth.eu/wp-content/uploads/2026/05/OAH_Catalogue-of-measures-1.pdf"
DSS_URL = "https://www.oneaquahealth.eu/decision-support-system/"

CRITERIA = {
    "effectiveness": {"label": "Expected ecological benefit", "weight": 30, "question": "How much forecast stress could this scenario avoid?"},
    "evidence": {"label": "Evidence strength", "weight": 15, "question": "How strong is the supporting evidence for this response type?"},
    "speed": {"label": "Time to effect", "weight": 12, "question": "Can it act inside the forecast risk window?"},
    "feasibility": {"label": "Site feasibility", "weight": 12, "question": "Can it be delivered under this reach and scenario context?"},
    "co_benefit": {"label": "Ecological co-benefit", "weight": 10, "question": "Does it support broader habitat and resilience outcomes?"},
    "one_health": {"label": "One Health relevance", "weight": 8, "question": "Could it benefit ecosystem, animal and human exposure pathways together?"},
    "reversibility": {"label": "Reversibility", "weight": 6, "question": "Can the action be safely adjusted or stopped?"},
    "cost": {"label": "Resource efficiency", "weight": 7, "question": "How favourable is its indicative resource requirement?"},
}

WEIGHT_PROFILES = {
    "balanced": {key: spec["weight"] for key, spec in CRITERIA.items()},
    "ecology_first": {"effectiveness": 42, "evidence": 13, "speed": 5, "feasibility": 8, "co_benefit": 17, "one_health": 8, "reversibility": 3, "cost": 4},
    "rapid_response": {"effectiveness": 27, "evidence": 12, "speed": 30, "feasibility": 13, "co_benefit": 5, "one_health": 5, "reversibility": 5, "cost": 3},
    "resource_constrained": {"effectiveness": 20, "evidence": 10, "speed": 8, "feasibility": 22, "co_benefit": 5, "one_health": 5, "reversibility": 5, "cost": 25},
    "precautionary": {"effectiveness": 20, "evidence": 28, "speed": 8, "feasibility": 12, "co_benefit": 8, "one_health": 10, "reversibility": 10, "cost": 4},
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


def _normalise_weights(weights: dict[str, float] | None = None) -> dict[str, float]:
    raw = {key: float((weights or {}).get(key, spec["weight"])) for key, spec in CRITERIA.items()}
    raw = {key: max(0.0, value) for key, value in raw.items()}
    total = sum(raw.values())
    if total <= 0:
        raw = {key: float(spec["weight"]) for key, spec in CRITERIA.items()}
        total = 100.0
    return {key: value / total * 100 for key, value in raw.items()}


def _criterion_scores(spec: dict, improvement: float, avoided: int, scenario: str,
                      urban_index: float) -> dict[str, float]:
    scenario_adjustment = {
        "storm": {"retention": 9, "runoff_diversion": 8, "retention_aeration": 6},
        "heatwave": {"aeration": 10, "retention_aeration": 7, "retention": -5},
        "spill": {"discharge_restriction": 14, "aeration": 8, "retention_aeration": 5},
    }.get(scenario, {})
    key = spec["key"]
    space_penalty = max(0.0, urban_index - 0.5) * 2 * spec["space_sensitivity"]
    feasibility = spec["feasibility"] + scenario_adjustment.get(key, 0) - space_penalty
    effectiveness = improvement * 2.5 + spec["do_gain"] * 5 + avoided
    return {
        "effectiveness": round(max(0, min(100, effectiveness)), 2),
        "evidence": float(spec["evidence_strength"]),
        "speed": round(max(0, 100 - min(spec["time_to_effect_h"], 72) / 72 * 100), 2),
        "feasibility": round(max(0, min(100, feasibility)), 2),
        "co_benefit": float(spec["co_benefit"]),
        "one_health": float(spec["one_health"]),
        "reversibility": float(spec["reversibility"]),
        "cost": float(spec["cost_score"]),
    }


def _score_candidates(candidates: list[dict], weights: dict[str, float]) -> list[dict]:
    ranked = []
    for candidate in candidates:
        contributions = {
            key: candidate["criterion_scores"][key] * weights[key] / 100
            for key in CRITERIA
        }
        ordered = sorted(contributions, key=contributions.get, reverse=True)
        weakest = min(candidate["criterion_scores"], key=candidate["criterion_scores"].get)
        ranked.append({
            **candidate,
            "decision_score": round(sum(contributions.values()), 2),
            "weighted_contributions": {key: round(value, 2) for key, value in contributions.items()},
            "decision_explanation": {
                "strongest": [{"criterion": key, "label": CRITERIA[key]["label"],
                               "contribution": round(contributions[key], 2)} for key in ordered[:2]],
                "main_tradeoff": {"criterion": weakest, "label": CRITERIA[weakest]["label"],
                                  "score": candidate["criterion_scores"][weakest]},
            },
        })
    ranked.sort(key=lambda item: (item["decision_score"], item["ecological_improvement_pct"]), reverse=True)
    for rank, candidate in enumerate(ranked, 1):
        candidate["rank"] = rank
        candidate["dominates"] = [
            other["key"] for other in ranked
            if other["key"] != candidate["key"]
            and all(candidate["criterion_scores"][key] >= other["criterion_scores"][key] for key in CRITERIA)
            and any(candidate["criterion_scores"][key] > other["criterion_scores"][key] for key in CRITERIA)
        ]
    return ranked


def _winner(candidates: list[dict], weights: dict[str, float]) -> str:
    ranked = _score_candidates(candidates, weights)
    return next((item["key"] for item in ranked if item.get("decision_role", "intervention") == "intervention"), ranked[0]["key"])


def _sensitivity(candidates: list[dict], weights: dict[str, float], winner: str) -> dict:
    scenarios = [{"label": "Current weights", "weights": weights, "winner": winner}]
    for key in CRITERIA:
        for multiplier, direction in ((0.5, "Lower"), (1.5, "Higher")):
            changed = {**weights, key: weights[key] * multiplier}
            normalised = _normalise_weights(changed)
            scenarios.append({
                "label": f"{direction} {CRITERIA[key]['label'].lower()}",
                "weights": normalised,
                "winner": _winner(candidates, normalised),
            })
    for name, profile in WEIGHT_PROFILES.items():
        if name == "balanced":
            continue
        normalised = _normalise_weights(profile)
        scenarios.append({"label": name.replace("_", " ").title(), "weights": normalised,
                          "winner": _winner(candidates, normalised)})
    distribution: dict[str, int] = {}
    for scenario in scenarios:
        distribution[scenario["winner"]] = distribution.get(scenario["winner"], 0) + 1
    matching = distribution.get(winner, 0)
    return {
        "scenarios_evaluated": len(scenarios),
        "recommended_in_scenarios": matching,
        "robustness_pct": round(matching / len(scenarios) * 100),
        "winner_distribution": distribution,
        "switches": [{"scenario": item["label"], "winner": item["winner"]}
                     for item in scenarios if item["winner"] != winner],
        "interpretation": (
            "robust" if matching / len(scenarios) >= 0.75
            else "weight-sensitive" if matching / len(scenarios) < 0.55
            else "moderately robust"
        ),
    }


def intervention_search(summary: dict, history: dict, forecast: dict,
                        weights: dict[str, float] | None = None) -> dict:
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
        candidate = {
            "key": key, **spec, **metrics,
            "critical_failures_avoided": avoided,
            "ecological_improvement_pct": improvement,
            "confidence": "medium-high" if key in {"aeration", "retention"} else "medium",
            "points": transformed,
            "decision_role": spec.get("decision_role", "intervention"),
            "evidence_basis": {
                "title": "OneAquaHealth Catalogue of Measures",
                "url": CATALOGUE_URL,
                "dss_url": DSS_URL,
                "scope": "Comparative planning prior; site-specific expert review remains required.",
            },
        }
        candidate["criterion_scores"] = _criterion_scores(
            candidate, improvement, avoided, summary.get("scenario", "none"),
            float(summary.get("urban_index", 0.5)),
        )
        results.append(candidate)
    decision_weights = _normalise_weights(weights)
    ranked = _score_candidates(results, decision_weights)
    recommended = next(
        (item for item in ranked if item["decision_role"] == "intervention"), ranked[0]
    )
    sensitivity = _sensitivity(results, decision_weights, recommended["key"])
    return {
        "segment_code": summary["code"],
        "scenario": summary.get("scenario", "none"),
        "label": "Simulation recommendation — not authoritative environmental advice",
        "baseline": baseline,
        "decision_model": {
            "name": "WatSen transparent weighted MCDA",
            "version": "1.0.0",
            "method": "Normalised additive utility with deterministic one-at-a-time and priority-profile sensitivity tests.",
            "weights": {key: round(value, 2) for key, value in decision_weights.items()},
            "criteria": [{"key": key, **spec, "direction": "higher-is-better"}
                         for key, spec in CRITERIA.items()],
            "weight_profiles": WEIGHT_PROFILES,
            "assumptions": [
                "Outcome values are labelled counterfactual simulations, not causal estimates.",
                "Cost bands are indicative planning priors, not procurement estimates.",
                "Site feasibility adjusts for scenario fit and urban space pressure.",
                "The monitoring action can rank highly but is not eligible as the primary ecological response.",
            ],
            "source": {"title": "OneAquaHealth Decision Support System",
                       "url": DSS_URL, "catalogue_url": CATALOGUE_URL},
        },
        "interventions": ranked,
        "recommended": recommended["key"],
        "recommendation": {
            "key": recommended["key"], "name": recommended["name"],
            "score": recommended["decision_score"], "rank": recommended["rank"],
            "reason": recommended["decision_explanation"],
            "policy": "Highest MCDA score among direct ecological responses under the active weights.",
        },
        "sensitivity": sensitivity,
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
    packaged_report = Path(__file__).resolve().parents[1] / "evidence" / "forecast_evaluation.json"
    repository_report = Path(__file__).resolve().parents[4] / "reports" / "forecast_evaluation.json"
    report_path = packaged_report if packaged_report.exists() else repository_report
    evaluation = None
    if report_path.exists():
        try:
            report = json.loads(report_path.read_text(encoding="utf-8"))
            chronological = report["chronological_holdout"]
            evaluation = {
                "evidence_status": report["dataset"]["source_kind"],
                "generated_at": report["generated_at"],
                "n_test_windows": chronological["n_windows"],
                **chronological["overall"],
                "horizon_bands": chronological["horizon_bands"],
                "event_detection": chronological["events"],
                "unseen_site_macro_average": report["leave_one_site_out"]["macro_average"],
                "unseen_city_macro_average": report["leave_one_city_out"]["macro_average"],
            }
        except (KeyError, TypeError, ValueError, OSError):
            evaluation = None
    return {
        "name": "WatForecast Ridge v3",
        "purpose": "Short-range stream stress forecasting for decision support.",
        "inputs": ["dissolved oxygen", "water temperature", "turbidity", "nitrate", "precipitation", "ASPT", "time features"],
        "training_set": "Mechanistically inspired synthetic development data across six European urban reaches.",
        "evaluation": evaluation or {
            "evidence_status": "unavailable",
            "message": "Run `make evaluate-forecaster` to generate the versioned evaluation artifact.",
        },
        "evaluation_protocol": "Per-site chronological holdout plus leave-one-site-out generalization; persistence and 24-hour seasonal baselines.",
        "known_limitations": ["Not validated for regulatory decision-making", "Synthetic-development data", "Rare severe events may be non-evaluable", "Accuracy varies with sensor availability"],
        "intended_use": "Research, citizen-science coordination and scenario exploration.",
    }
