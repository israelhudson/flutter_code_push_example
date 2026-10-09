"""Offline bridge tests: synthetic provider/review/device data, no remote effects."""
from contextlib import ExitStack
import copy
import hashlib
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch
import zipfile

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / 'tools/delivery'))
import release_lab as lab
import rehearse_release_lab as rehearsal
import shorebird_delivery as mobile


def target():
    return {'schema': 1, 'platform': 'android', 'app_id': mobile.APP_ID,
            'release_version': '1.1.0+2', 'provider_release_id': 776887,
            'flutter_version': '3.44.9', 'flutter_revision': 'c' * 40,
            'base_git_sha': None, 'patch_number': None, 'execution': mobile.EXECUTION,
            'generation_track': 'staging', 'promotion_track': 'stable',
            'device_validation_required': True, 'note': 'OFFLINE fixture; no live distribution.'}


def provider_patch(number, channel='staging'):
    pid = 600000 + number
    return {'id': pid, 'number': number, 'channel': channel, 'is_rolled_back': False,
            'artifacts': [{'id': pid * 10 + i, 'patch_id': pid, 'arch': arch,
                           'platform': 'android', 'hash': hashlib.sha256((str(number) + arch).encode()).hexdigest(),
                           'size': 6000 + i} for i, arch in enumerate(mobile.ARCHES)]}


def query(plan, kind, data, number=None):
    key = {'release': 'release', 'list': 'patches', 'info': 'patch'}[kind]
    command = {'release': 'releases info', 'list': 'patches list', 'info': 'patches info'}[kind]
    return mobile.observation(plan, kind, {'status': 'success', 'data': {key: data},
                                           'meta': {'command': command, 'version': '1.6.116'}}, number)


class ShorebirdBridgeTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='shorebird-bridge-offline-')
        self.addCleanup(self.temp.cleanup)
        self.world = rehearsal.OfflineWorld(self.temp.name)
        self.addCleanup(self.world.close)
        self.target = target()
        (self.world.repo / 'delivery/shorebird-lab-target.json').write_text(json.dumps(self.target))
        self.tag = self.world.prepare()
        self.world.freeze_report(self.tag)
        self.patch2 = provider_patch(2)
        self.before = query(self.target, 'list', [provider_patch(1, 'stable')])
        self.after = query(self.target, 'list', [provider_patch(1, 'stable'), self.patch2])
        self.staging = query(self.target, 'info', self.patch2, 2)
        self.release = query(self.target, 'release', {'id': 776887, 'app_id': mobile.APP_ID,
            'version': '1.1.0+2', 'flutter_revision': 'c' * 40, 'flutter_version': '3.44.9',
            'platform_statuses': {'android': 'active'}})
        self.dry = self.command(True)
        self.patch_failure = None

    @property
    def record(self):
        return self.world.state['candidates'][self.tag]

    def command(self, dry, intent_id=None):
        return {'schema': 1, 'target': mobile.target_identity(self.target),
                'source_sha': self.world.source, 'argv': mobile.patch_argv(self.target, dry),
                'exit_code': 0, 'stdout_sha256': 'd' * 64, 'stderr_sha256': 'e' * 64,
                'aab_sha256': 'a' * 64, 'intent_id': intent_id,
                'captured_at': '2026-10-09T10:00:00+00:00',
                'evidence_kind': 'local_operator_cli_and_aab',
                'local_artifacts': [{'arch': a['arch'], 'platform': 'android', 'hash': a['hash']}
                                    for a in mobile.clean_patch(self.patch2)['artifacts']]}

    def api(self, path, data=None, method='GET', missing=False):
        if method != 'PATCH':
            return self.world.api(path, data, method, missing)
        self.assertEqual(path, lab.endpoint('releases/100'))
        self.assertEqual(set(data), {'body'})
        self.world.calls.append({'path': 'releases/100', 'method': method, 'data': copy.deepcopy(data)})
        if self.patch_failure == 'before':
            raise lab.LabError('Offline missing reply before effect')
        self.world.releases[0]['body'] = data['body']
        if self.patch_failure == 'after':
            raise lab.LabError('Offline reply lost after effect')
        return copy.deepcopy(self.world.releases[0])

    def call(self, function, *args, **kwargs):
        with ExitStack() as stack:
            stack.enter_context(patch.object(lab, 'ROOT', self.world.repo))
            stack.enter_context(patch.object(lab, 'api', side_effect=self.api))
            stack.enter_context(patch.object(lab, 'git', side_effect=self.world.git))
            stack.enter_context(patch.dict(lab.os.environ, self.world.env))
            stack.enter_context(patch.object(lab.time, 'sleep'))
            stack.enter_context(patch.object(mobile, 'verify_local_checkout'))
            stack.enter_context(patch.object(mobile, 'authenticated_executor', return_value={**rehearsal.ISRAEL, 'type': 'User'}))
            return function(self.world.policy, self.tag, *args, **kwargs)

    def publish_github(self):
        self.world.approve('first', self.tag); self.world.approve('second', self.tag)
        self.world.authorize(); self.world.finish(self.tag)

    def plan(self):
        self.publish_github()
        result = self.call(mobile.plan, self.release, self.before, self.dry)
        self.intent = result['intent']
        self.generation = self.command(False, self.intent['intent_id'])
        return result

    def begin(self):
        self.plan()
        return self.call(mobile.begin_upload, self.intent['intent_id'])

    def device(self):
        return {'schema': 1, 'intent_id': self.intent['intent_id'], 'source_sha': self.world.source,
                'target': mobile.target_identity(self.target), 'track': 'staging', 'patch_number': 2,
                'observed_patch_number': 2, 'cold_restart': True, 'device': 'offline-emulator',
                'pid_before': 3656, 'pid_after': 4376, 'screenshot_sha256': 'b' * 64,
                'sdk_log_sha256': 'c' * 64}

    def receipt(self, device=None, stable=None):
        return self.call(mobile.record_receipt, self.after, self.staging, self.generation,
                         device=device, stable_info=stable)

    def completed(self):
        self.begin(); self.receipt(); device = self.device(); self.receipt(device)
        stable = query(self.target, 'info', provider_patch(2, 'stable'), 2)
        return self.receipt(device, stable)

    def test_no_intent_before_github_release_two_approvals_and_final_command(self):
        with self.assertRaises(lab.LabError):
            self.call(mobile.plan, self.release, self.before, self.dry)
        self.assertNotIn('mobile_delivery', self.record)
        self.world.approve('first', self.tag)
        with self.assertRaises(lab.LabError):
            self.call(mobile.plan, self.release, self.before, self.dry)

    def test_plan_intent_is_separate_and_idempotent_without_upload_permission(self):
        result = self.plan()
        originals = copy.deepcopy({k: self.record[k] for k in ('report', 'publication', 'receipt')})
        second = self.call(mobile.plan, self.release, self.before, self.dry)
        self.assertTrue(result['new_intent_recorded']); self.assertFalse(result['upload_permitted'])
        self.assertFalse(second['new_intent_recorded']); self.assertEqual(second['intent'], result['intent'])
        self.assertEqual(originals, {k: self.record[k] for k in originals})

    def test_begin_upload_persists_unknown_once_and_repeated_invocation_blocks(self):
        result = self.begin()
        self.assertTrue(result['upload_permitted_once'])
        self.assertEqual(self.record['mobile_delivery']['status'], 'upload_response_unknown')
        with self.assertRaises(lab.LabError):
            self.call(mobile.begin_upload, self.intent['intent_id'])

    def test_dry_run_wrong_sha_bypass_or_failed_exit_blocks_intent(self):
        self.publish_github()
        for key, value in [('source_sha', 'f' * 40), ('exit_code', 1),
                           ('argv', self.dry['argv'] + ['--allow-asset-diffs']), ('exit_code', False)]:
            bad = copy.deepcopy(self.dry); bad[key] = value
            with self.subTest(key=key, value=value), self.assertRaises(lab.LabError):
                self.call(mobile.plan, self.release, self.before, bad)
        self.assertNotIn('mobile_delivery', self.record)

    def test_observations_require_exact_target_query_and_release_revision_version(self):
        for key, value in [('flutter_revision', 'f' * 40), ('flutter_version', '3.44.1'),
                           ('app_id', 'ffffffff-ffff-ffff-ffff-ffffffffffff'), ('id', 99)]:
            raw = copy.deepcopy(self.release['data']); raw[key] = value
            with self.subTest(key=key), self.assertRaises(lab.LabError):
                query(self.target, 'release', raw)
        bad = copy.deepcopy(self.before); bad['argv'] = bad['argv'][:-1] + ['--release-version', 'latest']
        with self.assertRaises(lab.LabError):
            mobile.validate_observation(bad, self.target, 'list')

    def test_boolean_schema_and_exit_code_are_not_integer_proof(self):
        for proof, kind in [(self.before, 'list'), (self.release, 'release')]:
            for key, value in [('schema', True), ('exit_code', False)]:
                bad = copy.deepcopy(proof); bad[key] = value
                with self.subTest(key=key, kind=kind), self.assertRaises(lab.LabError):
                    mobile.validate_observation(bad, self.target, kind)
        bad = copy.deepcopy(self.dry); bad['schema'] = True
        with self.assertRaises(lab.LabError):
            mobile.validate_command(bad, self.target, self.world.source, True)

    def test_track_base_and_arbitrary_plan_extras_cannot_be_added(self):
        for key, value in [('generation_track', 'stable'), ('release_version', 'latest'),
                           ('base_git_sha', 'a' * 40), ('patch_number', 2), ('ignore_assets', True)]:
            bad = copy.deepcopy(self.target); bad[key] = value
            with self.subTest(key=key), self.assertRaises((lab.LabError, ValueError)):
                mobile.validate_target(bad)

    def test_zero_or_many_new_patches_and_removed_history_are_unknown(self):
        self.begin()
        cases = [[provider_patch(1, 'stable')],
                 [provider_patch(1, 'stable'), self.patch2, provider_patch(3)], [self.patch2]]
        for patches in cases:
            after = query(self.target, 'list', patches)
            with self.subTest(count=len(patches)), self.assertRaises(lab.LabError):
                self.call(mobile.record_receipt, after, self.staging, self.generation)
        self.assertEqual(self.record['mobile_delivery']['status'], 'upload_response_unknown')
        self.assertNotIn('receipt', self.record['mobile_delivery'])

    def test_foreign_code_patch_number_match_cannot_replace_local_aab_hashes(self):
        self.begin(); bad = copy.deepcopy(self.generation)
        bad['local_artifacts'][0]['hash'] = 'f' * 64
        with self.assertRaises(lab.LabError):
            self.call(mobile.record_receipt, self.after, self.staging, bad)

    def test_generation_failed_or_unbound_intent_cannot_produce_receipt(self):
        self.begin()
        for key, value in [('exit_code', 70), ('intent_id', 'f' * 64), ('source_sha', 'e' * 40)]:
            bad = copy.deepcopy(self.generation); bad[key] = value
            with self.subTest(key=key), self.assertRaises(lab.LabError):
                self.call(mobile.record_receipt, self.after, self.staging, bad)

    def test_staging_device_and_stable_are_distinct_durable_states(self):
        self.begin(); staged = self.receipt()
        self.assertTrue(staged['patch_generated']); self.assertFalse(staged['device_execution_verified'])
        self.assertFalse(staged['stable_confirmed'])
        device = self.device(); observed = self.receipt(device)
        self.assertTrue(observed['device_execution_verified']); self.assertFalse(observed['stable_confirmed'])
        stable = query(self.target, 'info', provider_patch(2, 'stable'), 2)
        promoted = self.receipt(device, stable)
        self.assertTrue(promoted['stable_confirmed'])
        self.assertFalse(promoted['store_delivery_performed'])

    def test_stable_requires_prior_device_receipt_not_just_a_simultaneous_claim(self):
        self.begin(); stable = query(self.target, 'info', provider_patch(2, 'stable'), 2)
        with self.assertRaises(lab.LabError):
            self.receipt(self.device(), stable)
        self.assertNotIn('receipt', self.record['mobile_delivery'])

    def test_device_wrong_patch_same_pid_or_missing_cold_restart_cannot_validate(self):
        self.begin(); self.receipt()
        for key, value in [('observed_patch_number', 1), ('pid_after', 3656), ('cold_restart', False),
                           ('track', 'stable'), ('source_sha', 'f' * 40)]:
            bad = self.device(); bad[key] = value
            with self.subTest(key=key), self.assertRaises(lab.LabError):
                self.receipt(bad)

    def test_existing_device_and_stable_evidence_cannot_regress(self):
        self.completed()
        with self.assertRaises(lab.LabError):
            self.receipt()

    def test_release_extension_retains_original_bytes_and_original_receipt(self):
        receipt = self.completed(); original = copy.deepcopy(self.record['publication'])
        self.call(mobile.append_release)
        body = self.world.releases[0]['body']
        self.assertTrue(body.startswith(original['release_payload']['body']))
        self.assertIn('Patch confirmado', body); self.assertIn(receipt['receipt_digest'], body)
        self.assertEqual(self.record['publication'], original)
        self.assertEqual(self.record['mobile_delivery']['status'], 'completed')

    def test_response_lost_after_release_patch_is_confirmed_by_get_without_second_patch(self):
        self.completed(); self.patch_failure = 'after'
        self.call(mobile.append_release)
        self.call(mobile.append_release)
        self.assertEqual(len([c for c in self.world.calls if c['method'] == 'PATCH']), 1)

    def test_unknown_patch_response_does_not_blind_retry_after_absent_effect(self):
        self.completed(); self.patch_failure = 'before'
        with self.assertRaises(lab.LabError):
            self.call(mobile.append_release)
        self.patch_failure = None
        with self.assertRaises(lab.LabError):
            self.call(mobile.append_release)
        self.assertEqual(len([c for c in self.world.calls if c['method'] == 'PATCH']), 1)
        self.assertEqual(self.record['mobile_delivery']['release_extension']['status'], 'patch_response_unknown')

    def test_lost_journal_claim_reply_does_not_authorize_a_retried_patch(self):
        self.completed()
        self.world.inject_failure('contents/' + lab.STATE_PATH, method='PUT', after=True, count=1)
        with self.assertRaises(lab.LabError):
            self.call(mobile.append_release)
        self.assertFalse(any(c['method'] == 'PATCH' for c in self.world.calls))
        self.assertEqual(self.record['mobile_delivery']['release_extension']['status'], 'patch_response_unknown')

    def test_concurrent_claim_created_after_initial_read_does_not_allow_second_patch(self):
        self.completed(); real_mutate = lab.mutate
        def interleaved(policy, tag, callback, action):
            if action == 'mobile_release_extension_intent':
                real_mutate(policy, tag, callback, action)
            return real_mutate(policy, tag, callback, action)
        with patch.object(lab, 'mutate', side_effect=interleaved), self.assertRaises(lab.LabError):
            self.call(mobile.append_release)
        self.assertFalse(any(c['method'] == 'PATCH' for c in self.world.calls))

    def test_manual_release_body_edit_is_never_overwritten(self):
        self.completed(); self.world.releases[0]['body'] += '\nManual edit\n'
        with self.assertRaises(lab.LabError):
            self.call(mobile.append_release)
        self.assertFalse(any(c['method'] == 'PATCH' for c in self.world.calls))

    def test_unowned_preexisting_extension_cannot_be_adopted(self):
        receipt = self.completed()
        expected = mobile.expected_extension(self.intent, self.record['publication'], receipt, self.target, self.world.policy['operators'])
        self.world.releases[0]['body'] = expected['body']
        with self.assertRaises(lab.LabError):
            self.call(mobile.append_release)
        self.assertNotIn('release_extension', self.record['mobile_delivery'])

    def test_reader_rejects_self_consistent_forgery_from_other_sha_or_github_intent(self):
        self.completed(); self.call(mobile.append_release)
        for key, value in [('source_sha', 'f' * 40), ('github_intent_id', 'e' * 64),
                           ('report_digest', 'd' * 64), ('decision_digest', 'c' * 64)]:
            forged = copy.deepcopy(self.record['mobile_delivery'])
            forged['intent'][key] = value
            identity = {k: v for k, v in forged['intent'].items() if k != 'intent_id'}
            forged['intent']['intent_id'] = lab.digest(identity)
            forged['receipt']['intent_id'] = forged['intent']['intent_id']
            forged['receipt']['source_sha'] = forged['intent']['source_sha']
            forged['receipt']['receipt_digest'] = lab.digest({k: v for k, v in forged['receipt'].items() if k != 'receipt_digest'})
            with self.subTest(key=key), self.assertRaises(lab.LabError):
                mobile.verify_mobile_release_extension(self.world.releases[0], self.record['publication'], forged, self.target, self.world.policy['operators'])

    def test_reader_rejects_changed_approved_plan_even_if_internal_hashes_are_recomputed(self):
        self.completed(); self.call(mobile.append_release)
        approved = copy.deepcopy(self.target); approved['provider_release_id'] = 999
        with self.assertRaises(lab.LabError):
            mobile.verify_mobile_release_extension(self.world.releases[0], self.record['publication'], self.record['mobile_delivery'], approved, self.world.policy['operators'])

    def test_root_release_verifier_accepts_extension_and_preserves_original_github_proof(self):
        self.completed(); self.call(mobile.append_release)
        original = self.record['receipt']['github_release']
        verified = lab.verify_release(self.world.releases[0], self.record['publication'],
                                      record=self.record, policy=self.world.policy)
        self.assertEqual(verified, original)
        with self.assertRaises(lab.LabError):
            lab.verify_release(self.world.releases[0], self.record['publication'])

    def test_root_release_verifier_rejects_forged_operator_policy_digest(self):
        self.completed(); self.call(mobile.append_release)
        forged = copy.deepcopy(self.world.policy); forged['operators'] = [rehearsal.FABRICIA]
        with self.assertRaises(lab.LabError):
            lab.verify_release(self.world.releases[0], self.record['publication'],
                               record=self.record, policy=forged)

    def test_extra_private_fields_in_input_proofs_are_rejected_before_journal_write(self):
        self.publish_github()
        for name in ('release', 'before', 'dry'):
            bad = copy.deepcopy(getattr(self, name)); bad['token'] = 'private-secret'
            args = [self.release, self.before, self.dry]
            args[{'release': 0, 'before': 1, 'dry': 2}[name]] = bad
            revision = self.world.state_revision
            with self.subTest(proof=name), self.assertRaises(lab.LabError):
                self.call(mobile.plan, *args)
            self.assertEqual(self.world.state_revision, revision)
        self.assertNotIn('private-secret', lab.canonical(self.world.state))

    def test_extra_private_nested_query_command_device_fields_are_rejected(self):
        self.begin(); self.receipt()
        variants = []
        after = copy.deepcopy(self.after); after['data'][1]['raw_stdout'] = 'private-secret'
        variants.append((after, self.staging, self.generation, None))
        proof = copy.deepcopy(self.generation); proof['local_artifacts'][0]['token'] = 'private-secret'
        variants.append((self.after, self.staging, proof, None))
        device = self.device(); device['credentials'] = 'private-secret'
        variants.append((self.after, self.staging, self.generation, device))
        for args in variants:
            revision = self.world.state_revision
            with self.assertRaises(lab.LabError):
                self.call(mobile.record_receipt, *args)
            self.assertEqual(self.world.state_revision, revision)
        self.assertNotIn('private-secret', lab.canonical(self.world.state))

    def test_executor_requires_real_user_operator_identity_not_environment_variables(self):
        for user in ({**rehearsal.FABRICIA, 'type': 'User'},
                     {**rehearsal.ISRAEL, 'type': 'Bot'},
                     {**rehearsal.ISRAEL, 'type': 'User', 'token': 'secret'}):
            with self.assertRaises(lab.LabError):
                mobile.validate_executor(user, self.world.policy['operators'])
        completed = type('Result', (), {'returncode': 0, 'stdout': json.dumps({**rehearsal.ISRAEL, 'type': 'User'})})()
        with patch.object(mobile.subprocess, 'run', return_value=completed) as run:
            snapshot = mobile.authenticated_executor(self.world.policy)
        self.assertEqual(snapshot['id'], rehearsal.ISRAEL['id'])
        self.assertEqual(run.call_args.args[0], ['gh', 'api', '--hostname', 'github.com', 'user', '--jq', '{id,login,type}'])

    def test_pure_reader_rejects_executor_outside_frozen_operators(self):
        self.completed(); self.call(mobile.append_release)
        with self.assertRaises(lab.LabError):
            mobile.verify_mobile_release_extension(self.world.releases[0], self.record['publication'],
                                                   self.record['mobile_delivery'], self.target, [rehearsal.FABRICIA])

    def test_ignored_pubspec_override_cannot_hide_dependencies_outside_approved_sha(self):
        (self.world.repo / 'shorebird.yaml').write_text('app_id: ' + mobile.APP_ID + '\n')
        self.world.local_git('add', 'shorebird.yaml')
        self.world.local_git('commit', '-m', 'fixture approved app identity')
        source = self.world.local_git('rev-parse', 'HEAD')
        (self.world.repo / '.git/info/exclude').write_text('pubspec_overrides.yaml\n')
        (self.world.repo / 'pubspec_overrides.yaml').write_text('dependency_overrides: {}\n')
        with patch.object(lab, 'ROOT', self.world.repo), patch.object(Path, 'cwd', return_value=self.world.repo),\
                patch.object(lab, 'git', side_effect=self.world.git), self.assertRaises(lab.LabError):
            mobile.verify_local_checkout(source)

    def test_missing_provider_arch_duplicate_arch_or_rolled_back_patch_is_rejected(self):
        for mutate in (lambda p: p['artifacts'].pop(),
                       lambda p: p['artifacts'][0].update(arch=p['artifacts'][1]['arch']),
                       lambda p: p.update(is_rolled_back=True)):
            bad = provider_patch(2); mutate(bad)
            with self.assertRaises(lab.LabError):
                query(self.target, 'info', bad, 2)

    def test_provider_observation_drops_notes_email_and_signed_urls(self):
        raw = provider_patch(2); raw.update(notes='private@example.com', download_url='https://signed.invalid/?token=secret')
        raw['artifacts'][0]['url'] = 'https://signed.invalid/?token=secret'
        captured = query(self.target, 'info', raw, 2)
        self.assertNotIn('private@example.com', lab.canonical(captured))
        self.assertNotIn('signed.invalid', lab.canonical(captured))

    def test_aab_hashes_use_full_libapp_bytes_not_diff_files(self):
        aab = Path(self.temp.name) / 'fixture.aab'
        with zipfile.ZipFile(aab, 'w') as archive:
            for arch, abi in mobile.ARCHES.items():
                archive.writestr('base/lib/' + abi + '/libapp.so', arch.encode())
        artifacts = mobile.aab_artifacts(aab)
        self.assertEqual({a['arch']: a['hash'] for a in artifacts},
                         {arch: hashlib.sha256(arch.encode()).hexdigest() for arch in mobile.ARCHES})

    def test_bridge_contains_no_remote_shorebird_mutation_executor(self):
        for kind in ('release', 'list', 'info'):
            args = mobile.provider_argv(self.target, kind, 2 if kind == 'info' else None)
            self.assertIn('info' if kind in ('release', 'info') else 'list', args)
            self.assertNotIn('patch', args); self.assertNotIn('set-track', args); self.assertNotIn('promote', args)


if __name__ == '__main__':
    unittest.main()
