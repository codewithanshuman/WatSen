"""FHIR R4 export aligned with the draft OneAquaHealth implementation guide.

The guide is a continuously built draft, so the canonical profile URLs are
declared explicitly and validation distinguishes local structural preflight
from validation by the official Java validator.
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone

BASE = "https://watsen.example/fhir"
OAH = "http://hl7.eu/fhir/ig/oah/StructureDefinition"
OAH_LOCATION = f"{OAH}/location-oah"
OAH_OBSERVATION = f"{OAH}/observation-with-component-oah"
OAH_SPECIMEN = f"{OAH}/specimen-oah"
LOCAL_CS = f"{BASE}/CodeSystem/stream-observation"

LOCAL_CODES = {
    "do_mgl": ("dissolved-oxygen", "Dissolved oxygen", "mg/L", "mg/L"),
    "ph": ("ph", "pH", "pH", "[pH]"),
    "turbidity_ntu": ("turbidity", "Turbidity", "NTU", "[NTU]"),
    "temp_c": ("water-temperature", "Water temperature", "°C", "Cel"),
    "nitrate_mgl": ("nitrate", "Nitrate as N", "mg/L", "mg/L"),
    "rain_mm": ("rainfall", "Rainfall depth", "mm", "mm"),
    "stress_index": ("stress-index", "WatSen composite stress index", "1", "1"),
    "bmwp_aspt": ("aspt", "Average Score Per Taxon (BMWP)", "1", "1"),
}


def _now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def _uuid() -> str:
    return f"urn:uuid:{uuid.uuid4()}"


def _profiled_meta(profile: str, scenario: str = "none") -> dict:
    return {
        "profile": [profile], "source": f"{BASE}/WatSen",
        "tag": [{
            "system": f"{BASE}/CodeSystem/evidence-kind",
            "code": "observed" if scenario == "none" else "simulated",
            "display": "Observed evidence" if scenario == "none" else f"Simulated {scenario} scenario",
        }],
    }


def location_resource(segment: dict, ref: str) -> dict:
    scenario = segment.get("scenario", "none")
    return {
        "fullUrl": ref,
        "resource": {
            "resourceType": "Location", "id": ref.split(":")[-1],
            "meta": _profiled_meta(OAH_LOCATION, scenario),
            "identifier": [{"system": f"{BASE}/segment", "value": segment["code"]}],
            "status": "active", "name": segment["name"],
            "description": f"Monitored stream reach in {segment['city']}",
            "mode": "instance",
            "physicalType": {"coding": [{
                "system": "http://terminology.hl7.org/CodeSystem/location-physical-type",
                "code": "area", "display": "Area",
            }]},
            "position": {"latitude": segment["lat"], "longitude": segment["lon"]},
            "address": {"city": segment["city"], "country": segment.get("country")},
        },
        "request": {"method": "POST", "url": "Location"},
    }


def specimen_resource(segment: dict, location_ref: str, ref: str) -> dict:
    bio = segment.get("biological_evidence") or {}
    return {
        "fullUrl": ref,
        "resource": {
            "resourceType": "Specimen", "id": ref.split(":")[-1],
            "meta": _profiled_meta(OAH_SPECIMEN, segment.get("scenario", "none")),
            "identifier": [{"system": f"{BASE}/biological-window", "value": f"{segment['code']}-30d"}],
            "status": "available",
            "type": {"coding": [{"system": LOCAL_CS, "code": "macroinvertebrate-kick-sample",
                                  "display": "Macroinvertebrate sampling window"}]},
            "subject": {"reference": location_ref},
            "collection": {"collectedDateTime": segment["updated_at"],
                           "method": {"text": "Citizen and expert-reviewed macroinvertebrate observations"}},
            "note": [{"text": f"{bio.get('n_observations', 0)} accepted observations; "
                                f"families: {', '.join(bio.get('families', [])) or 'none'}"}],
        },
        "request": {"method": "POST", "url": "Specimen"},
    }


def component_observation(values: dict[str, float], effective: str, location_ref: str,
                          ref: str, scenario: str = "none", specimen_ref: str | None = None) -> dict:
    components = []
    for variable, value in values.items():
        code, display, unit, ucum = LOCAL_CODES.get(variable, (variable, variable, "1", "1"))
        components.append({
            "code": {"coding": [{"system": LOCAL_CS, "code": code, "display": display}], "text": display},
            "valueQuantity": {"value": round(float(value), 3), "unit": unit,
                              "system": "http://unitsofmeasure.org", "code": ucum},
        })
    resource = {
        "resourceType": "Observation", "id": ref.split(":")[-1],
        "meta": _profiled_meta(OAH_OBSERVATION, scenario),
        "status": "final",
        "category": [{"coding": [{
            "system": "http://terminology.hl7.org/CodeSystem/observation-category",
            "code": "survey", "display": "Survey",
        }]}],
        "code": {"coding": [{"system": LOCAL_CS, "code": "stream-indicator-panel",
                              "display": "WatSen stream indicator panel"}]},
        "subject": {"reference": location_ref},
        "effectiveDateTime": effective, "issued": _now(), "component": components,
        "note": [{"text": "Scenario-transformed simulated values; not measurements."}] if scenario != "none" else [{"text": "Observed or derived monitoring values."}],
    }
    if specimen_ref:
        resource["specimen"] = {"reference": specimen_ref}
    return {"fullUrl": ref, "resource": resource,
            "request": {"method": "POST", "url": "Observation"}}


def risk_assessment_resource(brief: dict, location_ref: str, ref: str,
                             scenario: str = "none") -> dict:
    risk = brief.get("risk_level", "low")
    resource = {
        "resourceType": "RiskAssessment", "id": ref.split(":")[-1],
        "meta": _profiled_meta(f"{BASE}/StructureDefinition/one-health-risk", scenario),
        "status": "final", "subject": {"reference": location_ref},
        "occurrenceDateTime": brief.get("generated_at", _now()),
        "method": {"coding": [{"system": LOCAL_CS, "code": "one-health-brief",
                                "display": "WatSen One Health brief"}]},
        "prediction": [{
            "outcome": {"text": brief.get("headline", "")},
            "qualitativeRisk": {"coding": [{"system": f"{BASE}/CodeSystem/risk-level",
                                              "code": risk, "display": risk.title()}]},
            "whenPeriod": {"start": brief.get("period_start"), "end": brief.get("period_end")},
        }],
        "note": [{"text": _brief_text(brief)}],
    }
    return {"fullUrl": ref, "resource": resource,
            "request": {"method": "POST", "url": "RiskAssessment"}}


def provenance_resource(targets: list[str], scenario: str, ref: str) -> dict:
    observed = scenario == "none"
    return {
        "fullUrl": ref,
        "resource": {
            "resourceType": "Provenance", "id": ref.split(":")[-1],
            "recorded": _now(), "target": [{"reference": t} for t in targets],
            "activity": {"coding": [{"system": LOCAL_CS,
                                      "code": "sensor-harmonisation" if observed else "scenario-simulation",
                                      "display": "Sensor harmonisation" if observed else "Labelled scenario simulation"}]},
            "agent": [{"type": {"text": "assembler"}, "who": {"display": "WatSen"}}],
            "entity": [{"role": "source", "what": {"display": "Synthetic development dataset"}}],
        },
        "request": {"method": "POST", "url": "Provenance"},
    }


def _brief_text(brief: dict) -> str:
    parts = [brief.get(k, "") for k in ("ecosystem", "animal", "human", "what_changes")]
    body = "\n\n".join(p for p in parts if p)
    cites = brief.get("citations") or []
    return body + (f"\n\nEvidence: {', '.join(cites)}" if cites else "")


def bundle_from_store(summary: dict, history: dict, brief: dict | None = None,
                      hours: int = 24) -> dict:
    scenario = summary.get("scenario", "none")
    loc_ref = _uuid()
    entries = [location_resource(summary, loc_ref)]
    specimen_ref = None
    if (summary.get("biological_evidence") or {}).get("n_observations", 0):
        specimen_ref = _uuid()
        entries.append(specimen_resource(summary, loc_ref, specimen_ref))

    ts = history["t"][-hours:]
    observation_refs = []
    variables = ("do_mgl", "ph", "turbidity_ntu", "temp_c", "nitrate_mgl", "rain_mm")
    for offset, effective in enumerate(ts):
        values = {var: history[var][-hours + offset] for var in variables if var in history}
        ref = _uuid()
        observation_refs.append(ref)
        entries.append(component_observation(values, effective, loc_ref, ref, scenario))

    derived = {}
    if summary.get("stress") is not None:
        derived["stress_index"] = summary["stress"]
    if summary.get("aspt") is not None:
        derived["bmwp_aspt"] = summary["aspt"]
    if derived:
        ref = _uuid()
        observation_refs.append(ref)
        entries.append(component_observation(derived, ts[-1], loc_ref, ref, scenario, specimen_ref))
    if brief:
        entries.append(risk_assessment_resource(brief, loc_ref, _uuid(), scenario))
    entries.append(provenance_resource([loc_ref, *observation_refs], scenario, _uuid()))
    return {
        "resourceType": "Bundle", "id": str(uuid.uuid4()),
        "meta": {"lastUpdated": _now(), "source": f"{BASE}/WatSen",
                 "tag": [{"system": f"{BASE}/CodeSystem/conformance",
                          "code": "oah-draft-0.1.0", "display": "OAH draft CI build"}]},
        "type": "transaction", "timestamp": _now(), "entry": entries,
    }


def validate_bundle(bundle: dict) -> dict:
    errors, warnings = [], []
    if bundle.get("resourceType") != "Bundle" or bundle.get("type") != "transaction":
        errors.append("Resource must be a FHIR transaction Bundle.")
    entries = bundle.get("entry") or []
    refs = {e.get("fullUrl") for e in entries}
    kinds = {e.get("resource", {}).get("resourceType") for e in entries}
    for i, entry in enumerate(entries):
        resource = entry.get("resource") or {}
        if not entry.get("request"):
            errors.append(f"entry[{i}] has no transaction request")
        if resource.get("resourceType") in {"Location", "Observation", "Specimen"}:
            if not resource.get("meta", {}).get("profile"):
                errors.append(f"entry[{i}] has no declared profile")
        if resource.get("resourceType") == "Observation":
            if resource.get("status") != "final" or not resource.get("subject"):
                errors.append(f"entry[{i}] violates required Observation fields")
            if not resource.get("component"):
                errors.append(f"entry[{i}] has no indicator components")
            if resource.get("subject", {}).get("reference") not in refs:
                errors.append(f"entry[{i}] subject reference does not resolve")
    required = {"Location", "Observation", "Provenance"}
    if missing := required - kinds:
        errors.append(f"missing resource types: {sorted(missing)}")
    warnings.append("Local structural preflight only; run the HL7 validator CLI with the current OAH IG package for authoritative profile validation.")
    return {
        "status": "pass" if not errors else "fail",
        "validator": "WatSen local FHIR R4/OAH preflight",
        "profile_version": "OneAquaHealth 0.1.0-ci-build (draft)",
        "errors": errors, "warnings": warnings,
        "counts": {kind: sum(e.get("resource", {}).get("resourceType") == kind for e in entries)
                   for kind in sorted(k for k in kinds if k)},
        "authoritative_validation": False,
    }
