import json
from pathlib import Path
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / 'tools/delivery'))
import issue_preview as issue


class PreviewTests(unittest.TestCase):
    def snapshot(self, site, sha, text='app', tag=None):
        folder = site / 'snapshots' / sha
        (folder / 'app').mkdir(parents=True)
        (folder / 'app/index.html').write_text(text)
        (folder / 'index.html').write_text('Snapshot ' + sha)
        metadata = {'schema': 'pages-preview-v1', 'source_sha': sha,
                    'source_fingerprint': 'e' * 64,
                    'web_content_sha256': issue.preview.digest(issue.preview.hashes(folder / 'app'))}
        if tag:
            metadata['delivery_tag'] = tag
        (folder / 'metadata.json').write_text(json.dumps(metadata))
        (folder / 'files.json').write_text(json.dumps(issue.preview.hashes(folder)))
        return folder

    def test_same_inputs_and_bytes_reuse_existing_snapshot_without_changing_wrapper(self):
        with tempfile.TemporaryDirectory() as d:
            incoming, site = Path(d, 'incoming'), Path(d, 'site')
            sha = 'a' * 40
            original = self.snapshot(site, sha, tag='v1.12.0-rc.1')
            self.snapshot(incoming, sha)
            root = site / 'index.html'; root.write_text('original root')
            before = issue.preview.hashes(site)
            metadata = issue.merge(incoming, site, sha)
            self.assertEqual((original / 'metadata.json').read_text(), json.dumps({
                'schema': 'pages-preview-v1', 'source_sha': sha, 'source_fingerprint': 'e'*64,
                'web_content_sha256': metadata['web_content_sha256'], 'delivery_tag': 'v1.12.0-rc.1'}))
            self.assertEqual(issue.preview.hashes(site), {**before, '.nojekyll': issue.preview.hashes(site)['.nojekyll']})
            self.assertEqual(root.read_text(), 'original root')

    def test_different_bytes_same_sha_are_blocked(self):
        with tempfile.TemporaryDirectory() as d:
            incoming, site = Path(d, 'incoming'), Path(d, 'site')
            sha = 'a'*40
            self.snapshot(site, sha, text='original')
            self.snapshot(incoming, sha, text='different')
            before = issue.preview.hashes(site)
            with self.assertRaisesRegex(ValueError, 'bytes'):
                issue.merge(incoming, site, sha)
            self.assertEqual(before, issue.preview.hashes(site))

    def test_new_snapshot_preserves_old_snapshot_and_root(self):
        with tempfile.TemporaryDirectory() as d:
            incoming, site = Path(d, 'incoming'), Path(d, 'site')
            old, new = 'a'*40, 'b'*40
            self.snapshot(site, old)
            self.snapshot(incoming, new)
            (site / 'index.html').write_text('root original')
            before = issue.preview.hashes(site / 'snapshots' / old)
            issue.merge(incoming, site, new)
            self.assertEqual(before, issue.preview.hashes(site / 'snapshots' / old))
            self.assertEqual((site / 'index.html').read_text(), 'root original')
            self.assertEqual(issue.preview.validate_site(site), [old, new])

    def test_wrong_source_artifact_is_blocked(self):
        with tempfile.TemporaryDirectory() as d:
            incoming, site = Path(d, 'incoming'), Path(d, 'site')
            self.snapshot(incoming, 'a'*40)
            site.mkdir()
            with self.assertRaises(ValueError):
                issue.merge(incoming, site, 'b'*40)

    def flutter_snapshot(self, site, sha, version='123', loader='load', worker='worker'):
        folder = self.snapshot(site, sha)
        (site / 'index.html').write_text('original root')
        (folder / 'app/flutter_bootstrap.js').write_text(
            f'{loader}({{serviceWorkerVersion: "{version}"}});')
        (folder / 'app/flutter_service_worker.js').write_text(worker)
        metadata = json.loads((folder / 'metadata.json').read_text())
        metadata.update(source_tree='f'*40, fingerprint='c'*64, version='1.0.0',
                        source_build_inputs={'flutter': 'pinned'}, pages_build_inputs={'command': 'pinned'},
                        web_content_sha256=issue.preview.digest(issue.preview.hashes(folder / 'app')))
        (folder / 'metadata.json').write_text(json.dumps(metadata))
        (folder / 'files.json').unlink()
        (folder / 'files.json').write_text(json.dumps(issue.preview.hashes(folder)))
        return folder

    def test_flutter_generated_version_reuses_exact_original_bytes_and_manifest(self):
        with tempfile.TemporaryDirectory() as d:
            incoming, site = Path(d, 'incoming'), Path(d, 'site')
            sha = 'a'*40
            original = self.flutter_snapshot(site, sha)
            self.flutter_snapshot(incoming, sha, version='456')
            before = issue.preview.hashes(original)
            with self.assertRaises(ValueError):
                issue.merge(incoming, site, sha)
            result = issue.merge(incoming, site, sha, allow_flutter_cache_version=True)
            self.assertEqual(before, issue.preview.hashes(original))
            self.assertEqual(result['web_content_sha256'], issue.preview.digest(issue.preview.hashes(original / 'app')))
            self.assertEqual(result['snapshot_manifest_sha256'], issue.preview.digest(issue.preview.json_file(original / 'files.json')))
            self.assertFalse(result['reuse_evidence']['published_snapshot_modified'])

    def test_flutter_exception_rejects_worker_loader_inputs_and_ambiguous_versions(self):
        for change in ('worker', 'loader', 'inputs', 'duplicate', 'missing_worker', 'missing_identity'):
            with self.subTest(change=change), tempfile.TemporaryDirectory() as d:
                incoming, site = Path(d, 'incoming'), Path(d, 'site')
                sha = 'a'*40
                original = self.flutter_snapshot(site, sha)
                new = self.flutter_snapshot(incoming, sha, version='456',
                    loader='evil' if change == 'loader' else 'load',
                    worker='changed' if change == 'worker' else 'worker')
                metadata = json.loads((new / 'metadata.json').read_text())
                if change == 'inputs':
                    metadata['pages_build_inputs'] = {'command': 'different'}
                if change == 'missing_identity':
                    del metadata['source_tree']
                if change == 'missing_worker':
                    (new / 'app/flutter_service_worker.js').unlink()
                if change == 'duplicate':
                    with (new / 'app/flutter_bootstrap.js').open('a') as f:
                        f.write('serviceWorkerVersion: "789"')
                metadata['web_content_sha256'] = issue.preview.digest(issue.preview.hashes(new / 'app'))
                (new / 'metadata.json').write_text(json.dumps(metadata))
                (new / 'files.json').unlink()
                (new / 'files.json').write_text(json.dumps(issue.preview.hashes(new)))
                before = issue.preview.hashes(original)
                with self.assertRaises(ValueError):
                    issue.merge(incoming, site, sha, allow_flutter_cache_version=True)
                self.assertEqual(before, issue.preview.hashes(original))


if __name__ == '__main__':
    unittest.main()
