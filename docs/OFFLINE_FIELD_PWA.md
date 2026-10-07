# Offline field PWA and impact receipts

WatSen's Field Studio is installable and remains useful when a sampling site has
poor connectivity. The design separates capture readiness from scientific
acceptance: a good photograph can still be scientifically wrong, and a queued
record never enters the ecological index until server-side validation succeeds.

## Field flow

1. The contributor chooses or captures a JPG/PNG image.
2. The browser evaluates resolution, exposure, contrast and approximate
   sharpness locally. The image is not uploaded for these checks.
3. The contributor can save the file, selected reach, timestamp and quality
   result to IndexedDB, even with no connection.
4. When connectivity returns, WatSen classifies the image, submits the
   observation and runs the normal server trust, proximity and quality checks.
5. The local record is deleted only after the API returns a successful impact
   receipt. Failed records stay in the queue with a retry state.
6. Auto-accepted records update the 30-day evidence window immediately;
   uncertain records wait for expert review.

## Impact receipt contract

Every observation submission and expert review response includes
`impact_receipt` with:

- a receipt and observation identifier;
- `applied`, `accepted_no_index_change`, `pending_review`, or `not_applied`;
- exact before, after and delta values for ASPT, BMWP, accepted observations and
  composite stress;
- the validation/recomputation trace; and
- a boundary statement that the receipt describes a deterministic evidence
  update, not causal ecological impact.

An accepted record may produce no ASPT/BMWP change when that macroinvertebrate
family is already represented in the deduplicated evidence window. The receipt
makes this explicit rather than implying that every upload changes the score.

## Storage and privacy boundary

Queued images remain in browser IndexedDB on the current device. Removing a
queued record deletes that local copy. Successful synchronization also deletes
it after the server acknowledges the observation. This prototype does not yet
provide encrypted multi-user object storage, cross-device queue recovery or a
retention-policy console; those belong to the production architecture phase.

The current location submitted with the observation is the selected demo
reach. A production field deployment must add explicit location consent,
precision reduction where appropriate and role-based access before collecting
device GPS.

## Capture-quality boundary

The browser checks are lightweight image heuristics, not a taxonomic model and
not proof of sample validity. They help a contributor notice likely blur,
extreme exposure or inadequate resolution while a retake is still possible.
Server-side image assessment, observation validation and optional expert review
remain authoritative for the application workflow.

## Verification

```bash
cd services/api
python -m app.selftest

cd ../../web
npm run build
```

The API self-test verifies both accepted and unsafe-submission receipt
contracts. The production build emits the web manifest and service worker used
by the installable shell.
