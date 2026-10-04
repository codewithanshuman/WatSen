"""
The One Health brief.

This is the feature nobody else will have, so it is also the feature most
likely to be called a "wrapper around an LLM". The defence is architectural,
not rhetorical:

  1. Evidence is assembled by code, from the database. The model never queries
     anything and never sees a record we did not select.
  2. Every retrieved fact carries an id. The model is required to cite ids.
  3. The output is validated: any claim citing an id that is not in the
     evidence set fails the check and the brief is regenerated once, then
     falls back to the deterministic template.
  4. If no API key is configured, the template path produces a real brief
     anyway. The demo cannot die because a key expired at 3am.

That fourth point is the one that saves you on submission day.
"""
from __future__ import annotations

import json
import os
import re
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

from app.insight.kb import retrieve, KB

MODEL = os.getenv("BRIEF_MODEL", "claude-sonnet-4-6")
RISK_ORDER = {"low": 0, "moderate": 1, "high": 2}


@dataclass
class Evidence:
    id: str
    kind: str          # measurement | index | forecast | observation | literature
    text: str
    value: float | None = None
    source: str | None = None
    source_url: str | None = None

    def as_line(self) -> str:
        return f"[{self.id}] ({self.kind}) {self.text}"


def assemble_evidence(summary: dict, history: dict, forecast: dict,
                      observations: list[dict]) -> list[Evidence]:
    """Pull the week's facts out of the store. Pure code — no model involved."""
    ev: list[Evidence] = []
    c = summary.get("components", {})

    ev.append(Evidence("IDX-1", "index",
                       f"Current stress index for {summary['name']} ({summary['city']}) is "
                       f"{summary['stress']} out of 100, band '{summary['band']}'.",
                       summary["stress"]))

    recent = {k: history[k][-168:] for k in ("do_mgl", "turbidity_ntu", "temp_c", "rain_mm", "nitrate_mgl")}
    do_min = min(recent["do_mgl"])
    ev.append(Evidence("MEAS-DO", "measurement",
                       f"Dissolved oxygen over the past 7 days ranged "
                       f"{do_min:.1f}-{max(recent['do_mgl']):.1f} mg/L "
                       f"(mean {sum(recent['do_mgl'])/len(recent['do_mgl']):.1f}).", do_min))
    ev.append(Evidence("MEAS-TURB", "measurement",
                       f"Turbidity peaked at {max(recent['turbidity_ntu']):.0f} NTU in the past 7 days.",
                       max(recent["turbidity_ntu"])))
    ev.append(Evidence("MEAS-RAIN", "measurement",
                       f"Total rainfall over the past 7 days was {sum(recent['rain_mm']):.0f} mm.",
                       sum(recent["rain_mm"])))
    ev.append(Evidence("MEAS-NO3", "measurement",
                       f"Nitrate averaged {sum(recent['nitrate_mgl'])/len(recent['nitrate_mgl']):.1f} mg/L.",
                       sum(recent["nitrate_mgl"]) / len(recent["nitrate_mgl"])))
    ev.append(Evidence("MEAS-TEMP", "measurement",
                       f"Water temperature averaged {sum(recent['temp_c'])/len(recent['temp_c']):.1f} degC, "
                       f"peaking at {max(recent['temp_c']):.1f} degC.",
                       max(recent["temp_c"])))

    if summary.get("aspt") is not None:
        ev.append(Evidence("BIO-ASPT", "index",
                           f"Average Score Per Taxon from citizen macroinvertebrate records is "
                           f"{summary['aspt']}, which is the biological component of the index.",
                           summary["aspt"]))

    pts = forecast.get("points", [])
    if pts:
        peak = max(pts, key=lambda p: p["value"])
        ev.append(Evidence("FCST-PEAK", "forecast",
                           f"The 72-hour forecast peaks at {peak['value']:.0f} "
                           f"(80% interval {peak['lower']:.0f}-{peak['upper']:.0f}) at {peak['valid_at'][:16]}.",
                           peak["value"]))
    for i, a in enumerate(forecast.get("alerts", [])[:2], start=1):
        ev.append(Evidence(f"ALERT-{i}", "forecast",
                           f"{a['severity'].upper()} alert for {a['hazard']}: {a['headline']}"))

    accepted = [o for o in observations if o.get("state") in {"auto_accepted", "expert_confirmed"}]
    if accepted:
        taxa = {}
        for o in accepted:
            if o.get("predicted_taxon"):
                taxa[o["predicted_taxon"]] = taxa.get(o["predicted_taxon"], 0) + 1
        top = ", ".join(f"{k} (n={v})" for k, v in sorted(taxa.items(), key=lambda x: -x[1])[:5])
        ev.append(Evidence("OBS-TAXA", "observation",
                           f"{len(accepted)} validated citizen observations in the period. "
                           f"Most recorded families: {top}."))

    # literature: retrieved against the actual conditions, not hardcoded
    query_terms = []
    if do_min < 5:
        query_terms.append("low dissolved oxygen")
    if max(recent["turbidity_ntu"]) > 40:
        query_terms.append("turbidity pathogens runoff")
    if sum(recent["rain_mm"]) > 25:
        query_terms.append("combined sewer overflow rainfall")
    if max(recent["temp_c"]) > 24:
        query_terms.append("warm water cyanobacteria bloom")
    if (summary.get("aspt") or 9) < 4.5:
        query_terms.append("macroinvertebrate biotic index degraded")
    if not query_terms:
        query_terms.append("healthy stream baseline monitoring")

    for hit in retrieve(" ".join(query_terms), k=4):
        ev.append(Evidence(hit["id"], "literature", hit["text"],
                           source=hit.get("source"), source_url=hit.get("url")))

    return ev


SYSTEM = """You write One Health briefs for a public water-quality platform.

A One Health brief connects three things in one short narrative: the ecological
state of a stream, the risk to animals that use it, and the implications for the
people who live around it.

Hard rules:
- Use ONLY the numbered evidence provided. You have no other knowledge of this site.
- Cite the evidence id in square brackets after every factual claim, e.g. [MEAS-DO].
- If the evidence does not support a claim, do not make it. Say what is unknown.
- Never give individual medical advice and never state that water is safe or unsafe
  to drink. Municipal treatment sits between this stream and the tap; you are
  describing pressure on the system, not tap water quality.
- Audience is an informed resident or a city officer, not a scientist. No jargon
  without a plain gloss. British spelling. No bullet points.

Return strict JSON, no markdown fence:
{"headline": str,            // under 90 characters, specific, no hype
 "risk_level": "low"|"moderate"|"high",
 "ecosystem": str,           // 2-3 sentences
 "animal": str,              // 2-3 sentences
 "human": str,               // 2-3 sentences
 "what_changes": str,        // 1-2 sentences: what to watch or do next
 "citations": [str]}         // every id you cited
"""


def build_prompt(summary: dict, evidence: list[Evidence], period: tuple[str, str]) -> str:
    lines = "\n".join(e.as_line() for e in evidence)
    return (
        f"Site: {summary['name']}, {summary['city']} ({summary['country']})\n"
        f"Period: {period[0]} to {period[1]}\n\n"
        f"Evidence:\n{lines}\n\n"
        f"Write the brief."
    )


def validate(payload: dict, evidence: list[Evidence]) -> tuple[bool, list[str]]:
    valid_ids = {e.id for e in evidence}
    body = " ".join(str(payload.get(k, "")) for k in ("ecosystem", "animal", "human", "what_changes"))
    cited = set(re.findall(r"\[([A-Z0-9\-]+)\]", body))
    bogus = sorted(cited - valid_ids)
    problems = []
    if bogus:
        problems.append(f"cited unknown evidence ids: {bogus}")
    if not cited:
        problems.append("no evidence cited")
    declared = set(payload.get("citations") or [])
    if declared != cited:
        problems.append(f"citations list does not match text: declared={sorted(declared)} text={sorted(cited)}")
    for field in ("ecosystem", "animal", "human", "what_changes"):
        sentences = [s.strip() for s in re.split(r"(?<=[.!?])\s+", str(payload.get(field, ""))) if s.strip()]
        for sentence in sentences:
            if len(sentence.split()) >= 5 and not re.search(r"\[[A-Z0-9\-]+\]", sentence):
                problems.append(f"uncited factual sentence in {field}: {sentence[:80]}")
    if payload.get("risk_level") not in RISK_ORDER:
        problems.append("risk_level not one of low/moderate/high")
    for banned in ("safe to drink", "unsafe to drink", "you should see a doctor"):
        if banned in body.lower():
            problems.append(f"contains prohibited claim: {banned!r}")
    return (not problems), problems


def template_brief(summary: dict, evidence: list[Evidence]) -> dict:
    """Deterministic fallback. Never as good, always available."""
    by_id = {e.id: e for e in evidence}
    stress = summary.get("stress") or 0
    risk = "high" if stress >= 70 else "moderate" if stress >= 45 else "low"
    do = by_id.get("MEAS-DO")
    turb = by_id.get("MEAS-TURB")
    fc = by_id.get("FCST-PEAK")
    cites = [i for i in ("IDX-1", "MEAS-DO", "MEAS-TURB", "FCST-PEAK", "BIO-ASPT") if i in by_id]
    return {
        "headline": f"{summary['name']}: stress index {stress:.0f} ({summary['band']})",
        "risk_level": risk,
        "ecosystem": (
            f"The composite stress index stands at {stress:.0f} out of 100 [IDX-1]. "
            + (f"{do.text} " if do else "")
            + (f"{turb.text}" if turb else "")
        ).strip(),
        "animal": (
            "Dissolved oxygen is the variable that determines whether fish and "
            "invertebrates can hold on through a warm spell [MEAS-DO]. "
            + (f"The biological score from citizen records is {summary['aspt']} [BIO-ASPT]."
               if summary.get("aspt") else "")
        ).strip(),
        "human": (
            "Higher turbidity after rain is the usual marker for washed-in "
            "material reaching the channel [MEAS-TURB]. This describes pressure "
            "on the catchment, not the quality of treated drinking water."
        ),
        "what_changes": (f"{fc.text} Watch this reach over the next three days." if fc
                         else "Continue routine monitoring."),
        "citations": cites,
        "generator": "template",
    }


def generate(summary: dict, history: dict, forecast: dict, observations: list[dict],
             api_key: str | None = None) -> dict:
    period_end = datetime.now(timezone.utc).date()
    period_start = period_end - timedelta(days=7)
    evidence = assemble_evidence(summary, history, forecast, observations)
    key = api_key or os.getenv("ANTHROPIC_API_KEY")

    if not key:
        out = template_brief(summary, evidence)
        out.update(_envelope(summary, evidence, period_start, period_end, "template"))
        return out

    try:
        payload = _call_model(key, summary, evidence, (str(period_start), str(period_end)))
        ok, problems = validate(payload, evidence)
        if not ok:
            payload = _call_model(
                key, summary, evidence, (str(period_start), str(period_end)),
                correction=f"The previous attempt failed validation: {problems}. Fix it.")
            ok, problems = validate(payload, evidence)
        if not ok:
            out = template_brief(summary, evidence)
            out["validation_problems"] = problems
            out.update(_envelope(summary, evidence, period_start, period_end, "template-after-failure"))
            return out
        payload["generator"] = MODEL
        payload.update(_envelope(summary, evidence, period_start, period_end, MODEL))
        return payload
    except Exception as exc:                      # network, quota, parse
        out = template_brief(summary, evidence)
        out["error"] = f"{type(exc).__name__}: {exc}"
        out.update(_envelope(summary, evidence, period_start, period_end, "template-after-error"))
        return out


def _envelope(summary, evidence, start, end, model) -> dict:
    return {
        "segment_code": summary["code"],
        "period_start": str(start),
        "period_end": str(end),
        "model": model,
        "evidence": [e.__dict__ for e in evidence],
        "generated_at": datetime.now(timezone.utc).isoformat(),
    }


def _call_model(key: str, summary: dict, evidence: list[Evidence],
                period: tuple[str, str], correction: str | None = None) -> dict:
    import httpx

    prompt = build_prompt(summary, evidence, period)
    if correction:
        prompt += f"\n\n{correction}"

    r = httpx.post(
        "https://api.anthropic.com/v1/messages",
        headers={
            "x-api-key": key,
            "anthropic-version": "2023-06-01",
            "content-type": "application/json",
        },
        json={
            "model": MODEL,
            "max_tokens": 1200,
            "system": SYSTEM,
            "messages": [{"role": "user", "content": prompt}],
        },
        timeout=60.0,
    )
    r.raise_for_status()
    text = "".join(b.get("text", "") for b in r.json().get("content", []) if b.get("type") == "text")
    text = re.sub(r"^```(?:json)?|```$", "", text.strip(), flags=re.MULTILINE).strip()
    return json.loads(text)
