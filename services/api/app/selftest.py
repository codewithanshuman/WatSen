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
        v = r.json()["validation"]
        _assert(v["state"] == "auto_accepted", f"clean submission was {v['state']}")
        _assert(v["explanation"], "no explanation returned")
        return f"q={v['quality_score']}"
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
        v = r.json()["validation"]
        _assert(v["state"] != "auto_accepted", "obvious spam was auto-accepted")
        _assert(len(v["reasons"]) >= 3, "too few reasons for an obviously bad submission")
        return f"{v['state']}, {len(v['reasons'])} reasons"
    check("submit spam", submit_bad)

    check("contributor", lambda: (
        lambda d: (_assert(d["n_observations"] >= 1, "no observations recorded"),
                   f"{d['n_observations']} obs, mean q={d['mean_quality']}")[-1]
    )(get("/v1/contributors/selftest")))

    def resilience():
        for suffix in ("failure-chain", "interventions", "evidence-graph", "data-sufficiency", "one-health", "incident"):
            d = get(f"/v1/segments/{code}/{suffix}?scenario=storm")
            _assert(isinstance(d, dict) and d, f"empty {suffix}")
        hot = get("/v1/hotspots?scenario=storm")["hotspots"]
        _assert(len(hot) >= 3, "hotspot radar is empty")
        return "failure chain, interventions, graph, mission, One Health and replay"
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

    def fhir():
        d = get(f"/v1/segments/{code}/fhir?hours=6")
        _assert(d["resourceType"] == "Bundle", "not a Bundle")
        _assert(d["type"] == "transaction", "not a transaction bundle")
        kinds = {e["resource"]["resourceType"] for e in d["entry"]}
        _assert("Location" in kinds and "Observation" in kinds, f"missing resources: {kinds}")
        for e in d["entry"]:
            _assert("request" in e, "transaction entry without a request")
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
