# WatSen — Clarity for every catchment

> Citizen-powered freshwater resilience intelligence for the IEEE OneAquaHealth Global Hackathon 2026.

## Inspiration

Freshwater crises rarely begin with a single dramatic event. They build through small, connected changes: a storm washes nutrients into a stream, turbidity rises, dissolved oxygen falls, sensitive macroinvertebrates disappear, and risks spread across ecosystems, animals, and communities.

The problem is not always a lack of data. It is that the evidence lives in separate places. Sensor readings sit in one dashboard, citizen photographs in another workflow, forecasts in a model notebook, and health implications in reports that arrive too late.

We built **WatSen** to close that gap. Our goal was to create one understandable, auditable path from a field observation to a better water decision:

> **observe → verify → understand → forecast → compare → act**

## What it does

WatSen is a freshwater intelligence platform that connects sensor evidence, citizen science, ecological forecasting, human review, intervention simulation, and One Health communication.

The platform:

- brings six European demonstration reaches into a connected catchment view;
- calculates a transparent freshwater stress score from dissolved oxygen, turbidity, temperature, nitrate, rainfall, and biological evidence;
- forecasts stress 72 hours ahead with uncertainty intervals;
- detects emerging hotspots that may peak before the end of the forecast window;
- explains a likely failure chain from environmental pressure to ecological impact;
- recommends the next useful field measurement when evidence is incomplete;
- lets users compare six intervention scenarios against the same baseline;
- accepts macroinvertebrate photographs, performs image-quality checks, and creates an AI-assisted family suggestion;
- routes uncertain evidence to a human review queue before it can alter BMWP or ASPT;
- connects ecosystem, animal, and human-exposure signals in a clearly labelled One Health view; and
- exports evidence as an HL7 FHIR R4 transaction Bundle with provenance.

WatSen is intentionally honest about the boundary between a prototype and an operational environmental system. The included catchment is a deterministic, mechanistically inspired **synthetic demonstration dataset**. Forecasts and interventions are labelled simulations, the image fallback is labelled `demo-assist`, and the One Health output is an environmental early-warning indicator—not a clinical diagnosis.

## How we built it

The interface is a responsive React and Vite application with a custom sky-blue visual system, accessible keyboard navigation, responsive data visualisation, and original WatSen artwork. Recharts renders the historical, forecast, uncertainty, and intervention trajectories.

The backend is built with FastAPI and Pydantic. A deterministic in-memory store creates a repeatable six-city demonstration without requiring credentials or an external database. NumPy and scikit-learn power feature construction, anomaly detection, TF-IDF evidence retrieval, and the direct multi-horizon Ridge forecaster. Pillow performs real image-quality analysis; the architecture can load an exported ONNX classifier when a trained model is supplied.

Our composite stress value is a weighted, availability-aware score:

$$
S_t = 100 \times \frac{\sum_i w_i r_i(x_{i,t})}{\sum_{i \in A_t} w_i}
$$

where \(r_i\) converts each available measurement into a normalized risk contribution, \(w_i\) is its declared weight, and \(A_t\) contains only measurements available at time \(t\). Missing values are never silently replaced with zero.

Biological evidence uses accepted macroinvertebrate families:

$$
\mathrm{ASPT} = \frac{\mathrm{BMWP}}{N_{\text{scoring families}}}
$$

Every forecast carries an interval calibrated from held-out residuals. Scenario metadata and provenance remain attached through the interface and the FHIR export so simulated values are not mistaken for observations.

## The evidence loop

1. Sensors and climate context describe the physical water state.
2. A citizen contributes a macroinvertebrate photograph.
3. WatSen checks image quality and proposes a family-level identification.
4. Deterministic validation and anomaly detection decide whether the record can be accepted or needs expert review.
5. Accepted, deduplicated families update BMWP and ASPT.
6. Biological evidence updates the composite stress picture.
7. The 72-hour model forecasts possible deterioration and its uncertainty.
8. The failure chain explains what may be driving the change.
9. The intervention lab compares possible responses.
10. A One Health brief and FHIR bundle carry the evidence into a wider decision workflow.

## Challenges we faced

### Keeping the science honest

The hardest design challenge was resisting false precision. Environmental data are incomplete, and a polished chart can easily make a prototype look more certain than it is. We added visible uncertainty intervals, evidence types, provenance, scenario labels, model limitations, and explicit disclaimers throughout the experience.

### Making citizen science useful without removing people

A photograph can expand monitoring coverage, but an AI guess should not silently change an ecological index. We designed the classifier as an assistant: it checks quality, proposes a family, and routes uncertainty to human review. Only accepted evidence affects BMWP and ASPT.

### Connecting different kinds of evidence

Sensor values, biological indices, forecasts, incident timelines, and health communication have different meanings and timescales. We created a shared segment and provenance model so those layers can be connected without pretending they are interchangeable.

### Building a dependable hackathon demo

External keys, databases, and model artefacts can fail at the worst possible moment. We built deterministic fallbacks and a no-credentials demo path while preserving clean interfaces for PostgreSQL, ONNX inference, and external data sources. This made the complete story reproducible instead of depending on a fragile live service.

### Designing depth without overwhelming the user

WatSen contains forecasting, anomaly detection, biological scoring, review workflows, counterfactuals, interoperability, and One Health evidence. The interface had to make that depth discoverable. We used progressive disclosure: a calm overview first, then expandable failure-chain nodes, evidence cards, model details, and standards views for users who want to inspect the system.

## What we learned

We learned that trust in environmental AI comes less from adding another model and more from showing the chain around it: where an input came from, what was inferred, how confident the system is, who reviewed it, and how the result could change with new evidence.

We also learned that biological indicators are a powerful bridge between raw chemistry and ecosystem condition. Family-level macroinvertebrate identification is realistic for community participation and maps directly to BMWP/ASPT, making it a practical target for human-in-the-loop AI.

Finally, interoperability changes how a prototype is designed. Building provenance and FHIR export into the system from the beginning forced us to keep observed, inferred, and simulated values distinct throughout the stack.

## Accomplishments that we are proud of

- A complete closed evidence loop where accepted citizen observations can update biological evidence and stream stress.
- A 72-hour forecast with calibrated uncertainty instead of a single overconfident line.
- An explainable failure chain that connects observed, inferred, citizen, and forecast evidence.
- A six-option intervention lab that updates the projected trajectory.
- A reach-specific expert review queue and incident replay.
- A One Health bridge that communicates environmental relevance without making clinical claims.
- A traceable FHIR R4/OAH export with local structural preflight and clear validation limits.
- A polished responsive experience that works with a deterministic no-key demo.

## What's next for WatSen

Next, we would connect live hydrology, meteorology, land-use, and verified citizen-science feeds; train and calibrate the macroinvertebrate model on geographically diverse field images; validate the forecast across seasons and catchments; add durable PostgreSQL/PostGIS storage; run the official HL7 validator against the current OneAquaHealth implementation guide; and co-design field protocols with ecologists, municipalities, and citizen groups.

The long-term vision is simple: make freshwater evidence understandable early enough that communities can protect a catchment before a warning becomes a crisis.

## Try it out

- **Live demo:** _deployment URL will be added after production deployment_
- **Source code:** [github.com/codewithanshuman/WatSen](https://github.com/codewithanshuman/WatSen)

## Demo path

1. Open the workspace and choose a reach.
2. Switch between baseline, storm, heatwave, and spill scenarios.
3. Inspect the 72-hour forecast and expand the failure chain.
4. Compare intervention cards and watch the projected trajectory change.
5. Open **Field studio** to inspect the evidence loop and review queue.
6. Open **One Health** for the cross-domain environmental brief.
7. Open **Evidence & export** to inspect provenance, model limitations, and the FHIR preflight.
