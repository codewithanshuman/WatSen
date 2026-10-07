"""Directed catchment schematic for interactive, honest scenario planning.

The topology is a deterministic planning abstraction. Travel times and response
effects are deliberately labelled priors; they are not a calibrated hydraulic or
hydrodynamic model.
"""
from __future__ import annotations

from heapq import heappop, heappush


NODE_LAYOUT = [
    ("headwaters", "Upper catchment", "source", 72, 92, -10),
    ("tributary", "Tributary junction", "junction", 225, 183, -5),
    ("urban_outfall", "Urban drainage", "pressure", 222, 302, 8),
    ("monitor", "Monitored reach", "monitored", 410, 183, 0),
    ("habitat", "Riparian refuge", "habitat", 585, 88, -8),
    ("community", "Public riverfront", "community", 588, 272, 2),
    ("downstream", "Receiving reach", "outlet", 748, 183, -4),
]

EDGE_LAYOUT = [
    ("headwaters", "tributary", 4, 0.03),
    ("urban_outfall", "tributary", 2, 0.01),
    ("tributary", "monitor", 5, 0.04),
    ("monitor", "habitat", 4, 0.06),
    ("monitor", "community", 6, 0.04),
    ("habitat", "downstream", 5, 0.08),
    ("community", "downstream", 3, 0.05),
]

ORIGIN = {
    "none": ("headwaters", "Background catchment pressure"),
    "storm": ("urban_outfall", "First-flush runoff pulse"),
    "heatwave": ("headwaters", "Catchment-wide thermal pressure"),
    "spill": ("urban_outfall", "Controllable discharge pulse"),
}


def _clamp(value: float) -> float:
    return round(max(0.0, min(100.0, value)), 1)


def _shortest_arrivals(origin: str) -> dict[str, float]:
    adjacency: dict[str, list[tuple[str, float]]] = {}
    for source, target, travel_h, _ in EDGE_LAYOUT:
        adjacency.setdefault(source, []).append((target, travel_h))
    arrivals = {origin: 0.0}
    queue: list[tuple[float, str]] = [(0.0, origin)]
    while queue:
        elapsed, node = heappop(queue)
        if elapsed != arrivals[node]:
            continue
        for target, travel_h in adjacency.get(node, []):
            candidate = elapsed + travel_h
            if candidate < arrivals.get(target, float("inf")):
                arrivals[target] = candidate
                heappush(queue, (candidate, target))
    return arrivals


def _descendants(origin: str) -> set[str]:
    adjacency: dict[str, list[str]] = {}
    for source, target, _, _ in EDGE_LAYOUT:
        adjacency.setdefault(source, []).append(target)
    found, stack = {origin}, [origin]
    while stack:
        for target in adjacency.get(stack.pop(), []):
            if target not in found:
                found.add(target)
                stack.append(target)
    return found


def catchment_twin(summary: dict, forecast: dict, intervention_result: dict) -> dict:
    scenario = summary.get("scenario", "none")
    origin, pressure_label = ORIGIN.get(scenario, ORIGIN["none"])
    arrivals = _shortest_arrivals(origin)
    current = float(summary.get("stress") or 0)
    forecast_peak = max(float(point["value"]) for point in forecast["points"])
    impulse = max(8.0, forecast_peak - current)

    nodes = []
    for node_id, generic_label, role, x, y, offset in NODE_LAYOUT:
        arrival = arrivals.get(node_id)
        baseline = _clamp(current + offset)
        if arrival is None:
            peak = baseline
        elif node_id == "monitor":
            peak = round(forecast_peak, 1)
        else:
            attenuation = min(0.38, arrival * 0.022)
            vulnerability = 5 if role == "habitat" else 3 if role == "community" else 0
            peak = _clamp(baseline + impulse * (1 - attenuation) + vulnerability)
        label = {
            "headwaters": f"Upper {summary['name']}",
            "habitat": f"{summary['city']} riparian refuge",
            "community": f"{summary['city']} public riverfront",
            "downstream": "Downstream receiving reach",
        }.get(node_id, generic_label if node_id != "monitor" else summary["name"])
        nodes.append({
            "id": node_id, "label": label, "role": role, "x": x, "y": y,
            "arrival_h": arrival, "peak_h": None if arrival is None else min(72, round(arrival + 12)),
            "baseline_stress": baseline, "peak_stress": peak,
            "protected_asset": role in {"habitat", "community"},
            "threshold": 75 if role in {"habitat", "community"} else 70,
        })
    by_id = {node["id"]: node for node in nodes}
    edges = []
    for index, (source, target, travel_h, attenuation) in enumerate(EDGE_LAYOUT, 1):
        edge_arrival = arrivals.get(source)
        edges.append({
            "id": f"flow-{index}", "source": source, "target": target,
            "travel_time_h": travel_h, "attenuation_prior": attenuation,
            "activation_h": edge_arrival,
            "length_class": "short" if travel_h <= 3 else "medium" if travel_h <= 5 else "long",
        })

    action_nodes = {
        "retention": "tributary", "runoff_diversion": "tributary",
        "discharge_restriction": "urban_outfall", "aeration": "monitor",
        "retention_aeration": "tributary",
    }
    plans = [{
        "key": "observe", "name": "Monitor only", "action_node": None,
        "activation_h": None, "reduction_pct": 0, "cost_band": "none",
        "node_outcomes": {node["id"]: node["peak_stress"] for node in nodes},
        "boundary": "Observation changes confidence, not stream conditions.",
    }]
    for option in intervention_result["interventions"]:
        if option.get("decision_role") == "verification":
            continue
        action_node = action_nodes[option["key"]]
        affected = _descendants(action_node)
        action_arrival = by_id[action_node]["arrival_h"] or 0
        outcomes = {}
        for node in nodes:
            reduction = 0.0
            if node["id"] in affected:
                downstream_h = max(0.0, (node["arrival_h"] or action_arrival) - action_arrival)
                reduction = option["stress_reduction"] * max(0.55, 1 - downstream_h * 0.025)
            outcomes[node["id"]] = _clamp(node["peak_stress"] * (1 - reduction))
        plans.append({
            "key": option["key"], "name": option["name"],
            "action_node": action_node, "activation_h": option["time_to_effect_h"],
            "reduction_pct": round(option["stress_reduction"] * 100),
            "cost_band": option["cost_band"], "node_outcomes": outcomes,
            "boundary": "Counterfactual effect transferred through the schematic network; field calibration required.",
        })

    recommended_key = intervention_result["recommended"]
    recommended = next(plan for plan in plans if plan["key"] == recommended_key)
    assets = []
    for node in nodes:
        if not node["protected_asset"]:
            continue
        no_action = node["peak_stress"]
        with_plan = recommended["node_outcomes"][node["id"]]
        assets.append({
            "node_id": node["id"], "label": node["label"], "threshold": node["threshold"],
            "arrival_h": node["arrival_h"], "without_action": no_action,
            "with_recommended": with_plan,
            "status_without_action": "critical" if no_action >= node["threshold"] else "watch",
            "status_with_recommended": "protected" if with_plan < node["threshold"] else "critical",
        })
    critical_before = sum(asset["status_without_action"] == "critical" for asset in assets)
    critical_after = sum(asset["status_with_recommended"] == "critical" for asset in assets)
    first_asset_arrival = min((asset["arrival_h"] for asset in assets if asset["arrival_h"] is not None), default=None)

    return {
        "segment_code": summary["code"], "scenario": scenario,
        "model": {
            "name": "WatSen directed catchment planning schematic", "version": "1.0.0",
            "kind": "deterministic-topology-prior",
            "boundary": "Not a calibrated hydraulic, hydrodynamic or contaminant-transport model.",
            "assumptions": [
                "Travel times are transparent planning priors.",
                "Stress attenuates downstream in the schematic network.",
                "Response effects reuse the labelled intervention counterfactuals.",
                "Protected-asset thresholds are demonstration policy settings.",
            ],
        },
        "pressure": {"origin": origin, "label": pressure_label, "peak_stress": forecast_peak},
        "nodes": nodes, "edges": edges, "plans": plans, "recommended_plan": recommended_key,
        "objective": {
            "title": "Protect connected habitats and public river use",
            "condition": "Keep protected assets below stress 75 through the 72-hour event window.",
            "threshold": 75, "first_asset_arrival_h": first_asset_arrival,
            "critical_assets_without_action": critical_before,
            "critical_assets_with_recommended": critical_after,
            "recommended_plan": recommended["name"],
        },
        "protected_assets": assets,
    }
