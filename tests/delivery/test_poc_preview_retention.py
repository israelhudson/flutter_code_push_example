import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / 'tools/delivery'))
import preview_retention as retention
import test_issue_preview as preview_fixture


class RetentionTests(unittest.TestCase):
    def site(self, folder):
        site = Path(folder, 'site')
        fixture = preview_fixture.PreviewTests()
        for i in range(1, 7):
            sha = str(i) * 40
            fixture.snapshot(site, sha, tag='v1.0.0-rc.1' if i == 2 else None)
        (site / 'index.html').write_text('<a href="snapshots/' + '3'*40 + '/">Root</a>')
        subprocess.run(['git', 'init', '-b', retention.pages.HISTORY_BRANCH, str(site)], check=True, capture_output=True)
        for args in (['config', 'user.name', 'Fixture'], ['config', 'user.email', 'fixture@example.test'],
                     ['add', '.'], ['commit', '-m', 'preserved previews']):
            subprocess.run(['git', '-C', str(site), *args], check=True, capture_output=True)
        return site

    def commits(self, path):
        sha = path.rsplit('/', 1)[-1]
        return {'sha': sha, 'commit': {'committer': {'date': '2026-10-0'+sha[0]+'T12:00:00Z'}}}

    def test_archive_preserves_tags_metadata_root_and_latest_two_prs(self):
        with tempfile.TemporaryDirectory() as folder:
            site = self.site(folder)
            with patch.object(retention, 'tagged_commits', return_value={'1'*40}), patch.object(retention.lab, 'api', side_effect=self.commits):
                report = retention.plan(site)
                self.assertEqual(report['archived'], ['4'*40])
                before = {s: retention.pages.hashes(site/'snapshots'/s) for s in report['preserved']}
                retention.apply(site, report)
            for s, hashes in before.items():
                self.assertEqual(retention.pages.hashes(site/'snapshots'/s), hashes)
            self.assertFalse((site/'snapshots'/('4'*40)).exists())
            # Bytes remain in the previous ordinary Git commit, even after removal.
            original = retention.pages.git(site, 'show', report['history_commit']+':snapshots/'+'4'*40+'/app/index.html')
            self.assertEqual(original, 'app')

    def test_new_tag_or_dirty_checkout_blocks_before_removal(self):
        for new_tag in (True, False):
            with self.subTest(new_tag=new_tag), tempfile.TemporaryDirectory() as folder:
                site = self.site(folder)
                with patch.object(retention, 'tagged_commits', return_value={'1'*40}), patch.object(retention.lab, 'api', side_effect=self.commits):
                    report = retention.plan(site)
                if not new_tag: (site/'index.html').write_text('Changed')
                before = retention.pages.hashes(site)
                with patch.object(retention, 'tagged_commits', return_value={'4'*40}), self.assertRaises(ValueError):
                    retention.apply(site, report)
                self.assertEqual(before, retention.pages.hashes(site))

    def test_capacity_blocks_without_removing_release_previews(self):
        with tempfile.TemporaryDirectory() as folder:
            site = self.site(folder)
            before = retention.pages.hashes(site)
            with patch.object(retention, 'tagged_commits', return_value={'1'*40}), \
                    patch.object(retention.lab, 'api', side_effect=self.commits), \
                    patch.object(retention.pages, 'MAX_SITE_BYTES', 1), self.assertRaises(ValueError):
                retention.plan(site)
            self.assertEqual(before, retention.pages.hashes(site))

    def test_incoming_snapshot_is_protected_even_without_tag(self):
        with tempfile.TemporaryDirectory() as folder:
            site = self.site(folder)
            incoming = Path(folder, 'incoming')
            preview_fixture.PreviewTests().snapshot(incoming, '4'*40)
            with patch.object(retention, 'tagged_commits', return_value={'1'*40}), patch.object(retention.lab, 'api', side_effect=self.commits):
                report = retention.plan(site, incoming)
            self.assertNotIn('4'*40, report['archived'])

    def test_annotated_tags_and_pagination_are_resolved(self):
        refs = [{'object': {'type': 'commit', 'sha': 'a'*40}}]*99 + [{'object': {'type': 'tag', 'sha': 'b'*40}}]
        with patch.object(retention.lab, 'api', side_effect=[refs, {'object': {'type': 'commit', 'sha': 'c'*40}}, []]) as api:
            self.assertEqual(retention.tagged_commits(), {'a'*40, 'c'*40})
            self.assertIn('page=2', api.call_args_list[-1].args[0])

    def test_tag_api_failure_does_not_remove_any_preview(self):
        with tempfile.TemporaryDirectory() as folder:
            site = self.site(folder)
            before = retention.pages.hashes(site)
            with patch.object(retention.lab, 'api', side_effect=retention.lab.LabError('Unavailable')), self.assertRaises(retention.lab.LabError):
                retention.plan(site)
            self.assertEqual(before, retention.pages.hashes(site))


if __name__ == '__main__': unittest.main()
