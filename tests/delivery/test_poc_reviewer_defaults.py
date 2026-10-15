"""Reviewer snapshots must survive planning and freeze before any registration."""
import copy
import json
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / 'tools' / 'delivery'))
import delivery_v2 as v2


def snapshot():
    person = {'id': '1b2c3d4e-1515-4000-8000-000000000001', 'revision': 1,
              'name': 'Israel Hudson', 'slack_user': 'U0BMFQKC001',
              'github_user_id': 18661493, 'github_login': 'israelhudson'}
    return {'schema': 'delivery-reviewers-v1', 'repository': v2.lab.REPOSITORY,
            'team_id': 'T09CYB7AS77', 'solo': True,
            'technical': person, 'business': copy.deepcopy(person)}


class AutomaticReviewerTests(unittest.TestCase):
    def test_plan_keeps_both_automatic_roles_without_manual_inputs(self):
        reviewers = snapshot()
        plan = {'id': 'delivery-' + 'a' * 32, 'reviewers': reviewers}
        with patch.object(v2, 'api_control', return_value=plan) as remote:
            self.assertEqual(v2.control('plan', version='2.0.0')['reviewers'], reviewers)
            remote.assert_called_once_with('plan', version='2.0.0')

    def test_missing_or_foreign_snapshot_never_falls_back_to_config_users(self):
        wrong_team = snapshot()
        wrong_team['team_id'] = 'TOTHER'
        wrong_solo = snapshot()
        wrong_solo['solo'] = False
        for reviewers in (None, {}, wrong_team, wrong_solo):
            with self.subTest(reviewers=reviewers), patch.object(v2, 'api_control',
                    return_value={'reviewers': reviewers}), self.assertRaises(v2.lab.LabError):
                v2.control('plan', version='2.0.0')

    def test_two_people_required_outside_explicit_solo(self):
        reviewers = snapshot()
        reviewers['solo'] = False
        policy = json.loads(Path('delivery/delivery-policy.json').read_text())
        policy['solo'] = False
        with patch.object(Path, 'read_text', return_value=json.dumps(policy)):
            with self.assertRaises(v2.lab.LabError):
                v2.require_reviewers(reviewers)

    def test_business_reviewer_does_not_require_github_identity(self):
        reviewers = snapshot()
        reviewers['business']['github_user_id'] = None
        reviewers['business']['github_login'] = None
        self.assertEqual(v2.require_reviewers(reviewers), reviewers)

    def test_invalid_reviewer_revision_or_identity_is_rejected(self):
        for key, value in [('revision', True), ('revision', 0), ('id', 'arbitrary'),
                           ('slack_user', '@israel'), ('github_user_id', True),
                           ('github_login', 'bad/login')]:
            reviewers = snapshot()
            reviewers['technical'][key] = value
            with self.subTest(key=key, value=value), self.assertRaises(v2.lab.LabError):
                v2.require_reviewers(reviewers)

    def test_missing_reviewers_fail_before_journal_or_release_writes(self):
        with patch.object(v2, 'write_record') as journal, \
                patch.object(v2, 'candidate_release') as release, \
                patch.object(v2, 'api_control') as remote:
            with self.assertRaises(v2.lab.LabError):
                v2.control('register', report_text='{}')
            journal.assert_not_called()
            release.assert_not_called()
            remote.assert_not_called()

    def test_registered_ids_and_snapshot_must_match_immutable_manifest(self):
        report = {'id': 'delivery-' + 'a' * 32, 'reviewers': snapshot()}
        registered = {'reviewer_snapshot': report['reviewers'],
                      'technical_reviewer_id': report['reviewers']['technical']['id'],
                      'business_reviewer_id': report['reviewers']['business']['id'],
                      'technical_user': report['reviewers']['technical']['slack_user'],
                      'business_user': report['reviewers']['business']['slack_user']}
        with tempfile.TemporaryDirectory() as output, \
                patch.dict(os.environ, {'DELIVERY_LOG_DIR': output}), \
                patch.object(v2, 'write_record', return_value={'commit': 'b' * 40,
                    'digest': 'c' * 64}) as journal, \
                patch.object(v2, 'candidate_release', return_value={'id': 1,
                    'html_url': 'https://github.com/example/release'}), \
                patch.object(v2, 'api_control', return_value=registered), \
                patch.object(v2, 'drain') as drain:
            self.assertEqual(v2.control('register', report_text=json.dumps(report)), registered)
            self.assertEqual(journal.call_args.args[1]['reviewers'], report['reviewers'])
            drain.assert_called_once()
            drain.reset_mock()
            registered['technical_user'] = 'UOTHER'
            with self.assertRaises(v2.lab.LabError):
                v2.control('register', report_text=json.dumps(report))
            drain.assert_not_called()


if __name__ == '__main__':
    unittest.main()
