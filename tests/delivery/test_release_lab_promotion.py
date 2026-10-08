"""Offline integrated rehearsals: real helper/Git, synthetic API and reviewers.

No test can invoke the network: every helper API call must match the emulator.
These scenarios do not count as human GitHub approvals or live distribution.
"""
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


class PromotionFlowTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='release-lab-promotion-test-')
        self.addCleanup(self.temp.cleanup)
        self.world = rehearsal.OfflineWorld(self.temp.name)
        self.addCleanup(self.world.close)

    def prepared(self):
        tag = self.world.prepare()
        self.world.freeze_report(tag)
        return tag

    def authorized(self):
        tag = self.prepared()
        self.world.approve('first', tag)
        self.world.approve('second', tag)
        self.world.authorize()
        return tag

    def test_zero_one_two_approvals_require_separate_command_before_github_promotion(self):
        rehearsal.scenario_happy(self.world)

    def test_rejected_rc1_is_preserved_corrected_rc2_starts_at_zero_and_is_promoted(self):
        rehearsal.scenario_rc_correction(self.world)

    def test_report_tag_release_branch_and_base_drift_do_not_reuse_approvals(self):
        rehearsal.scenario_frozen_identity(self.world)

    def test_conflicting_stable_ref_is_never_moved_or_deleted(self):
        rehearsal.scenario_conflict(self.world)

    def test_lost_responses_and_partial_failure_reconcile_exactly_one_release(self):
        rehearsal.scenario_partial_recovery(self.world)

    def test_old_completed_version_wrong_initiator_rerun_and_bot_are_blocked(self):
        rehearsal.scenario_version_and_identity(self.world)

    def test_interleaved_approval_writers_retry_cas_without_losing_either_receipt(self):
        rehearsal.scenario_concurrent_journal(self.world)

    def test_failed_preview_cannot_produce_report_approval_or_publication(self):
        rehearsal.scenario_failed_preview(self.world)

    def test_removed_rules_after_approvals_and_final_command_prevent_publication_intent(self):
        tag = self.authorized()
        with patch.object(self.world, 'rulesets', return_value=[]), self.assertRaises(lab.LabError):
            self.world.finish(tag)
        self.world.assert_no_publication()
        self.assertNotIn('publication', self.world.state['candidates'][tag])

    def test_removed_rules_after_stable_creation_block_release_and_preserve_partial_intent(self):
        rehearsal.scenario_protection_drift(self.world)

    def test_unowned_stable_tag_at_same_commit_does_not_imply_publication_authority(self):
        tag = self.authorized()
        self.world.refs['tags/v1.4.0'] = self.world.source
        with self.assertRaises(lab.LabError):
            self.world.finish(tag)
        self.assertEqual(self.world.refs['tags/v1.4.0'], self.world.source)
        self.assertEqual(self.world.releases, [])
        self.assertNotIn('receipt', self.world.state['candidates'][tag])

    def test_conflicting_release_name_body_or_state_is_not_patched(self):
        tag = self.authorized()
        self.world.releases.append({'id': 777, 'tag_name': 'v1.4.0',
                                   'name': 'Unrelated existing release',
                                   'body': 'Different source and approvals',
                                   'draft': False, 'prerelease': False})
        original = copy.deepcopy(self.world.releases)
        with self.assertRaises(lab.LabError):
            self.world.finish(tag)
        self.assertEqual(self.world.releases, original)
        self.assertNotIn('receipt', self.world.state['candidates'][tag])
        self.assertFalse(any(c['method'] in ('PATCH', 'DELETE') for c in self.world.calls))

    def test_pending_or_cancelled_review_job_blocks_external_effects_even_if_reviews_exist(self):
        tag = self.authorized()
        self.world.runs[self.world.run_id]['jobs'][1]['conclusion'] = 'cancelled'
        with self.assertRaises(lab.LabError):
            self.world.finish(tag)
        self.world.assert_no_publication()

    def test_publication_failure_keeps_intent_and_blocks_new_candidate(self):
        tag = self.authorized()
        self.world.inject_failure('releases', method='POST', after=False)
        with self.assertRaises(lab.LabError):
            self.world.finish(tag)
        record = self.world.state['candidates'][tag]
        self.assertIn('publication', record)
        self.assertNotIn('receipt', record)
        prior = copy.deepcopy(self.world.refs)
        with self.assertRaises(lab.LabError):
            self.world.prepare('1.5.0')
        self.assertEqual(self.world.refs, prior)

    def test_same_attempt_process_retry_reuses_intent_and_cannot_duplicate_release(self):
        tag = self.authorized()
        self.world.inject_failure('releases', method='POST', after=False)
        with self.assertRaises(lab.LabError):
            self.world.finish(tag)
        intent = self.world.state['candidates'][tag]['publication']['intent_id']
        self.world.finish(tag)
        self.assertEqual(len(self.world.releases), 1)
        self.assertEqual(self.world.state['candidates'][tag]['publication']['intent_id'], intent)
        self.assertIn('receipt', self.world.state['candidates'][tag])

    def test_second_successful_finish_is_idempotent_without_a_second_post(self):
        tag = self.authorized()
        folder = self.world.finish(tag)
        first = json.loads((folder / 'receipt.json').read_text())
        mutations = [c for c in self.world.calls if c['method'] == 'POST']
        folder = self.world.finish(tag)
        second = json.loads((folder / 'receipt.json').read_text())
        self.assertEqual(first, second)
        self.assertEqual(mutations, [c for c in self.world.calls if c['method'] == 'POST'])
        self.assertEqual(len(self.world.releases), 1)

    def test_lost_tag_post_response_is_proven_by_get_before_release_post(self):
        tag = self.authorized()
        self.world.inject_failure('git/refs', method='POST', after=True)
        self.world.finish(tag)
        tag_post = next(i for i, c in enumerate(self.world.calls)
                        if c['path'] == 'git/refs' and c['method'] == 'POST'
                        and c['data']['ref'] == 'refs/tags/v1.4.0')
        release_post = next(i for i, c in enumerate(self.world.calls)
                            if c['path'] == 'releases' and c['method'] == 'POST')
        self.assertTrue(any(c['method'] == 'GET' and c['path'] == 'git/ref/tags/v1.4.0'
                            for c in self.world.calls[tag_post + 1:release_post]))
        self.assertEqual(len(self.world.releases), 1)

    def test_lost_release_post_response_is_read_back_before_receipt(self):
        tag = self.authorized()
        self.world.inject_failure('releases', method='POST', after=True)
        self.world.finish(tag)
        release_post = next(i for i, c in enumerate(self.world.calls)
                            if c['path'] == 'releases' and c['method'] == 'POST')
        after = self.world.calls[release_post + 1:]
        self.assertTrue(any(c['method'] == 'GET' and c['path'] == 'releases/tags/v1.4.0' for c in after))
        self.assertEqual(len(self.world.releases), 1)
        self.assertIn('receipt', self.world.state['candidates'][tag])

    def test_successful_post_without_published_get_proof_cannot_write_receipt(self):
        tag = self.authorized()
        original_route = self.world.route

        def route(path, data, method, missing):
            result = original_route(path, data, method, missing)
            if path == 'releases' and method == 'POST':
                self.world.releases[-1]['published_at'] = None
                self.world.emit('injected_unpublished_readback', note='POST returned an object but GET cannot prove publication')
            return result

        with patch.object(self.world, 'route', side_effect=route), self.assertRaises(lab.LabError):
            self.world.finish(tag)
        self.assertEqual(len(self.world.releases), 1)
        self.assertNotIn('receipt', self.world.state['candidates'][tag])
        self.assertEqual(self.world.state['candidates'][tag]['publication']['status'], 'failed')
        self.assertFalse(any(c['method'] in ('PATCH', 'DELETE') for c in self.world.calls))

    def test_recovery_requires_new_final_decision_and_preserves_original_approval_evidence(self):
        tag = self.authorized()
        original_run = self.world.run_id
        original_reviews = copy.deepcopy(self.world.runs[original_run]['reviews'])
        digest = self.world.state['candidates'][tag]['report_digest']
        self.world.inject_failure('releases', method='POST', after=False)
        with self.assertRaises(lab.LabError):
            self.world.finish(tag)
        self.world.set_run('9020')
        with self.assertRaises(lab.LabError):
            self.world.invoke('recover', tag=tag, report_digest=digest)
        self.assertNotIn('receipt', self.world.state['candidates'][tag])
        self.world.authorize(rehearsal.ISRAEL)
        self.world.invoke('recover', tag=tag, report_digest=digest)
        self.assertEqual(len(self.world.releases), 1)
        self.assertEqual(self.world.runs[original_run]['reviews'], original_reviews)
        self.assertIn('receipt', self.world.state['candidates'][tag])

    def test_recovery_cannot_continue_after_a_correction_changed_release_branch(self):
        tag = self.authorized()
        digest = self.world.state['candidates'][tag]['report_digest']
        self.world.inject_failure('releases', method='POST', after=False)
        with self.assertRaises(lab.LabError):
            self.world.finish(tag)
        self.world.correct_release()
        self.world.set_run('9030')
        self.world.authorize()
        with self.assertRaises(lab.LabError):
            self.world.invoke('recover', tag=tag, report_digest=digest)
        self.assertEqual(self.world.releases, [])
        self.assertNotIn('receipt', self.world.state['candidates'][tag])

    def test_version_comparison_is_numeric_instead_of_lexicographic(self):
        self.assertLess(lab.stable_version('1.9.0'), lab.stable_version('1.10.0'))
        self.assertLess(lab.stable_version('1.99.0'), lab.stable_version('2.0.0'))

    def test_simulated_completion_cannot_replace_the_real_stable_changelog_baseline(self):
        self.world.state = {'schema': 1, 'active': None, 'candidates': {}, 'events': [],
                            'last_completed_source_sha': self.world.source}
        self.world.state_revision = 1
        tag = self.world.prepare()
        self.assertEqual(self.world.state['candidates'][tag]['changelog_base_sha'], self.world.baseline)
        self.assertNotEqual(self.world.source, self.world.baseline)

    def test_lost_response_after_final_cut_journal_commit_returns_the_same_rc(self):
        original_route = self.world.route
        injected = False

        def route(path, data, method, missing):
            nonlocal injected
            result = original_route(path, data, method, missing)
            if (path == 'contents/' + lab.STATE_PATH and method == 'PUT'
                    and self.world.state.get('active') == 'v1.4.0-rc.1' and not injected):
                injected = True
                self.world.emit('injected_final_cut_lost_response', journal_effect_persisted=True)
                raise lab.LabError('Offline lost final cut journal response')
            return result

        with patch.object(self.world, 'route', side_effect=route):
            tag = self.world.prepare()
        self.assertTrue(injected)
        self.assertEqual(tag, 'v1.4.0-rc.1')
        self.assertEqual(set(self.world.state['candidates']), {tag})
        self.assertNotIn('preparation', self.world.state)
        self.assertEqual([ref for ref in self.world.refs if ref.startswith('tags/v') and '-rc.' in ref], ['tags/' + tag])


if __name__ == '__main__':
    unittest.main()
