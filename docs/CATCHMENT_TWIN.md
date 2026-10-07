# Directed Catchment Operations Room

WatSen's catchment operations room is an interactive scenario-planning surface,
not a conventional game and not a calibrated hydraulic model. It makes a
complex decision legible: where a pressure originates, how it could move
through a directed network, which assets may be reached, and how a selected
response changes the labelled counterfactual.

## What users can do

- scrub or play a 72-hour propagation timeline;
- inspect source, junction, monitored, habitat, community, and receiving nodes;
- see transparent travel-time and attenuation priors on each directed edge;
- switch between monitor-only and five direct response plans;
- compare the selected plan's node-level peak with the no-action peak;
- identify the next connected node reached by the pressure; and
- track whether protected habitat and public-use assets remain below the
  demonstration threshold.

This provides the clarity of a strategy simulation without points, avatars,
leaderboards, streaks, or rewards that could encourage unsafe environmental
decisions.

## Model boundary

The API identifies the model as a `deterministic-topology-prior`. The topology,
travel times, attenuation and asset thresholds are transparent development
assumptions. Response effects reuse the intervention engine's labelled
counterfactual priors.

It must not be represented as:

- a calibrated hydraulic or hydrodynamic model;
- a contaminant fate-and-transport model;
- a flood forecast;
- proof that an intervention will produce the displayed effect; or
- authority to act without permits, field verification and expert review.

Production calibration would require surveyed network topology, reach length,
flow and stage observations, dispersion and decay estimates, outfall and asset
locations, event observations, and validation against held-out incidents.

## API contract

```text
GET /v1/segments/{code}/catchment-twin?scenario=storm
```

The response includes:

- `nodes` with coordinates, roles, arrival and peak windows;
- directed `edges` with travel-time and attenuation priors;
- `plans` with node-level counterfactual outcomes;
- two `protected_assets` and their threshold states;
- an explicit `objective`; and
- a machine-readable model boundary and assumptions.

Contract checks run in `python -m app.selftest`.
