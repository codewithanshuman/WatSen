# WatSen Next-Level Roadmap

This roadmap turns WatSen from a polished hackathon prototype into a credible
freshwater decision-support product. It is intentionally maintained on the
local `next-level` branch while the submitted entry is being judged.

## Current implementation status

Completed locally on `next-level` (not pushed to the submitted deployment):

- live Open-Meteo context with provenance, cache policy, explicit unavailable
  state, and no silent synthetic fallback;
- a responsive live-evidence panel in the workspace;
- reproducible chronological, leave-one-reach-out and leave-one-city-out
  forecast evaluation with persistence/seasonal baselines, event metrics,
  conformal coverage and machine-readable artifacts; and
- corrected OAH profile selection plus official HL7 validator CI pinned to the
  OAH source commit and validator checksum.

Next implementation target: the transparent intervention MCDA and weight
sensitivity view, followed by offline field capture.

## Product position

**Primary track:** Track 6 — Resilience Informatics

**Supporting capabilities:** Track 2 — Data-to-Insight, Track 3 — AI-Supported
Assessment, and Track 7 — Digital Health Standards.

**One-sentence value proposition:** WatSen turns sensor, climate, and reviewed
citizen evidence into a traceable 72-hour freshwater risk forecast, recommends
the next useful measurement, and compares practical interventions before a
local warning becomes an ecosystem crisis.

## Success definition

The next version is complete when a judge or city operator can:

1. open a real monitored reach and distinguish live, observed, inferred, and
   simulated evidence at a glance;
2. reproduce the forecast evaluation and see how uncertainty was calibrated;
3. trace every recommendation to evidence and an explicit decision rule;
4. compare interventions by impact, cost, lead time, feasibility, and
   uncertainty—not only a predicted percentage improvement;
5. submit a field observation offline, synchronize it later, and follow its
   review and impact history;
6. export a bundle that passes the official HL7 validator against the current
   OneAquaHealth implementation guide; and
7. see measured pilot outcomes instead of unverified impact claims.

## Weighted competition plan

| Criterion | Weight | Current strength | Upgrade required |
| --- | ---: | --- | --- |
| Impact and OneAquaHealth alignment | 30% | Strong connected evidence story | Pilot evidence, explicit target users, measurable outcome model |
| Innovation and creativity | 20% | Forecast + citizen evidence + interventions | Catchment digital twin, active sampling, uncertainty-aware MCDA |
| Technical implementation | 20% | Working full-stack prototype | Real connectors, durable storage, reproducible validation, observability |
| Usability and UX | 15% | Polished, accessible dashboard | Offline field PWA, multilingual plain language, role-specific workflows |
| Feasibility and scalability | 15% | Clear architecture and standards export | Multi-tenant deployment, PostGIS, jobs, security, cost and rollout plan |

## P0 — Protect the submitted entry

- Keep the submitted production URL and `main` branch stable during judging.
- Record the submitted commit, production URL, demo video, and Devpost copy.
- Run automated uptime and API smoke checks without changing application data.
- Ask the organizer before making any judge-visible post-deadline feature change.
- Keep all new implementation work local or on an explicitly post-hackathon
  branch until updates are permitted.

## P1 — Replace synthetic-only credibility with a live evidence spine

Build a connector layer with a strict common observation contract:

- OneAquaHealth research-site and resilience-map data when the public service is
  available;
- Open-Meteo historical and forecast weather as a no-key climate source;
- Copernicus/Sentinel-derived surface-water context where licensing and latency
  permit;
- optional city or agency CSV/FHIR imports; and
- the current deterministic dataset as an explicit, reliable demo fallback.

Every datum must include source, observed time, ingestion time, license,
quality flag, unit, spatial resolution, and whether it is observed, inferred,
forecast, or simulated. The UI must expose a **Live / Demonstration** mode and a
data-freshness indicator. Silent fallback is forbidden.

### Acceptance tests

- A connector outage never breaks the demo.
- Live values and demo values cannot be visually confused.
- Units and timestamps are normalized and validated.
- A provenance record exists for every plotted point.
- Cached data has an explicit age and expiry policy.

## P1 — Make the forecast scientifically defensible

- Use blocked time-series evaluation and leave-one-city-out validation.
- Compare against persistence, seasonal-naive, and simple linear baselines.
- Report MAE, RMSE, threshold-event precision/recall, lead time, Brier score,
  calibration error, and interval coverage by horizon and city.
- Calibrate prediction intervals per horizon and surface low-coverage warnings.
- Add missingness and sensor-drift tests.
- Publish a reproducible model card and downloadable evaluation artefact.
- Add a shadow-mode policy: forecasts inform decisions but do not automatically
  trigger regulatory or clinical action.

### Acceptance tests

- Evaluation can be reproduced from a single documented command.
- No model is presented as useful unless it beats declared baselines.
- The displayed interval coverage matches the evaluated artefact.
- A data shift or unavailable sensor visibly reduces confidence.

## P1 — Upgrade interventions into an explainable decision engine

Replace fixed improvement cards with a multi-criteria decision analysis layer.
Rank nature-based and operational responses using:

- expected stress reduction and uncertainty;
- implementation cost band;
- time to effect;
- ecological co-benefit;
- human and animal health relevance;
- site constraints and reversibility; and
- strength of supporting evidence.

Use a transparent PROMETHEE-style or weighted outranking calculation, show the
weight sensitivity, and link each intervention to the OneAquaHealth catalogue
of rehabilitation measures. Users must be able to compare rankings without
mistaking a simulation for a promise.

## P1 — Turn FHIR export into standards proof

- Pin the current OneAquaHealth FHIR implementation-guide version.
- Generate profile-conformant Location, Observation, Specimen, Provenance, and
  relevant alert/communication resources.
- Run the official HL7 validator in CI and attach its report as a build artefact.
- Add deterministic identifiers and idempotent submission behavior.
- Test against the OneAquaHealth/HL7 Europe sandbox when permitted.
- Publish a machine-readable capability statement and mapping table.

## P2 — Build a real field workflow

- Installable offline-first PWA with queued synchronization.
- GPS/site-distance checks and explicit location-consent handling.
- EXIF-aware capture, blur/exposure/obstruction quality checks, and duplicate
  detection before upload.
- Family-level AI suggestions with top alternatives, confidence, visual
  evidence guidance, and mandatory human override.
- Expert review SLA, audit trail, disagreement capture, and reviewer notes.
- An impact receipt showing exactly what changed after an accepted observation.
- Plain-language and multilingual field guidance; never reward upload volume.

## P2 — Add catchment intelligence instead of a decorative map

- Represent reaches as a directed upstream/downstream graph.
- Estimate travel time and propagation windows for runoff or spill scenarios.
- Show upstream contributors, downstream assets, sensitive habitats, and
  exposure points.
- Add satellite and land-use context with resolution and recency labels.
- Support spatial queries and catchment boundaries with PostgreSQL/PostGIS.
- Let users replay an incident and compare predicted versus observed evolution.

## P2 — Production architecture

- PostgreSQL/PostGIS as the durable source of truth.
- Object storage for photographs and signed upload URLs.
- Background jobs for ingestion, inference, validation, and notifications.
- Redis or equivalent only where caching/queues measurably help.
- Role-based access for citizen, reviewer, scientist, and city operator.
- Append-only provenance/audit events and data-retention controls.
- Structured logs, traces, service-level indicators, and alerting.
- Rate limiting, file scanning, consent records, and privacy-preserving location
  defaults.

## P2 — Prove impact with people

Run a small, ethical pilot with separate citizen and expert tasks. Measure:

- task completion time and abandonment;
- photo-quality pass rate;
- percentage of observations needing expert correction;
- reviewer time per record;
- alert lead time versus the existing workflow;
- action selection agreement and time to decision; and
- System Usability Scale plus short qualitative interviews.

Report the sample size, protocol, limitations, and raw aggregate results.
Never invent impact numbers.

## Judge-facing experience

Add an optional **90-second judge path** that does not hide the full product:

1. A storm arrives at Coimbra.
2. WatSen shows the observed rainfall and water-quality response.
3. The forecast highlights a likely oxygen-stress peak and its uncertainty.
4. The evidence chain explains why.
5. Active sampling identifies dissolved oxygen as the most valuable next check.
6. A reviewed citizen observation updates the biological window.
7. The decision engine compares responses and explains the ranking.
8. The One Health view translates relevance without making a clinical claim.
9. The standards view proves provenance and official FHIR validation.

The opening screen should explicitly state the primary track, target users,
problem, measurable outcome, and what is live versus simulated.

## Do not build

- A generic chatbot with no authority, evidence boundary, or measurable task.
- More decorative animation before real-data and validation gaps are closed.
- A single opaque “AI water score.”
- Medical diagnosis or causal health claims from environmental proxies.
- Leaderboards that reward quantity over evidence quality.
- Blockchain unless a specific multi-party trust problem cannot be solved by a
  signed append-only audit log.

## Delivery sequence

### Sprint 1 — Credibility

Live/demo data contract, Open-Meteo connector, freshness/provenance UI,
reproducible forecast evaluation, and official FHIR validator CI.

### Sprint 2 — Decisions

Intervention MCDA, sensitivity analysis, catchment graph, incident replay, and
role-specific action workflow.

### Sprint 3 — Field and scale

Offline PWA, resilient synchronization, expert-review operations,
PostgreSQL/PostGIS persistence, observability, privacy, and security controls.

### Sprint 4 — Evidence of impact

Usability pilot, performance report, architecture diagram, rollout economics,
90-second judge path, and a concise 3–5 minute demo video.
