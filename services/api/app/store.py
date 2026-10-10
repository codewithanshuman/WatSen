"""
The data access layer.

One interface, two implementations:

  MockStore      — synthetic catchment, in memory, deterministic. No database,
                   no API keys, no network. This is what `make dev` runs and
                   what the demo falls back to.
  PostgresStore  — the real thing, against db/001_schema.sql.

Person 4 codes against the HTTP API and never needs to know which is live.
Person 2 swaps the implementation without touching a router.

`STORE_BACKEND=mock|postgres` in the environment decides.
"""
from __future__ import annotations

import math
import os
import threading
import uuid
from datetime import datetime, timedelta, timezone
from functools import lru_cache

import numpy as np

from app.core import stress as stress_mod
from app.core.anomaly import Submission, SubmissionScorer
from app.core.scenarios import apply as apply_scenario, apply_forecast
from app.core.synthetic import SEGMENTS, generate_series, SegmentProfile
from app.ml.forecaster import RidgeForecaster, build_dataset, frame_matrix, alerts_from_forecast

HISTORY_HOURS = 24 * 60

# ASPT per segment — stands in for the biology until the classifier is wired
# to real observations. Roughly tracks how urbanised each reach is.
BASE_ASPT = {
    "PT-CBR-01": 4.4, "PT-CBR-02": 5.6, "IT-BLG-01": 3.2,
    "RO-BUC-01": 4.0, "ES-VLC-01": 4.7, "NL-UTR-01": 6.4,
}
# Compatibility name used by the training script. Runtime code calls
# ``biological_index`` so accepted citizen evidence can change the score.
ASPT = BASE_ASPT

TAXA_POOL = {
    "clean": ["Perlidae", "Heptageniidae", "Ephemerellidae", "Rhyacophilidae", "Leuctridae"],
    "mid": ["Baetidae", "Hydropsychidae", "Gammaridae", "Limnephilidae", "Elminthidae"],
    "poor": ["Chironomidae", "Asellidae", "Oligochaeta", "Physidae", "Erpobdellidae"],
}


class MockStore:
    def __init__(self, seed: int = 42):
        self.rng = np.random.default_rng(seed)
        self.segments: dict[str, SegmentProfile] = {s.code: s for s in SEGMENTS}
        self.frames: dict[str, dict] = {
            s.code: generate_series(s, hours=HISTORY_HOURS) for s in SEGMENTS
        }
        self.observations: list[dict] = []
        self.audit_events: list[dict] = []
        self.evidence_lock = threading.RLock()
        self.submission_responses: dict[str, dict] = {}
        self.receipt_history: dict[str, list[dict]] = {}
        self.briefs: dict[str, dict] = {}
        self.scorer = SubmissionScorer()
        self._model: RidgeForecaster | None = None
        self._model_lock = threading.Lock()
        self._forecast_cache: dict[tuple, dict] = {}
        self._seed_observations()
        self._fit_scorer()

    # ── segments ───────────────────────────────────────────────────
    def list_segments(self) -> list[dict]:
        return [self.segment_summary(code) for code in self.segments]

    def frame(self, code: str, scenario: str = "none") -> dict:
        return apply_scenario(self.frames[code], scenario)

    def segment_summary(self, code: str, scenario: str = "none") -> dict:
        p = self.segments[code]
        frame = self.frame(code, scenario)
        current = self.current_stress(code, scenario)
        obs_30d = sum(
            1 for o in self.observations
            if o["segment_code"] == code
            and _utc(datetime.fromisoformat(o["observed_at"])) > _now() - timedelta(days=30)
        )
        bio = self.biological_index(code)
        return {
            "code": p.code,
            "name": p.name,
            "city": p.city,
            "country": p.country_iso2,
            "lat": p.lat,
            "lon": p.lon,
            "geometry": {"type": "LineString", "coordinates": p.path},
            "urban_index": round(p.urban, 2),
            "stress": current["value"],
            "band": current["band"],
            "components": current["components"],
            "aspt": bio["aspt"],
            "bmwp": bio["bmwp"],
            "biological_evidence": bio,
            "observations_30d": obs_30d,
            "updated_at": frame["t"][-1].isoformat(),
            "scenario": scenario,
        }

    def current_stress(self, code: str, scenario: str = "none") -> dict:
        frame = self.frame(code, scenario)
        vals = {
            "do_mgl": float(np.mean(frame["do_mgl"][-24:])),
            "turbidity_ntu": float(np.mean(frame["turbidity_ntu"][-24:])),
            "temp_c": float(np.mean(frame["temp_c"][-24:])),
            "nitrate_mgl": float(np.mean(frame["nitrate_mgl"][-24:])),
            "bmwp_aspt": self.biological_index(code)["aspt"],
        }
        return stress_mod.composite({k: v for k, v in vals.items() if v is not None})

    def history(self, code: str, hours: int = 336, scenario: str = "none") -> dict:
        frame = self.frame(code, scenario)
        hours = min(hours, len(frame["t"]))
        target = stress_mod.series_from_measurements(
            {k: v[-hours:] for k, v in frame.items() if k != "t"},
            aspt=self.biological_index(code)["aspt"]
        )
        return {
            "scenario": scenario,
            "t": [x.isoformat() for x in frame["t"][-hours:]],
            "stress": [None if np.isnan(v) else round(float(v), 2) for v in target],
            **{
                k: [round(float(x), 3) for x in frame[k][-hours:]]
                for k in ("do_mgl", "ph", "turbidity_ntu", "temp_c", "rain_mm", "nitrate_mgl")
            },
        }

    # ── forecasting ────────────────────────────────────────────────
    def model(self) -> RidgeForecaster:
        if self._model is None:
            with self._model_lock:
                if self._model is None:
                    frames = list(self.frames.values())
                    aspts = [BASE_ASPT.get(c) for c in self.frames]
                    X, Y, _ = build_dataset(frames, aspts, stride=24)
                    self._model = RidgeForecaster().fit(X, Y)
        return self._model

    def forecast(self, code: str, scenario: str = "none") -> dict:
        bio = self.biological_index(code)
        cache_key = (code, scenario, bio["aspt"], bio["n_observations"])
        if cache_key in self._forecast_cache:
            return self._forecast_cache[cache_key]
        frame = self.frame(code, scenario)
        mat, _ = frame_matrix(frame, aspt=bio["aspt"])
        issued = _now()
        points = apply_forecast(self.model().forecast(mat[-168:], issued), scenario)
        result = {
            "segment_code": code,
            "scenario": scenario,
            "issued_at": issued.isoformat(),
            "model_version": self.model().version,
            "model_card": "/v1/models/watforecast",
            "training_data": "synthetic-development",
            "interval_label": "split-conformal likely range",
            "biological_input": bio,
            "horizon_h": len(points),
            "points": [p.__dict__ for p in points],
            "alerts": alerts_from_forecast(points, code),
        }
        self._forecast_cache[cache_key] = result
        return result

    # ── observations ───────────────────────────────────────────────
    def _seed_observations(self) -> None:
        for code, p in self.segments.items():
            aspt = BASE_ASPT.get(code, 4.5)
            pool = TAXA_POOL["clean"] if aspt >= 5.8 else TAXA_POOL["mid"] if aspt >= 4.0 else TAXA_POOL["poor"]
            for i in range(int(self.rng.integers(14, 34))):
                age_h = int(self.rng.integers(1, 24 * 45))
                taxon = str(self.rng.choice(pool + TAXA_POOL["mid"]))
                conf = float(np.clip(self.rng.normal(0.84, 0.12), 0.2, 0.995))
                self.observations.append({
                    "id": str(uuid.uuid4()),
                    "segment_code": code,
                    "contributor": f"citizen-{int(self.rng.integers(1, 40)):03d}",
                    "observed_at": (_now() - timedelta(hours=age_h)).isoformat(),
                    "lat": p.lat + float(self.rng.normal(0, 0.0016)),
                    "lon": p.lon + float(self.rng.normal(0, 0.0016)),
                    "note": "Kick sample from the left bank.",
                    "predicted_taxon": taxon,
                    "taxon_confidence": round(conf, 3),
                    "bmwp_contribution": stress_mod.BMWP_FAMILY.get(taxon),
                    "quality_score": round(float(np.clip(self.rng.normal(0.82, 0.16), 0.05, 1.0)), 3),
                    "state": "auto_accepted",
                    "reviewed_by": None,
                    "reviewed_at": None,
                })

    def _fit_scorer(self) -> None:
        hist = [
            Submission(
                observed_at=datetime.fromisoformat(o["observed_at"]),
                taxon=o["predicted_taxon"],
                taxon_confidence=o["taxon_confidence"],
                distance_to_stream_m=float(abs(self.rng.normal(14, 10))),
                n_photos=int(self.rng.integers(1, 4)),
                note=o["note"],
                submissions_last_hour=int(self.rng.integers(1, 3)),
                contributor_trust=float(self.rng.uniform(0.35, 0.95)),
            )
            for o in self.observations
        ]
        self.scorer.fit(hist)

    def list_observations(self, code: str | None = None, limit: int = 100) -> list[dict]:
        rows = [o for o in self.observations if code is None or o["segment_code"] == code]
        rows.sort(key=lambda o: o["observed_at"], reverse=True)
        return rows[:limit]

    def add_observation(self, payload: dict, scored: dict) -> dict:
        taxon = payload.get("predicted_taxon")
        row = {
            "id": str(uuid.uuid4()),
            "segment_code": payload.get("segment_code"),
            "contributor": payload.get("contributor", "anonymous"),
            "observed_at": payload["observed_at"],
            "lat": payload["lat"],
            "lon": payload["lon"],
            "note": payload.get("note", ""),
            "predicted_taxon": taxon,
            "taxon_confidence": payload.get("taxon_confidence"),
            "bmwp_contribution": stress_mod.BMWP_FAMILY.get(taxon) if taxon else None,
            "quality_score": scored["quality_score"],
            "state": scored["state"],
            "explanation": scored["explanation"],
            "anomaly_reasons": [r["code"] for r in scored["reasons"]],
            "reviewed_by": None,
            "reviewed_at": None,
            "model": payload.get("model"),
            "image_quality": payload.get("image_quality"),
            "client_submission_id": payload.get("client_submission_id"),
        }
        self.observations.append(row)
        self.briefs.clear()
        self._forecast_cache.clear()
        self._audit(row["segment_code"], "citizen_observation", {
            "observation_id": row["id"], "state": row["state"],
            "taxon": row["predicted_taxon"], "quality": row["quality_score"],
        })
        return row

    def observation(self, observation_id: str) -> dict | None:
        return next((o for o in self.observations if o["id"] == observation_id), None)

    def review_observation(self, observation_id: str, action: str,
                           reviewer: str, corrected_taxon: str | None = None,
                           reviewer_note: str = "") -> dict:
        row = self.observation(observation_id)
        if row is None:
            raise KeyError(observation_id)
        before = {key: row.get(key) for key in ("state", "predicted_taxon")}
        if action == "confirm" and row.get("predicted_taxon") not in stress_mod.BMWP_FAMILY:
            raise ValueError("Choose a scoring family with the correct action before confirming")
        if action == "confirm":
            row["state"] = "expert_confirmed"
        elif action == "correct":
            if not corrected_taxon or corrected_taxon not in stress_mod.BMWP_FAMILY:
                raise ValueError("corrected_taxon must be a scoring BMWP family")
            row["predicted_taxon"] = corrected_taxon
            row["bmwp_contribution"] = stress_mod.BMWP_FAMILY[corrected_taxon]
            row["state"] = "expert_confirmed"
        elif action == "reject":
            row["state"] = "rejected"
        else:
            raise ValueError("action must be confirm, correct or reject")
        row["reviewed_by"] = reviewer
        row["reviewed_at"] = _now().isoformat()
        row["reviewer_note"] = reviewer_note
        self.briefs.clear()
        self._forecast_cache.clear()
        self._audit(row["segment_code"], "expert_review", {
            "observation_id": row["id"], "action": action,
            "taxon": row.get("predicted_taxon"), "reviewer": reviewer,
            "reviewer_note": reviewer_note, "before": before,
            "after": {key: row.get(key) for key in ("state", "predicted_taxon")},
        })
        return row

    def review_queue(self) -> dict:
        rows = sorted(
            [o for o in self.observations if o["state"] in {"needs_review", "auto_accepted"}],
            key=lambda o: (o["state"] != "needs_review", o["observed_at"]),
            reverse=False,
        )
        return {
            "summary": {
                "high_confidence": sum(o["state"] == "auto_accepted" for o in rows),
                "needs_expert_review": sum(o["state"] == "needs_review" for o in rows),
                "rejected_automatically": sum(o["state"] == "rejected" for o in self.observations),
            },
            "observations": rows[:100],
        }

    def biological_index(self, code: str, days: int = 30) -> dict:
        now = datetime.now(timezone.utc)
        cutoff = now - timedelta(days=days)
        accepted = [
            o for o in self.observations
            if o["segment_code"] == code
            and o.get("state") in {"auto_accepted", "expert_confirmed"}
            and (o.get("quality_score") or 0) >= .7
            and _utc(datetime.fromisoformat(o["observed_at"])) >= cutoff
            and _utc(datetime.fromisoformat(o["observed_at"])) <= now
            and o.get("predicted_taxon") in stress_mod.BMWP_FAMILY
        ]
        taxa = sorted({o["predicted_taxon"] for o in accepted})
        result = stress_mod.bmwp_from_taxa(taxa)
        # Sparse observations are blended with the baseline prior. Once at
        # least five scoring families exist, the biological evidence stands on
        # its own. This keeps one photograph from swinging an ecosystem score.
        evidence_weight = min(1.0, result["n_taxa"] / 5)
        prior = BASE_ASPT.get(code)
        if result["aspt"] is None:
            aspt = prior
            source = "baseline-prior"
        elif prior is not None and evidence_weight < 1:
            aspt = round(prior * (1 - evidence_weight) + result["aspt"] * evidence_weight, 2)
            source = "citizen-evidence-blended"
        else:
            aspt = result["aspt"]
            source = "citizen-evidence"
        return {
            **result, "aspt": aspt, "source": source, "window_days": days,
            "n_observations": len(accepted), "families": taxa,
            "confidence": round(.35 + .6 * evidence_weight, 2),
        }

    def distance_to_stream_m(self, code: str, lat: float, lon: float) -> float:
        path = self.segments[code].path
        return round(min(
            _point_segment_m(lat, lon, path[i][1], path[i][0], path[i + 1][1], path[i + 1][0])
            for i in range(len(path) - 1)
        ), 1)

    def submissions_last_hour(self, contributor: str) -> int:
        cutoff = _now() - timedelta(hours=1)
        return 1 + sum(
            o.get("contributor") == contributor
            and _utc(datetime.fromisoformat(o["observed_at"])) >= cutoff
            for o in self.observations
        )

    def contributor_trust(self, handle: str) -> dict:
        mine = [o for o in self.observations if o.get("contributor") == handle]
        if not mine:
            return {"score": .5, "location_validity": .5, "historical_confirmations": .5,
                    "expert_agreement": .5, "duplicate_rejection_rate": 1.0,
                    "observation_completeness": .5}
        quality = np.mean([o.get("quality_score") or 0 for o in mine])
        confirmed = sum(o.get("state") == "expert_confirmed" for o in mine)
        rejected = sum(o.get("state") == "rejected" for o in mine)
        complete = np.mean([bool(o.get("predicted_taxon")) and bool(o.get("note")) for o in mine])
        parts = {
            "location_validity": round(float(np.mean(["far_from_water" not in o.get("anomaly_reasons", []) for o in mine])), 3),
            "historical_confirmations": round((confirmed + 1) / (len(mine) + 2), 3),
            "expert_agreement": round((confirmed + 1) / (sum(o.get("reviewed_at") is not None for o in mine) + 2), 3),
            "duplicate_rejection_rate": round(1 - rejected / len(mine), 3),
            "observation_completeness": round(float(complete), 3),
        }
        parts["score"] = round(float(.35 * quality + .65 * np.mean(list(parts.values()))), 3)
        return parts

    def nearest_sensor_readings(self, code: str, observed_at: datetime,
                                variables: list[str]) -> dict[str, float]:
        frame = self.frames[code]
        target = _utc(observed_at)
        idx = min(range(len(frame["t"])), key=lambda i: abs((_utc(frame["t"][i]) - target).total_seconds()))
        if abs((_utc(frame["t"][idx]) - target).total_seconds()) > 3 * 3600:
            return {}
        return {k: float(frame[k][idx]) for k in variables if k in frame}

    def incident(self, code: str, scenario: str = "none") -> dict:
        frame = self.frame(code, scenario)
        end = _utc(frame["t"][-1])
        events = [
            {"at": (end - timedelta(hours=7)).isoformat(), "type": "observed", "title": "Rainfall increase detected"},
            {"at": (end - timedelta(hours=5)).isoformat(), "type": "observed", "title": "Turbidity anomaly crossed watch threshold"},
        ]
        recent = self.list_observations(code, 3)
        for row in reversed(recent):
            events.append({"at": row["observed_at"], "type": "citizen", "title": f"Citizen evidence: {row.get('predicted_taxon') or 'stream observation'}", "observation_id": row["id"]})
        events.extend([
            {"at": (end - timedelta(hours=1)).isoformat(), "type": "forecast", "title": "72-hour forecast issued"},
            {"at": end.isoformat(), "type": "decision", "title": "Intervention simulations available"},
        ])
        events.sort(key=lambda e: e["at"])
        return {"id": f"AQ-{end.year}-{code.replace('-', '')}", "segment_code": code,
                "scenario": scenario, "events": events}

    def _audit(self, code: str, event_type: str, details: dict) -> None:
        self.audit_events.append({"at": _now().isoformat(), "segment_code": code,
                                  "type": event_type, "details": details})

    def contributor_record(self, handle: str) -> dict:
        mine = [o for o in self.observations if o.get("contributor") == handle]
        if not mine:
            return {"contributor": handle, "n_observations": 0, "segments": [],
                    "mean_quality": None, "taxa": [], "observations": []}
        q = [o["quality_score"] for o in mine if o.get("quality_score") is not None]
        taxa = sorted({o["predicted_taxon"] for o in mine if o.get("predicted_taxon")})
        segs = sorted({o["segment_code"] for o in mine})
        return {
            "contributor": handle,
            "n_observations": len(mine),
            "mean_quality": round(float(np.mean(q)), 3) if q else None,
            "segments": segs,
            "taxa": taxa,
            "bmwp_contributed": sum(o["bmwp_contribution"] or 0 for o in mine),
            "observations": sorted(mine, key=lambda o: o["observed_at"], reverse=True)[:20],
            "trust": self.contributor_trust(handle),
        }


def _now() -> datetime:
    return datetime.now(timezone.utc).replace(microsecond=0)


def _utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def _haversine_m(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    radius = 6_371_000.0
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp = math.radians(lat2 - lat1)
    dl = math.radians(lon2 - lon1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return radius * 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))


def _point_segment_m(lat: float, lon: float, lat1: float, lon1: float,
                     lat2: float, lon2: float) -> float:
    """Point-to-segment distance using a local equirectangular projection."""
    scale_x = 111_320 * math.cos(math.radians(lat))
    scale_y = 110_540
    px, py = (lon - lon1) * scale_x, (lat - lat1) * scale_y
    bx, by = (lon2 - lon1) * scale_x, (lat2 - lat1) * scale_y
    denom = bx * bx + by * by
    t = 0.0 if denom == 0 else max(0.0, min(1.0, (px * bx + py * by) / denom))
    return math.hypot(px - t * bx, py - t * by)


@lru_cache(maxsize=1)
def get_store() -> MockStore:
    backend = os.getenv("STORE_BACKEND", "mock").lower()
    if backend != "mock":
        raise RuntimeError(
            f"STORE_BACKEND={backend!r} is not available in this build. "
            "Use mock rather than reporting a database backend that is not active."
        )
    return MockStore(seed=int(os.getenv("DEMO_SEED", "42")))
