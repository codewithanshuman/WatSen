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
5. The local record is deleted only in the same database transaction that saves
   a matching server receipt. Failed records keep their photo, successful image
   assessment and exact submission payload. Retries back off from 5 seconds to
   5 minutes; validation/conflict errors pause for attention. A manual sync can
   bypass backoff. Sync runs while Field Studio is open, on reconnect, on focus
   and at a 15-second retry check interval; it does not run while the app is closed.
6. Auto-accepted records update the 30-day evidence window immediately;
   uncertain records wait for expert review.

## Impact receipt contract

Every observation submission and expert review response includes
`impact_receipt` with:

- a receipt and observation identifier;
- `applied`, `accepted_no_index_change`, `pending_review`, or `not_applied`;
- `reverted` when a review excludes evidence that previously contributed;
- exact before, after and delta values for ASPT, BMWP, accepted observations and
  composite stress;
- the validation/recomputation trace; and
- a boundary statement that the receipt describes a deterministic evidence
  update, not causal ecological impact.

An accepted record may produce no ASPT/BMWP change when that macroinvertebrate
family is already represented in the deduplicated evidence window. The receipt
makes this explicit rather than implying that every upload changes the score.

The local receipt ledger survives page reloads and supports filters, individual
JSON exports, complete-ledger exports and checks for new server review receipts.
Every review has a separate receipt ID, state/taxon transition and reviewer note.
The workbench supports confirming, correcting and excluding an observation.
Quality, observation age and scoring-family gates remain active after review.
Demo image suggestions always require expert review before index inclusion.

## Retry protection and server boundary

Each capture sends a stable `client_submission_id`. Concurrent or repeated
identical requests return the original response without adding another record;
reusing the ID with a different payload returns HTTP 409. The current server
stores the replay journal in memory with a lock. **This protection is limited
to one server process**, and does not survive a cold start or coordinate Vercel
instances. A shared database with a unique key and atomic receipt transaction
is still required before collecting real multi-user field evidence.

The worker precaches all emitted JS/CSS chunks, including the lazy workspace,
with a build-content revision. Cached API responses carry their saved time and
trigger a visible saved-evidence notice. Errors cannot overwrite successful
cache entries. Receipt history is always fetched from the server.

## Storage and privacy boundary

Queued images remain in browser IndexedDB on the current device. Removing a
queued record deletes that local copy. Successful synchronization deletes the
full-size image after the server acknowledges the observation and its receipt
is saved locally. A reduced JPEG (at most 720 pixels on its longest side) stays
with the device receipt for the review workbench. JSON exports exclude images.
Receipt history and reduced photos remain until browser site data is cleared;
review photos are not currently available to a reviewer on a different device.
This prototype does not yet
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
python -m unittest app.test_evidence_workflow -v

cd ../../web
npm run build
npm run test:field
```

The API self-test verifies both accepted and unsafe-submission receipt
contracts. The production build emits the web manifest and service worker used
by the installable shell.
