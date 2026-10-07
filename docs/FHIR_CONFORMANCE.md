# WatSen FHIR/OAH conformance evidence

Verified on **7 October 2026** with the official HL7 FHIR validator CLI.

| Item | Pinned value |
|---|---|
| FHIR version | R4 `4.0.1` |
| HL7 validator | `7.0.0` |
| Validator SHA-256 | `0ec7285b0f23999c25979533c6e9105f5f01087889fcc113ac1dfc65560bcc69` |
| OneAquaHealth source | `hl7-eu/oah@b907cf0869b59d82d9138b3d147fca66f333d911` |
| SUSHI | `3.20.1` |
| Result | **0 errors, 17 warnings, 10 informational messages** |

The tested transaction Bundle contains OAH-profiled `Location`, `Observation`
and `Specimen` resources, a resolvable `PractitionerRole`, and `Provenance`.
The OAH profiles require observation performers and a specimen collector; both
references resolve inside the transaction Bundle.

CI rebuilds the OAH FHIR Shorthand source at the pinned commit, exports a fresh
WatSen fixture, verifies the validator binary checksum, runs the validator, and
uploads the raw `OperationOutcome`. The gate fails on `fatal` or `error`
severity. It uses `-tx n/a` so the result does not depend on an external
terminology server; UCUM, SNOMED and project-local terminology messages remain
visible as warnings instead of being silently discarded.

Reproduce the fast local checks with:

```bash
make fhir-fixture
make test
```

The complete authoritative CLI command is encoded in
`.github/workflows/quality.yml` so its versions and validation policy are
reviewable with the source.
