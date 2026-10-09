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


if __name__ == '__main__':
    unittest.main()
