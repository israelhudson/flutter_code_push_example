import copy
from datetime import datetime, timezone
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / 'tools/delivery'))
from policy import REQUIRED, assert_record_change, decide, digest, preview_usable
from preview import fingerprint
import github_delivery as delivery

HEAD = 'a' * 40


def review(login=REQUIRED[0], state='APPROVED', sha=HEAD, n=1):
    return {'id': n, 'user': {'login': login}, 'state': state, 'commit_id': sha}


class ApprovalTests(unittest.TestCase):
    def test_zero_one_and_two(self):
        reviews = []
        for count in range(3):
            result = decide(reviews, HEAD, 'author')
            self.assertEqual(result['count'], count)
            self.assertEqual(result['allowed'], count == 2)
            if count < 2:
                reviews.append(review(REQUIRED[count], n=count + 1))

    def test_same_person_twice_cannot_approve_alone(self):
        self.assertFalse(decide([review(n=1), review(n=2)], HEAD, 'author')['allowed'])

    def test_other_people_and_author_cannot_substitute(self):
        self.assertEqual(decide([review('ian'), review('israelhudson')], HEAD, 'author')['count'], 0)
        self.assertEqual(decide([review()], HEAD, REQUIRED[0])['count'], 0)

    def test_commit_change_invalidates_approvals(self):
        self.assertFalse(decide([review(u) for u in REQUIRED], 'b' * 40, 'author')['allowed'])

    def test_dismissal_and_changes_requested_revoke(self):
        for state in ('DISMISSED', 'CHANGES_REQUESTED'):
            self.assertEqual(decide([review(), review(state=state, n=2)], HEAD, 'author')['count'], 0)

    def test_comment_does_not_revoke_and_api_order_does_not_matter(self):
        self.assertEqual(decide([review(state='COMMENTED', n=2), review()], HEAD, 'author')['count'], 1)

    def test_reapproval_after_changes(self):
        self.assertEqual(decide([review(state='CHANGES_REQUESTED'), review(n=2)], HEAD, 'author')['count'], 1)

    def test_bot_and_pending_do_not_count(self):
        self.assertEqual(decide([review('samuelcamilo[bot]'), review(state='PENDING')], HEAD, 'author')['count'], 0)

    def test_only_one_new_manifest(self):
        assert_record_change([{'filename': 'record', 'status': 'added'}], 'record')
        for files in ([], [{'filename': 'workflow', 'status': 'added'}],
                      [{'filename': 'record', 'status': 'modified'}],
                      [{'filename': 'record', 'status': 'added'}] * 2):
            with self.assertRaises(ValueError):
                assert_record_change(files, 'record')

    def test_record_hash_binds_source_preview_and_changelog(self):
        record = {'source': HEAD, 'preview': '123', 'changes': ['a']}
        for key in record:
            changed = copy.deepcopy(record); changed[key] = 'changed'
            self.assertNotEqual(digest(record), digest(changed))
        self.assertEqual(digest(record), digest(dict(reversed(list(record.items())))))

    def test_no_publish_side_effect_at_zero_one_or_unmerged_two(self):
        for count, merged in [(0, True), (1, True), (2, False)]:
            decision = {'count': count, 'allowed': count == 2}
            with patch.object(delivery, 'inspect', return_value=({'merged': merged}, {}, decision)), patch.object(delivery, 'api') as api:
                with self.assertRaises(ValueError):
                    delivery.publish(3)
                api.assert_not_called()


class PreviewTests(unittest.TestCase):
    def test_expiration_and_changed_inputs(self):
        a = {'expired': False, 'expires_at': '2026-10-07T00:00:00Z'}
        m = {'fingerprint': 'same-content'}
        now = datetime(2026, 10, 6, tzinfo=timezone.utc)
        self.assertTrue(preview_usable(m, 'same-content', a, now))
        self.assertFalse(preview_usable(m, 'different-inputs', a, now))
        self.assertFalse(preview_usable(m, 'same-content', {**a, 'expired': True}, now))
        self.assertFalse(preview_usable(m, 'same-content', a, datetime(2026, 10, 7, tzinfo=timezone.utc)))

    def test_squash_sha_difference_preserves_content_identity(self):
        with tempfile.TemporaryDirectory() as folder:
            def g(*args):
                return subprocess.check_output(['git', '-C', folder, *args], stderr=subprocess.DEVNULL).decode().strip()
            g('init'); g('config', 'user.name', 'Fixture'); g('config', 'user.email', 'fixture@example.invalid')
            p = Path(folder); (p / 'delivery').mkdir(); (p / 'lib').mkdir()
            (p / 'delivery/build-inputs.json').write_text('{"flutter":"fixed"}')
            (p / 'lib/main.dart').write_text('void main() {}')
            g('add', '.'); g('commit', '-m', 'source'); a = g('rev-parse', 'HEAD')
            g('commit', '--allow-empty', '-m', 'different squash history'); b = g('rev-parse', 'HEAD')
            with patch('preview.git', side_effect=g):
                self.assertNotEqual(a, b)
                self.assertEqual(fingerprint(a), fingerprint(b))
                (p / 'delivery/build-inputs.json').write_text('{"flutter":"changed"}')
                g('add', '.'); g('commit', '-m', 'new compiler')
                self.assertNotEqual(fingerprint(a), fingerprint('HEAD'))

class PublisherBoundaryTests(unittest.TestCase):
    def state(self):
        pr = {'merged': True, 'head': {'sha': HEAD}, 'user': {'login': 'author'},
              'html_url': 'https://github.com/example/pull/3'}
        record = {'tag': 'lab/delivery/2026-10-06-rc.1', 'source_sha': 'b' * 40,
                  'patches': {'ios': None, 'android': None}, 'preview': {'artifact_id': 7}}
        decision = {'count': 2, 'allowed': True, 'approved': list(REQUIRED)}
        return pr, record, decision

    def test_two_current_review_payloads_allow_only_lab_release_and_receipt(self):
        state = self.state()
        calls = []
        def api(path, data=None, method=None):
            calls.append((path, data, method))
            if path.endswith('/pulls/3'):
                return state[0]
            if data and data.get('draft') is True:
                self.assertTrue(data['prerelease'])
                self.assertEqual(data['make_latest'], 'false')
                return {'id': 9}
            return {'html_url': 'https://github.com/example/releases/tag/lab'}
        def pages(path):
            return [review(u, n=i) for i, u in enumerate(REQUIRED)] if '/reviews' in path else []
        def upload(args, check):
            self.assertEqual(args[:3], ['gh', 'release', 'upload'])
            receipt = next(Path(arg) for arg in args if str(arg).endswith('/receipt.json'))
            import json
            data = json.loads(receipt.read_text())
            self.assertFalse(data['distribution_performed'])
            self.assertTrue(data['dry_run'])
            self.assertEqual(data['patches'], {'ios': None, 'android': None})
        with patch.object(delivery, 'inspect', return_value=state), patch.object(delivery, 'api', side_effect=api), patch.object(delivery, 'pages', side_effect=pages), patch.object(delivery, 'artifact_data', return_value=({}, {}, b'fixture-not-a-real-app', {})), patch.object(delivery, 'record_body', return_value='LAB ONLY'), patch.object(delivery.subprocess, 'run', side_effect=upload):
            delivery.publish(3)
        writes = [c for c in calls if c[1] is not None]
        self.assertEqual(len(writes), 2)
        self.assertEqual(writes[-1][1], {'draft': False, 'make_latest': 'false'})

    def test_revocation_during_upload_never_publishes_draft(self):
        state = self.state()
        revoked = (state[0], state[1], {'count': 1, 'allowed': False})
        with patch.object(delivery, 'inspect', side_effect=[state, revoked]), patch.object(delivery, 'api', side_effect=[state[0], {'id': 9}]) as api, patch.object(delivery, 'pages', side_effect=[[review(u) for u in REQUIRED], []]), patch.object(delivery, 'artifact_data', return_value=({}, {}, b'fixture', {})), patch.object(delivery, 'record_body', return_value='LAB ONLY'), patch.object(delivery.subprocess, 'run'):
            with self.assertRaisesRegex(ValueError, 'Estado mudou'):
                delivery.publish(3)
            self.assertFalse(any(call.args[-1] == 'PATCH' for call in api.call_args_list))


if __name__ == '__main__':
    unittest.main()
