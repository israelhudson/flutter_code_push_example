"""Offline fixtures only: no live approvals, cancellations or publications."""
import copy
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / 'tools/delivery'))
import release_lab as lab
import rehearse_release_lab as rehearsal


class RejectionCloseTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='release-lab-rejection-close-')
        self.addCleanup(self.temp.cleanup)
        self.world = rehearsal.OfflineWorld(self.temp.name)
        self.addCleanup(self.world.close)
        self.tag = self.world.prepare()
        self.world.freeze_report(self.tag)
        self.run_id = self.world.run_id
        self.run = self.world.runs[self.run_id]
        self.run.update(path='.github/workflows/release-lab-prepare.yml', status='waiting',
                        conclusion=None, head_repository={'full_name': lab.REPOSITORY})
        self.cancels = []
        original_api = self.world.api

        def api(path, data=None, method='GET', missing=False):
            if method == 'POST' and path.endswith('/cancel'):
                self.assertEqual(path, lab.endpoint('actions/runs/' + self.run_id + '/cancel'))
                self.assertEqual(self.record()['status'], 'rejected')
                self.assertIn('candidate_rejected', [e['event'] for e in self.record()['slack_events']])
                self.assertNotIn('publication', self.record())
                self.cancels.append(path)
                self.run.update(status='completed', conclusion='cancelled')
                return None  # GitHub returns 202 with an empty response body.
            return original_api(path, data, method, missing)

        self.world.api = api

    def record(self):
        return self.world.state['candidates'][self.tag]

    def reject(self, role='second'):
        person = next(p for p in self.world.policy['approvers'] if p['role'] == role)
        self.run['reviews'] = [rehearsal.synthetic_review(person, person['environment'], 'rejected')]
        self.run['jobs'] = [{'name': 'Avaliar / Gate ' + role, 'conclusion': 'failure'}]

    def close_run(self, run_id=None):
        destination = self.world.invoke('close_rejected_run', evaluation_run_id=run_id or self.run_id)
        return json.loads((destination / 'rejection-close.json').read_text())

    def preserved(self):
        return copy.deepcopy({k: self.record().get(k) for k in
                              ('report', 'report_digest', 'approval_receipts', 'receipt', 'publication')})

    def test_second_rejection_closes_without_waiting_for_the_first_and_preserves_rc(self):
        self.reject()
        evidence, refs = self.preserved(), copy.deepcopy(self.world.refs)
        result = self.close_run()
        self.assertTrue(result['cancel_requested'])
        self.assertEqual(len(self.cancels), 1)
        self.assertEqual(self.record()['status'], 'rejected')
        self.assertEqual(self.record()['approval_progress']['recorded'], 0)
        self.assertEqual(self.preserved(), evidence)
        self.assertEqual(self.world.refs, refs)
        self.assertEqual(self.world.releases, [])
        self.assertFalse(result['approval_or_publication_performed'])
        with self.assertRaises(lab.LabError):
            self.world.approve('first', self.tag)

    def test_first_rejection_closes_without_waiting_for_the_second(self):
        self.reject('first')
        self.assertTrue(self.close_run()['cancel_requested'])
        self.assertEqual(self.record()['status_observation']['rejected_reviews'][0]['user']['login'], 'israelhudson')

    def test_technical_gate_failure_without_official_rejection_never_cancels_or_mutates(self):
        self.run['jobs'] = [{'name': 'Avaliar / Gate second', 'conclusion': 'failure'}]
        before = copy.deepcopy(self.world.state)
        result = self.close_run()
        self.assertEqual(result['reason'], 'no_authorized_gate_rejection')
        self.assertEqual(self.cancels, [])
        self.assertEqual(self.world.state, before)

    def test_other_run_id_is_blocked_before_any_effect(self):
        self.reject()
        before = copy.deepcopy(self.world.state)
        with self.assertRaises(lab.LabError):
            self.close_run('9999')
        self.assertEqual(self.cancels, [])
        self.assertEqual(self.world.state, before)

    def test_changed_original_run_attempt_actor_workflow_or_repository_is_blocked(self):
        self.reject()
        for change in [{'run_attempt': 2}, {'actor': rehearsal.FABRICIA},
                       {'path': '.github/workflows/unrelated.yml'},
                       {'head_repository': {'full_name': 'someone/else'}}]:
            with self.subTest(change=change):
                before = copy.deepcopy(self.run)
                self.run.update(change)
                with self.assertRaises(lab.LabError):
                    self.close_run()
                self.run.clear(); self.run.update(before)
        self.assertEqual(self.cancels, [])

    def test_wrong_gate_id_no_review_and_wrong_reviewer_no_cancel(self):
        self.reject()
        self.run['reviews'][0]['environments'][0]['id'] = 777
        self.assertEqual(self.close_run()['reason'], 'no_authorized_gate_rejection')
        self.reject()
        self.run['reviews'][0]['user'].update(rehearsal.ISRAEL)
        with self.assertRaises(lab.LabError):
            self.close_run()
        self.assertEqual(self.cancels, [])

    def test_terminal_history_receipt_or_publication_intent_is_preserved_without_cancel(self):
        self.reject()
        variants = [{'status': 'completed'}, {'status': 'superseded'}, {'status': 'cancelled'},
                    {'status': 'evaluation_failed'}, {'publication': {'status': 'started'}},
                    {'receipt': {'fixture': 'existing'}}]
        initial = copy.deepcopy(self.record())
        for change in variants:
            with self.subTest(change=change):
                self.record().clear(); self.record().update(copy.deepcopy(initial)); self.record().update(change)
                before = copy.deepcopy(self.world.state)
                result = self.close_run()
                self.assertEqual(result['reason'], 'preserved_terminal_or_publication')
                self.assertEqual(self.world.state, before)
        self.assertEqual(self.cancels, [])

    def test_completed_original_run_does_not_cancel_or_rewrite_candidate(self):
        self.reject()
        self.run.update(status='completed', conclusion='failure')
        before = copy.deepcopy(self.world.state)
        self.assertEqual(self.close_run()['reason'], 'original_run_already_completed')
        self.assertEqual(self.world.state, before)
        self.assertEqual(self.cancels, [])

    def test_new_preparation_intent_is_preserved_without_cancel(self):
        self.reject()
        self.world.state['preparation'] = {'fixture': 'concurrent RC cut'}
        before = copy.deepcopy(self.world.state)
        self.assertEqual(self.close_run()['reason'], 'preserved_terminal_or_publication')
        self.assertEqual(self.world.state, before)
        self.assertEqual(self.cancels, [])

    def test_tampered_report_policy_or_tag_is_blocked(self):
        self.reject()
        original = copy.deepcopy(self.record())
        for change in [{'report_digest': 'f' * 64}, {'policy_digest': 'f' * 64}, {'source_sha': 'a' * 40}]:
            with self.subTest(change=change):
                self.record().clear(); self.record().update(copy.deepcopy(original)); self.record().update(change)
                with self.assertRaises(lab.LabError):
                    self.close_run()
        self.record().clear(); self.record().update(original)
        self.world.refs['tags/' + self.tag] = self.world.baseline
        with self.assertRaises(lab.LabError):
            self.close_run()
        self.assertEqual(self.cancels, [])

    def test_unknown_cancel_response_preserves_proven_rejection_and_never_retries_inside_cas(self):
        self.reject()
        original_api = self.world.api

        def lost_reply(path, data=None, method='GET', missing=False):
            value = original_api(path, data, method, missing)
            if method == 'POST' and path.endswith('/cancel'):
                raise lab.LabError('Offline cancellation reply lost')
            return value

        self.world.api = lost_reply
        with self.assertRaises(lab.LabError):
            self.close_run()
        self.assertEqual(len(self.cancels), 1)
        self.assertEqual(self.record()['status'], 'rejected')
        self.assertTrue(any(e['event'] == 'candidate_rejected' for e in self.record()['slack_events']))
        diagnostic = next(Path(self.temp.name).glob('*-close_rejected_run-output/rejection-close.json'))
        recorded = json.loads(diagnostic.read_text())
        self.assertTrue(recorded['cancel_attempted'])
        self.assertEqual(recorded['cancel_response'], 'unknown')
        self.assertEqual(self.close_run()['reason'], 'original_run_already_completed')
        self.assertEqual(len(self.cancels), 1)

    def test_publication_appearing_during_recheck_prevents_cancellation_and_is_preserved(self):
        self.reject()
        original_change = lab.journal_change

        def racing_change(*args, **kwargs):
            value = original_change(*args, **kwargs)
            self.record()['publication'] = {'status': 'started', 'fixture': 'concurrent'}
            return value

        with patch.object(lab, 'journal_change', side_effect=racing_change):
            self.assertEqual(self.close_run()['reason'], 'preserved_after_recheck')
        self.assertEqual(self.cancels, [])
        self.assertEqual(self.record()['publication']['fixture'], 'concurrent')

    def test_close_requires_original_operator_context_and_default_observer_is_unchanged(self):
        self.reject()
        self.world.env.update(GITHUB_EVENT_NAME='workflow_run', GITHUB_ACTOR='github-actions[bot]',
                              GITHUB_ACTOR_ID='41898282', GITHUB_TRIGGERING_ACTOR='github-actions[bot]')
        lab.validate_context(self.world.policy, 'reconcile-run', self.world.env)
        with self.assertRaises(lab.LabError):
            self.close_run()
        self.assertEqual(self.cancels, [])


if __name__ == '__main__':
    unittest.main()
