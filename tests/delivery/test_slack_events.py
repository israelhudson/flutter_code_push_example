"""Candidate transition/notification fixtures; no real Slack or approvals."""
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
import slack_events as events
import slack_outbox


class SlackEventsTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='slack-events-fixture-')
        self.addCleanup(self.temp.cleanup)
        self.world = rehearsal.OfflineWorld(self.temp.name)
        self.addCleanup(self.world.close)
        self.tag = self.world.prepare('1.7.0')
        self.world.freeze_report(self.tag)
        self.world.runs[self.world.run_id].update(path='.github/workflows/release-lab-prepare.yml',
                                                  status='in_progress', conclusion=None)

    def record(self, tag=None):
        return self.world.state['candidates'][tag or self.tag]

    def api(self, path, data=None, method='GET', missing=False):
        self.assertEqual(method, 'GET', 'Rendering/verifying notices must be read-only')
        value = self.world.api(path, data, method, missing)
        if '/git/ref/tags/' in path:
            value['object']['type'] = 'commit'
        return value

    def drain(self, tag=None, render_only=True, sender=None):
        with patch.object(lab, 'ROOT', self.world.repo), patch.object(lab, 'git', side_effect=self.world.git):
            kwargs = {'state': copy.deepcopy(self.world.state), 'api': self.api, 'render_only': render_only}
            if sender: kwargs['sender'] = sender
            return events.drain(self.world.policy, tag or self.tag, Path(self.temp.name)/'notice-output', **kwargs)

    def queued(self, tag=None):
        return [e['event'] for e in self.record(tag)['slack_events']]

    def test_candidate_is_queued_only_after_report_and_keeps_commit_fallback(self):
        self.assertEqual(self.queued(), ['candidate_available'])
        before = copy.deepcopy(self.world.state)
        result = self.drain()
        self.assertEqual(result['results'][0]['state'], 'rendered')
        self.assertEqual(self.world.state, before)
        item = self.record()['slack_events'][0]
        notice = events.render_event(self.world.policy, self.record(), item)
        slack_outbox.validate_notice(notice)
        self.assertIn('histórico de commits', notice['payload']['text'])
        self.assertEqual(notice['identity']['run_id'], self.world.run_id)

    def test_one_approval_then_two_approvals_queue_distinct_milestones_without_publish(self):
        self.world.approve('second', self.tag)
        self.assertEqual(self.queued(), ['candidate_available', 'approval_second'])
        self.assertEqual(self.record()['approval_progress']['recorded'], 1)
        self.drain()
        self.world.approve('first', self.tag)
        self.assertEqual(self.queued(), ['candidate_available', 'approval_second', 'approval_first', 'approvals_complete'])
        self.assertEqual(self.record()['status'], 'awaiting_publish_authorization')
        result = self.drain()
        self.assertEqual(len(result['results']), 4)
        self.world.assert_no_publication()
        text = events.render_event(self.world.policy, self.record(), self.record()['slack_events'][1])['payload']['text']
        self.assertIn('Marco histórico', text)
        self.assertNotIn('Aguardando 1/2', text)

    def test_two_approvals_do_not_queue_publication_before_final_command(self):
        self.world.approve('first', self.tag); self.world.approve('second', self.tag)
        self.assertNotIn('publication_completed', self.queued())
        with self.assertRaises(lab.LabError): self.world.finish(self.tag)
        self.world.assert_no_publication()

    def test_promotion_notice_requires_real_release_and_same_final_receipt(self):
        self.world.approve('first', self.tag); self.world.approve('second', self.tag)
        self.world.authorize(); self.world.finish(self.tag)
        self.assertIn('publication_completed', self.queued())
        self.drain()
        self.record()['receipt']['source_sha'] = 'f'*40
        with self.assertRaises(lab.LabError): self.drain()

    def test_rejection_is_historical_and_new_rc_has_own_frozen_identity(self):
        self.world.runs[self.world.run_id]['reviews'].append(
            rehearsal.synthetic_review(rehearsal.FABRICIA, 'aprovacao-fahnassau30', 'rejected'))
        self.world.invoke('reconcile_run', evaluation_run_id=self.world.run_id)
        self.assertIn('candidate_rejected', self.queued())
        self.drain()
        first_key = events.render_event(self.world.policy, self.record(), self.record()['slack_events'][0])['event_key']
        self.world.correct_release('1.7.0')
        self.world.set_run('1702')
        new = self.world.prepare('1.7.0'); self.world.freeze_report(new)
        self.world.runs[self.world.run_id].update(path='.github/workflows/release-lab-prepare.yml')
        self.assertEqual(self.record(new).get('approval_receipts', {}), {})
        self.assertIn('candidate_superseded', self.queued())
        second_key = events.render_event(self.world.policy, self.record(new), self.record(new)['slack_events'][0])['event_key']
        self.assertNotEqual(first_key, second_key)
        self.drain(new)

    def test_legacy_delivery_and_failed_unfrozen_preview_are_not_backfilled(self):
        self.record().pop('notification_schema')
        self.assertEqual(self.drain()['results'], [])
        self.record()['notification_schema'] = 1
        self.record()['slack_events'] = []
        self.record().pop('report'); self.record().pop('report_digest')
        self.assertEqual(self.drain()['results'], [])

    def test_altered_tag_report_run_or_queued_pointer_is_blocked_before_sender(self):
        baseline = copy.deepcopy(self.record())
        for key, replacement in [('report_digest', 'f'*64), ('evaluation_run_id', '909090'), ('source_sha', 'f'*40)]:
            with self.subTest(key=key):
                self.record()[key] = replacement
                with self.assertRaises(lab.LabError): self.drain()
                self.world.state['candidates'][self.tag] = copy.deepcopy(baseline)
        self.record()['slack_events'][0]['source_sha'] = 'e'*40
        with self.assertRaises(lab.LabError): self.drain()

    def test_cancelled_run_is_queued_and_worker_does_not_reopen_the_candidate(self):
        self.world.runs[self.world.run_id].update(status='completed', conclusion='cancelled')
        self.world.invoke('reconcile_run', evaluation_run_id=self.world.run_id)
        self.assertIn('candidate_cancelled', self.queued())
        before = copy.deepcopy(self.world.state)
        self.drain()
        self.assertEqual(self.world.state, before)

    def test_all_queued_events_are_drained_not_only_the_last_trigger(self):
        self.world.approve('first', self.tag); self.world.approve('second', self.tag)
        seen = []
        def sender(notice, output):
            slack_outbox.validate_notice(notice)
            seen.append(notice['event'])
            return {'state': 'sent', 'duplicate': False, 'ts': '123.456'}
        result = self.drain(render_only=False, sender=sender)
        self.assertEqual(seen, self.queued())
        self.assertEqual(len(result['results']), 4)


if __name__ == '__main__':
    unittest.main()
