# Transparent Intervention MCDA

WatSen ranks six direct-response and verification options with an explicit,
editable multi-criteria decision analysis (MCDA). It is a planning aid: the
result is not regulatory advice, a causal impact estimate, or a procurement
quote.

## Calculation

Each option receives a higher-is-better utility score \(u_{ij}\) from 0 to 100
for criterion \(j\). User weights are constrained to non-negative values and
normalised to 100. The displayed score is:

$$
S_i = \frac{\sum_j w_j u_{ij}}{\sum_j w_j}
$$

The interface exposes every raw utility and weighted contribution. Ties are
resolved by the simulated ecological-improvement percentage. Citizen sampling
is allowed to rank with the options but is marked as a verification action and
cannot become the primary ecological-response recommendation.

## Criteria and balanced weights

| Criterion | Weight | Meaning |
| --- | ---: | --- |
| Expected ecological benefit | 30 | Simulated stress reduction, dissolved-oxygen gain, and critical hours avoided |
| Evidence strength | 15 | Planning prior for the strength of evidence supporting the response type |
| Time to effect | 12 | Ability to act inside the 72-hour risk window |
| Site feasibility | 12 | Base feasibility adjusted for scenario fit and urban space pressure |
| Ecological co-benefit | 10 | Habitat and longer-term resilience value |
| One Health relevance | 8 | Relevance across ecosystem, animal, and human exposure pathways |
| Reversibility | 6 | Ability to alter or stop the response safely |
| Resource efficiency | 7 | Indicative resource requirement; not a cost estimate |

Balanced, ecology-first, rapid-response, resource-constrained, and
precautionary profiles are included. Every weight remains editable.

## Sensitivity analysis

For the active weights, WatSen deterministically checks 21 cases:

- the current weights;
- each of the eight criteria independently reduced by 50%;
- each of the eight criteria independently increased by 50%; and
- four alternative priority profiles.

Robustness is the percentage of cases in which the same eligible direct action
remains the winner. The runner-up margin is also displayed. This is local
one-at-a-time sensitivity analysis, not a probabilistic uncertainty model.

## Evidence and limitations

The option structure and decision workflow are grounded in the
[OneAquaHealth Decision Support System](https://www.oneaquahealth.eu/decision-support-system/)
and the [OneAquaHealth Catalogue of Measures](https://www.oneaquahealth.eu/wp-content/uploads/2026/05/OAH_Catalogue-of-measures-1.pdf).
OneAquaHealth describes a workflow that connects indicators and stressors to
candidate measures while retaining expert judgement. WatSen's criterion scores
are transparent development priors, not values published or endorsed by the
project.

Before field action, operators must verify local source attribution, permits,
site access, receiving-pathway risks, equipment safety, maintenance needs, and
current measurements. Future field pilots should replace the priors with
site-specific costs, observed outcomes, confidence ranges, and stakeholder
weights.

## Reproduction

The API accepts any subset of these 0–100 query parameters on
`GET /v1/segments/{code}/interventions`: `weight_effectiveness`,
`weight_evidence`, `weight_speed`, `weight_feasibility`, `weight_co_benefit`,
`weight_one_health`, `weight_reversibility`, and `weight_cost`.

Run the contract and guardrail tests with:

```bash
cd services/api
python -m app.selftest
```
