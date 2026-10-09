"""Frozen communication boundaries; provider results below are local fixtures."""
from copy import deepcopy
import json
import io
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch
import subprocess
import zipfile

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / 'tools/delivery'))
import changelog_summary as summary


COLLECTED = '2026-10-09T01:00:00Z'
SELECTED = '2026-10-09T01:01:00Z'


def report():
    return {'candidate_tag': 'v1.7.0-rc.1', 'source_sha': 'a' * 40,
            'changelog_base_sha': 'b' * 40,
            'changes': ['feat: tema manual', 'docs: guia de validação']}


def source():
    return {'kind': 'pr', 'id': '17',
            'url': 'https://github.com/israelhudson/flutter_code_push_example/pull/17',
            'title': 'Tema manual',
            'body': '## O que muda para o usuário\nÉ possível alternar tema claro e escuro.\n'
                    '## Como validar\nAlterne os temas e reinicie o app.\n'
                    '## Limitações\nA escolha não é salva.\n'
                    '## Registro técnico\nClasse MainApp modificada.'}


def ai_result(context):
    return {'status': 'completed', 'candidate_tag': context['candidate_tag'],
            'source_sha': context['source_sha'], 'context_sha256': context['context_sha256'],
            'text': 'Agora você pode alternar tema claro e escuro pelo botão do topo.',
            'source_ids': ['17'], 'provider': 'fixture-only', 'model': 'fixture-model',
            'prompt_revision': '1', 'finished_at': '2026-10-09T01:00:30Z'}


class FrozenCommunicationTests(unittest.TestCase):
    def test_no_context_is_immediate_commit_fallback(self):
        value = summary.frozen_communication(report(), selected_at=SELECTED)
        self.assertEqual(value['selection']['source'], 'commits_fallback')
        self.assertIn('feat: tema manual', value['selection']['text'])
        self.assertEqual(value['selection']['fallback_reason'], 'ai_not_configured')

    def test_explicit_pr_sections_are_copied_without_technical_section(self):
        context = summary.freeze_context(report(), [source()], COLLECTED)
        selection = summary.select_summary(context, selected_at=SELECTED)
        self.assertEqual(selection['source'], 'pr_sections')
        self.assertIn('A escolha não é salva.', selection['text'])
        self.assertNotIn('Classe MainApp', selection['text'])

    def test_technical_title_is_not_rewritten_as_a_product_claim(self):
        item = source()
        item['body'] = '## Registro técnico\nrefactor: move classes'
        context = summary.freeze_context(report(), [item], COLLECTED)
        selection = summary.select_summary(context, selected_at=SELECTED)
        self.assertEqual(selection['source'], 'commits_fallback')

    def test_source_edit_after_collect_does_not_mutate_snapshot(self):
        item = source()
        context = summary.freeze_context(report(), [item], COLLECTED)
        item['body'] = 'Texto posterior'
        self.assertIn('É possível alternar', context['sources'][0]['body'])
        self.assertNotIn('Texto posterior', json.dumps(context))

    def test_context_from_other_rc_or_changed_commit_interval_is_refused(self):
        context = summary.freeze_context(report(), [source()], COLLECTED)
        for key, value in (('candidate_tag', 'v1.7.0-rc.2'), ('source_sha', 'c' * 40),
                           ('changelog_base_sha', 'd' * 40), ('changes', ['Outro histórico'])):
            with self.subTest(key=key):
                other = report()
                other[key] = value
                with self.assertRaises(ValueError):
                    summary.frozen_communication(other, context=context, selected_at=SELECTED)

    def test_tampered_source_description_fails_hash_verification(self):
        context = summary.freeze_context(report(), [source()], COLLECTED)
        context['sources'][0]['body'] = 'Fonte trocada depois da revisão'
        with self.assertRaises(ValueError):
            summary.verified_context(report(), context)

    def test_duplicate_sources_or_invalid_url_fail(self):
        for sources in ([source(), source()], [dict(source(), url='http://github.com/x')],
                        [dict(source(), url='https://user:secret@example.com/pr')]):
            with self.subTest(sources=sources):
                with self.assertRaises(ValueError):
                    summary.freeze_context(report(), sources, COLLECTED)

    def test_valid_result_requires_exact_identity_sources_and_provider_metadata(self):
        context = summary.freeze_context(report(), [source()], COLLECTED)
        value = summary.select_summary(context, ai_result(context), SELECTED)
        self.assertEqual(value['source'], 'ai')
        self.assertEqual(value['optional_result_status'], 'selected')
        self.assertEqual(value['ai']['provider'], 'fixture-only')

    def test_late_result_is_evidence_only_even_if_it_arrives_during_revision(self):
        context = summary.freeze_context(report(), [source()], COLLECTED)
        result = ai_result(context)
        result['finished_at'] = '2026-10-09T01:02:00Z'
        value = summary.select_summary(context, result, SELECTED)
        self.assertEqual(value['source'], 'commits_fallback')
        self.assertEqual(value['optional_result_status'], 'late_result')
        self.assertNotIn(result['text'], value['text'])
        self.assertEqual(value['optional_result_sha256'], summary.digest(result))

    def test_fractional_seconds_do_not_make_late_ai_result_look_early(self):
        context = summary.freeze_context(report(), [source()], COLLECTED)
        result = ai_result(context)
        result['finished_at'] = '2026-10-09T01:01:00.999Z'
        value = summary.select_summary(context, result, '2026-10-09T01:01:00.001Z')
        self.assertEqual(value['optional_result_status'], 'late_result')

    def test_old_rc_result_never_attaches_to_new_rc(self):
        context = summary.freeze_context(report(), [source()], COLLECTED)
        result = ai_result(context)
        result['candidate_tag'] = 'v1.6.0-rc.1'
        value = summary.select_summary(context, result, SELECTED)
        self.assertEqual(value['source'], 'commits_fallback')
        self.assertEqual(value['optional_result_status'], 'identity_mismatch')

    def test_ai_failure_timeout_or_no_credit_use_commits_instead_of_pr_sections(self):
        context = summary.freeze_context(report(), [source()], COLLECTED)
        for state in ('disabled', 'failed', 'timeout', 'running', 'no_access', 'no_credits'):
            with self.subTest(state=state):
                value = summary.select_summary(context, {'status': state}, SELECTED)
                self.assertEqual(value['source'], 'commits_fallback')
                self.assertEqual(value['optional_result_status'], state)
                self.assertIn('feat: tema manual', value['text'])

    def test_missing_timestamp_invalid_sources_or_metadata_are_fallback(self):
        context = summary.freeze_context(report(), [source()], COLLECTED)
        for key, value in (('finished_at', None), ('source_ids', ['unknown']),
                           ('text', 'x' * (summary.SUMMARY_LIMIT + 1)), ('model', '')):
            with self.subTest(key=key):
                result = ai_result(context)
                result[key] = value
                selected = summary.select_summary(context, result, SELECTED)
                self.assertEqual(selected['source'], 'commits_fallback')
                self.assertEqual(selected['optional_result_status'], 'invalid_result')

    def test_oversized_pr_sections_fall_back_without_dropping_limitations(self):
        sources = [dict(source(), id=str(index), body=source()['body'] * 2) for index in range(8)]
        context = summary.freeze_context(report(), sources, COLLECTED)
        self.assertEqual(summary.select_summary(context, selected_at=SELECTED)['source'], 'commits_fallback')

    def test_long_commit_history_is_bounded_and_links_back_to_full_report(self):
        value = report()
        value['changes'] = ['x' * 500] * 20
        selection = summary.frozen_communication(value, selected_at=SELECTED)['selection']
        self.assertLessEqual(len(selection['text']), summary.SUMMARY_LIMIT)
        self.assertIn('Histórico completo', selection['text'])

    def test_legitimate_long_or_control_character_commit_history_never_blocks_freeze(self):
        value = report()
        value['changes'] = ['x' * 700 + '\x1b\nsubject'] + ['another commit'] * 1001
        original = deepcopy(value)
        communication = summary.frozen_communication(value, selected_at=SELECTED)
        context = communication['context']
        self.assertTrue(context['history_truncated'])
        self.assertEqual(context['commit_count'], 1002)
        self.assertEqual(context['source_history_sha256'], summary.digest(value['changes']))
        self.assertEqual(len(context['changes']), 1000)
        self.assertLessEqual(len(context['changes'][0]), 500)
        self.assertNotIn('\x1b', context['changes'][0])
        self.assertEqual(value, original)
        value['communication'] = communication
        self.assertEqual(summary.verify_communication(value)['source'], 'commits_fallback')

    def test_frozen_selection_cannot_be_replaced_without_hash_change(self):
        value = report()
        value['communication'] = summary.frozen_communication(value, selected_at=SELECTED)
        summary.verify_communication(value)
        value['communication']['selection']['text'] = 'Mudança posterior'
        with self.assertRaises(ValueError):
            summary.verify_communication(value)

    def test_cli_writes_copies_and_does_not_modify_source_report(self):
        with tempfile.TemporaryDirectory() as temp:
            folder = Path(temp)
            original = json.dumps(report())
            (folder / 'report.json').write_text(original)
            status = summary.main(['--report', str(folder / 'report.json'), '--output', str(folder / 'out')])
            self.assertEqual(status, 0)
            self.assertEqual((folder / 'report.json').read_text(), original)
            self.assertTrue((folder / 'out/communication.json').is_file())


class OptionalCollectionTests(unittest.TestCase):
    def pull(self, number=17, merge_sha='a' * 40, merged=True, repo=summary.REPOSITORY):
        return {'number': number, 'merge_commit_sha': merge_sha,
                'merged_at': COLLECTED if merged else None, 'title': source()['title'],
                'body': source()['body'], 'base': {'repo': {'full_name': repo}}}

    def git_results(self):
        return ['feat: tema manual\n', 'a' * 40 + '\n']

    def test_collects_only_merged_pr_in_exact_commit_interval(self):
        pulls = [self.pull(), self.pull(number=18, merged=False),
                 self.pull(number=19, merge_sha='c' * 40),
                 self.pull(number=20, repo='someone/else')]
        with patch.object(summary.subprocess, 'check_output', side_effect=self.git_results()), \
                patch.object(summary.subprocess, 'run', return_value=subprocess.CompletedProcess([], 0, json.dumps(pulls), '')) as api:
            value, context, metadata = summary.collect_pr_context(report(), Path('.'))
        self.assertEqual([item['id'] for item in context['sources']], ['17'])
        self.assertEqual(value['changes'], ['feat: tema manual'])
        self.assertEqual(metadata['ai_requests'], 0)
        self.assertLessEqual(api.call_args.kwargs['timeout'], 3)
        self.assertEqual(api.call_args.args[0][0:2], ['gh', 'api'])

    def test_api_timeout_preserves_commits_without_retaining_token_stderr(self):
        error = subprocess.TimeoutExpired(['gh', 'api'], 3, stderr='credential-must-not-log')
        with patch.object(summary.subprocess, 'check_output', side_effect=self.git_results()), \
                patch.object(summary.subprocess, 'run', side_effect=error):
            value, context, metadata = summary.collect_pr_context(report(), Path('.'))
        self.assertEqual(context['sources'], [])
        self.assertIn('feat: tema manual', summary.select_summary(context)['text'])
        self.assertNotIn('credential-must-not-log', json.dumps(metadata))

    def test_collector_enforces_total_budget_without_waiting_for_other_commits(self):
        git = ['first\nsecond\n', 'a' * 40 + '\n' + 'c' * 40 + '\n']
        with patch.object(summary.subprocess, 'check_output', side_effect=git), \
                patch.object(summary.time, 'monotonic', side_effect=[0, 21]), \
                patch.object(summary.subprocess, 'run') as api:
            _, context, metadata = summary.collect_pr_context(report(), Path('.'))
        api.assert_not_called()
        self.assertIn('pr_collection_budget_exceeded', metadata['errors'])
        self.assertEqual(context['changes'], ['first', 'second'])

    def test_cli_collector_writes_context_without_touching_candidate(self):
        with tempfile.TemporaryDirectory() as temp:
            folder = Path(temp)
            (folder / 'candidate.json').write_text(json.dumps(report()))
            with patch.object(summary.subprocess, 'check_output', side_effect=self.git_results()), \
                    patch.object(summary.subprocess, 'run', return_value=subprocess.CompletedProcess([], 0, '[]', '')):
                status = summary.main(['--collect-candidate', str(folder / 'candidate.json'),
                                       '--repo', str(folder), '--output', str(folder / 'out')])
            self.assertEqual(status, 0)
            self.assertTrue((folder / 'out/context.json').is_file())
            self.assertFalse(json.loads((folder / 'out/collection.json').read_text())['provider_active'])


class OpportunisticArtifactTests(unittest.TestCase):
    def archive(self, files=None):
        stream = io.BytesIO()
        with zipfile.ZipFile(stream, 'w') as archive:
            for name, body in (files or {'context.json': json.dumps(summary.freeze_context(report()))}).items():
                archive.writestr(name, body)
        return stream.getvalue()

    def listing(self, **kwargs):
        item = {'id': 123, 'name': 'release-lab-context', 'expired': False,
                'size_in_bytes': 1000, 'workflow_run': {'id': 999}, **kwargs}
        return json.dumps({'artifacts': [item]}).encode()

    def responses(self, listing, archive=None):
        values = [listing] + ([archive] if archive is not None else [])
        return [subprocess.CompletedProcess([], 0, value, b'') for value in values]

    def test_available_context_read_is_bounded_and_linked_to_same_run(self):
        with patch.object(summary.subprocess, 'run', side_effect=self.responses(self.listing(), self.archive())) as api:
            context, observation = summary.read_available_context('999')
        self.assertEqual(context['candidate_tag'], report()['candidate_tag'])
        self.assertEqual(observation['status'], 'available')
        self.assertEqual(api.call_count, 2)
        self.assertLessEqual(api.call_args.kwargs['timeout'], 3)

    def test_missing_artifact_never_polls_or_downloads(self):
        with patch.object(summary.subprocess, 'run', side_effect=self.responses(b'{"artifacts":[]}')) as api:
            context, observation = summary.read_available_context('999')
        self.assertIsNone(context)
        self.assertEqual(observation['status'], 'not_ready')
        self.assertEqual(api.call_count, 1)

    def test_timeout_is_fallback_not_delivery_exception(self):
        with patch.object(summary.subprocess, 'run', side_effect=subprocess.TimeoutExpired([], 3)):
            context, observation = summary.read_available_context('999')
        self.assertIsNone(context)
        self.assertEqual(observation['status'], 'timeout')

    def test_different_run_or_expired_or_oversized_metadata_prevent_download(self):
        for changes in ({'workflow_run': {'id': 123}}, {'expired': True}, {'size_in_bytes': 600000}):
            with self.subTest(changes=changes), \
                    patch.object(summary.subprocess, 'run', side_effect=self.responses(self.listing(**changes))) as api:
                context, observation = summary.read_available_context('999')
            self.assertIsNone(context)
            self.assertEqual(observation['status'], 'invalid_or_unavailable')
            self.assertEqual(api.call_count, 1)

    def test_traversal_duplicate_context_or_zip_bomb_are_refused_without_extracting(self):
        invalid = [{'../context.json': '{}'}, {'context.json': '{}', 'other/context.json': '{}'},
                   {'context.json': 'x' * 600000}]
        for files in invalid:
            with self.subTest(files=list(files)), \
                    patch.object(summary.subprocess, 'run', side_effect=self.responses(self.listing(), self.archive(files))):
                context, observation = summary.read_available_context('999')
            self.assertIsNone(context)
            self.assertEqual(observation['status'], 'invalid_or_unavailable')

    def test_request_cannot_select_another_artifact_or_unbounded_timeout(self):
        with patch.object(summary.subprocess, 'run') as api:
            for kwargs in ({'run_id': 'anything'}, {'run_id': '999', 'artifact_name': 'other'},
                           {'run_id': '999', 'budget_seconds': 40}):
                context, observation = summary.read_available_context(**kwargs)
                self.assertIsNone(context)
                self.assertEqual(observation['status'], 'invalid_request')
        api.assert_not_called()


if __name__ == '__main__':
    unittest.main()
