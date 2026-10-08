"""Offline real-owner issue approval and frozen GitHub release promotion gates."""
import copy
import json
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / 'tools/delivery'))
import github_lab_promote as promote
import github_lab_release as release
from remote_state import GitDataAPIError
import test_github_lab_release as release_fixture


class FakePromotionAPI(release_fixture.FakeReleaseAPI):
    def __init__(self, original, plan):
        self.__dict__.update(copy.copy(original.__dict__))
        self.calls = []
        self.issue = {'id': 700, 'number': 12, 'html_url': release.URL + '/issues/12',
                      'state': 'open', 'title': promote.issue_title(plan),
                      'body': promote.issue_body(plan), 'created_at': '2026-10-07T21:00:00Z',
                      'updated_at': '2026-10-07T23:00:00Z',
                      'user': {'login': 'israelhudson', 'id': 42, 'type': 'User'},
                      'assignees': [{'login': 'israelhudson', 'id': 42, 'type': 'User'}]}
        self.comments, self.issue_reads = [], 0
        self.assets_reads = 0
        self.on_recheck = None
        self.on_asset_recheck = None
        self.ambiguous_promotion = False
        self.final_asset_drift = False

    def comment(self, body, comment_id=701, **changes):
        value = {'id': comment_id, 'body': body,
                 'html_url': release.URL + '/issues/12#issuecomment-' + str(comment_id),
                 'user': {'login': 'israelhudson', 'id': 42, 'type': 'User'},
                 'created_at': '2026-10-07T22:00:00Z', 'updated_at': '2026-10-07T22:00:00Z'}
        value.update(changes)
        self.comments.append(value)
        return value

    def __call__(self, method, path, data=None):
        endpoint = path[len(release.BASE):]
        if endpoint == '/issues/12':
            self.calls.append((method, path, copy.deepcopy(data)))
            self.issue_reads += 1
            if self.issue_reads == 2 and self.on_recheck:
                self.on_recheck()
            return copy.deepcopy(self.issue)
        if endpoint.startswith('/issues/12/comments?'):
            self.calls.append((method, path, copy.deepcopy(data)))
            page = int(endpoint.rsplit('page=', 1)[1])
            return copy.deepcopy(self.comments[(page - 1) * 100:page * 100])
        if endpoint.startswith('/releases/500/assets?'):
            self.assets_reads += 1
            if self.assets_reads == 2 and self.on_asset_recheck:
                self.on_asset_recheck()
        if endpoint == '/releases/500' and method == 'PATCH':
            self.calls.append((method, path, copy.deepcopy(data)))
            assert set(data) == {'prerelease', 'name', 'body', 'make_latest'}
            assert data['prerelease'] is False and data['make_latest'] == 'false'
            self.release.update(copy.deepcopy(data))
            if self.final_asset_drift:
                self.assets['candidate.json']['id'] += 1
            if self.ambiguous_promotion:
                self.ambiguous_promotion = False
                raise GitDataAPIError()
            return copy.deepcopy(self.release)
        return super().__call__(method, path, data)


class GitHubLabPromoteTests(unittest.TestCase):
    def setUp(self):
        self.lab = release_fixture.GitHubLabReleaseTests()
        self.lab.setUp()
        self.addCleanup(self.lab.doCleanups)
        self.lab.prepare_tag()
        self.lab.run_release('publish')
        self.plan = json.loads((self.lab.output / 'plan.json').read_text())
        self.api = FakePromotionAPI(self.lab.api, self.plan)
        self.env = {**self.lab.env, 'GITHUB_WORKFLOW_REF': promote.WORKFLOW}
        self.counter = 0

    def approve(self, **changes):
        return self.api.comment(promote.commands(self.plan)[0], **changes)

    def run_promotion(self, action='plan', env=None, manifest_hash=None):
        self.counter += 1
        self.output = self.lab.folder / ('promotion-' + str(self.counter))
        return promote.run(action, self.lab.candidate, manifest_hash or self.lab.hash, 12, self.output,
                           self.env if env is None else env, api=self.api, remote=self.lab.remote)

    def mutations(self):
        return [call for call in self.api.calls if call[0] != 'GET']

    def test_plan_without_approval_is_read_only_and_awaits_real_issue_review(self):
        original = copy.deepcopy(self.api.release)
        assets = copy.deepcopy(self.api.assets)
        head = self.lab.git.head
        result = self.run_promotion()
        self.assertEqual(result['status'], 'awaiting_review')
        self.assertEqual(result['real_issue_review_count'], 0)
        self.assertEqual(result['real_pr_review_count'], 0)
        self.assertEqual(result['historical_simulated_approval_count'], 2)
        self.assertFalse(result['distribution_performed'])
        self.assertFalse(result['promoted'])
        self.assertEqual(self.mutations(), [])
        self.assertEqual(self.api.release, original)
        self.assertEqual(self.api.assets, assets)
        self.assertEqual(self.lab.git.head, head)

    def test_owner_workflow_branch_and_actor_numeric_id_required(self):
        for key, value in (('GITHUB_ACTOR', 'someone'), ('GITHUB_ACTOR_ID', '99'),
                           ('GITHUB_TRIGGERING_ACTOR', 'someone'), ('GITHUB_TRIGGERING_ACTOR_ID', '99'),
                           ('GITHUB_WORKFLOW_REF', release.WORKFLOW), ('GITHUB_REF', 'refs/heads/feature'),
                           ('GITHUB_ACTIONS', 'false'), ('GITHUB_EVENT_NAME', 'push')):
            with self.subTest(key=key), self.assertRaises(release.ReleaseError):
                self.run_promotion(env={**self.env, key: value})
        self.assertEqual(self.mutations(), [])

    def test_wrong_manifest_hash_never_promotes(self):
        self.approve()
        with self.assertRaisesRegex(release.ReleaseError, 'Hash do manifesto'):
            self.run_promotion('promote', manifest_hash='a' * 64)
        self.assertEqual(self.mutations(), [])

    def test_issue_must_be_open_owner_assigned_exact_record_and_not_a_pr(self):
        original = copy.deepcopy(self.api.issue)
        variants = ({'state': 'closed'}, {'pull_request': {}}, {'title': 'Another review'},
                    {'body': original['body'].replace(self.lab.hash, 'a' * 64)}, {'assignees': []},
                    {'user': {'login': 'israelhudson', 'id': 99, 'type': 'User'}},
                    {'user': {'login': 'israelhudson', 'id': 42, 'type': 'Bot'}})
        for change in variants:
            self.api.issue = {**original, **change}
            with self.subTest(change=change), self.assertRaises(release.ReleaseError):
                self.run_promotion('promote')
        self.assertEqual(self.mutations(), [])

    def test_only_exact_owner_user_command_without_simulation_counts(self):
        command = promote.commands(self.plan)[0]
        self.api.comment(command, 710, user={'login': 'other', 'id': 7, 'type': 'User'})
        self.api.comment(command, 711, user={'login': 'israelhudson', 'id': 99, 'type': 'User'})
        self.api.comment(command, 712, user={'login': 'israelhudson', 'id': 42, 'type': 'Bot'})
        self.api.comment(command, 713, simulation=True)
        self.api.comment(command + '\nExtra words', 714)
        self.api.comment(command.replace(self.lab.hash, 'a' * 64), 715)
        self.assertEqual(self.run_promotion()['status'], 'awaiting_review')
        with self.assertRaisesRegex(release.ReleaseError, 'aprovação real'):
            self.run_promotion('promote')
        self.assertEqual(self.mutations(), [])

    def test_edited_latest_command_invalidates_earlier_approval(self):
        self.approve(comment_id=701)
        self.approve(comment_id=702, updated_at='2026-10-07T22:30:00Z')
        self.assertEqual(self.run_promotion()['approval_status'], 'edited')
        with self.assertRaises(release.ReleaseError):
            self.run_promotion('promote')
        self.assertEqual(self.mutations(), [])

    def test_newer_edited_owner_comment_cannot_resurrect_older_approval(self):
        self.approve(comment_id=701)
        self.api.comment('Revocation text edited away', 702, updated_at='2026-10-07T22:30:00Z')
        self.assertEqual(self.run_promotion()['approval_status'], 'edited')
        with self.assertRaises(release.ReleaseError):
            self.run_promotion('promote')
        self.assertEqual(self.mutations(), [])

    def test_deleted_selected_approval_is_not_accepted(self):
        self.approve()
        self.api.on_recheck = lambda: self.api.comments.clear()
        with self.assertRaisesRegex(release.ReleaseError, 'Revisão/issue mudou'):
            self.run_promotion('promote')
        self.assertEqual(self.mutations(), [])

    def test_old_owner_comment_edited_after_approval_requires_new_decision(self):
        self.api.comment('Earlier note edited after approval', 700,
                         created_at='2026-10-07T21:30:00Z', updated_at='2026-10-07T22:30:00Z')
        self.approve(comment_id=701)
        self.assertEqual(self.run_promotion()['approval_status'], 'edited')
        with self.assertRaises(release.ReleaseError):
            self.run_promotion('promote')
        self.assertEqual(self.mutations(), [])
        self.approve(comment_id=702, created_at='2026-10-07T22:45:00Z', updated_at='2026-10-07T22:45:00Z')
        self.assertEqual(self.run_promotion()['approval_status'], 'approved')

    def test_latest_owner_decisive_comment_wins_by_id(self):
        self.approve(comment_id=702)
        self.api.comment(promote.commands(self.plan)[1], 703)
        self.assertEqual(self.run_promotion()['approval_status'], 'revoked')
        self.approve(comment_id=704)
        self.api.comments.reverse()
        result = self.run_promotion()
        self.assertEqual(result['approval_status'], 'approved')
        self.assertEqual(result['approval_comment_id'], 704)
        self.assertEqual(self.mutations(), [])

    def test_comment_identity_and_dates_cannot_claim_other_issue(self):
        comment = self.approve(html_url=release.URL + '/issues/99#issuecomment-701')
        with self.assertRaisesRegex(release.ReleaseError, 'identité|identidade'):
            self.run_promotion()
        comment['html_url'] = release.URL + '/issues/12#issuecomment-701'
        comment['created_at'] = comment['updated_at'] = '2026-10-08T22:00:00Z'
        with self.assertRaises(release.ReleaseError):
            self.run_promotion()
        self.assertEqual(self.mutations(), [])

    def test_missing_draft_changed_release_tag_or_asset_is_blocked(self):
        self.approve()
        original = copy.deepcopy(self.api.release)
        self.api.release = None
        with self.assertRaises(release.ReleaseError):
            self.run_promotion('promote')
        self.api.release = {**original, 'draft': True}
        with self.assertRaises(release.ReleaseError):
            self.run_promotion('promote')
        self.api.release = {**original, 'body': 'tampered'}
        with self.assertRaises(release.ReleaseError):
            self.run_promotion('promote')
        self.api.release = original
        self.api.tag['object']['sha'] = 'a' * 40
        with self.assertRaises(release.ReleaseError):
            self.run_promotion('promote')
        self.api.tag['object']['sha'] = self.lab.source
        self.api.assets['candidate.json']['digest'] = 'sha256:' + 'a' * 64
        with self.assertRaises(release.ReleaseError):
            self.run_promotion('promote')
        self.assertEqual(self.mutations(), [])

    def test_promotion_preserves_same_id_tag_source_asset_ids_and_bytes(self):
        self.approve()
        original_assets = copy.deepcopy(self.api.assets)
        original_tag = copy.deepcopy(self.api.tag)
        head = self.lab.git.head
        result = self.run_promotion('promote')
        self.assertTrue(result['promoted'])
        self.assertEqual(result['status'], 'promoted')
        self.assertEqual(result['release_id'], 500)
        self.assertFalse(self.api.release['prerelease'])
        self.assertFalse(self.api.release['draft'])
        self.assertEqual(self.api.release['tag_name'], self.lab.candidate)
        self.assertEqual(self.api.assets, original_assets)
        self.assertEqual(self.api.tag, original_tag)
        self.assertEqual(self.lab.git.head, head)
        self.assertEqual(len(self.mutations()), 1)
        receipt = json.loads((self.output / 'promotion-receipt.json').read_text())
        self.assertEqual(receipt['approval']['reviewer']['id'], 42)
        self.assertEqual(receipt['approval']['comment_id'], 701)
        self.assertEqual(receipt['source_sha'], self.lab.source)
        self.assertEqual(receipt['real_issue_review_count'], 1)
        self.assertEqual(receipt['real_pr_review_count'], 0)
        self.assertFalse(receipt['distribution_performed'])
        self.assertIn(release.release_body(self.plan), self.api.release['body'])

    def test_repeat_after_promotion_verifies_same_receipt_without_remote_writes(self):
        self.approve()
        first = self.run_promotion('promote')
        self.api.calls.clear()
        self.env['GITHUB_RUN_ID'] = '124'
        second = self.run_promotion('promote')
        self.assertEqual(first['promotion_identity'], second['promotion_identity'])
        self.assertTrue(second['promoted'])
        self.assertEqual(self.mutations(), [])

    def test_uncertain_promotion_reply_recovers_on_next_manual_run_without_retry(self):
        self.approve()
        self.api.ambiguous_promotion = True
        with self.assertRaisesRegex(release.ReleaseError, 'Efeito GitHub incerto'):
            self.run_promotion('promote')
        self.assertEqual(len(self.mutations()), 1)
        self.assertFalse(self.api.release['prerelease'])
        self.assertEqual(json.loads((self.output / 'checkpoint.json').read_text())['status'], 'uncertain')
        self.api.calls.clear()
        self.assertTrue(self.run_promotion('promote')['promoted'])
        self.assertEqual(self.mutations(), [])

    def test_review_revoke_or_issue_edit_during_recheck_blocks_only_patch(self):
        self.approve()
        self.api.on_recheck = lambda: self.api.comment(promote.commands(self.plan)[1], 702)
        with self.assertRaisesRegex(release.ReleaseError, 'Revisão/issue mudou'):
            self.run_promotion('promote')
        self.assertEqual(self.mutations(), [])
        self.assertTrue(self.api.release['prerelease'])

    def test_asset_id_replaced_before_patch_fails_even_with_identical_digest(self):
        self.approve()
        self.api.on_asset_recheck = lambda: self.api.assets['candidate.json'].update(id=999)
        with self.assertRaisesRegex(release.ReleaseError, 'arquivos mudaram'):
            self.run_promotion('promote')
        self.assertEqual(self.mutations(), [])

    def test_harmless_download_count_changes_do_not_block_promotion(self):
        self.approve()
        def downloads():
            self.api.assets['candidate.json']['download_count'] = 10
            self.api.release['assets'] = list(self.api.assets.values())
        self.api.on_asset_recheck = downloads
        self.assertTrue(self.run_promotion('promote')['promoted'])
        self.assertEqual(len(self.mutations()), 1)

    def test_plan_after_revocation_reports_stable_history_without_rewriting(self):
        self.approve()
        self.run_promotion('promote')
        self.api.calls.clear()
        self.api.comment(promote.commands(self.plan)[1], 702)
        result = self.run_promotion()
        self.assertTrue(result['already_promoted'])
        self.assertEqual(result['approval_status'], 'revoked')
        self.assertEqual(result['real_issue_review_count'], 0)
        self.assertEqual(self.mutations(), [])
        with self.assertRaises(release.ReleaseError):
            self.run_promotion('promote')
        self.assertEqual(self.mutations(), [])

    def test_revoked_candidate_during_recheck_blocks_promotion(self):
        self.approve()
        native_load = self.lab.remote.load
        count = 0
        def load(path):
            nonlocal count
            count += 1
            if count == 2:
                self.lab.store.revoke(self.lab.candidate, 'vinicius', self.lab.hash)
                self.lab.save_state()
            return native_load(path)
        self.lab.remote.load = load
        with self.assertRaises(release.ReleaseError):
            self.run_promotion('promote')
        self.assertEqual(self.mutations(), [])

    def test_asset_id_drift_after_effect_prevents_success_confirmation(self):
        self.approve()
        self.api.final_asset_drift = True
        with self.assertRaisesRegex(release.ReleaseError, 'IDs/conteúdo'):
            self.run_promotion('promote')
        self.assertEqual(len(self.mutations()), 1)
        self.assertFalse(json.loads((self.output / 'result.json').read_text())['promoted'])
        self.assertFalse((self.output / 'promotion-receipt.json').exists())

    def test_comment_pagination_limit_duplicate_ids_and_invalid_ids_fail_closed(self):
        for comments in ([self.api.comment('unrelated', 900)] * 2,
                         [{'id': -1, 'body': 'unrelated'}],
                         [{'id': index + 1, 'body': 'unrelated'} for index in range(1000)]):
            self.api.comments = comments
            with self.subTest(count=len(comments)), self.assertRaises(release.ReleaseError):
                self.run_promotion()
        self.assertEqual(self.mutations(), [])


if __name__ == '__main__':
    unittest.main()
