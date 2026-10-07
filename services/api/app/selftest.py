"""
Smoke test.  `make test`

Hits every endpoint the demo touches and fails loudly if any contract drifts.
Run it before every push. On submission day, run it against the deployed URL:

    python -m app.selftest --base https://aquasentinel.onrender.com
"""
from __future__ import annotations

import argparse
import sys
from datetime import datetime, timedelta, timezone

PASS, FAIL = "PASS", "FAIL"
results: list[tuple[str, str, str]] = []


def check(name: str, fn):
    try:
        detail = fn()
        results.append((PASS, name, detail or ""))
    except AssertionError as e:
        results.append((FAIL, name, str(e)))
    except Exception as e:
        results.append((FAIL, name, f"{type(e).__name__}: {e}"))


def run(client) -> int:
    def get(path, **kw):
        r = client.get(path, **kw)
        assert r.status_code == 200, f"{path} -> {r.status_code} {r.text[:160]}"
        return r.json()

    check("health", lambda: (
        lambda d: (
            _assert(d["status"] == "ok", "status not ok"),
            f"backend={d['backend']} segments={d['segments']} brief={d['brief_model']}",
        )[-1]
    )(get("/health")))

    def segments():
        d = get("/v1/segments")
        segs = d["segments"]
        _assert(len(segs) >= 3, "expected at least 3 segments")
        for s in segs:
            _assert(0 <= (s["stress"] or 0) <= 100, f"{s['code']} stress out of range")
            _assert(s["band"] in ("good", "fair", "poor", "severe", "unknown"),
                    f"{s['code']} bad band {s['band']}")
        return f"{len(segs)} segments, bands ok"
    check("segments", segments)

    def geojson():
        d = get("/v1/segments.geojson")
        _assert(d["type"] == "FeatureCollection", "not a FeatureCollection")
        f = d["features"][0]
        _assert(f["geometry"]["type"] == "LineString", "geometry is not a LineString")
        _assert("stress" in f["properties"], "stress missing from properties")
        return f"{len(d['features'])} features"
    check("geojson", geojson)

    code = get("/v1/segments")["segments"][0]["code"]
    selected = get(f"/v1/segments/{code}")

    def history():
        d = get(f"/v1/segments/{code}/history?hours=168")
        _assert(len(d["t"]) == 168, f"expected 168 points, got {len(d['t'])}")
        for var in ("do_mgl", "turbidity_ntu", "temp_c", "stress"):
            _assert(var in d, f"{var} missing")
            _assert(len(d[var]) == 168, f"{var} wrong length")
        return "168h x 7 variables"
    check("history", history)

    def live_context():
        d = get(f"/v1/segments/{code}/live-context")
        _assert(d["segment_code"] == code, "live context returned the wrong reach")
        _assert(d["mode"] in ("live", "unavailable"), "invalid live-context mode")
        _assert(d["source"]["name"] == "Open-Meteo Forecast API", "source provenance missing")
        _assert(len(d["limitations"]) >= 1, "live context has no limitation disclosure")
        if d["mode"] == "live":
            _assert(d["current"], "live context has no current values")
            _assert(all("unit" in item and "observed_at" in item for item in d["current"]),
                    "live values are missing units or timestamps")
        cached = get(f"/v1/segments/{code}/live-context")
        _assert(cached["cache"] == "hit", "live context was not cached")
        return f"{d['mode']}, cache={cached['cache']}"
    check("live context provenance", live_context)

    def forecast():
        d = get(f"/v1/segments/{code}/forecast")
        pts = d["points"]
        _assert(len(pts) == 72, f"expected 72 points, got {len(pts)}")
        for p in pts:
            _assert(p["lower"] <= p["value"] <= p["upper"],
                    f"interval does not contain the mean at {p['valid_at']}")
        widths = [p["upper"] - p["lower"] for p in pts]
        _assert(widths[-1] >= widths[0],
                "uncertainty does not grow with horizon — check the quantiles")
        return f"72h, interval {widths[0]:.1f} -> {widths[-1]:.1f}"
    check("forecast", forecast)

    def scenarios():
        keys = [s["key"] for s in get("/v1/scenarios")["scenarios"]]
        _assert("storm" in keys, "storm scenario missing")
        base = get(f"/v1/segments/{code}")["stress"]
        storm = get(f"/v1/segments/{code}?scenario=storm")["stress"]
        _assert(storm > base, f"storm ({storm}) did not raise stress above baseline ({base})")
        return f"baseline {base} -> storm {storm}"
    check("scenarios", scenarios)

    def alerts():
        d = get("/v1/alerts?scenario=storm")
        _assert(isinstance(d["alerts"], list), "alerts is not a list")
        for a in d["alerts"]:
            _assert(a["severity"] in ("watch", "warning", "critical"), "bad severity")
        return f"{len(d['alerts'])} alerts under storm"
    check("alerts", alerts)

    def submit_clean():
        r = client.post("/v1/observations", json={
            "segment_code": code,
            "observed_at": (datetime.now(timezone.utc) - timedelta(hours=2)).isoformat(),
            "lat": selected["lat"], "lon": selected["lon"], "contributor": "selftest",
            "note": "Three-minute kick sample.", "predicted_taxon": "Gammaridae",
            "taxon_confidence": 0.93, "n_photos": 2,
        })
        _assert(r.status_code == 201, f"{r.status_code} {r.text[:160]}")
        body = r.json()
        v = body["validation"]
        _assert(v["state"] == "auto_accepted", f"clean submission was {v['state']}")
        _assert(v["explanation"], "no explanation returned")
        receipt = body["impact_receipt"]
        _assert(receipt["observation_id"] == body["observation"]["id"],
                "impact receipt is not linked to its observation")
        _assert(receipt["status"] in ("applied", "accepted_no_index_change"),
                f"unexpected accepted receipt status {receipt['status']}")
        _assert(receipt["accepted"] is True, "accepted evidence receipt is not marked accepted")
        _assert(set(receipt["changes"]) == {"aspt", "bmwp", "accepted_observations", "stress"},
                "impact receipt change set drifted")
        _assert("not causal" in receipt["boundary"], "receipt boundary is missing")
        return f"q={v['quality_score']}, receipt={receipt['status']}"
    check("submit clean", submit_clean)

    def submit_bad():
        r = client.post("/v1/observations", json={
            "segment_code": code, "observed_at": datetime.now(timezone.utc).isoformat(),
            "lat": 44.5, "lon": 11.4, "contributor": "selftest-spam", "note": "",
            "predicted_taxon": "Perlidae", "taxon_confidence": 0.2,
            "distance_to_stream_m": 900, "submissions_last_hour": 20,
            "readings": {"ph": 14.5}, "contributor_trust": 0.02,
        })
        _assert(r.status_code == 201, f"{r.status_code}")
        body = r.json()
        v = body["validation"]
        _assert(v["state"] != "auto_accepted", "obvious spam was auto-accepted")
        _assert(len(v["reasons"]) >= 3, "too few reasons for an obviously bad submission")
        receipt = body["impact_receipt"]
        _assert(receipt["status"] in ("pending_review", "not_applied"),
                f"unsafe submission receipt was {receipt['status']}")
        _assert(receipt["accepted"] is False, "unsafe evidence receipt is marked accepted")
        _assert(receipt["changes"]["accepted_observations"]["delta"] == 0,
                "unsafe evidence changed the accepted evidence window")
        return f"{v['state']}, {len(v['reasons'])} reasons, receipt={receipt['status']}"
    check("submit spam", submit_bad)

    check("contributor", lambda: (
        lambda d: (_assert(d["n_observations"] >= 1, "no observations recorded"),
                   f"{d['n_observations']} obs, mean q={d['mean_quality']}")[-1]
    )(get("/v1/contributors/selftest")))

    def resilience():
        for suffix in ("failure-chain", "interventions", "catchment-twin", "evidence-graph", "data-sufficiency", "one-health", "incident"):
            d = get(f"/v1/segments/{code}/{suffix}?scenario=storm")
            _assert(isinstance(d, dict) and d, f"empty {suffix}")
        decision = get(f"/v1/segments/{code}/interventions?scenario=storm")
        weights = decision["decision_model"]["weights"]
        ranked = decision["interventions"]
        _assert(abs(sum(weights.values()) - 100) < 0.05, f"MCDA weights total {sum(weights.values())}")
        _assert([item["rank"] for item in ranked] == list(range(1, len(ranked) + 1)),
                "MCDA ranks are not continuous")
        _assert(all(ranked[i]["decision_score"] >= ranked[i + 1]["decision_score"]
                    for i in range(len(ranked) - 1)), "MCDA options are not score-sorted")
        recommended = next(item for item in ranked if item["key"] == decision["recommended"])
        _assert(recommended["decision_role"] == "intervention",
                "a verification action was selected as the primary response")
        _assert(abs(sum(recommended["weighted_contributions"].values())
                    - recommended["decision_score"]) < 0.06,
                "weighted contributions do not reproduce the decision score")
        _assert(decision["sensitivity"]["scenarios_evaluated"] >= 20,
                "too few deterministic sensitivity scenarios")
        cost_query = (
            f"/v1/segments/{code}/interventions?scenario=storm"
            "&weight_effectiveness=0&weight_evidence=0&weight_speed=0"
            "&weight_feasibility=0&weight_co_benefit=0&weight_one_health=0"
            "&weight_reversibility=0&weight_cost=100"
        )
        cost_first = get(cost_query)
        _assert(cost_first["decision_model"]["weights"]["cost"] == 100,
                "custom MCDA weights were not applied")
        _assert(cost_first["interventions"][0]["key"] == "citizen_sampling",
                "resource-efficiency stress test did not alter the ranking")
        _assert(cost_first["recommended"] != "citizen_sampling",
                "verification action escaped the primary-response guardrail")
        twin = get(f"/v1/segments/{code}/catchment-twin?scenario=storm")
        node_ids = {node["id"] for node in twin["nodes"]}
        _assert(len(node_ids) == 7 and len(twin["edges"]) == 7,
                "catchment twin topology drifted")
        _assert(twin["model"]["kind"] == "deterministic-topology-prior",
                "catchment model boundary is missing")
        _assert("not a calibrated" in twin["model"]["boundary"].lower(),
                "catchment twin does not disclose its model boundary")
        _assert(twin["pressure"]["origin"] in node_ids, "pressure origin is not a node")
        _assert(len(twin["protected_assets"]) == 2, "protected assets are missing")
        _assert(twin["recommended_plan"] in {plan["key"] for plan in twin["plans"]},
                "recommended catchment plan is unavailable")
        _assert(all(set(plan["node_outcomes"]) == node_ids for plan in twin["plans"]),
                "a response plan is missing node outcomes")
        hot = get("/v1/hotspots?scenario=storm")["hotspots"]
        _assert(len(hot) >= 3, "hotspot radar is empty")
        return (f"MCDA {len(ranked)} options / {decision['sensitivity']['scenarios_evaluated']} "
                "sensitivity tests, 7-node directed twin, mission, One Health and replay")
    check("resilience loop", resilience)

    def brief():
        d = get(f"/v1/segments/{code}/brief?scenario=storm")
        for k in ("headline", "risk_level", "ecosystem", "animal", "human", "evidence"):
            _assert(k in d and d[k], f"brief missing {k}")
        _assert(d["risk_level"] in ("low", "moderate", "high"), "bad risk_level")
        ids = {e["id"] for e in d["evidence"]}
        import re
        body = " ".join(d[k] for k in ("ecosystem", "animal", "human", "what_changes"))
        cited = set(re.findall(r"\[([A-Z0-9\-]+)\]", body))
        _assert(cited <= ids, f"brief cites evidence that does not exist: {cited - ids}")
        return f"{d['generator']}, {len(ids)} evidence items, {len(cited)} cited"
    check("brief grounding", brief)

    def model_evidence():
        d = get("/v1/models/watforecast")
        evaluation = d["evaluation"]
        _assert(evaluation.get("evidence_status") == "synthetic-development", str(evaluation))
        _assert(evaluation.get("n_test_windows", 0) > 0, "evaluation artifact was not loaded")
        _assert("unseen_site_macro_average" in evaluation, "missing unseen-site evaluation")
        _assert("unseen_city_macro_average" in evaluation, "missing unseen-city evaluation")
        return (f"{evaluation['n_test_windows']} test windows, "
                f"MAE={evaluation['mae']}, coverage={evaluation['interval_80_coverage']}")
    check("forecast evidence", model_evidence)

    def fhir():
        d = get(f"/v1/segments/{code}/fhir?hours=6")
        _assert(d["resourceType"] == "Bundle", "not a Bundle")
        _assert(d["type"] == "transaction", "not a transaction bundle")
        kinds = {e["resource"]["resourceType"] for e in d["entry"]}
        _assert({"Location", "Observation", "PractitionerRole"} <= kinds,
                f"missing resources: {kinds}")
        refs = {e["fullUrl"] for e in d["entry"]}
        for e in d["entry"]:
            _assert("request" in e, "transaction entry without a request")
            resource = e["resource"]
            if resource["resourceType"] == "Observation":
                _assert(resource["meta"]["profile"] == [
                    "http://hl7.eu/fhir/ig/oah/StructureDefinition/observation-indicators-oah"
                ], "wrong OAH observation profile")
                _assert(all(p["reference"] in refs for p in resource["performer"]),
                        "unresolved observation performer")
            if resource["resourceType"] == "Specimen":
                _assert(resource["collection"]["collector"]["reference"] in refs,
                        "unresolved specimen collector")
        return f"{len(d['entry'])} entries, {sorted(kinds)}"
    check("fhir bundle", fhir)

    def fhir_validation():
        d = get(f"/v1/segments/{code}/fhir/validate?hours=2")
        _assert(d["status"] == "pass", str(d["errors"]))
        _assert(d["authoritative_validation"] is False, "local preflight mislabelled authoritative")
        return f"{len(d['errors'])} errors; correctly labelled local preflight"
    check("fhir preflight", fhir_validation)

    def csv():
        r = client.get("/v1/export/observations.csv")
        _assert(r.status_code == 200, f"{r.status_code}")
        _assert(r.text.startswith("id,segment_code"), "unexpected CSV header")
        return f"{len(r.text.splitlines()) - 1} rows"
    check("csv export", csv)

    width = max(len(n) for _, n, _ in results)
    print()
    for status, name, detail in results:
        mark = "\033[32m ok \033[0m" if status == PASS else "\033[31mFAIL\033[0m"
        print(f"  [{mark}] {name:<{width}}  {detail}")
    failed = sum(1 for s, _, _ in results if s == FAIL)
    print(f"\n{len(results) - failed}/{len(results)} passed")
    return 1 if failed else 0


def _assert(cond, msg):
    if not cond:
        raise AssertionError(msg)


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--base", default=None, help="test a deployed URL instead of in-process")
    args = ap.parse_args()

    if args.base:
        import httpx
        client = httpx.Client(base_url=args.base, timeout=60)
    else:
        from fastapi.testclient import TestClient
        from app.main import app
        client = TestClient(app)

    sys.exit(run(client))
