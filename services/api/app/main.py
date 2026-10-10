"""
WatSen API.

Run:  uvicorn app.main:app --reload --port 8000
Docs: http://localhost:8000/docs

This file IS the interface contract. Freeze it on day 3. If an endpoint shape
changes after that, announce it in the team channel before you push.
"""
from __future__ import annotations

import os
from datetime import datetime, timezone

from fastapi import FastAPI, File, HTTPException, Query, UploadFile, Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field, field_validator

from app.core import fhir
from app.core import decision
from app.core import catchment
from app.core import evidence_workflow as evidence
from app.core.stress import BMWP_FAMILY
from app.core.scenarios import SCENARIOS
from app.core.anomaly import Submission
from app.insight import brief as brief_engine
from app.store import get_store
from app.ml.vision import VisionRuntime
from app.ingest.live_context import live_context
from app.core.synthetic import BY_CODE

app = FastAPI(
    title="WatSen API",
    version="0.3.0",
    description=(
        "Urban freshwater intelligence. Stream state, 72-hour stress forecasts, "
        "validated citizen observations, One Health briefs and FHIR export."
    ),
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=os.getenv(
        "CORS_ORIGINS",
        "http://localhost:5173,http://127.0.0.1:5173,http://localhost:4173,http://127.0.0.1:4173,http://localhost:3000",
    ).split(","),
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ── models ─────────────────────────────────────────────────────────

class ObservationIn(BaseModel):
    client_submission_id: str | None = Field(None, min_length=8, max_length=128, pattern=r"^[a-zA-Z0-9_-]+$")
    segment_code: str = Field(..., examples=["IT-BLG-01"])
    observed_at: datetime
    lat: float = Field(..., ge=-90, le=90)
    lon: float = Field(..., ge=-180, le=180)
    contributor: str = "anonymous"
    note: str = ""
    predicted_taxon: str | None = Field(None, examples=["Baetidae"])
    taxon_confidence: float | None = Field(None, ge=0, le=1)
    n_photos: int = Field(1, ge=0, le=100)
    readings: dict[str, float] | None = None
    model: str | None = None
    image_quality: dict | None = None

    @field_validator("observed_at")
    @classmethod
    def normalise_timestamp(cls, value: datetime) -> datetime:
        if value.tzinfo is None:
            value = value.replace(tzinfo=timezone.utc)
        return value.astimezone(timezone.utc)


class ReviewIn(BaseModel):
    action: str = Field(..., pattern="^(confirm|correct|reject)$")
    reviewer: str = "expert-reviewer"
    corrected_taxon: str | None = None
    reviewer_note: str = Field("", max_length=2000)


# ── meta ───────────────────────────────────────────────────────────

@app.get("/health", tags=["meta"])
def health():
    store = get_store()
    return {
        "status": "ok",
        "backend": "mock" if store.__class__.__name__ == "MockStore" else "postgres",
        "segments": len(store.segments),
        "observations": len(store.observations),
        "brief_model": "live" if os.getenv("ANTHROPIC_API_KEY") else "template-fallback",
        "time": datetime.now(timezone.utc).isoformat(),
    }


# ── segments ───────────────────────────────────────────────────────

SCENARIO_Q = Query("none", description="Labelled demo perturbation. Always echoed back in the response.")


@app.get("/v1/scenarios", tags=["meta"])
def scenarios():
    """What each demo scenario does. Show this in the UI next to the selector."""
    return {"scenarios": [{"key": k, "description": v} for k, v in SCENARIOS.items()]}


@app.get("/v1/segments", tags=["segments"])
def list_segments(scenario: str = SCENARIO_Q):
    _check_scenario(scenario)
    store = get_store()
    return {"scenario": scenario,
            "segments": [store.segment_summary(c, scenario) for c in store.segments]}


@app.get("/v1/segments.geojson", tags=["segments"])
def segments_geojson(scenario: str = SCENARIO_Q, horizon: int = Query(0, ge=0, le=72)):
    """Map source with current or forecast stress at a selected horizon."""
    _check_scenario(scenario)
    store = get_store()
    features = []
    for code in store.segments:
        s = store.segment_summary(code, scenario)
        if horizon:
            stress = store.forecast(code, scenario)["points"][horizon - 1]["value"]
            band = "good" if stress < 25 else "fair" if stress < 50 else "poor" if stress < 75 else "severe"
        else:
            stress, band = s["stress"], s["band"]
        features.append({
            "type": "Feature",
            "geometry": s["geometry"],
            "properties": {
                "code": s["code"], "name": s["name"], "city": s["city"],
                "stress": stress, "band": band, "horizon_h": horizon,
                "aspt": s["aspt"], "observations_30d": s["observations_30d"],
            },
        })
    return {"type": "FeatureCollection", "features": features}


@app.get("/v1/segments/{code}", tags=["segments"])
def get_segment(code: str, scenario: str = SCENARIO_Q):
    _check_scenario(scenario)
    store = get_store()
    if code not in store.segments:
        raise HTTPException(404, f"unknown segment {code}")
    return store.segment_summary(code, scenario)


@app.get("/v1/segments/{code}/history", tags=["segments"])
def get_history(code: str, hours: int = Query(336, ge=24, le=24 * 240),
                scenario: str = SCENARIO_Q):
    _check_scenario(scenario)
    store = get_store()
    if code not in store.segments:
        raise HTTPException(404, f"unknown segment {code}")
    return store.history(code, hours=hours, scenario=scenario)


@app.get("/v1/segments/{code}/live-context", tags=["segments"])
def get_live_context(code: str, refresh: bool = False):
    """Live weather context, never silently substituted for water evidence."""
    if code not in BY_CODE:
        raise HTTPException(404, f"unknown segment {code}")
    return live_context(BY_CODE[code], force=refresh)


# ── forecast ───────────────────────────────────────────────────────

@app.get("/v1/segments/{code}/forecast", tags=["forecast"])
def get_forecast(code: str, scenario: str = SCENARIO_Q):
    _check_scenario(scenario)
    store = get_store()
    if code not in store.segments:
        raise HTTPException(404, f"unknown segment {code}")
    return store.forecast(code, scenario)


@app.get("/v1/alerts", tags=["forecast"])
def list_alerts(scenario: str = SCENARIO_Q):
    _check_scenario(scenario)
    store = get_store()
    out = []
    for code in store.segments:
        out.extend(store.forecast(code, scenario)["alerts"])
    order = {"critical": 0, "warning": 1, "watch": 2}
    out.sort(key=lambda a: (order.get(a["severity"], 9), a["valid_from"]))
    return {"scenario": scenario, "alerts": out}


# ── observations ───────────────────────────────────────────────────

@app.get("/v1/observations", tags=["observations"])
def list_observations(segment_code: str | None = None, limit: int = Query(100, le=500)):
    return {"observations": get_store().list_observations(segment_code, limit)}


@app.post("/v1/observations", tags=["observations"], status_code=201)
def submit_observation(payload: ObservationIn, response: Response):
    store = get_store()
    data = payload.model_dump(mode="json")
    # Check raw metadata before JSON-mode serialization can normalize NaN to null.
    evidence.fingerprint({**data, "image_quality": payload.image_quality, "readings": payload.readings})
    with store.evidence_lock:
        existing = evidence.replay(store, data)
        if existing is not None:
            response.status_code = 200
            return existing
        return evidence.record_submission(store, data, _submit_observation(payload))


def _submit_observation(payload: ObservationIn):
    """
    Validate and store a citizen submission.

    The response always includes `explanation` — a plain-language reason the
    submission was accepted or held. Show it to the contributor verbatim.
    """
    store = get_store()
    if payload.segment_code not in store.segments:
        raise HTTPException(404, f"unknown segment {payload.segment_code}")

    before_bio = store.biological_index(payload.segment_code)
    before_stress = store.segment_summary(payload.segment_code)["stress"]

    sensors = None
    if payload.readings:
        sensors = store.nearest_sensor_readings(
            payload.segment_code, payload.observed_at, list(payload.readings))

    distance = store.distance_to_stream_m(payload.segment_code, payload.lat, payload.lon)
    submissions_1h = store.submissions_last_hour(payload.contributor)
    trust = store.contributor_trust(payload.contributor)["score"]

    sub = Submission(
        observed_at=payload.observed_at,
        taxon=payload.predicted_taxon,
        taxon_confidence=payload.taxon_confidence or 0.0,
        distance_to_stream_m=distance,
        n_photos=payload.n_photos,
        note=payload.note,
        readings=payload.readings,
        sensor_readings=sensors,
        submissions_last_hour=submissions_1h,
        contributor_trust=trust,
    )
    scored = evidence.require_model_review(payload.model_dump(), store.scorer.score(sub))
    row = store.add_observation(
        {**payload.model_dump(), "observed_at": payload.observed_at.isoformat(),
         "distance_to_stream_m": distance}, scored
    )
    after_bio = store.biological_index(payload.segment_code)
    after_stress = store.segment_summary(payload.segment_code)["stress"]
    receipt = evidence.impact_receipt(store, row, before_bio, after_bio, before_stress, after_stress)
    return {"observation": row, "validation": scored,
            "server_checks": {"distance_to_stream_m": distance,
                              "submissions_last_hour": submissions_1h,
                              "contributor_trust": trust},
            "biological_index": after_bio, "impact_receipt": receipt}


@app.post("/v1/classify", tags=["observations"])
async def classify_image(image: UploadFile = File(...)):
    """Assess an image and return an AI suggestion, never an automatic fact."""
    raw = await image.read()
    if not raw or len(raw) > 12 * 1024 * 1024:
        raise HTTPException(400, "image must be between 1 byte and 12 MB")
    try:
        return VisionRuntime().assess(raw, image.filename or "upload")
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc


@app.get("/v1/review-queue", tags=["observations"])
def review_queue():
    return get_store().review_queue()


@app.post("/v1/observations/{observation_id}/review", tags=["observations"])
def review_observation(observation_id: str, payload: ReviewIn):
    with get_store().evidence_lock:
        return _review_observation(observation_id, payload)


def _review_observation(observation_id: str, payload: ReviewIn):
    store = get_store()
    existing = store.observation(observation_id)
    if existing is None:
        raise HTTPException(404, "observation not found")
    code = existing["segment_code"]
    previous = {key: existing.get(key) for key in ("state", "predicted_taxon")}
    if (payload.action == "correct" or existing.get("reviewed_at")) and not payload.reviewer_note.strip():
        raise HTTPException(422, "Explain the correction or revised decision in a reviewer note.")
    before_bio = store.biological_index(code)
    before_stress = store.segment_summary(code)["stress"]
    try:
        row = store.review_observation(
            observation_id, payload.action, payload.reviewer, payload.corrected_taxon, payload.reviewer_note.strip())
    except KeyError as exc:
        raise HTTPException(404, "observation not found") from exc
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc
    after_bio = store.biological_index(code)
    after_stress = store.segment_summary(code)["stress"]
    return {"observation": row, "biological_index": after_bio,
            "impact_receipt": evidence.impact_receipt(
                store, row, before_bio, after_bio, before_stress, after_stress,
                event=payload.action, previous=previous, reviewer_note=payload.reviewer_note.strip())}


@app.get("/v1/taxa", tags=["observations"])
def scoring_taxa():
    return {"taxa": [{"family": family, "bmwp": score} for family, score in sorted(BMWP_FAMILY.items())]}


@app.get("/v1/observations/{observation_id}/receipts", tags=["observations"])
def observation_receipts(observation_id: str):
    store = get_store()
    with store.evidence_lock:
        if store.observation(observation_id) is None:
            raise HTTPException(404, "This observation is unavailable in the current demo server session. Your device receipt remains available.")
        return {"observation_id": observation_id,
                "receipts": store.receipt_history.get(observation_id, []),
                "storage_boundary": evidence.STORAGE_BOUNDARY}


@app.get("/v1/contributors/{handle}", tags=["observations"])
def contributor(handle: str):
    """The feedback loop. Everything this person submitted and what it did."""
    return get_store().contributor_record(handle)


# ── resilience decision support ──────────────────────────────────

def _decision_inputs(code: str, scenario: str):
    _check_scenario(scenario)
    store = get_store()
    if code not in store.segments:
        raise HTTPException(404, f"unknown segment {code}")
    return (
        store,
        store.segment_summary(code, scenario),
        store.history(code, 168, scenario),
        store.forecast(code, scenario),
    )


@app.get("/v1/hotspots", tags=["resilience"])
def hotspots(scenario: str = SCENARIO_Q):
    _check_scenario(scenario)
    store = get_store()
    rows = []
    for code in store.segments:
        summary = store.segment_summary(code, scenario)
        forecast = store.forecast(code, scenario)
        current = summary["stress"]
        at24, at72 = forecast["points"][23], forecast["points"][-1]
        rows.append({
            "segment_code": code, "name": summary["name"], "city": summary["city"],
            "current": current, "at_24h": at24["value"], "at_72h": at72["value"],
            "delta_72h": round(at72["value"] - current, 1),
            "emerging": current < 50 <= max(p["value"] for p in forecast["points"]),
        })
    rows.sort(key=lambda r: (r["emerging"], r["at_72h"]), reverse=True)
    return {"scenario": scenario, "hotspots": rows}


@app.get("/v1/segments/{code}/failure-chain", tags=["resilience"])
def get_failure_chain(code: str, scenario: str = SCENARIO_Q):
    _, summary, history, forecast = _decision_inputs(code, scenario)
    return decision.failure_chain(summary, history, forecast)


@app.get("/v1/segments/{code}/interventions", tags=["resilience"])
def get_interventions(
    code: str,
    scenario: str = SCENARIO_Q,
    weight_effectiveness: float | None = Query(None, ge=0, le=100),
    weight_evidence: float | None = Query(None, ge=0, le=100),
    weight_speed: float | None = Query(None, ge=0, le=100),
    weight_feasibility: float | None = Query(None, ge=0, le=100),
    weight_co_benefit: float | None = Query(None, ge=0, le=100),
    weight_one_health: float | None = Query(None, ge=0, le=100),
    weight_reversibility: float | None = Query(None, ge=0, le=100),
    weight_cost: float | None = Query(None, ge=0, le=100),
):
    _, summary, history, forecast = _decision_inputs(code, scenario)
    requested = {
        "effectiveness": weight_effectiveness, "evidence": weight_evidence,
        "speed": weight_speed, "feasibility": weight_feasibility,
        "co_benefit": weight_co_benefit, "one_health": weight_one_health,
        "reversibility": weight_reversibility, "cost": weight_cost,
    }
    weights = {key: value for key, value in requested.items() if value is not None}
    return decision.intervention_search(summary, history, forecast, weights or None)


@app.get("/v1/segments/{code}/catchment-twin", tags=["resilience"])
def get_catchment_twin(code: str, scenario: str = SCENARIO_Q):
    """Directed planning schematic; explicitly not a calibrated flow model."""
    _, summary, history, forecast = _decision_inputs(code, scenario)
    interventions = decision.intervention_search(summary, history, forecast)
    return catchment.catchment_twin(summary, forecast, interventions)


@app.get("/v1/segments/{code}/evidence-graph", tags=["resilience"])
def evidence_graph(code: str, scenario: str = SCENARIO_Q):
    store, summary, history, forecast = _decision_inputs(code, scenario)
    chain = decision.failure_chain(summary, history, forecast)
    observations = store.list_observations(code, 40)
    nodes = chain["nodes"] + [
        {"id": f"citizen-{o['id'][:8]}", "label": o.get("predicted_taxon") or "Citizen sample",
         "kind": "citizen", "evidence": o.get("state"), "confidence": o.get("quality_score"),
         "source": o["id"]}
        for o in observations[:4]
    ]
    edges = chain["edges"] + [[f"citizen-{o['id'][:8]}", "biology"] for o in observations[:4]]
    return {"segment_code": code, "nodes": nodes, "edges": edges,
            "legend": ["observed", "citizen", "inferred", "forecast", "simulated", "literature"]}


@app.get("/v1/segments/{code}/data-sufficiency", tags=["resilience"])
def data_sufficiency(code: str, scenario: str = SCENARIO_Q):
    store, summary, history, forecast = _decision_inputs(code, scenario)
    return decision.data_sufficiency(summary, history, forecast, store.list_observations(code, 200))


@app.get("/v1/segments/{code}/one-health", tags=["insight"])
def one_health_bridge(code: str, scenario: str = SCENARIO_Q):
    store, summary, history, _ = _decision_inputs(code, scenario)
    return decision.one_health_bridge(summary, history, store.list_observations(code, 200))


@app.get("/v1/segments/{code}/incident", tags=["resilience"])
def incident(code: str, scenario: str = SCENARIO_Q):
    _check_scenario(scenario)
    store = get_store()
    if code not in store.segments:
        raise HTTPException(404, f"unknown segment {code}")
    return store.incident(code, scenario)


@app.get("/v1/models/aquaforecast", tags=["meta"])
def aquaforecast_model_card():
    return decision.model_card()


@app.get("/v1/models/watforecast", tags=["meta"])
def watforecast_model_card():
    """Canonical WatSen model-card route; the legacy route remains compatible."""
    return decision.model_card()


# ── One Health brief ───────────────────────────────────────────────

@app.get("/v1/segments/{code}/brief", tags=["insight"])
def get_brief(code: str, refresh: bool = False, scenario: str = SCENARIO_Q):
    _check_scenario(scenario)
    store = get_store()
    if code not in store.segments:
        raise HTTPException(404, f"unknown segment {code}")
    cache_key = f"{code}:{scenario}"
    if not refresh and cache_key in store.briefs:
        return store.briefs[cache_key]

    out = brief_engine.generate(
        summary=store.segment_summary(code, scenario),
        history=store.history(code, hours=336, scenario=scenario),
        forecast=store.forecast(code, scenario),
        observations=store.list_observations(code, limit=200),
    )
    out["scenario"] = scenario
    store.briefs[cache_key] = out
    return out


# ── export ─────────────────────────────────────────────────────────

@app.get("/v1/segments/{code}/fhir", tags=["export"])
def get_fhir(code: str, hours: int = Query(24, ge=1, le=168), include_brief: bool = True,
             scenario: str = SCENARIO_Q):
    _check_scenario(scenario)
    store = get_store()
    if code not in store.segments:
        raise HTTPException(404, f"unknown segment {code}")
    b = store.briefs.get(f"{code}:{scenario}") if include_brief else None
    bundle = fhir.bundle_from_store(
        store.segment_summary(code, scenario),
        store.history(code, hours=max(hours, 24), scenario=scenario), b, hours=hours
    )
    return JSONResponse(bundle, media_type="application/fhir+json")


@app.get("/v1/segments/{code}/fhir/validate", tags=["export"])
def validate_fhir(code: str, hours: int = Query(6, ge=1, le=24),
                  scenario: str = SCENARIO_Q):
    _check_scenario(scenario)
    store = get_store()
    if code not in store.segments:
        raise HTTPException(404, f"unknown segment {code}")
    bundle = fhir.bundle_from_store(
        store.segment_summary(code, scenario),
        store.history(code, max(24, hours), scenario), None, hours=hours,
    )
    return fhir.validate_bundle(bundle)


@app.get("/v1/export/observations.csv", tags=["export"])
def export_csv(segment_code: str | None = None):
    import csv, io
    rows = get_store().list_observations(segment_code, limit=5000)
    buf = io.StringIO()
    cols = ["id", "segment_code", "observed_at", "lat", "lon", "predicted_taxon",
            "taxon_confidence", "bmwp_contribution", "quality_score", "state"]
    w = csv.DictWriter(buf, fieldnames=cols, extrasaction="ignore")
    w.writeheader()
    w.writerows(rows)
    from fastapi.responses import Response
    return Response(buf.getvalue(), media_type="text/csv",
                    headers={"Content-Disposition": "attachment; filename=observations.csv"})


def _check_scenario(scenario: str) -> None:
    if scenario not in SCENARIOS:
        raise HTTPException(400, f"unknown scenario {scenario!r}; one of {sorted(SCENARIOS)}")
