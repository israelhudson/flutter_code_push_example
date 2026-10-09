"""Pages retention and artifact boundaries, with a synthetic compiler only."""
import importlib.util
import json
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest
from unittest.mock import patch

from test_snapshots import Repository

ROOT = Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location('pages_preview', ROOT / 'deploy/pages_preview.py')
pages = importlib.util.module_from_spec(spec)
spec.loader.exec_module(pages)


class PagesPreviewTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='pages-test-')
        self.addCleanup(self.temp.cleanup)
        self.folder = Path(self.temp.name)
        self.repo = Repository(self.folder / 'repo')
        self.inputs = json.loads((ROOT / 'delivery/build-inputs.json').read_text())
        self.repo.write('delivery/build-inputs.json', json.dumps(self.inputs))
        self.sha = self.repo.commit('fixed build inputs')
        self.repo.git('checkout', '--detach', self.sha)
        self.site = self.folder / 'site'
        self.run = subprocess.run

    def compile(self, sha=None, extra_file=None, delivery_tag=None, candidate_manifest=None):
        def fake_run(args, **kwargs):
            if args[0] != 'flutter':
                return self.run(args, **kwargs)
            self.assertNotIn('GH_TOKEN', kwargs['env'])
            if args[1] == 'build':
                output = self.repo.path / 'build/web'
                output.mkdir(parents=True, exist_ok=True)
                (output / 'index.html').write_text('<html>synthetic compiled fixture</html>')
                (output / 'main.dart.js').write_text('compiled fixture ' + (sha or self.sha))
                (output / '.last_build_id').write_text('flutter-build-control-id')
                if extra_file:
                    (output / extra_file).parent.mkdir(parents=True, exist_ok=True)
                    (output / extra_file).write_text('not a public asset')
                self.assertEqual(args[-1], '--base-href=' + pages.PROJECT_BASE + 'snapshots/' + (sha or self.sha) + '/app/')
            return subprocess.CompletedProcess(args, 0)
        version = {'frameworkVersion': self.inputs['flutter_version'], 'frameworkRevision': self.inputs['flutter_revision']}
        with patch.object(pages.subprocess, 'check_output', return_value=json.dumps(version).encode()), \
                patch.object(pages.subprocess, 'run', side_effect=fake_run):
            return pages.build(self.repo.path, sha or self.sha, self.site, delivery_tag, candidate_manifest)

    def test_delivery_is_visible_separately_from_app_metadata(self):
        metadata = self.compile(delivery_tag='v1.7.0-rc.1')
        wrapper = (self.site / 'snapshots' / self.sha / 'index.html').read_text()
        self.assertIn('Criado para a entrega <strong>v1.7.0-rc.1</strong>', wrapper)
        self.assertIn('metadado do app no build web: ' + metadata['version'], wrapper)
        self.assertEqual(metadata['delivery_tag'], 'v1.7.0-rc.1')

    def test_frozen_candidate_must_identify_the_same_source_and_tag(self):
        candidate = self.folder / 'candidate.json'
        candidate.write_text(json.dumps({'candidate_tag': 'v1.7.0-rc.1', 'source_sha': self.sha}))
        metadata = self.compile(candidate_manifest=candidate)
        self.assertEqual(metadata['delivery_tag'], 'v1.7.0-rc.1')
        before = pages.hashes(self.site)
        candidate.write_text(json.dumps({'candidate_tag': 'v1.7.0-rc.1', 'source_sha': 'a' * 40}))
        with self.assertRaisesRegex(ValueError, 'Manifesto congelado'):
            self.compile(candidate_manifest=candidate)
        self.assertEqual(pages.hashes(self.site), before)
        candidate.write_text(json.dumps({'candidate_tag': 'v1.7.0-rc.2', 'source_sha': self.sha}))
        with self.assertRaisesRegex(ValueError, 'Manifesto congelado'):
            self.compile(delivery_tag='v1.7.0-rc.1', candidate_manifest=candidate)

    def test_same_sha_in_another_candidate_preserves_original_snapshot_identity(self):
        original = self.compile(delivery_tag='v1.7.0-rc.1')
        before = pages.hashes(self.site / 'snapshots' / self.sha)
        reused = self.compile(delivery_tag='v1.7.0-rc.2')
        self.assertEqual(reused, original)
        self.assertEqual(pages.hashes(self.site / 'snapshots' / self.sha), before)
        self.assertIn('pode ser reutilizado por outra candidata',
                      (self.site / 'snapshots' / self.sha / 'index.html').read_text())

    def test_invalid_delivery_tag_is_rejected_before_build(self):
        with self.assertRaisesRegex(ValueError, 'tag RC'):
            self.compile(delivery_tag='<script>latest</script>')
        self.assertFalse(self.site.exists())

    def test_snapshot_metadata_matches_code_and_preserves_ci_identity(self):
        metadata = self.compile()
        self.assertEqual(metadata['source_sha'], self.sha)
        self.assertEqual(metadata['source_fingerprint'], pages.source_fingerprint(self.repo.path, self.sha, self.inputs))
        self.assertNotEqual(metadata['pages_build_inputs']['command'], metadata['source_build_inputs']['command'])
        self.assertIn(self.sha, (self.site / 'snapshots' / self.sha / 'index.html').read_text())
        self.assertEqual(pages.validate_site(self.site), [self.sha])
        snapshot = self.site / 'snapshots' / self.sha
        self.assertEqual(metadata['snapshot_manifest_sha256'], pages.digest(pages.json_file(snapshot / 'files.json')))
        self.assertNotIn('snapshot_manifest_sha256', pages.json_file(snapshot / 'metadata.json'))

    def test_flutter_build_marker_is_not_published(self):
        self.compile()
        self.assertTrue((self.repo.path / 'build/web/.last_build_id').is_file())
        self.assertFalse((self.site / 'snapshots' / self.sha / 'app/.last_build_id').exists())
        self.assertNotIn('app/.last_build_id', pages.json_file(self.site / 'snapshots' / self.sha / 'files.json'))

    def test_other_hidden_files_are_still_rejected(self):
        for name in ('.env', '.unknown-marker', 'assets/.last_build_id'):
            with self.subTest(name=name), self.assertRaisesRegex(ValueError, 'oculto'):
                self.compile(extra_file=name)
            shutil.rmtree(self.site)
            (self.repo.path / 'build/web' / name).unlink()

    def test_existing_snapshot_reuses_bytes_without_rebuilding(self):
        original = self.compile()
        with patch.object(pages.subprocess, 'check_output', side_effect=AssertionError('must not rebuild')):
            self.assertEqual(pages.build(self.repo.path, self.sha, self.site), original)

    def test_new_snapshot_retains_previous_and_updates_root(self):
        original = self.compile()
        old_hash = pages.hashes(self.site / 'snapshots' / self.sha)
        newer = self.repo.change('lib/main.dart', 'void main() { print("next"); }\n')
        self.repo.git('checkout', '--detach', newer)
        self.compile(newer)
        self.assertEqual(pages.hashes(self.site / 'snapshots' / self.sha), old_hash)
        self.assertEqual(pages.json_file(self.site / 'snapshots' / self.sha / 'metadata.json'),
                         {key: value for key, value in original.items() if key != 'snapshot_manifest_sha256'})
        self.assertEqual(len(pages.validate_site(self.site)), 2)
        self.assertIn(newer, (self.site / 'index.html').read_text())

    def test_existing_bytes_cannot_be_replaced(self):
        self.compile()
        (self.site / 'snapshots' / self.sha / 'app/main.dart.js').write_text('unexpected replacement')
        with self.assertRaisesRegex(ValueError, 'alterado'):
            pages.build(self.repo.path, self.sha, self.site)

    def test_export_excludes_git_and_blocks_state(self):
        self.compile()
        (self.site / '.git').mkdir()
        (self.site / '.git/internal-secret').write_text('not public')
        output = self.folder / 'public'
        pages.export(self.site, output)
        self.assertFalse((output / '.git').exists())
        self.assertEqual(pages.validate_site(output), [self.sha])
        (self.site / 'state.sqlite').write_text('not web')
        with self.assertRaisesRegex(ValueError, 'Estado/segredo'):
            pages.export(self.site, self.folder / 'blocked')

    def test_mutable_checkout_and_unknown_sha_are_rejected(self):
        self.repo.git('checkout', 'main')
        with self.assertRaisesRegex(ValueError, 'detached'):
            pages.build(self.repo.path, self.sha, self.site)
        with self.assertRaisesRegex(ValueError, 'SHA40'):
            pages.build(self.repo.path, 'main', self.site)

    def test_site_rejects_links_and_banks_hidden_as_assets(self):
        self.compile()
        folder = self.site / 'snapshots' / self.sha / 'app'
        (folder / 'link').symlink_to('/outside/private/file')
        with self.assertRaisesRegex(ValueError, 'symlinks'):
            pages.validate_site(self.site)
        (folder / 'link').unlink()
        (folder / 'innocent.bin').write_bytes(b'SQLite format 3\x00other')
        with self.assertRaisesRegex(ValueError, 'SQLite'):
            pages.validate_site(self.site)


if __name__ == '__main__':
    unittest.main()
