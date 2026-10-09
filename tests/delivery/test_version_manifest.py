"""Delivery/catalog versions must not impersonate installed app or patch versions."""
import copy
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'tools/delivery'))
import version_manifest as versions

SOURCE = 'a' * 40
APP_ID = '11111111-2222-3333-4444-555555555555'


class VersionManifestTests(unittest.TestCase):
    def setUp(self):
        self.args = {'candidate_tag': 'v1.7.0-rc.2', 'stable_tag': 'v1.7.0',
                     'source_sha': SOURCE, 'pubspec_version': '1.1.0+2', 'platforms': {},
                     'preview': {'success': True, 'source_sha': SOURCE,
                                 'web_content_sha256': 'b' * 64, 'snapshot_manifest_sha256': 'c' * 64,
                                 'snapshot_url': versions.PREVIEW_ORIGIN + SOURCE + '/'}}

    def test_delivery_version_and_web_metadata_have_independent_identity(self):
        manifest = versions.build_manifest(**self.args)
        self.assertEqual(manifest['delivery']['stable_tag'], 'v1.7.0')
        self.assertEqual(manifest['pubspec_metadata']['release_version'], '1.1.0+2')
        self.assertEqual(manifest['platforms']['web']['build_id'], SOURCE)
        self.assertIsNone(manifest['platforms']['android']['planned_app_version'])
        self.assertIsNone(manifest['platforms']['ios']['planned_app_version'])
        self.assertFalse(manifest['distribution_performed'])

    def test_platforms_may_have_different_exact_shorebird_bases(self):
        self.args['platforms'] = {
            'android': {'base': {'release_version': '2.4.0+81', 'source_sha': 'd' * 40, 'app_id': APP_ID, 'flavor': 'production'}},
            'ios': {'base': {'release_version': '2.3.2+76', 'source_sha': 'e' * 40, 'app_id': APP_ID, 'flavor': 'production'}}}
        manifest = versions.build_manifest(**self.args)
        self.assertEqual(manifest['platforms']['android']['planned_app_version']['release_version'], '2.4.0+81')
        self.assertEqual(manifest['platforms']['ios']['planned_app_version']['release_version'], '2.3.2+76')
        for platform in ('android', 'ios'):
            item = manifest['platforms'][platform]
            self.assertEqual(item['shorebird_base']['verification'], 'configured_unverified')
            self.assertIsNone(item['patch_number'])
            self.assertIsNone(item['observed_app_version'])
        text = versions.render_markdown(manifest)
        self.assertIn('2.4.0+81', text)
        self.assertIn('2.3.2+76', text)
        self.assertIn('Não gerado', text)

    def test_patch_identity_includes_app_platform_base_and_number(self):
        android = versions.patch_identity(APP_ID, 'android', '2.4.0+81', 3)
        ios = versions.patch_identity(APP_ID, 'ios', '2.3.2+76', 3)
        self.assertNotEqual(android, ios)
        self.assertNotEqual(android, versions.patch_identity(APP_ID, 'android', '2.4.0+82', 3))
        self.assertNotEqual(android, versions.patch_identity('aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee', 'android', '2.4.0+81', 3))

    def test_patch_identification_refuses_web_latest_implicit_build_and_fake_numbers(self):
        for platform, base, number in [('web', '2.4.0+81', 3), ('android', 'latest', 3),
                                       ('android', '2.4.0', 3), ('ios', '2.4.0+81', 0),
                                       ('ios', '2.4.0+81', True), ('ios', '2.4.0+81', '3')]:
            with self.subTest(platform=platform, base=base, number=number), self.assertRaises(ValueError):
                versions.patch_identity(APP_ID, platform, base, number)
        with self.assertRaises(ValueError):
            versions.patch_identity(None, 'android', '2.4.0+81', 3)

    def test_delivery_ref_and_source_cannot_drift(self):
        for key, bad in [('candidate_tag', 'v1.7.0'), ('stable_tag', 'v1.7.1'), ('source_sha', 'main')]:
            with self.subTest(key=key), self.assertRaises(ValueError):
                versions.build_manifest(**{**self.args, key: bad})

    def test_failed_or_different_preview_cannot_become_version_evidence(self):
        for key, bad in [('success', False), ('source_sha', 'd' * 40),
                         ('snapshot_url', 'https://other.example/'), ('web_content_sha256', None)]:
            with self.subTest(key=key), self.assertRaises(ValueError):
                versions.build_manifest(**{**self.args, 'preview': {**self.args['preview'], key: bad}})

    def test_mobile_input_is_not_an_observed_provider_result(self):
        for base in ('latest', {'release_version': 'latest', 'source_sha': SOURCE},
                     {'release_version': '2.4.0+81', 'source_sha': 'main'}):
            with self.subTest(base=base), self.assertRaises(ValueError):
                versions.build_manifest(**{**self.args, 'platforms': {'android': {'base': base}}})
        with self.assertRaises(ValueError):
            versions.build_manifest(**{**self.args, 'platforms': {'web': {}}})

    def test_validating_frozen_plan_rejects_fabricated_mobile_delivery(self):
        original = versions.build_manifest(**self.args)
        for key, bad in [('patch_number', 1), ('patch_status', 'generated'),
                         ('distribution_status', 'published'), ('observed_app_version', '2.4.0+81'),
                         ('provider_receipt', {'success': True})]:
            forged = copy.deepcopy(original)
            forged['platforms']['android'][key] = bad
            with self.subTest(key=key), self.assertRaisesRegex(ValueError, 'inventar'):
                versions.validate_manifest(forged)
        original['distribution_performed'] = True
        with self.assertRaisesRegex(ValueError, 'recibo'):
            versions.validate_manifest(original)

    def test_web_does_not_acquire_shorebird_patch_or_an_altered_app_version(self):
        for key, bad in [('patch_number', 1), ('shorebird_status', 'available'),
                         ('app_version', versions.split_app_version('2.4.0+81'))]:
            manifest = versions.build_manifest(**self.args)
            manifest['platforms']['web'][key] = bad
            with self.subTest(key=key), self.assertRaises(ValueError):
                versions.validate_manifest(manifest)
        manifest = versions.build_manifest(**self.args)
        manifest['pubspec_metadata']['build_number'] = '999'
        with self.assertRaisesRegex(ValueError, 'pubspec'):
            versions.validate_manifest(manifest)

    def test_offline_cli_writes_both_machine_manifest_and_readable_table(self):
        with tempfile.TemporaryDirectory(prefix='versions-cli-') as folder:
            root = Path(folder)
            report = {**self.args, 'pubspec_version': self.args['pubspec_version']}
            source = root / 'report.json'
            source.write_text(json.dumps(report))
            result = subprocess.run([sys.executable, str(ROOT / 'tools/delivery/version_manifest.py'),
                                     '--report', str(source), '--output', str(root / 'out')],
                                    capture_output=True, text=True)
            self.assertEqual(result.returncode, 0, result.stderr)
            metadata = json.loads(result.stdout)
            manifest = json.loads((root / 'out/version-manifest.json').read_text())
            self.assertEqual(metadata['version_manifest_digest'], versions.digest(manifest))
            self.assertIn('Não distribuído', (root / 'out/version-manifest.md').read_text())
            self.assertFalse(metadata['distribution_performed'])


if __name__ == '__main__':
    unittest.main()
