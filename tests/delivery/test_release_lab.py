"""Offline boundaries for real two-person LAB approvals; no synthetic publishing."""
import copy
import json
from pathlib import Path
import shutil
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / 'tools/delivery'))
import release_lab as lab
import test_pages_preview as preview_fixture


REPOSITORY = 'israelhudson/flutter_code_push_example'
ISRAEL = {'id': 18661493, 'login': 'israelhudson'}
FABRICIA = {'id': 339824994, 'login': 'fahnassau30'}
ENV_IDS = {'aprovacao-israel': 101, 'aprovacao-fahnassau30': 102,
           'autorizar-publicacao': 103}
TAG = 'v1.4.0-rc.1'
SOURCE = 'a' * 40


def policy():
    return {'schema': 1, 'repository': REPOSITORY,
            'operators': [copy.deepcopy(ISRAEL)],
            'approvers': [dict(ISRAEL, role='first', environment='aprovacao-israel'),
                          dict(FABRICIA, role='second', environment='aprovacao-fahnassau30')],
            'publishers': [copy.deepcopy(ISRAEL), copy.deepcopy(FABRICIA)],
            'final_environment': 'autorizar-publicacao',
            'state_branch': 'codex/release-lab-state',
            'result_simulated': True, 'distribution_performed': False}


def review(person, environment, state='approved'):
    return {'state': state, 'user': dict(person, type='User'),
            'environments': [{'id': ENV_IDS[environment], 'name': environment}]}


def approvals():
    return [review(ISRAEL, 'aprovacao-israel'),
            review(FABRICIA, 'aprovacao-fahnassau30')]


class PolicyTests(unittest.TestCase):
    def test_policy_accepts_distinct_mandatory_approvers_and_either_publisher(self):
        result = lab.validate_policy(policy())
        self.assertEqual(result['approvers'][0]['id'], ISRAEL['id'])
        self.assertEqual({p['id'] for p in result['publishers']},
                         {ISRAEL['id'], FABRICIA['id']})

    def test_same_person_cannot_fill_both_mandatory_roles(self):
        invalid = policy()
        invalid['approvers'][1].update(ISRAEL)
        with self.assertRaises(lab.LabError):
            lab.validate_policy(invalid)

    def test_final_publishers_must_be_the_required_approver_set(self):
        for publishers in ([ISRAEL], [FABRICIA], [ISRAEL, FABRICIA, {'id': 7, 'login': 'third'}]):
            with self.subTest(publishers=publishers):
                invalid = policy()
                invalid['publishers'] = copy.deepcopy(publishers)
                with self.assertRaises(lab.LabError):
                    lab.validate_policy(invalid)

    def test_distinct_roles_cannot_share_one_environment(self):
        invalid = policy()
        invalid['approvers'][1]['environment'] = 'aprovacao-israel'
        with self.assertRaises(lab.LabError):
            lab.validate_policy(invalid)

    def test_final_decision_has_its_own_environment(self):
        invalid = policy()
        invalid['final_environment'] = 'aprovacao-israel'
        with self.assertRaises(lab.LabError):
            lab.validate_policy(invalid)

    def test_empty_or_ambiguous_account_identity_is_rejected(self):
        for replacement in ({'id': 0, 'login': 'israelhudson'},
                            {'id': ISRAEL['id'], 'login': ''}):
            with self.subTest(replacement=replacement):
                invalid = policy()
                invalid['operators'] = [replacement]
                with self.assertRaises(lab.LabError):
                    lab.validate_policy(invalid)


class EnvironmentReviewTests(unittest.TestCase):
    def test_zero_or_one_approval_cannot_enable_final_command(self):
        for records in ([], approvals()[:1], approvals()[1:]):
            with self.subTest(records=records), self.assertRaises(lab.LabError):
                lab.validate_reviews(records, policy(), ENV_IDS, stage='approvals')

    def test_two_real_identities_enable_approval_stage_without_publishing(self):
        result = lab.validate_reviews(approvals(), policy(), ENV_IDS, stage='approvals')
        self.assertEqual({item['reviewer']['id'] for item in result['approvers']},
                         {ISRAEL['id'], FABRICIA['id']})
        self.assertFalse(result.get('publisher'))

    def test_final_requires_a_third_separate_human_decision(self):
        with self.assertRaises(lab.LabError):
            lab.validate_reviews(approvals(), policy(), ENV_IDS, stage='final')

    def test_either_required_approver_can_take_the_final_decision(self):
        for publisher in (ISRAEL, FABRICIA):
            with self.subTest(publisher=publisher):
                records = approvals() + [review(publisher, 'autorizar-publicacao')]
                result = lab.validate_reviews(records, policy(), ENV_IDS, stage='final')
                self.assertEqual(result['publisher']['reviewer']['id'], publisher['id'])

    def test_final_decision_does_not_replace_a_missing_version_approval(self):
        records = approvals()[:1] + [review(FABRICIA, 'autorizar-publicacao')]
        with self.assertRaises(lab.LabError):
            lab.validate_reviews(records, policy(), ENV_IDS, stage='final')

    def test_duplicate_person_in_two_environments_is_not_two_approvals(self):
        records = [review(ISRAEL, 'aprovacao-israel'),
                   review(ISRAEL, 'aprovacao-fahnassau30')]
        with self.assertRaises(lab.LabError):
            lab.validate_reviews(records, policy(), ENV_IDS, stage='approvals')

    def test_login_alone_cannot_substitute_numeric_account_identity(self):
        records = approvals()
        records[1]['user']['id'] = 99
        with self.assertRaises(lab.LabError):
            lab.validate_reviews(records, policy(), ENV_IDS, stage='approvals')

    def test_numeric_id_alone_cannot_substitute_another_login(self):
        records = approvals()
        records[1]['user']['login'] = 'other'
        with self.assertRaises(lab.LabError):
            lab.validate_reviews(records, policy(), ENV_IDS, stage='approvals')

    def test_bot_cannot_be_counted_as_a_human_review(self):
        records = approvals()
        records[1]['user']['type'] = 'Bot'
        with self.assertRaises(lab.LabError):
            lab.validate_reviews(records, policy(), ENV_IDS, stage='approvals')

    def test_changed_environment_id_invalidates_a_familiar_name(self):
        records = approvals()
        records[1]['environments'][0]['id'] = 999
        with self.assertRaises(lab.LabError):
            lab.validate_reviews(records, policy(), ENV_IDS, stage='approvals')

    def test_rejection_or_pending_cannot_count_as_approval(self):
        for state in ('rejected', 'pending', 'cancelled', 'skipped'):
            with self.subTest(state=state):
                records = approvals()
                records[1]['state'] = state
                with self.assertRaises(lab.LabError):
                    lab.validate_reviews(records, policy(), ENV_IDS, stage='approvals')

    def test_conflicting_history_cannot_choose_a_convenient_api_order(self):
        approved = review(FABRICIA, 'aprovacao-fahnassau30')
        rejected = review(FABRICIA, 'aprovacao-fahnassau30', 'rejected')
        for second_history in ([approved, rejected], [rejected, approved]):
            with self.subTest(history=second_history), self.assertRaises(lab.LabError):
                lab.validate_reviews([review(ISRAEL, 'aprovacao-israel')] + second_history,
                                     policy(), ENV_IDS, stage='approvals')

    def test_wrong_identity_in_history_cannot_be_hidden_behind_a_valid_approval(self):
        approved = review(FABRICIA, 'aprovacao-fahnassau30')
        wrong = review({'id': 7, 'login': 'third'}, 'aprovacao-fahnassau30')
        for second_history in ([approved, wrong], [wrong, approved]):
            with self.subTest(history=second_history), self.assertRaises(lab.LabError):
                lab.validate_reviews([review(ISRAEL, 'aprovacao-israel')] + second_history,
                                     policy(), ENV_IDS, stage='approvals')

    def test_unlisted_publisher_cannot_use_the_final_environment(self):
        records = approvals() + [review({'id': 7, 'login': 'third'}, 'autorizar-publicacao')]
        with self.assertRaises(lab.LabError):
            lab.validate_reviews(records, policy(), ENV_IDS, stage='final')


class CandidateStateTests(unittest.TestCase):
    def setUp(self):
        self.record = {'candidate_tag': TAG, 'source_sha': SOURCE, 'version': '1.4.0', 'status': 'prepared'}
        self.state = {'active': TAG, 'candidates': {TAG: copy.deepcopy(self.record)}}

    def test_current_candidate_is_bound_to_its_exact_source_commit(self):
        self.assertEqual(lab.ensure_current(self.state, TAG, SOURCE)['source_sha'], SOURCE)

    def test_changed_source_cannot_reuse_candidate_authorization(self):
        with self.assertRaises(lab.LabError):
            lab.ensure_current(self.state, TAG, 'b' * 40)

    def test_new_rc_blocks_old_rc_without_deleting_its_history(self):
        next_tag = 'v1.4.0-rc.2'
        self.state['active'] = next_tag
        self.state['candidates'][next_tag] = dict(self.record, candidate_tag=next_tag, source_sha='b' * 40)
        before = copy.deepcopy(self.state)
        with self.assertRaises(lab.LabError):
            lab.ensure_current(self.state, TAG, SOURCE)
        self.assertEqual(self.state, before)
        self.assertEqual(lab.ensure_current(self.state, next_tag)['candidate_tag'], next_tag)

    def test_missing_record_does_not_get_created_by_the_gate(self):
        self.state['candidates'].clear()
        with self.assertRaises(lab.LabError):
            lab.ensure_current(self.state, TAG)
        self.assertEqual(self.state['candidates'], {})


class ClassificationTests(unittest.TestCase):
    BASE = {'source_sha': 'b' * 40, 'release_version': '1.3.0+1'}

    def test_unknown_mobile_base_blocks_patch_forecast_even_for_dart_only(self):
        result = lab.classify_paths(['lib/main.dart'], None)
        self.assertEqual(result['classification'], 'Inconclusivo — alvo bloqueado')

    def test_native_sdk_and_packaged_asset_changes_require_a_store_release(self):
        for changed in ('android/app/src/main/kotlin/MainActivity.kt',
                        'ios/Runner/AppDelegate.swift', 'assets/new-image.png'):
            with self.subTest(changed=changed):
                result = lab.classify_paths([changed], self.BASE)
                self.assertEqual(result['classification'], 'Loja / nova release nativa')

    def test_dependency_change_remains_unknown_without_compatibility_evidence(self):
        for changed in ('pubspec.yaml', 'pubspec.lock'):
            with self.subTest(changed=changed):
                result = lab.classify_paths([changed], self.BASE)
                self.assertEqual(result['classification'], 'Inconclusivo — alvo bloqueado')

    def test_dart_only_is_a_preliminary_forecast_with_a_reason(self):
        result = lab.classify_paths(['lib/main.dart', 'lib/feature.dart'], self.BASE)
        self.assertEqual(result['classification'], 'Patch possível')
        self.assertTrue(result['reason'])
        self.assertTrue(result['target_blocked'])


class TrustedContextTests(unittest.TestCase):
    def setUp(self):
        self.env = {'GITHUB_ACTIONS': 'true', 'GITHUB_EVENT_NAME': 'workflow_dispatch',
                    'GITHUB_REPOSITORY': REPOSITORY,
                    'GITHUB_ACTOR': ISRAEL['login'], 'GITHUB_ACTOR_ID': str(ISRAEL['id']),
                    'GITHUB_TRIGGERING_ACTOR': ISRAEL['login'],
                    'GITHUB_RUN_ID': '9001', 'GITHUB_RUN_ATTEMPT': '1',
                    'GITHUB_REF': 'refs/heads/main'}

    def test_operator_can_prepare_only_once_from_main(self):
        lab.validate_context(policy(), 'prepare', self.env)

    def test_rerun_cannot_reuse_earlier_human_approvals(self):
        with self.assertRaises(lab.LabError):
            lab.validate_context(policy(), 'prepare', {**self.env, 'GITHUB_RUN_ATTEMPT': '2'})

    def test_repository_account_and_trusted_ref_cannot_be_substituted(self):
        variants = ({'GITHUB_REPOSITORY': 'someone/other'},
                    {'GITHUB_ACTOR': FABRICIA['login'], 'GITHUB_ACTOR_ID': str(FABRICIA['id'])},
                    {'GITHUB_ACTOR_ID': '7'}, {'GITHUB_TRIGGERING_ACTOR': 'other'},
                    {'GITHUB_REF': 'refs/heads/feature/arbitrary'})
        for change in variants:
            with self.subTest(change=change), self.assertRaises(lab.LabError):
                lab.validate_context(policy(), 'prepare', {**self.env, **change})


class FrozenIdentityTests(unittest.TestCase):
    def setUp(self):
        self.record = {'candidate_tag': TAG, 'source_sha': SOURCE,
                       'release_branch': 'release/1.4.0', 'policy_digest': lab.digest(policy())}

    def test_moved_tag_blocks_before_reading_environment_rules(self):
        with patch.object(lab, 'resolve_tag', return_value='b' * 40), \
                patch.object(lab, 'environments') as environments, \
                self.assertRaises(lab.LabError):
            lab.assert_record(policy(), self.record)
        environments.assert_not_called()

    def test_changed_policy_does_not_reuse_frozen_approvals(self):
        changed = policy()
        changed['operators'].append(copy.deepcopy(FABRICIA))
        with patch.object(lab, 'resolve_tag') as resolve_tag, self.assertRaises(lab.LabError):
            lab.assert_record(changed, self.record)
        resolve_tag.assert_not_called()

    def test_advanced_release_requires_new_rc_instead_of_old_approval(self):
        with patch.object(lab, 'resolve_tag', return_value=SOURCE), \
                patch.object(lab, 'api', return_value={'object': {'sha': 'b' * 40}}), \
                patch.object(lab, 'environments') as environments, \
                self.assertRaises(lab.LabError):
            lab.assert_record(policy(), self.record)
        environments.assert_not_called()


class InputValidationTests(unittest.TestCase):
    def test_invalid_version_or_title_is_rejected_before_any_remote_mutation(self):
        invalid = [('v1.4.0', 'Entrega'), ('1.4', 'Entrega'), ('1.4.0-rc.1', 'Entrega'),
                   ('01.4.0', 'Entrega'), ('1.4.0\n', 'Entrega'), ('1.4.0', ''),
                   ('1.4.0', ' '), ('1.4.0', 'Primeira\nSegunda'), ('1.4.0', 'a' * 121)]
        for version, title in invalid:
            with self.subTest(version=version, title=title), \
                    patch.object(lab, 'api') as api, \
                    patch.object(lab, 'environments') as environments, \
                    self.assertRaises(lab.LabError):
                lab.prepare(policy(), version, title, '/unused')
            environments.assert_not_called()
            api.assert_not_called()


class FinalReceiptTests(unittest.TestCase):
    """Exercise the final callback with local state and explicit fake REST reviews."""
    REPORT = 'c' * 64

    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.folder = Path(self.temporary.name)
        self.record = {'candidate_tag': TAG, 'source_sha': SOURCE, 'version': '1.4.0',
                       'title': 'Entrega de teste offline', 'status': 'awaiting_approvals',
                       'evaluation_run_id': '9001', 'preparer': copy.deepcopy(ISRAEL),
                       'report_digest': self.REPORT,
                       'report': {'platforms': {'android': lab.classify_paths(['lib/main.dart'], None),
                                                'ios': lab.classify_paths(['lib/main.dart'], None)},
                                  'preview': {'source_sha': SOURCE, 'snapshot_url':
                                              'https://israelhudson.github.io/flutter_code_push_example/snapshots/' + SOURCE + '/'}},
                       'approval_receipts': {role: {'report_digest': self.REPORT}
                                             for role in ('first', 'second')}}
        self.state = {'schema': 1, 'active': TAG, 'candidates': {TAG: self.record}, 'events': []}
        self.reviews = approvals() + [review(FABRICIA, 'autorizar-publicacao')]
        self.jobs = [{'name': 'Avaliar a mesma candidata / Gate ' + role, 'conclusion': 'success'}
                     for role in ('first', 'second')]

    def run_finish(self, tag=TAG, report_digest=REPORT):
        def read(_):
            return copy.deepcopy(self.state), 'journal-before'

        def write(_, state, old_sha, message):
            self.assertEqual(old_sha, 'journal-before')
            self.state = copy.deepcopy(state)
            return {'sha': 'journal-after'}

        def api(path, *args, **kwargs):
            self.assertEqual(path, lab.endpoint('actions/runs/9001/jobs?per_page=100'))
            return {'jobs': copy.deepcopy(self.jobs)}

        with patch.dict(lab.os.environ, {'GITHUB_RUN_ID': '9001'}), \
                patch.object(lab, 'state_read', side_effect=read), \
                patch.object(lab, 'state_write', side_effect=write) as writes, \
                patch.object(lab, 'current_reviews', return_value=(self.reviews, ENV_IDS)), \
                patch.object(lab, 'api', side_effect=api), \
                patch.object(lab, 'outputs'):
            lab.finish(policy(), tag, report_digest, self.folder)
            return writes

    def test_success_records_real_decisions_but_only_simulated_result(self):
        self.run_finish()
        receipt = json.loads((self.folder / 'receipt.json').read_text())
        self.assertTrue(receipt['human_decision_real'])
        self.assertTrue(receipt['result_simulated'])
        self.assertFalse(receipt['distribution_performed'])
        self.assertFalse(receipt['patch_generated'])
        self.assertEqual(receipt['source_sha'], SOURCE)
        self.assertTrue(all(item['target_blocked'] for item in receipt['platforms'].values()))
        self.assertEqual(receipt['preview']['source_sha'], SOURCE)
        self.assertEqual(receipt['publisher']['reviewer']['id'], FABRICIA['id'])
        self.assertEqual({r['reviewer']['id'] for r in receipt['approvers']},
                         {ISRAEL['id'], FABRICIA['id']})
        self.assertEqual(self.state['candidates'][TAG]['status'], 'completed')
        self.assertEqual(self.state['last_completed_source_sha'], SOURCE)
        self.assertEqual(len((self.folder / 'events.jsonl').read_text().splitlines()), 1)

    def test_failed_cancelled_skipped_or_pending_job_cannot_complete(self):
        for conclusion in ('failure', 'cancelled', 'skipped', None):
            with self.subTest(conclusion=conclusion):
                self.jobs[1]['conclusion'] = conclusion
                with self.assertRaises(lab.LabError):
                    self.run_finish()
                self.assertNotIn('receipt', self.state['candidates'][TAG])
                self.assertFalse((self.folder / 'receipt.json').exists())

    def test_reviews_without_both_successful_job_receipts_cannot_complete(self):
        self.state['candidates'][TAG]['approval_receipts'].pop('second')
        with self.assertRaises(lab.LabError):
            self.run_finish()
        self.assertEqual(self.state['events'], [])

    def test_report_drift_cannot_complete_or_write_a_receipt(self):
        with self.assertRaises(lab.LabError):
            self.run_finish(report_digest='d' * 64)
        self.assertFalse((self.folder / 'receipt.json').exists())
        self.assertEqual(self.state['events'], [])

    def test_old_run_cannot_complete_after_rc2_replaced_it(self):
        self.state['active'] = 'v1.4.0-rc.2'
        with self.assertRaises(lab.LabError):
            self.run_finish()
        self.assertNotIn('receipt', self.state['candidates'][TAG])
        self.assertEqual(self.state['events'], [])


class StaticArtifactBoundaryTests(unittest.TestCase):
    """Only validated static files cross from the build job into a fresh writer."""
    def setUp(self):
        self.fixture = preview_fixture.PagesPreviewTests()
        self.fixture.setUp()
        self.addCleanup(self.fixture.doCleanups)
        self.fixture.compile()
        self.incoming = self.fixture.site
        self.site = self.fixture.folder / 'retained-site'
        self.site.mkdir()
        self.folder = self.fixture.folder / 'merge-report'
        self.sha = self.fixture.sha
        self.record = {'candidate_tag': TAG, 'source_sha': self.sha,
                       'evaluation_run_id': '9001'}
        self.state = {'active': TAG, 'candidates': {TAG: self.record}}
        # Import the trusted implementation before ROOT is redirected to the
        # disposable source repository, which has no deploy tooling of its own.
        sys.path.insert(0, str(Path(__file__).resolve().parents[2] / 'deploy'))
        import pages_preview
        self.pages = pages_preview

    def run_merge(self):
        def git(*args):
            if args[0] == 'fetch':
                return ''
            return self.fixture.repo.git(*args)

        with patch.dict(lab.os.environ, {'GITHUB_RUN_ID': '9001'}), \
                patch.object(lab, 'ROOT', self.fixture.repo.path), \
                patch.object(lab, 'state_read', return_value=(self.state, 'unused')), \
                patch.object(lab, 'assert_record', return_value=ENV_IDS), \
                patch.object(lab, 'git', side_effect=git), patch.object(lab, 'outputs'):
            lab.merge_preview(policy(), TAG, self.incoming, self.site, self.folder)

    def rewrite_metadata(self, snapshot, changes):
        file = snapshot / 'metadata.json'
        metadata = json.loads(file.read_text())
        metadata.update(changes)
        file.write_text(json.dumps(metadata, ensure_ascii=False, indent=2) + '\n')
        hashes = self.pages.hashes(snapshot)
        hashes.pop('files.json', None)
        (snapshot / 'files.json').write_text(json.dumps(hashes, indent=2) + '\n')

    def assert_destination_untouched(self):
        self.assertEqual(list(self.site.iterdir()), [])
        self.assertFalse(self.folder.exists())

    def test_root_or_nested_git_payload_is_rejected_before_import(self):
        for git_path in (self.incoming / '.git',
                         self.incoming / 'snapshots' / self.sha / 'app' / '.git'):
            with self.subTest(path=git_path.relative_to(self.incoming)):
                git_path.mkdir()
                (git_path / 'config').write_text('untrusted repository configuration')
                with self.assertRaises(lab.LabError):
                    self.run_merge()
                self.assert_destination_untouched()
                shutil.rmtree(git_path)

    def test_symlink_as_artifact_root_is_rejected_without_following_it(self):
        actual = self.fixture.folder / 'real-incoming-site'
        self.incoming.rename(actual)
        self.incoming.symlink_to(actual, target_is_directory=True)
        with self.assertRaises(lab.LabError):
            self.run_merge()
        self.assert_destination_untouched()

    def test_an_extra_valid_snapshot_cannot_cross_the_candidate_boundary(self):
        extra = 'b' * 40
        extra_snapshot = self.incoming / 'snapshots' / extra
        shutil.copytree(self.incoming / 'snapshots' / self.sha, extra_snapshot)
        self.rewrite_metadata(extra_snapshot, {'source_sha': extra})
        self.assertEqual(len(self.pages.validate_site(self.incoming)), 2)
        with self.assertRaises(lab.LabError):
            self.run_merge()
        self.assert_destination_untouched()

    def test_self_consistent_metadata_must_still_match_trusted_git_inputs(self):
        snapshot = self.incoming / 'snapshots' / self.sha
        original = json.loads((snapshot / 'metadata.json').read_text())
        mismatches = {'source_tree': 'c' * 40,
                      'source_build_inputs': {**original['source_build_inputs'], 'flavor': 'other'},
                      'pages_build_inputs': {**original['pages_build_inputs'], 'command': ['flutter', 'build', 'web', '--debug']},
                      'source_fingerprint': 'f' * 64}
        for key, value in mismatches.items():
            with self.subTest(key=key):
                self.rewrite_metadata(snapshot, {**original, key: value})
                self.assertEqual(self.pages.validate_site(self.incoming), [self.sha])
                with self.assertRaises(lab.LabError):
                    self.run_merge()
                self.assert_destination_untouched()
        self.rewrite_metadata(snapshot, original)

    def test_divergent_historical_snapshot_is_preserved_instead_of_overwritten(self):
        shutil.copytree(self.incoming, self.site, dirs_exist_ok=True)
        snapshot = self.site / 'snapshots' / self.sha
        self.rewrite_metadata(snapshot, {'source_fingerprint': '0' * 64})
        self.assertEqual(self.pages.validate_site(self.site), [self.sha])
        before = self.pages.hashes(self.site)
        with self.assertRaises(lab.LabError):
            self.run_merge()
        self.assertEqual(self.pages.hashes(self.site), before)
        self.assertFalse(self.folder.exists())


if __name__ == '__main__':
    unittest.main()
