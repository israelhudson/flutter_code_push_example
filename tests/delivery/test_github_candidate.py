"""Offline GitHub adapter boundaries; no remote or Shorebird operations."""
import copy
import json
from pathlib import Path
import sys
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / 'tools/delivery'))
import configure_lab
import github_delivery as delivery
from policy import LEDGER, REQUIRED, decide, digest

BASELINE = 'a' * 40
B = 'b' * 40
FIX = 'f' * 40
MAIN = 'd' * 40
RECORD_HEAD = 'e' * 40


class Remote:
    def __init__(self, source=B, release_head=None, tag_refs=None, rules=None):
        self.source = source
        self.release_head = release_head
        self.tag_refs = tag_refs or []
        self.writes = []
        self.records = []
        self.rules = rules if rules is not None else [
            configure_lab.tag_rule(configure_lab.TAG_RULE_NAME,
                                   delivery.TAG_RULE_PATTERNS['legacy']),
            configure_lab.tag_rule(configure_lab.NEUTRAL_TAG_RULE_NAME,
                                   delivery.TAG_RULE_PATTERNS['neutral'])]
        for i, rule in enumerate(self.rules, 1):
            rule['id'] = i

    def api(self, path, data=None, method=None):
        if data is not None:
            self.writes.append((path, copy.deepcopy(data), method))
            if path.endswith('/git/blobs'):
                self.records.append(json.loads(data['content']))
            if path.endswith('/pulls'):
                return {'html_url': 'https://github.com/example/pull/4', 'number': 4}
            return {'sha': RECORD_HEAD}
        if path.endswith('/rulesets'):
            return self.rules
        if '/rulesets/' in path:
            return self.rules[int(path.rsplit('/', 1)[1]) - 1]
        if '/branches/' in path:
            return {'protected': True}
        if path.endswith('/git/ref/heads/main'):
            return {'object': {'sha': MAIN}}
        if '/compare/' in path:
            return {'status': 'ahead' if self.source == B else 'diverged'}
        if '/git/ref/heads/' in path:
            return {'object': {'sha': RECORD_HEAD}}
        if '/git/commits/' in path:
            return {'tree': {'sha': RECORD_HEAD}}
        raise AssertionError('Unexpected read: ' + path)

    def pages(self, path, key=None):
        if '/git/matching-refs/heads/release/' in path:
            return ([] if self.release_head is None else
                    [{'ref': 'refs/heads/release/entrega-0042',
                      'object': {'sha': self.release_head}}])
        if '/git/matching-refs/tags/' in path:
            return self.tag_refs
        if '/pulls?' in path:
            return []
        raise AssertionError('Unexpected pagination: ' + path)

    def git(self, *args):
        if args[0] == 'rev-parse':
            return ('1' * 40 if args[1].endswith('^{tree}') else args[1])
        if args[0] == 'show':
            return 'name: example\nversion: 1.1.0+2\n'
        if args[0] == 'rev-list':
            return BASELINE
        if args[0] == 'log':
            # The range must retain the last completed baseline for RC2; a
            # previous RC would silently omit B from the version's changelog.
            if args[-1] != f'{BASELINE}..{self.source}':
                raise AssertionError('Wrong changelog baseline: ' + args[-1])
            return B + '\tOriginal delivery' + (
                '\n' + FIX + '\tRelease-only fix' if self.source == FIX else '')
        raise AssertionError(args)

    def mocks(self):
        return [patch.object(delivery, 'api', side_effect=self.api),
                patch.object(delivery, 'pages', side_effect=self.pages),
                patch.object(delivery, 'git', side_effect=self.git),
                patch.object(delivery, 'is_ancestor', return_value=True),
                patch.object(delivery, 'fingerprint', return_value='verified-content-and-build-inputs'),
                patch.object(delivery, 'artifact_data', return_value=(
                    {'expired': False, 'expires_at': '2099-01-01T00:00:00Z',
                     'workflow_run': {'id': 9}},
                    {'fingerprint': 'verified-content-and-build-inputs',
                     'source_sha': self.source, 'sha256': 'preview-hash'}, b'preview', {}))]


class CandidateTests(unittest.TestCase):
    def create(self, remote, **kwargs):
        from contextlib import ExitStack
        with ExitStack() as stack:
            for mock in remote.mocks():
                stack.enter_context(mock)
            return delivery.create_candidate(remote.source, 7,
                delivery_id='entrega-0042', previous_sha=BASELINE, **kwargs)

    def test_neutral_rc_and_release_branch_bind_exact_snapshot(self):
        remote = Remote()
        self.create(remote)
        record = remote.records[0]
        self.assertEqual(record['tag'], 'entrega-0042-rc.1')
        self.assertEqual(record['source_sha'], B)
        self.assertEqual(record['release_branch'], 'release/entrega-0042')
        self.assertEqual(record['baseline'], {'mode': 'explicit', 'source_sha': BASELINE})
        self.assertEqual(record['patches'], {'ios': None, 'android': None})
        writes = [data for _, data, _ in remote.writes]
        self.assertIn({'ref': 'refs/heads/release/entrega-0042', 'sha': B}, writes)
        tag = next(data for path, data, _ in remote.writes if path.endswith('/git/tags'))
        self.assertEqual(tag['object'], B)
        self.assertEqual(tag['message'], 'LAB ONLY manifest-sha256:' + digest(record))
        tree = next(data for path, data, _ in remote.writes if path.endswith('/git/trees'))
        self.assertEqual(tree['tree'][0]['path'], 'delivery/candidates/entrega-0042-rc.1.json')

    def test_rc2_fixes_release_without_using_new_main_or_rc1_as_baseline(self):
        remote = Remote(FIX, B, [{'ref': 'refs/tags/entrega-0042-rc.1',
                                 'object': {'sha': B}}])
        self.create(remote)
        record = remote.records[0]
        self.assertEqual(record['tag'], 'entrega-0042-rc.2')
        self.assertEqual(record['source_sha'], FIX)
        self.assertEqual(record['previous_sha'], BASELINE)
        self.assertEqual([c['sha'] for c in record['changes']], [B, FIX])
        self.assertNotIn(MAIN, json.dumps(record))
        updates = [(data, method) for path, data, method in remote.writes
                   if '/git/refs/heads/release/' in path]
        self.assertEqual(updates, [({'sha': FIX, 'force': False}, 'PATCH')])
        self.assertFalse(any(data.get('ref') == 'refs/tags/entrega-0042-rc.1'
                             for _, data, _ in remote.writes))

    def test_namespace_rules_are_required_before_any_mutation(self):
        for change in ('legacy-only', 'disabled', 'bypass', 'deletion-missing', 'excluded'):
            remote = Remote()
            if change == 'legacy-only':
                remote.rules = remote.rules[:1]
            elif change == 'disabled':
                remote.rules[1]['enforcement'] = 'disabled'
            elif change == 'bypass':
                remote.rules[1]['bypass_actors'] = [{'actor_id': 5}]
            elif change == 'deletion-missing':
                remote.rules[1]['rules'] = [{'type': 'update'}]
            else:
                remote.rules[1]['conditions']['ref_name']['exclude'] = ['refs/tags/entrega-0042-rc.1']
            with self.subTest(change=change), self.assertRaisesRegex(ValueError, 'Proteção'):
                self.create(remote)
            self.assertEqual(remote.writes, [])

    def test_missing_baseline_and_invalid_delivery_reject_without_remote_access(self):
        with patch.object(delivery, 'git', return_value=B), patch.object(delivery, 'api') as api:
            with self.assertRaisesRegex(ValueError, 'previous-sha'):
                delivery.create_candidate(B, 7, delivery_id='entrega-0042')
            with self.assertRaisesRegex(ValueError, 'delivery_id'):
                delivery.create_candidate(B, 7, delivery_id='bad/ref', previous_sha=BASELINE)
            api.assert_not_called()

    def test_unrelated_release_snapshot_cannot_force_push(self):
        remote = Remote(FIX, B)
        with patch.object(delivery, 'git', side_effect=remote.git), patch.object(delivery, 'is_ancestor', side_effect=[True, False]), patch.object(delivery, 'pages', side_effect=remote.pages), patch.object(delivery, 'api') as api:
            with self.assertRaisesRegex(ValueError, 'histórico'):
                delivery.create_candidate(FIX, 7, delivery_id='entrega-0042', previous_sha=BASELINE)
            api.assert_not_called()

    def test_legacy_signature_and_first_baseline_remain_supported(self):
        remote = Remote()
        from contextlib import ExitStack
        with ExitStack() as stack:
            for mock in remote.mocks():
                stack.enter_context(mock)
            delivery.create_candidate(B, 7, demo=True)
        record = remote.records[0]
        self.assertRegex(record['tag'], delivery.LEGACY_TAG_PATTERN)
        self.assertEqual(record['baseline']['mode'], 'repository-root')
        self.assertNotIn('release_branch', record)

    def test_open_candidate_blocks_new_rc_without_mutations(self):
        remote = Remote()
        prior = {'source_sha': FIX, 'preview': {'artifact_id': 8}}
        def pages(path, key=None):
            if '/pulls?' in path:
                return [{'number': 3, 'state': 'open',
                         'head': {'ref': 'codex/candidate-prior', 'sha': RECORD_HEAD},
                         'html_url': 'https://github.com/example/pull/3'}]
            if '/pulls/3/files' in path:
                return [{'filename': 'delivery/candidates/prior.json'}]
            return remote.pages(path, key)
        from contextlib import ExitStack
        with ExitStack() as stack:
            for mock in remote.mocks():
                stack.enter_context(mock)
            stack.enter_context(patch.object(delivery, 'pages', side_effect=pages))
            stack.enter_context(patch.object(delivery, 'content', return_value=json.dumps(prior)))
            with self.assertRaisesRegex(ValueError, 'Outra RC'):
                delivery.create_candidate(B, 7, delivery_id='entrega-0042', previous_sha=BASELINE)
        self.assertEqual(remote.writes, [])


class RealApprovalBoundaryTests(unittest.TestCase):
    def test_simulated_required_names_do_not_count_as_real_reviews(self):
        for field, value in [('simulation', True), ('simulated', True),
                             ('is_simulated', True), ('simulated_role', 'samuel'),
                             ('mode', 'simulation'), ('mode', 'laboratory')]:
            reviews = [{'id': n, 'user': {'login': login}, 'state': 'APPROVED',
                        'commit_id': RECORD_HEAD, field: value}
                       for n, login in enumerate(REQUIRED)]
            with self.subTest(field=field):
                self.assertEqual(decide(reviews, RECORD_HEAD, 'israelhudson')['count'], 0)

    def test_two_reviews_only_release_the_manual_command(self):
        record = {'tag': 'entrega-0042-rc.1', 'changes': [], 'compare_url': 'compare',
                  'source_sha': B, 'previous_sha': BASELINE, 'mobile_base': '1.1.0+2',
                  'mode': 'post-main-merge-dry-run',
                  'preview': {'url': 'preview', 'expires_at': '2099', 'origin': 'build', 'sha256': 'hash'}}
        body = delivery.record_body(record, {'count': 2, 'approved': list(REQUIRED)})
        self.assertIn('apenas liberam o comando final', body)
        self.assertIn('action=publish', body)
        self.assertIn('Run workflow', body)

    def test_old_rc_cannot_publish_after_newer_tag_exists(self):
        record = {'tag': 'entrega-0042-rc.1'}
        pr = {'merged': True}
        decision = {'allowed': True}
        with patch.object(delivery, 'inspect', return_value=(pr, record, decision)), patch.object(delivery, 'pages', return_value=[{'ref': 'refs/tags/entrega-0042-rc.2'}]), patch.object(delivery, 'api') as api:
            with self.assertRaisesRegex(ValueError, 'obsoleta'):
                delivery.publish(4)
            api.assert_not_called()

    def test_rc_created_during_asset_upload_leaves_release_in_draft(self):
        record = {'tag': 'entrega-0042-rc.1', 'source_sha': B,
                  'patches': {'ios': None, 'android': None}, 'preview': {'artifact_id': 7}}
        pr = {'merged': True, 'head': {'sha': RECORD_HEAD},
              'user': {'login': 'israelhudson'}, 'html_url': 'https://github.com/example/pull/4'}
        reviews = [{'id': n, 'user': {'login': login}, 'state': 'APPROVED', 'commit_id': RECORD_HEAD}
                   for n, login in enumerate(REQUIRED)]
        decision = {'allowed': True, 'approved': list(REQUIRED)}
        tag_reads = 0
        def pages(path):
            nonlocal tag_reads
            if '/matching-refs/tags/' in path:
                tag_reads += 1
                return [] if tag_reads == 1 else [{'ref': 'refs/tags/entrega-0042-rc.2'}]
            return reviews if path.endswith('/reviews') else []
        with patch.object(delivery, 'inspect', return_value=(pr, record, decision)), patch.object(delivery, 'pages', side_effect=pages), patch.object(delivery, 'api', side_effect=[pr, {'id': 9}]) as api, patch.object(delivery, 'artifact_data', return_value=({}, {}, b'web', {})), patch.object(delivery, 'record_body', return_value='LAB'), patch.object(delivery.subprocess, 'run'):
            with self.assertRaisesRegex(ValueError, 'obsoleta'):
                delivery.publish(4)
            self.assertFalse(any(call.args[-1] == 'PATCH' for call in api.call_args_list))


class InspectTests(unittest.TestCase):
    def state(self):
        record = {'schema': 1, 'repository': delivery.REPO,
                  'tag': 'entrega-0042-rc.2', 'source_sha': FIX,
                  'delivery_id': 'entrega-0042', 'release_branch': 'release/entrega-0042',
                  'previous_sha': BASELINE,
                  'baseline': {'source_sha': BASELINE, 'mode': 'explicit'},
                  'approvers': list(REQUIRED), 'patches': {'ios': None, 'android': None},
                  'preview': {'artifact_id': 7, 'fingerprint': 'same-build', 'sha256': 'same-zip'}}
        pr = {'base': {'ref': LEDGER}, 'head': {'ref': 'codex/candidate-entrega-0042-rc.2',
              'sha': RECORD_HEAD, 'repo': {'full_name': delivery.REPO}},
              'user': {'login': 'israelhudson'}, 'merged': True}
        return record, pr

    def read(self, record, pr, mutate_tag=False):
        calls = []
        def api(path, data=None, method=None):
            self.assertIsNone(data)
            calls.append(path)
            if '/pulls/' in path:
                return pr
            if '/git/ref/tags/' in path:
                return {'object': {'type': 'tag', 'sha': 'tag-object'}}
            if '/git/tags/' in path:
                return {'object': {'sha': B if mutate_tag else FIX},
                        'message': 'LAB ONLY manifest-sha256:' + digest(record)}
            raise AssertionError(path)
        def pages(path):
            if path.endswith('/files'):
                return [{'filename': 'delivery/candidates/entrega-0042-rc.2.json', 'status': 'added'}]
            return [{'id': i, 'user': {'login': login}, 'state': 'APPROVED', 'commit_id': RECORD_HEAD}
                    for i, login in enumerate(REQUIRED)]
        with patch.object(delivery, 'api', side_effect=api), patch.object(delivery, 'pages', side_effect=pages), patch.object(delivery, 'content', return_value=json.dumps(record)), patch.object(delivery, 'assert_tag_protection') as protection, patch.object(delivery, 'artifact_data', return_value=(
                {'expired': False, 'expires_at': '2099-01-01T00:00:00Z'},
                {'fingerprint': 'same-build', 'sha256': 'same-zip'}, b'web', {})):
            result = delivery.inspect(4)
            protection.assert_called_once_with(True)
        return result, calls

    def test_neutral_manifest_preserves_real_review_gate_and_fixed_snapshot(self):
        record, pr = self.state()
        (actual_pr, actual_record, decision), calls = self.read(record, pr)
        self.assertEqual(actual_pr, pr)
        self.assertEqual(actual_record['source_sha'], FIX)
        self.assertTrue(decision['allowed'])
        self.assertFalse(any('/heads/main' in p or '/heads/release/' in p for p in calls))

    def test_original_snapshot_cannot_replace_corrected_snapshot(self):
        record, pr = self.state()
        with self.assertRaisesRegex(ValueError, 'SHA/tag/manifesto'):
            self.read(record, pr, mutate_tag=True)

    def test_delivery_identity_mismatch_rejects_before_tag_read(self):
        record, pr = self.state()
        record['release_branch'] = 'release/entrega-9999'
        with self.assertRaisesRegex(ValueError, 'Identidade da entrega'):
            self.read(record, pr)


class ConfigureTests(unittest.TestCase):
    def test_adds_neutral_rule_without_replacing_legacy_or_weakening_two_reviews(self):
        legacy = configure_lab.tag_rule(configure_lab.TAG_RULE_NAME, delivery.TAG_RULE_PATTERNS['legacy'])
        writes = []
        def api(path, data=None, method=None):
            if data is not None:
                writes.append((path, data, method))
                return {}
            if path.endswith('/rulesets'):
                return [{'id': 1, 'name': configure_lab.TAG_RULE_NAME}]
            if '/rulesets/' in path:
                return legacy
            return [{'ref': 'refs/heads/' + LEDGER}]
        with patch.object(configure_lab, 'api', side_effect=api), patch.object(configure_lab, 'git', return_value=B):
            configure_lab.configure(B)
        rule = next(data for path, data, _ in writes if path.endswith('/rulesets'))
        self.assertEqual(rule['conditions']['ref_name']['include'], ['refs/tags/entrega-*-rc.*'])
        self.assertEqual(rule['bypass_actors'], [])
        self.assertFalse(any('/rulesets/' in path for path, _, _ in writes))
        protection = next(data for path, data, _ in writes if path.endswith('/protection'))
        self.assertTrue(protection['enforce_admins'])
        self.assertEqual(protection['required_pull_request_reviews']['required_approving_review_count'], 2)

    def test_conflicting_existing_rule_causes_no_mutations(self):
        wrong = configure_lab.tag_rule(configure_lab.TAG_RULE_NAME, delivery.TAG_RULE_PATTERNS['legacy'])
        wrong['bypass_actors'] = [{'actor_id': 1}]
        def api(path, data=None, method=None):
            if data is not None:
                raise AssertionError('A conflict must not mutate any refs or protections')
            return ([{'id': 1, 'name': configure_lab.TAG_RULE_NAME}]
                    if path.endswith('/rulesets') else wrong)
        with patch.object(configure_lab, 'api', side_effect=api), patch.object(configure_lab, 'git', return_value=B):
            with self.assertRaisesRegex(ValueError, 'sem sobrescrever'):
                configure_lab.configure(B)


if __name__ == '__main__':
    unittest.main()
