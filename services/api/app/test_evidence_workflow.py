"""Regression tests for retry/review transitions that must preserve evidence."""
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
import unittest
import uuid
import json

from fastapi.testclient import TestClient
from app.main import app
from app.store import MockStore, get_store


class EvidenceWorkflowTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.client = TestClient(app)
        cls.store = get_store()
        cls.segment = next(iter(cls.store.segments.values()))

    def payload(self, **changes):
        return {
            "client_submission_id": str(uuid.uuid4()),
            "segment_code": self.segment.code, "observed_at": (datetime.now(timezone.utc) - timedelta(minutes=5)).isoformat(),
            "lat": self.segment.lat, "lon": self.segment.lon,
            "contributor": "test-" + uuid.uuid4().hex, "note": "Kick sample with clear body and appendage detail.",
            "predicted_taxon": "Gammaridae", "taxon_confidence": .96, "n_photos": 2,
            **changes,
        }

    def submit(self, payload):
        response = self.client.post('/v1/observations', json=payload)
        self.assertEqual(response.status_code, 201, response.text)
        return response.json()

    def test_retry_and_conflict_preserve_single_observation(self):
        payload = self.payload()
        initial = self.submit(payload)
        replay = self.client.post('/v1/observations', json=payload)
        self.assertEqual(replay.status_code, 200)
        self.assertTrue(replay.json()['replayed'])
        self.assertEqual(initial['impact_receipt'], replay.json()['impact_receipt'])
        self.assertEqual(sum(row.get('client_submission_id') == payload['client_submission_id'] for row in self.store.observations), 1)
        conflict = self.client.post('/v1/observations', json={**payload, 'note': 'Changed capture'})
        self.assertEqual(conflict.status_code, 409)

    def test_concurrent_retries_create_one_receipt(self):
        payload = self.payload()
        with ThreadPoolExecutor(max_workers=4) as pool:
            responses = list(pool.map(lambda _: self.client.post('/v1/observations', json=payload), range(4)))
        self.assertEqual(sorted(r.status_code for r in responses), [200, 200, 200, 201])
        self.assertEqual(len({r.json()['impact_receipt']['receipt_id'] for r in responses}), 1)

    def test_nonfinite_metadata_is_rejected_before_mutation(self):
        payload = self.payload(image_quality={'score': float('nan')})
        before = len(self.store.observations)
        response = self.client.post('/v1/observations', content=json.dumps(payload), headers={'content-type': 'application/json'})
        self.assertEqual(response.status_code, 422)
        self.assertEqual(len(self.store.observations), before)
        self.assertNotIn(payload['client_submission_id'], self.store.submission_responses)

    def test_demo_identification_review_correction_and_reversal(self):
        payload = self.payload(model='demo-image-assist-1', image_quality={'score': .95})
        initial = self.submit(payload)
        receipt = initial['impact_receipt']
        self.assertEqual(initial['observation']['state'], 'needs_review')
        self.assertEqual(receipt['changes']['accepted_observations']['delta'], 0)
        observation_id = initial['observation']['id']
        route = f'/v1/observations/{observation_id}/review'
        missing_note = self.client.post(route, json={'action': 'correct', 'corrected_taxon': 'Baetidae'})
        self.assertEqual(missing_note.status_code, 422)
        corrected = self.client.post(route, json={'action': 'correct', 'corrected_taxon': 'Baetidae', 'reviewer_note': 'Gill and body features support Baetidae.', 'reviewer': 'test-expert'})
        self.assertEqual(corrected.status_code, 200, corrected.text)
        self.assertEqual(corrected.json()['impact_receipt']['transition']['before']['predicted_taxon'], 'Gammaridae')
        self.assertTrue(corrected.json()['impact_receipt']['included_in_index'])
        self.assertEqual(corrected.json()['impact_receipt']['changes']['accepted_observations']['delta'], 1)
        rejected = self.client.post(route, json={'action': 'reject', 'reviewer_note': 'Further inspection shows incorrect specimen provenance.'})
        self.assertEqual(rejected.status_code, 200)
        self.assertEqual(rejected.json()['impact_receipt']['status'], 'reverted')
        self.assertEqual(rejected.json()['impact_receipt']['changes']['accepted_observations']['delta'], -1)
        history = self.client.get(f'/v1/observations/{observation_id}/receipts').json()['receipts']
        self.assertEqual(len(history), 3)
        self.assertEqual(len({r['receipt_id'] for r in history}), 3)
        self.assertEqual(history[0], receipt)
        retried = self.client.post('/v1/observations', json=payload).json()
        self.assertEqual(retried['observation']['state'], 'needs_review')
        self.assertEqual(retried['impact_receipt'], receipt)

    def test_old_and_future_evidence_cannot_enter_current_window(self):
        for date in (datetime.now(timezone.utc) - timedelta(days=45), datetime.now(timezone.utc) + timedelta(hours=1)):
            body = self.submit(self.payload(observed_at=date.isoformat()))
            receipt = body['impact_receipt']
            self.assertFalse(receipt['included_in_index'])
            self.assertTrue(receipt['eligibility_reasons'])
            self.assertEqual(receipt['changes']['accepted_observations']['delta'], 0)

    def test_low_quality_cannot_be_bypassed_by_confirmation(self):
        body = self.submit(self.payload(model='demo-image-assist-1', taxon_confidence=.2, image_quality={'score': .3}))
        observation_id = body['observation']['id']
        response = self.client.post(f'/v1/observations/{observation_id}/review', json={'action': 'confirm', 'reviewer_note': 'Family verified, photographic limitations remain.'})
        self.assertEqual(response.status_code, 200)
        if body['observation']['quality_score'] < .7:
            self.assertFalse(response.json()['impact_receipt']['included_in_index'])


if __name__ == '__main__':
    unittest.main()
