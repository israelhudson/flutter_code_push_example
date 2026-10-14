import copy
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / 'tools/delivery'))
import poc_slack as poc
import release_lab as lab


class FinalReleaseTests(unittest.TestCase):
    def setUp(self):
        self.c = {'id': 'poc-' + 'a'*32, 'version': '1.15.1', 'rc_number': 1,
                  'rc_tag': 'poc-v1.15.1-rc.1', 'source_sha': 'a'*40,
                  'report_digest': 'b'*64, 'publication_scope': 'github_test', 'status': 'published'}
        report = {'title': 'Corrigir login', 'rc_tag': self.c['rc_tag'], 'changelog': '- Renovar sessão',
                  'preview_url': f'https://israelhudson.github.io/flutter_code_push_example/snapshots/{self.c["source_sha"]}/',
                  'platforms': {'android': {'base_release_version': None, 'effective_patch': None}}}
        self.c['report_text'] = lab.canonical(report)
        self.receipt = {'tag': 'poc-v1.15.1', 'source_sha': self.c['source_sha'],
                        'report_digest': self.c['report_digest'], 'release_id': 123,
                        'release_url': 'https://github.com/israelhudson/flutter_code_push_example/releases/tag/poc-v1.15.1'}
        self.release = {'id': 123, 'tag_name': 'poc-v1.15.1', 'name': 'POC Slack — 1.15.1',
                        'html_url': self.receipt['release_url'], 'draft': False, 'prerelease': True,
                        'body': poc.legacy_release_body(self.c), 'published_at': '2026-10-14T00:00:00Z',
                        'assets': [{'id': 456, 'name': 'mobile-receipt.json', 'digest': 'sha256:proof', 'size': 42}]}
        self.writes = []

    def api(self, path, data=None, method='GET', missing=False):
        if '/git/ref/' in path:
            return {'object': {'type': 'commit', 'sha': self.c['source_sha'], 'url': 'fixture'}}
        if method == 'PATCH':
            self.writes.append((method, copy.deepcopy(data)))
            self.release.update({k: v for k, v in data.items() if k != 'make_latest'})
        if method == 'POST':
            self.writes.append((method, copy.deepcopy(data)))
            self.release.update(data)
        return copy.deepcopy(self.release)

    def authorization(self):
        return {'already_published': True, 'receipt': self.receipt}

    def test_explicit_repair_preserves_assets_tags_receipt_and_second_call_is_read_only(self):
        before = copy.deepcopy(self.receipt)
        with tempfile.TemporaryDirectory() as out, patch.object(lab, 'api', side_effect=self.api), \
                patch.object(poc, 'control'), patch.object(lab, 'create_ref_verified') as refs:
            result = poc.finalize_existing(self.c, self.authorization(), out)
            self.assertTrue(result['changed']); self.assertFalse(result['prerelease'])
            self.assertEqual(len(self.writes), 1)
            self.assertEqual(set(self.writes[0][1]), {'body', 'prerelease', 'make_latest'})
            self.assertEqual(self.writes[0][1]['make_latest'], 'false')
            self.assertEqual(self.release['assets'][0]['id'], 456)
            self.assertEqual(self.receipt, before)
            self.assertFalse(poc.finalize_existing(self.c, self.authorization(), out)['changed'])
            self.assertEqual(len(self.writes), 1); refs.assert_not_called()
            self.assertTrue(Path(out, 'release-correction-intent.json').is_file())

    def test_repair_blocks_unpublished_candidate_before_claim(self):
        for state in ('pending', 'approved', 'publishing', 'adjustment_requested'):
            with self.subTest(state=state), tempfile.TemporaryDirectory() as out, patch.object(poc, 'protect'), \
                    patch.object(poc, 'control', return_value={**self.c, 'status': state}) as control, \
                    patch.object(lab, 'api') as api:
                with self.assertRaises(lab.LabError): poc.publish(self.c['id'], out, finalize=True)
                self.assertEqual(control.call_count, 1); api.assert_not_called()

    def test_repair_blocks_drift_in_receipt_release_or_refs(self):
        for field, value in [('release_id', 999), ('source_sha', 'c'*40), ('tag', 'poc-v9.0.0'), ('report_digest', 'c'*64)]:
            with self.subTest(receipt=field), tempfile.TemporaryDirectory() as out, patch.object(lab, 'api') as api:
                auth = self.authorization(); auth['receipt'] = {**self.receipt, field: value}
                if field == 'release_id': api.side_effect = self.api
                with self.assertRaises(lab.LabError): poc.finalize_existing(self.c, auth, out)
                self.assertFalse(self.writes)
        for field, value in [('body', 'Someone edited this'), ('draft', True), ('name', 'Other release'), ('tag_name', 'other')]:
            with self.subTest(release=field), tempfile.TemporaryDirectory() as out, patch.object(lab, 'api', side_effect=self.api):
                old = self.release[field]; self.release[field] = value
                with self.assertRaises(lab.LabError): poc.finalize_existing(self.c, self.authorization(), out)
                self.release[field] = old; self.assertFalse(self.writes)
        with tempfile.TemporaryDirectory() as out, patch.object(lab, 'api', return_value={'object': {'type': 'commit', 'sha': 'c'*40}}):
            with self.assertRaises(lab.LabError): poc.finalize_existing(self.c, self.authorization(), out)

    def test_concurrent_edit_stops_patch(self):
        def api(path, *args, **kwargs):
            if path.endswith('/releases/123'): self.release['body'] = 'Concurrent edit'
            return self.api(path, *args, **kwargs)
        with tempfile.TemporaryDirectory() as out, patch.object(lab, 'api', side_effect=api), patch.object(poc, 'control'):
            with self.assertRaises(lab.LabError): poc.finalize_existing(self.c, self.authorization(), out)
            self.assertFalse(self.writes)

    def test_lost_patch_response_is_reconciled_without_second_mutation(self):
        def api(path, data=None, method='GET', **kwargs):
            result = self.api(path, data, method, **kwargs)
            if method == 'PATCH': raise lab.LabError('response lost')
            return result
        with tempfile.TemporaryDirectory() as out, patch.object(poc, 'control'):
            with patch.object(lab, 'api', side_effect=api), self.assertRaises(lab.LabError):
                poc.finalize_existing(self.c, self.authorization(), out)
            with patch.object(lab, 'api', side_effect=self.api):
                result = poc.finalize_existing(self.c, self.authorization(), out)
            self.assertFalse(result['changed']); self.assertEqual(len(self.writes), 1)

    def test_new_publication_is_final_and_independently_receipted(self):
        def api(path, data=None, method='GET', **kwargs):
            if method == 'GET': return None
            return self.api(path, data, method, **kwargs)
        with tempfile.TemporaryDirectory() as out, patch.object(poc, 'protect'), \
                patch.object(poc, 'control', side_effect=[self.c, {}, {}, {}, {}]) as control, \
                patch.object(lab, 'create_ref_verified') as refs, patch.object(lab, 'api', side_effect=api):
            result = poc.publish(self.c['id'], out)
            self.assertFalse(result['prerelease']); self.assertFalse(result['distribution_performed'])
            self.assertFalse(self.writes[0][1]['prerelease'])
            self.assertEqual(self.writes[0][1]['make_latest'], 'false')
            refs.assert_called_once_with('tags/poc-v1.15.1', self.c['source_sha'])
            self.assertEqual(control.call_args_list[-1].args[0], 'complete')

    def test_new_publication_does_not_silently_accept_old_prerelease(self):
        with tempfile.TemporaryDirectory() as out, patch.object(poc, 'protect'), \
                patch.object(poc, 'control', side_effect=[self.c, {}, {}, {}]) as control, \
                patch.object(lab, 'create_ref_verified'), patch.object(lab, 'api', side_effect=self.api):
            with self.assertRaises(lab.LabError): poc.publish(self.c['id'], out)
            self.assertFalse(self.writes)
            self.assertNotIn('complete', [call.args[0] for call in control.call_args_list])

    def test_notes_are_readable_and_frozen_json_is_not_rewritten(self):
        report = json.loads(self.c['report_text'])
        report['title'] = '<img src=x> @everyone [link](https://invalid) ```'
        self.c['report_text'] = lab.canonical(report)
        body = poc.release_body(self.c)
        self.assertIn('## Release final no GitHub', body)
        self.assertIn('[Abrir preview aprovado](', body)
        self.assertIn('````json\n' + self.c['report_text'] + '\n````', body)
        self.assertNotIn('<img', body.split('<details>')[0])
        self.assertNotIn('@everyone', body.split('<details>')[0])
        self.assertIn('não promove patches', body)


if __name__ == '__main__': unittest.main()
