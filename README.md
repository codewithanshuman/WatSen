# WatSen

Citizen-powered freshwater resilience intelligence for the OneAquaHealth IEEE
Global Hackathon 2026.

WatSen connects sensor evidence, citizen macroinvertebrate observations,
short-range ecological forecasting, expert review, intervention simulations and
One Health communication in one auditable loop.

> WatSen does not replace scientists or citizens. It connects them—turning
> fragmented observations into evidence, forecasts and actions before a
> freshwater ecosystem reaches crisis.

## Project links

- **Source:** [github.com/codewithanshuman/WatSen](https://github.com/codewithanshuman/WatSen)
- **Live demo:** [watsen-nine.vercel.app](https://watsen-nine.vercel.app)
- **Devpost submission copy:** [DEVPOST.md](DEVPOST.md)
- **Forecast evidence:** [docs/FORECAST_EVALUATION.md](docs/FORECAST_EVALUATION.md)
- **FHIR conformance evidence:** [docs/FHIR_CONFORMANCE.md](docs/FHIR_CONFORMANCE.md)
- **Intervention decision method:** [docs/INTERVENTION_MCDA.md](docs/INTERVENTION_MCDA.md)
- **Catchment twin boundary:** [docs/CATCHMENT_TWIN.md](docs/CATCHMENT_TWIN.md)

## Run the complete demo

No credentials are required.

```bash
docker compose up --build
```

- Web: <http://localhost:5173>
- API: <http://localhost:8000/docs>

Local development:

```bash
cd services/api
python -m pip install -r requirements.txt
uvicorn app.main:app --reload --port 8000

cd ../../web
npm install
npm run dev
```

The resilience map is implemented without a commercial map service, so the
entire core narrative works offline. An Anthropic key is optional; without it,
the One Health brief uses the evidence-grounded deterministic generator.

## Visual system

The WatSen interface uses the supplied artwork from `D:\WatSen\assets` across
the product experience: the original water-drop logo and favicon, predictive
water hero, field-camera capture state, One Health sky and bottle artwork,
animated water/loading states, and the illustrated footer. Runtime copies live
under `web/public/assets` so the production bundle can serve them directly.

## The evidence loop

```text
stream sensors + climate + citizen photograph
                      ↓
          image quality + AI suggestion
                      ↓
       server-side location/trust validation
                      ↓
             human expert review
                      ↓
         deduplicated BMWP families → ASPT
                      ↓
            composite ecosystem stress
                      ↓
          72-hour forecast + uncertainty
                      ↓
    failure chain + adaptive sampling mission
                      ↓
          counterfactual interventions
                      ↓
        One Health brief + OAH/FHIR export
```

Accepted, recent citizen observations now change BMWP/ASPT and therefore the
biological component of stream stress. Sparse citizen evidence is blended with
a declared baseline prior until five scoring families are available; after that
the recent evidence stands on its own.

## What is implemented

- Interactive predictive resilience map with a now-to-72-hour timeline
- Regional risk radar and emerging-hotspot detection
- Interactive seven-node directed catchment operations room with 72-hour
  propagation playback, protected assets and switchable response plans
- 72-hour direct multi-horizon Ridge forecast with held-out residual calibration
- Reproducible chronological and leave-one-site-out evaluation against
  persistence and 24-hour seasonal baselines
- Expandable, typed failure chain: observed, citizen, inferred and forecast
- Six labelled counterfactual responses ranked by an editable eight-criterion
  MCDA, with contribution breakdowns, priority profiles and 21-case sensitivity
  analysis
- Adaptive Citizen Sampling and a community verification mission
- Image upload, quality assessment and optional ONNX macroinvertebrate inference
- Human review queue with confirm, correct and reject actions
- Server-derived distance, submission velocity and contributor trust
- Observation-driven BMWP/ASPT and stream stress
- Evidence graph, provenance badges and incident replay
- Explicit ecosystem, animal/biodiversity and human-exposure bridge
- Evidence-grounded One Health brief with source provenance
- FHIR R4 transaction Bundle declaring draft OneAquaHealth Location,
  component Observation and Specimen profiles, plus Provenance
- Local FHIR/OAH structural preflight plus CI validation with the official HL7
  validator against a commit-pinned OneAquaHealth source build
- Model card and honest synthetic-development limitations
- Deterministic, fixed-date demo data via `DEMO_END` and `DEMO_SEED`

## Image model modes

`POST /v1/classify` supports two explicit modes:

1. **ONNX** — set `CLASSIFIER_ONNX` to a trained exported model. The API uses
   ONNX Runtime and calibrated class probabilities.
2. **Demo assist** — when no model artefact exists, image quality is genuinely
   measured and a deterministic suggestion exercises the complete review flow.
   It is labelled `demo-assist`, always requires human confirmation and is never
   presented as a trained classifier.

Train and export a real model after placing family folders under
`data/macroinvertebrates/{train,val}/`:

```bash
make train-classifier
```

## API highlights

```text
GET  /v1/hotspots
GET  /v1/segments/{code}/failure-chain
GET  /v1/segments/{code}/interventions
GET  /v1/segments/{code}/catchment-twin
GET  /v1/segments/{code}/evidence-graph
GET  /v1/segments/{code}/data-sufficiency
GET  /v1/segments/{code}/one-health
GET  /v1/segments/{code}/incident
POST /v1/classify
POST /v1/observations
GET  /v1/review-queue
POST /v1/observations/{id}/review
GET  /v1/models/watforecast
GET  /v1/segments/{code}/fhir
GET  /v1/segments/{code}/fhir/validate
```

## Scientific honesty

- Development data are described as **mechanistically inspired synthetic test
  data**, not a validated catchment simulation.
- The model is not validated for regulatory decision-making.
- Scenario values are tagged simulated in the API, interface and FHIR metadata.
- Interventions are labelled simulations, not authoritative environmental advice.
- One Health output is an environmental early-warning indicator, not a clinical
  diagnosis or a statement about treated drinking water.
- The local FHIR check is not represented as authoritative OAH conformance.
- Missing aquatic variables are never silently filled with zero.
- OpenAQ temperature is stored as air temperature, not water temperature.

## Verification

```bash
cd services/api
python -m app.selftest
python -m app.ml.evaluate_forecaster --days 180 --stride 12

cd ../../web
npm run build
```

The endpoint suite covers the original API plus the closed resilience loop and
FHIR preflight. The generated forecast report is committed at
[`docs/FORECAST_EVALUATION.md`](docs/FORECAST_EVALUATION.md), with machine-readable
metrics in [`reports/forecast_evaluation.json`](reports/forecast_evaluation.json).
CI also exports a reproducible Bundle and runs the official HL7 validator
against FHIR R4 and a commit-pinned build of the draft OneAquaHealth profiles.
The CI gate is network-independent: it enforces structural/profile errors and
uses the bundled OAH definitions, while external terminology-service messages
remain reported as non-blocking warnings.

## Optional infrastructure

The default demo uses the truthful in-memory `MockStore`. It does not claim to
be PostgreSQL-backed. The PostGIS and Redis containers are retained as an
explicit optional infrastructure profile for future durable-store work:

```bash
docker compose --profile infrastructure up db cache
```

Setting `STORE_BACKEND=postgres` currently fails fast with an explanatory error
instead of allowing `/health` to misreport the active backend.

## Suggested 3–5 minute demo

1. Start on the observed resilience map.
2. Switch to the storm scenario and scrub the 72-hour timeline.
3. Open the emerging hotspot and walk through its failure chain.
4. Show widening uncertainty and the adaptive citizen mission.
5. Upload a photograph; explain that AI suggests and a human confirms.
6. Confirm the observation and show the biological evidence window update.
7. Play the directed catchment pulse, switch response plans and inspect a
   protected habitat or community asset.
8. Move an intervention priority, inspect the score breakdown and show how the
   recommendation and sensitivity result respond.
9. Open the measurable One Health bridge and cited brief.
10. Finish with the OAH-profiled FHIR bundle, provenance and validation status.
