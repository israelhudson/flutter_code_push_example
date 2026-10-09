"""A Slack illustration renders frozen source text; it never sends a message."""
from copy import deepcopy
import hashlib
import json
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / 'tools/delivery'))
import changelog_summary as summary
import slack_preview as slack


def report():
    sha = 'a' * 40
    return {'candidate_tag': 'v1.7.0-rc.1', 'source_sha': sha,
            'changelog_base_sha': 'b' * 40, 'run_id': '123456', 'title': 'Tema manual', 'presentation_schema': 2,
            'publication_mode': 'github_release_only', 'changes': ['feat: tema manual'],
            'preview': {'success': True, 'source_sha': sha,
                        'snapshot_url': 'https://israelhudson.github.io/flutter_code_push_example/snapshots/' + sha + '/'}}


def policy():
    people = [{'login': 'israelhudson'}, {'login': 'fahnassau30'}]
    return {'repository': 'israelhudson/flutter_code_push_example',
            'approvers': people, 'publishers': deepcopy(people)}


class SlackPreviewTests(unittest.TestCase):
    def test_schema_two_commit_fallback_uses_presentation_aliases(self):
        payload, markdown, metadata = slack.render_preview(report(), policy())
        self.assertFalse(metadata['message_sent'])
        self.assertEqual(metadata['summary_source'], 'commits_fallback')
        self.assertIn('Aprovador 1 E Aprovador 2', markdown)
        self.assertIn('Aprovador 1 OU Aprovador 2', markdown)
        self.assertIn('gate final separado', markdown)
        self.assertIn('SIMULAÇÃO', payload['text'])

    def test_unversioned_legacy_preview_keeps_exact_baseline_payload_hash(self):
        value = report()
        value.pop('presentation_schema')
        payload, markdown, _ = slack.render_preview(value, policy())
        raw = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(',', ':')).encode()
        self.assertEqual(hashlib.sha256(raw).hexdigest(),
                         '53cb55a9c354ebc6a69071b5995c0b1a67762186a7576ae4c99e80a99af535ae')
        self.assertIn('israelhudson E fahnassau30', markdown)
        self.assertFalse(any(block['type'] == 'actions' for block in payload['blocks']))

    def test_only_integer_two_uses_new_presentation_and_one_keeps_legacy(self):
        value = report()
        value.pop('presentation_schema')
        legacy = slack.render_preview(value, policy())[0]
        value['presentation_schema'] = 1
        self.assertEqual(slack.render_preview(value, policy())[0], legacy)
        for schema in (True, 2.0, '2', 3):
            value['presentation_schema'] = schema
            with self.subTest(schema=schema), self.assertRaises(ValueError):
                slack.render_preview(value, policy())

    def test_readable_blocks_have_dividers_three_url_buttons_and_accessible_fallback(self):
        value = report()
        payload, markdown, _ = slack.render_preview(value, policy())
        actions = [block for block in payload['blocks'] if block['type'] == 'actions']
        self.assertEqual(len(actions), 1)
        self.assertEqual([button['text']['text'] for button in actions[0]['elements']],
                         ['Preview', 'Changelog', 'Revisar GitHub'])
        self.assertGreaterEqual(sum(block['type'] == 'divider' for block in payload['blocks']), 2)
        for button in actions[0]['elements']:
            self.assertIn(button['url'], payload['text'])
            self.assertTrue(button['accessibility_label'])
            self.assertNotIn('value', button)
            self.assertNotIn('action_id', button)
        self.assertIn('Aprovador 1', markdown)
        self.assertNotIn('fahnassau30', markdown)
        self.assertNotIn('israelhudson E', markdown)
        self.assertLessEqual(len(payload['text']), 4000)

    def test_plain_text_mentions_are_escaped_in_accessible_fallback(self):
        value = report()
        value['title'] = '<@U123> <!channel>'
        payload, _, _ = slack.render_preview(value, policy())
        self.assertIn('&lt;@U123&gt;', payload['text'])
        self.assertTrue(all(block['text']['type'] == 'plain_text' for block in payload['blocks']
                            if block['type'] == 'section'))

    def test_frozen_pr_sections_are_labelled_without_claiming_ai_generated_them(self):
        value = report()
        context = summary.freeze_context(value, [{'kind': 'pr', 'id': '17',
            'url': 'https://github.com/israelhudson/flutter_code_push_example/pull/17',
            'title': 'Tema', 'body': '## O que muda para o usuário\nAlterne claro e escuro.\n## Como validar\nToque no botão.'}])
        value['communication'] = summary.frozen_communication(value, context=context)
        _, markdown, metadata = slack.render_preview(value, policy())
        self.assertIn('texto copiado; sem IA', markdown)
        self.assertIn('Alterne claro e escuro.', markdown)
        self.assertEqual(metadata['summary_source'], 'pr_sections')
        self.assertEqual(metadata['context_sha256'], context['context_sha256'])

    def test_modified_selected_summary_is_refused(self):
        value = report()
        value['communication'] = summary.frozen_communication(value)
        value['communication']['selection']['text'] = 'Publicado sem autorização'
        with self.assertRaises(ValueError):
            slack.render_preview(value, policy())

    def test_summary_for_different_rc_is_refused_even_with_valid_digest(self):
        value = report()
        other = report()
        other['candidate_tag'] = 'v1.7.0-rc.2'
        value['communication'] = summary.frozen_communication(other)
        with self.assertRaises(ValueError):
            slack.render_preview(value, policy())

    def test_long_commit_history_is_truncated_before_slack_limit(self):
        value = report()
        value['changes'] = ['x' * 500] * 50
        payload, markdown, _ = slack.render_preview(value, policy())
        self.assertLess(len(payload['blocks'][0]['text']['text']), 3000)
        self.assertIn('Histórico completo', markdown)

    def test_long_subjects_and_controls_do_not_turn_optional_notice_into_failure(self):
        value = report()
        value['changes'] = ['x' * 700 + '\x1b\nsubject'] + ['later'] * 1001
        for frozen in (False, True):
            with self.subTest(frozen=frozen):
                if frozen:
                    value['communication'] = summary.frozen_communication(value)
                payload, markdown, _ = slack.render_preview(value, policy())
                self.assertLess(len(payload['blocks'][0]['text']['text']), 3000)
                self.assertNotIn('\x1b', markdown)
                self.assertIn('Histórico completo', markdown)

    def test_wrong_preview_or_source_is_refused(self):
        for mutation in ({'success': False}, {'source_sha': 'c' * 40},
                         {'snapshot_url': 'https://evil.example/snapshot'}):
            with self.subTest(mutation=mutation):
                value = report()
                value['preview'].update(mutation)
                with self.assertRaises(ValueError):
                    slack.render_preview(value, policy())

    def test_credentials_are_not_read_or_inserted_in_the_artifact(self):
        with patch.dict(os.environ, {'SLACK_WEBHOOK_URL': 'fixture-secret-never-use',
                                     'SLACK_BOT_TOKEN': 'fixture-secret-never-use'}):
            output = slack.render_preview(report(), policy())
        self.assertNotIn('fixture-secret-never-use', json.dumps(output))

    def test_send_option_does_not_exist(self):
        with self.assertRaises(SystemExit) as exit_info:
            slack.main(['--send'])
        self.assertEqual(exit_info.exception.code, 2)

    def test_cli_preserves_frozen_report_and_writes_preview(self):
        with tempfile.TemporaryDirectory() as temp:
            folder = Path(temp)
            original = json.dumps(report())
            (folder / 'report.json').write_text(original)
            (folder / 'policy.json').write_text(json.dumps(policy()))
            self.assertEqual(slack.main(['--report', str(folder / 'report.json'),
                '--policy', str(folder / 'policy.json'), '--output', str(folder / 'out')]), 0)
            self.assertEqual((folder / 'report.json').read_text(), original)
            metadata = json.loads((folder / 'out/slack-preview-metadata.json').read_text())
            self.assertFalse(metadata['message_sent'])


if __name__ == '__main__':
    unittest.main()
