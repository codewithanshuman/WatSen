"""
Submission quality scoring.

Two layers, deliberately:

  1. Deterministic rules that produce a *reason* a person can read. These catch
     the majority of bad submissions and are the only thing shown to the
     contributor. Never show a raw anomaly score to a citizen — it reads as an
     accusation and it is what kills participation.

  2. Isolation Forest over the numeric feature vector for the residual weird
     cases no rule anticipated. Unsupervised, so it needs no labels — which
     matters because we will not have labelled spam during the hackathon.

Output is a quality score in 0..1 plus a list of reason codes. The router maps
`state` from the score: >=0.75 auto_accepted, >=0.4 needs_review, else rejected.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

import numpy as np
from sklearn.ensemble import IsolationForest

# reason code -> message shown to the contributor
MESSAGES = {
    "low_taxon_confidence": "The model could not identify what is in the photo with confidence. A closer, better-lit shot usually fixes this.",
    "out_of_range_season": "This taxon is uncommon here in {month}. Worth double-checking the location and date.",
    "far_from_water": "The location is about {distance_m:.0f} m from the nearest mapped stream. If that is right, ignore this.",
    "duplicate_burst": "Several near-identical submissions arrived from this account within a few minutes.",
    "future_timestamp": "The recorded time is in the future, so the device clock may be wrong.",
    "stale_timestamp": "This observation is more than {age_days:.0f} days old. It still counts, but it will not feed today's index.",
    "impossible_reading": "A manual reading is outside the physically possible range for {variable}.",
    "contradicts_sensor": "The reported condition disagrees with the sensor reading from the same hour.",
    "statistical_outlier": "This submission is unusual compared with others from this stream. Flagged for a human to look at.",
}

PLAUSIBLE_RANGE = {
    "do_mgl": (0.0, 20.0),
    "ph": (3.0, 11.0),
    "turbidity_ntu": (0.0, 2000.0),
    "temp_c": (-2.0, 42.0),
    "nitrate_mgl": (0.0, 100.0),
}

# Coarse seasonality: month indices (1-12) in which a family is commonly
# recorded as an identifiable adult/late instar in temperate Europe.
TAXON_SEASON = {
    "Perlidae": {3, 4, 5, 6, 7},
    "Ephemeridae": {4, 5, 6, 7, 8},
    "Heptageniidae": {3, 4, 5, 6, 7, 8, 9},
    "Baetidae": set(range(1, 13)),
    "Chironomidae": set(range(1, 13)),
    "Gammaridae": set(range(1, 13)),
    "Asellidae": set(range(1, 13)),
    "Hydropsychidae": {4, 5, 6, 7, 8, 9, 10},
    "Limnephilidae": {6, 7, 8, 9, 10, 11},
    "Simuliidae": {2, 3, 4, 5, 6, 7, 8, 9},
}

FEATURES = [
    "taxon_confidence", "distance_m", "hour", "n_photos",
    "note_len", "submissions_1h", "contributor_trust",
]


@dataclass
class Submission:
    observed_at: datetime
    taxon: str | None = None
    taxon_confidence: float = 0.0
    distance_to_stream_m: float = 0.0
    n_photos: int = 1
    note: str = ""
    readings: dict[str, float] | None = None
    sensor_readings: dict[str, float] | None = None
    submissions_last_hour: int = 1
    contributor_trust: float = 0.5

    def vector(self) -> np.ndarray:
        return np.array([
            self.taxon_confidence,
            self.distance_to_stream_m,
            float(self.observed_at.hour),
            float(self.n_photos),
            float(len(self.note or "")),
            float(self.submissions_last_hour),
            self.contributor_trust,
        ], dtype=float)


def rule_check(sub: Submission, now: datetime | None = None) -> list[dict]:
    now = now or datetime.now(timezone.utc)
    obs = sub.observed_at
    if obs.tzinfo is None:
        obs = obs.replace(tzinfo=timezone.utc)
    hits: list[dict] = []

    def add(code: str, penalty: float, **fmt):
        hits.append({
            "code": code,
            "penalty": penalty,
            "message": MESSAGES[code].format(**fmt) if fmt else MESSAGES[code],
        })

    if obs > now + timedelta(hours=2):
        add("future_timestamp", 0.35)
    age_days = (now - obs).total_seconds() / 86400
    if age_days > 30:
        add("stale_timestamp", 0.10, age_days=age_days)

    if sub.taxon and sub.taxon_confidence < 0.55:
        add("low_taxon_confidence", 0.30)

    if sub.taxon in TAXON_SEASON and obs.month not in TAXON_SEASON[sub.taxon]:
        add("out_of_range_season", 0.25, month=obs.strftime("%B"))

    if sub.distance_to_stream_m > 120:
        add("far_from_water", 0.30, distance_m=sub.distance_to_stream_m)

    if sub.submissions_last_hour >= 8:
        add("duplicate_burst", 0.40)

    for var, val in (sub.readings or {}).items():
        lo, hi = PLAUSIBLE_RANGE.get(var, (-np.inf, np.inf))
        if not (lo <= val <= hi):
            add("impossible_reading", 0.45, variable=var)
            break

    sensors = sub.sensor_readings or {}
    for var, val in (sub.readings or {}).items():
        ref = sensors.get(var)
        if ref is None:
            continue
        spread = {"do_mgl": 3.0, "ph": 1.2, "temp_c": 4.0, "turbidity_ntu": 60.0}.get(var, 1e9)
        if abs(val - ref) > spread:
            add("contradicts_sensor", 0.25)
            break

    return hits


class SubmissionScorer:
    """Rules plus an Isolation Forest fitted on accepted history."""

    def __init__(self, contamination: float = 0.06, random_state: int = 7):
        self.forest = IsolationForest(
            n_estimators=200, contamination=contamination,
            random_state=random_state, n_jobs=1,
        )
        self.fitted = False
        self._mu = None
        self._sd = None

    def fit(self, history: list[Submission]) -> "SubmissionScorer":
        if len(history) < 30:
            return self                       # not enough signal; rules only
        x = np.vstack([s.vector() for s in history])
        self._mu = x.mean(axis=0)
        self._sd = x.std(axis=0)
        self._sd[self._sd == 0] = 1.0
        self.forest.fit((x - self._mu) / self._sd)
        self.fitted = True
        return self

    def score(self, sub: Submission, now: datetime | None = None) -> dict:
        hits = rule_check(sub, now=now)
        quality = 1.0
        for h in hits:
            quality *= (1.0 - h["penalty"])

        forest_score = None
        if self.fitted:
            z = (sub.vector() - self._mu) / self._sd
            # decision_function: positive is normal, negative is outlier
            forest_score = float(self.forest.decision_function(z.reshape(1, -1))[0])
            if forest_score < 0:
                penalty = min(0.35, abs(forest_score) * 1.4)
                quality *= (1.0 - penalty)
                hits.append({
                    "code": "statistical_outlier",
                    "penalty": round(penalty, 3),
                    "message": MESSAGES["statistical_outlier"],
                })

        quality = float(np.clip(quality, 0.0, 1.0))
        return {
            "quality_score": round(quality, 3),
            "state": state_for(quality),
            "reasons": hits,
            "forest_score": forest_score,
            "explanation": compose_explanation(hits, quality),
        }


def state_for(quality: float) -> str:
    if quality >= 0.75:
        return "auto_accepted"
    if quality >= 0.40:
        return "needs_review"
    return "rejected"


def compose_explanation(hits: list[dict], quality: float) -> str:
    if not hits:
        return "Thanks — this one checked out and is already on the map."
    lead = (
        "Thanks for this. One thing worth a look:"
        if quality >= 0.4
        else "Thanks for this. We have held it back for a human to check:"
    )
    body = " ".join(h["message"] for h in hits[:3])
    return f"{lead} {body}"
