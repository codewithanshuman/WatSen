"""Atomic evidence transitions within the current demonstration store.

The lock and replay journal are process-local. A database transaction with a
unique client_submission_id is required for multi-instance production use.
"""
from copy import deepcopy
from datetime import datetime, timedelta, timezone
import hashlib
import json
import uuid

from fastapi import HTTPException
from app.core.stress import BMWP_FAMILY


STORAGE_BOUNDARY = "Demonstration server: receipts and replay keys last for this server process. Download or retain device receipts; cross-instance persistence is not configured."


def fingerprint(payload):
    try:
        canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"), allow_nan=False)
    except (ValueError, TypeError) as exc:
        raise HTTPException(422, "Observation values must be valid JSON with finite numbers.") from exc
    return hashlib.sha256(canonical.encode()).hexdigest()


def replay(store, payload):
    key = payload.get("client_submission_id")
    entry = store.submission_responses.get(key) if key else None
    if entry is None:
        return None
    if entry["fingerprint"] != fingerprint(payload):
        raise HTTPException(409, "This capture ID already belongs to a different submission. Keep its original payload or create a new capture.")
    return {**deepcopy(entry["response"]), "replayed": True}


def record_submission(store, payload, response):
    response["replayed"] = False
    response["storage_boundary"] = STORAGE_BOUNDARY
    if payload.get("client_submission_id"):
        store.submission_responses[payload["client_submission_id"]] = {
            "fingerprint": fingerprint(payload), "response": deepcopy(response),
        }
    return response


def require_model_review(payload, scored):
    model = payload.get("model")
    quality = payload.get("image_quality") or {}
    reasons = []
    if model and (model.startswith("demo-") or (payload.get("taxon_confidence") or 0) < .82):
        reasons.append("The image suggestion needs expert identification before it can enter the biological index.")
    if model and (not isinstance(quality.get("score"), (int, float)) or quality["score"] < .72):
        reasons.append("Image quality needs expert review.")
    if payload.get("predicted_taxon") not in BMWP_FAMILY:
        reasons.append("A scoring macroinvertebrate family has not been identified.")
    if reasons:
        scored = deepcopy(scored)
        if scored["state"] == "auto_accepted":
            scored["state"] = "needs_review"
        scored["reasons"].append({"code": "expert_identification_required", "penalty": 0, "message": " ".join(reasons)})
        scored["explanation"] = " ".join(reasons) + " " + ("The record is held for review." if scored["state"] == "needs_review" else "The record remains rejected by quality checks.")
    return scored


def impact_receipt(store, row, before_bio, after_bio, before_stress, after_stress,
                   event="submission", previous=None, reviewer_note=""):
    now = datetime.now(timezone.utc)
    accepted = row["state"] in {"auto_accepted", "expert_confirmed"}
    observed = datetime.fromisoformat(row["observed_at"])
    if observed.tzinfo is None:
        observed = observed.replace(tzinfo=timezone.utc)
    reasons = []
    if not accepted:
        reasons.append("Awaiting expert review" if row["state"] == "needs_review" else "Rejected by validation or review")
    if observed < now - timedelta(days=30):
        reasons.append("Outside the 30-day evidence window")
    if observed > now:
        reasons.append("Observation time is in the future")
    if (row.get("quality_score") or 0) < .7:
        reasons.append("Evidence quality below the 0.70 index threshold")
    if row.get("predicted_taxon") not in BMWP_FAMILY:
        reasons.append("No scoring family identified")
    changed = any(before_bio.get(k) != after_bio.get(k) for k in ("aspt", "bmwp", "n_observations"))
    if row["state"] == "rejected":
        status = "reverted" if changed else "not_applied"
        message = "Previous evidence was removed and the biological window was recomputed." if changed else "The record is excluded from the biological index."
    elif row["state"] == "needs_review":
        status, message = "pending_review", "Awaiting expert identification. The biological index is unchanged."
    elif reasons:
        status, message = "accepted_no_index_change", "Review saved; this record is excluded from the current index: " + "; ".join(reasons) + "."
    else:
        status = "applied" if changed else "accepted_no_index_change"
        message = "Accepted evidence updated the biological window." if changed else "Review recorded. The biological window was already up to date."
        if before_bio.get("aspt") == after_bio.get("aspt") and before_bio.get("bmwp") == after_bio.get("bmwp"):
            message += " No ASPT/BMWP change; scoring families are deduplicated."
    changes = {}
    for label, key in (("aspt", "aspt"), ("bmwp", "bmwp"), ("accepted_observations", "n_observations")):
        before, after = before_bio.get(key), after_bio.get(key)
        changes[label] = {"before": before, "after": after, "delta": round(after - before, 2) if before is not None and after is not None else None}
    changes["stress"] = {"before": before_stress, "after": after_stress, "delta": round(after_stress - before_stress, 2)}
    receipt = {
        "receipt_id": f"impact-{uuid.uuid4()}", "observation_id": row["id"],
        "client_submission_id": row.get("client_submission_id"),
        "created_at": now.isoformat(), "event": event,
        "segment_code": row["segment_code"], "segment_name": store.segments[row["segment_code"]].name,
        "scenario": "none", "window_days": 30, "included_in_index": not reasons,
        "eligibility_reasons": reasons, "status": status, "message": message, "accepted": accepted,
        "changes": changes, "reviewer": row.get("reviewed_by"), "reviewer_note": reviewer_note,
        "transition": {"before": previous, "after": {k: row.get(k) for k in ("state", "predicted_taxon")}},
        "trace": [event, "server_quality_checks", row["state"], "biological_window_recomputed"],
        "boundary": "Baseline stress, 30-day evidence window. A deterministic evidence update, not causal ecological impact.",
        "storage_boundary": STORAGE_BOUNDARY,
    }
    store.receipt_history.setdefault(row["id"], []).append(deepcopy(receipt))
    return receipt
