"""Readable notes retain frozen evidence and do not regenerate source claims."""
from copy import deepcopy
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / 'tools/delivery'))
import changelog_summary as summary
import release_notes as notes


def report():
    return {'candidate_tag': 'v1.10.0-rc.1', 'source_sha': 'a' * 40,
            'changelog_base_sha': 'b' * 40, 'title': 'Tema do aplicativo',
            'changes': ['feat: selecionar tema claro ou escuro', 'fix(theme): preservar escolha ao reiniciar']}


class BriefNotesTests(unittest.TestCase):
    def test_commit_fallback_has_few_literal_topics_and_never_mutates_report(self):
        value = report()
        before = deepcopy(value)
        result = notes.brief_notes(value)
        self.assertEqual(value, before)
        self.assertEqual(result['source'], 'commits_fallback')
        self.assertEqual(result['changes'], ['selecionar tema claro ou escuro', 'preservar escolha ao reiniciar'])
        self.assertTrue(3 <= len(result['description']) <= 4)
        self.assertFalse(result['truncated'])

    def test_frozen_pr_description_and_caveats_are_selected_literally(self):
        value = report()
        context = summary.freeze_context(value, [{'kind': 'pr', 'id': '17',
            'url': 'https://github.com/israelhudson/flutter_code_push_example/pull/17',
            'title': 'Tema', 'body': '## O que muda para quem usa\nEscolha tema claro ou escuro.\n'
                                     '## Como validar\nTroque o tema e reinicie.\n'
                                     '## Limitações\nPreview web; sem distribuição mobile.'}])
        value['communication'] = summary.frozen_communication(value, context=context)
        result = notes.brief_notes(value)
        self.assertIn('Escolha tema claro ou escuro.', result['description'])
        self.assertEqual(result['validation'], ['Troque o tema e reinicie.'])
        self.assertEqual(result['limitations'], ['Preview web; sem distribuição mobile.'])
        self.assertEqual(result['source'], 'pr_sections')

    def test_selection_modified_or_from_another_candidate_is_rejected(self):
        for different_candidate in (False, True):
            value = report()
            other = deepcopy(value)
            if different_candidate:
                other['candidate_tag'] = 'v1.10.0-rc.2'
            value['communication'] = summary.frozen_communication(other)
            if not different_candidate:
                value['communication']['selection']['text'] = 'Trocado após o freeze'
            with self.subTest(different_candidate=different_candidate), self.assertRaises(ValueError):
                notes.brief_notes(value)

    def test_long_history_is_bounded_without_dropping_original_data(self):
        value = report()
        value['changes'] = ['feat: ' + str(i) + ' ' + 'x' * 700 + '\x1b\nsubject' for i in range(1100)]
        before = deepcopy(value)
        result = notes.brief_notes(value)
        self.assertEqual(len(result['changes']), 4)
        self.assertTrue(all(len(row) <= 150 for row in result['changes']))
        self.assertTrue(result['truncated'])
        self.assertNotIn('\x1b', str(result))
        self.assertEqual(value, before)

    def test_empty_commit_history_remains_explicit(self):
        value = report()
        value['changes'] = []
        self.assertIn('Sem commits adicionais', notes.brief_notes(value)['changes'][0])

    def test_presentation_aliases_follow_roles_without_changing_account_identity(self):
        policy = {'approvers': [{'login': 'fahnassau30', 'id': 2, 'role': 'second'},
                                {'login': 'israelhudson', 'id': 1, 'role': 'first'}]}
        before = deepcopy(policy)
        self.assertEqual(notes.approver_labels(policy), ['Aprovador 2', 'Aprovador 1'])
        self.assertEqual(policy, before)


if __name__ == '__main__':
    unittest.main()
