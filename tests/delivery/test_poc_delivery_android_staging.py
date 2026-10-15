"""Offline authorization/recovery tests. No GitHub or Shorebird effects."""
import copy
import hashlib
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / 'tools/delivery'))
import delivery_android_staging as bridge


def reviewer_snapshot():
    person = {'id': '1b2c3d4e-1515-4000-8000-000000000001', 'revision': 1,
              'name': 'Israel Hudson', 'slack_user': 'U0BMFQKC001',
              'github_user_id': 18661493, 'github_login': 'israelhudson'}
    return {'schema': 'delivery-reviewers-v1', 'repository': bridge.lab.REPOSITORY,
            'team_id': 'T09CYB7AS77', 'solo': True,
            'technical': person, 'business': copy.deepcopy(person)}


class AndroidStagingTests(unittest.TestCase):
    def setUp(self):
        self.candidate = 'delivery-' + 'a' * 32
        self.source = 'b' * 40
        self.plan = bridge.expected_plan()
        self.target = self.plan['target']
        self.manifest = {'id': self.candidate, 'repository': bridge.lab.REPOSITORY,
                         'version': '1.20.0', 'source_sha': self.source,
                         'publication_scope': 'github_test', 'rc_number': 2,
                         'validation_mode': 'full',
                         'rc_tag': 'poc-v1.20.0-rc.2', 'reviewers': reviewer_snapshot(),
                         'mobile_execution_plan': self.plan}
        self.events = []
        for revision, status in enumerate(('pending', 'approved', 'publishing', 'published')):
            self.events.append({'candidate': self.candidate, 'source_sha': self.source,
                                'revision': revision, 'solo': True, 'status': status,
                                'reviewers': reviewer_snapshot(), 'rejected_role': None,
                                'rejected_at': None,
                                'technical_at': '2026-10-15T18:00:00+00:00' if revision else None,
                                'business_at': '2026-10-15T18:00:01+00:00' if revision else None,
                                'publication_run': '100' if revision >= 2 else None})
        self.run = {'id': 100, 'repository': {'full_name': bridge.lab.REPOSITORY},
                    'event': 'workflow_dispatch', 'head_branch': 'main',
                    'path': '.github/workflows/delivery-publish.yml',
                    'status': 'completed', 'conclusion': 'success'}
        self.release = {'id': 200, 'tag_name': 'poc-v1.20.0', 'draft': False, 'prerelease': False,
                        'html_url': 'https://github.com/' + bridge.lab.REPOSITORY + '/releases/tag/poc-v1.20.0',
                        'assets': []}
        self.ref = {'object': {'type': 'commit', 'sha': self.source}}
        self.proof = self.authorize()

    def authorize(self, **changes):
        args = {'manifest': self.manifest, 'events': self.events, 'run': self.run,
                'release': self.release, 'rc': self.ref, 'final': self.ref}
        args.update(changes)
        return bridge.verify_authorization(**args)

    def patch(self, number, channel='staging'):
        pid = 10000 + number
        return {'id': pid, 'number': number, 'channel': channel, 'is_rolled_back': False,
                'artifacts': [{'id': pid * 10 + i, 'patch_id': pid, 'arch': arch,
                               'platform': 'android', 'hash': hashlib.sha256((arch + str(number)).encode()).hexdigest(),
                               'size': 9000} for i, arch in enumerate(bridge.mobile.ARCHES)]}

    def query(self, kind, data, number=None):
        key = {'list': 'patches', 'info': 'patch'}[kind]
        return bridge.mobile.observation(self.target, kind, {'status': 'success', 'data': {key: data},
            'meta': {'command': 'patches ' + kind, 'version': '1.6.116'}}, number)

    def command(self, dry, intent=None):
        return {'schema': 1, 'target': bridge.mobile.target_identity(self.target),
                'source_sha': self.source, 'argv': bridge.mobile.patch_argv(self.target, dry),
                'exit_code': 0, 'stdout_sha256': 'd' * 64, 'stderr_sha256': 'e' * 64,
                'aab_sha256': 'f' * 64, 'intent_id': intent,
                'captured_at': '2026-10-15T18:30:00+00:00', 'evidence_kind': 'local_operator_cli_and_aab',
                'local_artifacts': [{'arch': a['arch'], 'platform': 'android', 'hash': a['hash']}
                                    for a in self.patch(5)['artifacts']]}

    def receipt_inputs(self):
        intent = {'schema': 'delivery-android-staging-intent-v1', 'candidate_id': self.candidate,
                  'source_sha': self.source, 'report_digest': bridge.lab.digest(self.manifest),
                  'authorization': self.proof, 'operator': bridge.OPERATOR,
                  'mobile_execution_plan': self.plan, 'dry_run': self.command(True),
                  'patches_before': self.query('list', [self.patch(4)]),
                  'attempt': 'synthetic-offline', 'state': 'upload_response_unknown'}
        intent['intent_id'] = bridge.lab.digest(intent)
        return {'manifest': self.manifest, 'proof': self.proof, 'intent': intent,
                'generation': self.command(False, intent['intent_id']),
                'after': self.query('list', [self.patch(4), self.patch(5)]),
                'info': self.query('info', self.patch(5), 5)}

    def test_same_person_in_two_frozen_roles_is_valid_only_in_explicit_solo(self):
        self.assertEqual(self.proof['source_sha'], self.source)
        changed = copy.deepcopy(self.manifest)
        changed['reviewers']['solo'] = False
        with self.assertRaises(bridge.lab.LabError):
            self.authorize(manifest=changed)

    def test_one_role_acceptance_never_authorizes_upload(self):
        changed = copy.deepcopy(self.events)
        for event in changed:
            event['business_at'] = None
        with self.assertRaises(bridge.lab.LabError):
            self.authorize(events=changed)

    def test_pending_rejected_or_cancelled_history_never_authorizes(self):
        for status in ('pending', 'approved', 'publishing', 'rejected', 'cancelled'):
            changed = copy.deepcopy(self.events)
            changed[-1]['status'] = status
            with self.subTest(status=status), self.assertRaises(bridge.lab.LabError):
                self.authorize(events=changed)

    def test_changed_acceptance_or_missing_revision_is_rejected(self):
        for changed in (copy.deepcopy(self.events), self.events[1:]):
            changed[-1]['technical_at'] = '2026-10-15T18:01:00+00:00'
            with self.assertRaises(bridge.lab.LabError):
                self.authorize(events=changed)

    def test_no_environment_actor_or_manual_run_can_replace_real_publication(self):
        for change in ({'head_branch': 'slack-main'}, {'event': 'schedule'},
                       {'conclusion': 'failure'}, {'status': 'in_progress'},
                       {'path': '.github/workflows/release-lab-evaluate.yml'}, {'id': 101}):
            with self.subTest(change=change), self.assertRaises(bridge.lab.LabError):
                self.authorize(run={**self.run, **change})

    def test_rc_and_final_tags_must_both_point_to_approved_commit(self):
        for name in ('rc', 'final'):
            for ref in ({'object': {'type': 'commit', 'sha': 'c' * 40}},
                        {'object': {'type': 'tag', 'sha': self.source}}):
                with self.subTest(name=name, ref=ref), self.assertRaises(bridge.lab.LabError):
                    self.authorize(**{name: ref})

    def test_unapproved_mobile_plan_or_wrong_source_in_event_fails(self):
        changed = copy.deepcopy(self.manifest)
        changed['mobile_execution_plan']['stable_authorized'] = True
        with self.assertRaises(bridge.lab.LabError):
            self.authorize(manifest=changed)
        changed = copy.deepcopy(self.events)
        changed[0]['source_sha'] = 'c' * 40
        with self.assertRaises(bridge.lab.LabError):
            self.authorize(events=changed)

    def test_prerelease_is_not_a_final_publication(self):
        with self.assertRaises(bridge.lab.LabError):
            self.authorize(release={**self.release, 'prerelease': True})

    def test_controls_only_candidate_never_authorizes_android_patch(self):
        for mode in ('controls_only', None):
            with self.subTest(mode=mode), self.assertRaises(bridge.lab.LabError):
                self.authorize(manifest={**self.manifest, 'validation_mode': mode})

    def test_actual_operator_and_clean_checkout_precede_provider_queries(self):
        with tempfile.TemporaryDirectory() as out, \
                patch.object(bridge.mobile, 'authenticated_executor', side_effect=bridge.lab.LabError('auth')) as auth, \
                patch.object(bridge, 'authorization') as authorization:
            with self.assertRaises(bridge.lab.LabError):
                bridge.readiness(self.candidate, Path(out))
            authorization.assert_not_called()
            self.assertEqual(auth.call_args.args[0]['operators'], [bridge.OPERATOR])
        with tempfile.TemporaryDirectory() as out, \
                patch.object(bridge.mobile, 'authenticated_executor', return_value=bridge.OPERATOR), \
                patch.object(bridge, 'authorization', return_value=(self.manifest, self.proof, self.release)), \
                patch.object(bridge.mobile, 'verify_local_checkout'), \
                patch.object(bridge.lab, 'git', return_value='?? lib/hidden.dart'), \
                patch.object(bridge.mobile, 'capture_provider') as provider:
            with self.assertRaises(bridge.lab.LabError):
                bridge.readiness(self.candidate, Path(out))
            provider.assert_not_called()

    def test_receipt_has_real_provider_number_and_no_device_or_stable_claim(self):
        receipt = bridge.make_receipt(**self.receipt_inputs())
        self.assertEqual(receipt['patch_number'], 5)
        self.assertEqual(receipt['provider_patch_id'], 10005)
        self.assertTrue(receipt['uploaded'])
        self.assertFalse(receipt['promoted_to_stable'])
        self.assertFalse(receipt['device_validation']['successful_launch_confirmed'])
        self.assertFalse(receipt['device_validation']['cold_restart_confirmed'])

    def test_wrong_hash_of_even_one_architecture_fails(self):
        args = self.receipt_inputs()
        args['generation']['local_artifacts'][0]['hash'] = '0' * 64
        with self.assertRaises(bridge.lab.LabError):
            bridge.make_receipt(**args)

    def test_zero_multiple_or_missing_old_patches_remain_unknown(self):
        for patches in ([self.patch(4)], [self.patch(4), self.patch(5), self.patch(6)], [self.patch(5)]):
            args = self.receipt_inputs()
            args['after'] = self.query('list', patches)
            with self.subTest(count=len(patches)), self.assertRaises(bridge.lab.LabError):
                bridge.make_receipt(**args)

    def test_stable_or_another_sha_cannot_be_presented_as_this_upload(self):
        args = self.receipt_inputs()
        args['after'] = self.query('list', [self.patch(4), self.patch(5, 'stable')])
        args['info'] = self.query('info', self.patch(5, 'stable'), 5)
        with self.assertRaises(bridge.lab.LabError):
            bridge.make_receipt(**args)
        args = self.receipt_inputs()
        args['generation']['source_sha'] = 'f' * 40
        with self.assertRaises(bridge.lab.LabError):
            bridge.make_receipt(**args)

    def test_intent_cannot_be_changed_after_reservation(self):
        args = self.receipt_inputs()
        args['intent']['source_sha'] = 'd' * 40
        with self.assertRaises(bridge.lab.LabError):
            bridge.make_receipt(**args)

    def test_upload_never_repeats_existing_intent_even_if_response_was_lost(self):
        with tempfile.TemporaryDirectory() as out, \
                patch.object(bridge, 'readiness', return_value=(self.manifest, self.proof, self.release, bridge.OPERATOR)), \
                patch.object(bridge, 'other_pending'), \
                patch.object(bridge, 'history_head', return_value='f' * 40), \
                patch.object(bridge, 'json_record', return_value={'state': 'upload_response_unknown'}), \
                patch.object(bridge, 'run_patch') as upload:
            with self.assertRaises(bridge.lab.LabError):
                bridge.upload(self.candidate, Path(out))
            upload.assert_not_called()

    def test_create_only_reservation_refuses_existing_record_and_racing_writer(self):
        path = f'candidates/{self.candidate}/{bridge.INTENT}'
        with patch.object(bridge, 'history_head', return_value='a' * 40), \
                patch.object(bridge, 'json_record', return_value={'exists': True}), \
                patch.object(bridge.lab, 'api') as api:
            with self.assertRaises(bridge.lab.LabError):
                bridge.create_once(path, {'value': 1})
            api.assert_not_called()
        with patch.object(bridge, 'history_head', return_value='a' * 40), \
                patch.object(bridge, 'json_record', return_value=None), \
                patch.object(bridge.lab, 'api', side_effect=bridge.lab.LabError('lost PUT reply')):
            with self.assertRaisesRegex(bridge.lab.LabError, 'upload proibido'):
                bridge.create_once(path, {'value': 1})

    def test_reconcile_requires_local_generation_proof_before_provider_number(self):
        with tempfile.TemporaryDirectory() as out, \
                patch.object(bridge, 'readiness', return_value=(self.manifest, self.proof, self.release, bridge.OPERATOR)), \
                patch.object(bridge, 'history_head', return_value='a' * 40), \
                patch.object(bridge, 'json_record', return_value=self.receipt_inputs()['intent']), \
                patch.object(bridge.mobile, 'capture_provider') as provider:
            with self.assertRaises(bridge.lab.LabError):
                bridge.reconcile(self.candidate, Path(out))
            provider.assert_not_called()

    def test_existing_exact_asset_does_not_trigger_another_asset_upload(self):
        receipt = bridge.make_receipt(**self.receipt_inputs())
        data = (bridge.lab.canonical(receipt) + '\n').encode()
        release = {**self.release, 'assets': [{'name': bridge.ASSET, 'size': len(data),
                                             'digest': 'sha256:' + hashlib.sha256(data).hexdigest()}]}
        with tempfile.TemporaryDirectory() as out, patch.object(bridge.lab, 'api', return_value=release), \
                patch.object(bridge.subprocess, 'run') as run:
            bridge.attach(self.proof, receipt, Path(out))
            run.assert_not_called()
        release['assets'][0]['digest'] = 'sha256:' + '0' * 64
        with tempfile.TemporaryDirectory() as out, patch.object(bridge.lab, 'api', return_value=release), \
                patch.object(bridge.subprocess, 'run') as run:
            with self.assertRaises(bridge.lab.LabError):
                bridge.attach(self.proof, receipt, Path(out))
            run.assert_not_called()

    def test_sealed_receipt_recovers_failed_asset_after_another_patch_exists(self):
        args = self.receipt_inputs()
        sealed = bridge.make_receipt(**args)
        # The provider now also has patch 6. Recovery asks for sealed patch 5
        # directly, without reinterpreting that later patch as this upload.
        def provider(target, kind, number=None):
            if kind == 'list':
                return self.query('list', [self.patch(4), self.patch(5), self.patch(6)])
            self.assertEqual((kind, number), ('info', 5))
            return self.query('info', self.patch(5), 5)
        with tempfile.TemporaryDirectory() as out:
            Path(out, 'upload-proof.json').write_text(json.dumps(args['generation']))
            with patch.object(bridge, 'readiness', return_value=(self.manifest, self.proof, self.release, bridge.OPERATOR)), \
                    patch.object(bridge, 'history_head', return_value='a' * 40), \
                    patch.object(bridge, 'json_record', side_effect=[args['intent'], sealed]), \
                    patch.object(bridge.mobile, 'capture_provider', side_effect=provider) as observed, \
                    patch.object(bridge, 'create_once') as journal, \
                    patch.object(bridge, 'run_patch') as upload, \
                    patch.object(bridge, 'attach') as attach:
                result = bridge.reconcile(self.candidate, Path(out))
                self.assertEqual(result, sealed)
                observed.assert_called_once_with(self.target, 'info', 5)
                journal.assert_not_called()
                upload.assert_not_called()
                attach.assert_called_once_with(self.proof, sealed, Path(out))

    def test_sealed_receipt_recovery_rejects_changed_claim_or_provider_artifacts(self):
        args = self.receipt_inputs()
        sealed = bridge.make_receipt(**args)
        for mutate_receipt in (True, False):
            changed = copy.deepcopy(sealed)
            provider_patch = self.patch(5)
            if mutate_receipt:
                changed['device_validation']['successful_launch_confirmed'] = True
            else:
                provider_patch['artifacts'][0]['hash'] = '0' * 64
            with self.subTest(mutate_receipt=mutate_receipt), tempfile.TemporaryDirectory() as out:
                Path(out, 'upload-proof.json').write_text(json.dumps(args['generation']))
                with patch.object(bridge, 'readiness', return_value=(self.manifest, self.proof, self.release, bridge.OPERATOR)), \
                        patch.object(bridge, 'history_head', return_value='a' * 40), \
                        patch.object(bridge, 'json_record', side_effect=[args['intent'], changed]), \
                        patch.object(bridge.mobile, 'capture_provider', return_value=self.query('info', provider_patch, 5)), \
                        patch.object(bridge, 'attach') as attach, \
                        patch.object(bridge, 'run_patch') as upload:
                    with self.assertRaises(bridge.lab.LabError):
                        bridge.reconcile(self.candidate, Path(out))
                    attach.assert_not_called()
                    upload.assert_not_called()

    def test_logs_cannot_be_saved_inside_git_repository(self):
        with self.assertRaises(bridge.lab.LabError):
            bridge.private_output(bridge.lab.ROOT / 'build/private-evidence')


if __name__ == '__main__':
    unittest.main()
