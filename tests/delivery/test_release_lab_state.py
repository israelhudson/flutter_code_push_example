"""Local state projection using synthetic REST reviews; no live approvals."""
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


class CandidateStateTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='release-lab-state-test-')
        self.addCleanup(self.temp.cleanup)
        self.world = rehearsal.OfflineWorld(self.temp.name)
        self.addCleanup(self.world.close)
        self.tag = self.world.prepare()
        self.world.freeze_report(self.tag)
        self.world.runs[self.world.run_id].update(
            path='.github/workflows/release-lab-prepare.yml', status='in_progress', conclusion=None)

    def reconcile(self, run_id=None):
        return self.world.invoke('reconcile_run', evaluation_run_id=run_id or self.world.run_id)

    def record(self):
        return self.world.state['candidates'][self.tag]

    def protected(self):
        return copy.deepcopy({k: self.record().get(k) for k in
                              ('report', 'report_digest', 'approval_receipts', 'receipt', 'publication')})

    def refreeze(self, **kwargs):
        # Replace only a synthetic fixture setup; no live frozen candidate is edited.
        self.record().pop('report')
        self.record().pop('report_digest')
        return self.world.invoke('report', tag=self.tag,
                                 smoke_path=Path(self.temp.name) / 'fixture-smoke.json',
                                 metadata_path=Path(self.temp.name) / 'fixture-metadata.json', **kwargs)

    def test_zero_one_and_two_recorded_approvals_have_distinct_waiting_states(self):
        self.assertEqual(self.record()['status'], 'awaiting_approvals')
        self.reconcile()
        self.assertEqual(self.record()['approval_progress']['recorded'], 0)
        self.world.approve('first', self.tag)
        self.assertEqual(self.record()['status'], 'awaiting_approvals')
        self.assertEqual(self.record()['approval_progress']['recorded'], 1)
        self.world.approve('second', self.tag)
        self.assertEqual(self.record()['status'], 'awaiting_publish_authorization')
        self.assertEqual(self.record()['approval_progress']['recorded'], 2)
        with self.assertRaises(lab.LabError):
            self.world.finish(self.tag)
        self.world.assert_no_publication()

    def test_frozen_version_table_and_communication_are_copied_to_release_and_receipt(self):
        report = copy.deepcopy(self.record()['report'])
        self.assertEqual(report['communication']['selection']['source'], 'commits_fallback')
        self.assertEqual(report['version_manifest']['delivery']['candidate_tag'], self.tag)
        self.world.approve('first', self.tag)
        self.world.approve('second', self.tag)
        self.world.authorize()
        self.world.finish(self.tag)
        receipt = self.record()['receipt']
        self.assertEqual(receipt['version_manifest'], report['version_manifest'])
        self.assertEqual(receipt['version_manifest_digest'], report['version_manifest_digest'])
        self.assertEqual(receipt['communication'], report['communication'])
        body = self.world.releases[0]['body']
        self.assertIn('Entrega e versões por plataforma', body)
        self.assertIn('Não distribuído', body)
        self.assertIn(report['communication']['selection']['text'], body)

    def test_invalid_receipt_closes_observation_without_rewriting_the_receipt(self):
        self.world.approve('first', self.tag)
        self.record()['approval_receipts']['first']['source_sha'] = 'f' * 40
        before = self.protected()
        self.reconcile()
        self.assertEqual(self.record()['status'], 'evaluation_failed')
        self.assertEqual(self.protected(), before)
        self.assertTrue(self.record()['status_observation']['invalid_receipts'])

    def test_frozen_summary_hash_mismatch_is_blocked_before_creating_a_publication_intent(self):
        self.record()['report']['communication']['selection']['text'] = 'changed after freeze'
        self.record()['report_digest'] = lab.digest(self.record()['report'])
        with self.assertRaises(ValueError):
            self.world.approve('first', self.tag)
        self.assertNotIn('publication', self.record())
        self.world.assert_no_publication()

    def test_long_or_large_commit_history_is_preserved_without_blocking_required_report(self):
        raw = ['feat: ' + 'x' * 700, 'feat: subject with control \x01'] + [f'fix: fixture {i}' for i in range(1001)]
        original_git = self.world.git

        def git(*args):
            if args[0] == 'log':
                return '\n'.join(raw)
            return original_git(*args)

        with patch.object(self.world, 'git', side_effect=git):
            self.refreeze()
        self.assertEqual(self.record()['report']['changes'], raw)
        selected = lab.changelog_summary.verify_communication(self.record()['report'])
        self.assertLessEqual(len(selected['text']), 1400)
        self.assertEqual(self.record()['report_digest'], lab.digest(self.record()['report']))

    def test_available_matching_pr_context_is_frozen_without_waiting_for_ai(self):
        value = self.record()['report']
        context = lab.changelog_summary.freeze_context(value, sources=[
            {'kind': 'pr', 'id': '17', 'url': 'https://github.com/' + lab.REPOSITORY + '/pull/17',
             'title': 'Tema manual', 'body': '## O que muda para quem usa\nEscolher tema claro ou escuro no topo.\n\n## Como validar\nTrocar o tema e reiniciar.'}])
        with patch.object(lab.changelog_summary, 'read_available_context',
                          return_value=(context, {'status': 'available', 'waited_for_result': False})) as read:
            self.refreeze(context_artifact='release-lab-context')
        read.assert_called_once_with(self.world.run_id, artifact_name='release-lab-context', budget_seconds=3)
        selected = self.record()['report']['communication']['selection']
        self.assertEqual(selected['source'], 'pr_sections')
        self.assertIn('Escolher tema claro ou escuro', selected['text'])
        self.assertEqual(self.record()['report']['communication_context_observation']['status'], 'available')

    def test_context_from_a_different_rc_is_ignored_with_immediate_commit_fallback(self):
        wrong = copy.deepcopy(self.record()['report']['communication']['context'])
        wrong['candidate_tag'] = 'v1.4.0-rc.2'
        with patch.object(lab.changelog_summary, 'read_available_context',
                          return_value=(wrong, {'status': 'available', 'waited_for_result': False})):
            self.refreeze(context_artifact='release-lab-context')
        self.assertEqual(self.record()['report']['communication']['selection']['source'], 'commits_fallback')
        self.assertEqual(self.record()['report']['communication_context_observation']['status'], 'invalid_context_ignored')

    def test_future_dated_optional_context_cannot_block_required_report(self):
        future = lab.changelog_summary.freeze_context(self.record()['report'], collected_at='2099-01-01T00:00:00Z')
        with patch.object(lab.changelog_summary, 'read_available_context',
                          return_value=(future, {'status': 'available', 'waited_for_result': False})):
            self.refreeze(context_artifact='release-lab-context')
        self.assertEqual(self.record()['report']['communication']['selection']['source'], 'commits_fallback')
        self.assertEqual(self.record()['report']['communication_context_observation']['status'], 'invalid_context_ignored')

    def test_official_review_without_receipt_does_not_create_approval(self):
        self.world.runs[self.world.run_id]['reviews'] = [
            rehearsal.synthetic_review(rehearsal.ISRAEL, 'aprovacao-israel'),
            rehearsal.synthetic_review(rehearsal.FABRICIA, 'aprovacao-fahnassau30')]
        before = self.protected()
        self.reconcile()
        self.assertEqual(self.record()['status'], 'awaiting_approvals')
        self.assertEqual(self.record()['approval_progress']['recorded'], 0)
        self.assertEqual(self.protected(), before)

    def test_rejected_review_is_registered_without_modifying_frozen_material(self):
        self.world.approve('first', self.tag)
        self.world.runs[self.world.run_id]['reviews'].append(
            rehearsal.synthetic_review(rehearsal.FABRICIA, 'aprovacao-fahnassau30', 'rejected'))
        before = self.protected()
        self.reconcile()
        self.assertEqual(self.record()['status'], 'rejected')
        self.assertEqual(self.protected(), before)
        with self.assertRaises(lab.LabError):
            self.world.finish(self.tag)
        self.world.assert_no_publication()

    def test_cancelled_original_run_is_registered_after_its_finalizer_cannot_run(self):
        original_run = self.world.run_id
        self.world.runs[original_run].update(status='completed', conclusion='cancelled')
        self.world.set_run('9999')  # A separate completion observer reads original REST data.
        before = self.protected()
        self.reconcile(original_run)
        self.assertEqual(self.record()['status'], 'cancelled')
        self.assertEqual(self.record()['status_observation']['run_id'], original_run)
        self.assertEqual(self.protected(), before)

    def test_failed_preview_job_closes_evaluation_without_publishing(self):
        self.world.runs[self.world.run_id]['jobs'] = [
            {'name': 'Avaliar a mesma candidata / Publicar bytes verificados, confirmar preview e changelog',
             'conclusion': 'failure'}]
        before = self.protected()
        self.reconcile()
        self.assertEqual(self.record()['status'], 'evaluation_failed')
        self.assertEqual(self.protected(), before)
        self.world.assert_no_publication()

    def test_optional_slack_failure_does_not_close_an_otherwise_waiting_evaluation(self):
        self.world.runs[self.world.run_id]['jobs'] = [
            {'name': 'ILUSTRAR AVISO SLACK — simulação, sem envio', 'conclusion': 'failure'}]
        self.reconcile()
        self.assertEqual(self.record()['status'], 'awaiting_approvals')

    def test_concurrent_second_approval_is_not_overwritten_by_older_reconciliation(self):
        self.world.approve('first', self.tag)
        original_route, raced = self.world.route, False

        def route(path, data, method, missing):
            nonlocal raced
            if path == 'contents/' + lab.STATE_PATH and method == 'PUT' and not raced:
                raced = True
                self.world.approve('second', self.tag)
            return original_route(path, data, method, missing)

        with patch.object(self.world, 'route', side_effect=route):
            folder = self.reconcile()
        self.assertTrue(raced)
        self.assertEqual(self.record()['status'], 'awaiting_publish_authorization')
        self.assertEqual(self.record()['approval_progress']['recorded'], 2)
        self.assertEqual(set(self.record()['approval_receipts']), {'first', 'second'})
        self.assertIn('2/2 recibos', (folder / 'candidate-status.md').read_text())

    def test_failed_or_cancelled_evaluation_cannot_reopen_after_later_observation(self):
        self.world.runs[self.world.run_id].update(status='completed', conclusion='cancelled')
        self.reconcile()
        self.world.runs[self.world.run_id].update(status='in_progress', conclusion=None)
        self.reconcile()
        self.assertEqual(self.record()['status'], 'cancelled')
        with self.assertRaises(lab.LabError):
            self.world.approve('first', self.tag)

    def test_superseded_candidate_history_is_not_rewritten_by_late_completion(self):
        original_run = self.world.run_id
        self.world.set_run('9002')
        second = self.world.prepare()
        self.assertNotEqual(second, self.tag)
        prior = copy.deepcopy(self.world.state)
        folder = self.reconcile(original_run)
        value = json.loads((folder / 'candidate-status.json').read_text())
        self.assertFalse(value['updated'])
        self.assertEqual(self.world.state, prior)

    def test_completed_release_survives_a_failed_evidence_upload_job(self):
        self.world.approve('first', self.tag)
        self.world.approve('second', self.tag)
        self.world.authorize()
        self.world.finish(self.tag)
        self.world.runs[self.world.run_id].update(status='completed', conclusion='failure')
        prior = copy.deepcopy(self.world.state)
        self.reconcile()
        self.assertEqual(self.world.state, prior)
        self.assertEqual(self.record()['status'], 'completed')

    def test_partial_publication_failure_is_preserved_for_explicit_recovery(self):
        self.world.approve('first', self.tag)
        self.world.approve('second', self.tag)
        self.world.authorize()
        self.world.inject_failure('releases', method='POST', after=False)
        with self.assertRaises(lab.LabError):
            self.world.finish(self.tag)
        before = self.protected()
        self.world.runs[self.world.run_id].update(status='completed', conclusion='failure')
        self.reconcile()
        self.assertEqual(self.record()['status'], 'publication_failed')
        self.assertEqual(self.protected(), before)

    def test_preparation_error_with_no_registered_evaluation_changes_no_candidate(self):
        prior = copy.deepcopy(self.world.state)
        folder = self.reconcile('123456')
        self.assertEqual(self.world.state, prior)
        self.assertEqual(json.loads((folder / 'candidate-status.json').read_text())['reason'],
                         'no_registered_candidate')

    def test_wrong_actor_rerun_or_untrusted_workflow_cannot_write_observational_state(self):
        run = self.world.runs[self.world.run_id]
        prior_run = copy.deepcopy(run)
        for changes in ({'actor': rehearsal.FABRICIA}, {'run_attempt': 2},
                        {'path': '.github/workflows/arbitrary.yml'},
                        {'head_repository': {'full_name': 'someone/fork'}}):
            with self.subTest(changes=changes):
                run.update(changes)
                prior = copy.deepcopy(self.world.state)
                with self.assertRaises(lab.LabError):
                    self.reconcile()
                self.assertEqual(self.world.state, prior)
                run.clear(); run.update(copy.deepcopy(prior_run))

    def test_completion_observer_context_cannot_be_used_by_a_manual_effectful_command(self):
        env = {**self.world.env, 'GITHUB_EVENT_NAME': 'workflow_run',
               'GITHUB_ACTOR': 'github-actions', 'GITHUB_ACTOR_ID': '41898282',
               'GITHUB_TRIGGERING_ACTOR': 'github-actions'}
        lab.validate_context(self.world.policy, 'reconcile-run', env)
        with self.assertRaises(lab.LabError):
            lab.validate_context(self.world.policy, 'finish', env)
        with self.assertRaises(lab.LabError):
            lab.validate_context(self.world.policy, 'reconcile-run',
                                 {**env, 'GITHUB_EVENT_NAME': 'workflow_dispatch'})

    def test_state_finalizer_uses_always_and_completion_observer_has_no_artifact_input(self):
        root = Path(__file__).resolve().parents[2]
        evaluator = (root / '.github/workflows/release-lab-evaluate.yml').read_text()
        finalizer = evaluator.split('  finalize_status:\n', 1)[1]
        self.assertIn("if: ${{ always() && needs.preflight.result == 'success' }}", finalizer)
        self.assertIn('approve_first, approve_second, authorize_publish, publish]', finalizer)
        observer = (root / '.github/workflows/release-lab-reconcile.yml').read_text()
        self.assertIn('types: [completed]', observer)
        self.assertIn('ref: refs/heads/main', observer)
        self.assertNotIn('actions/download-artifact@', observer)
        self.assertNotIn('environment:', observer)
        self.assertNotIn('pages: write', observer)
        context_job = evaluator.split('  changelog_context:\n', 1)[1].split('  web:\n', 1)[0]
        self.assertIn('continue-on-error: true', context_job)
        web_job = evaluator.split('  web:\n', 1)[1].split('  slack_preview:\n', 1)[0]
        self.assertIn('needs: [preflight, build]', web_job)
        self.assertNotIn('needs: [preflight, build, changelog_context]', web_job)


if __name__ == '__main__':
    unittest.main()
