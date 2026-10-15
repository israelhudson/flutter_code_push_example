"""Ownership routing is observational and never borrows Delivery approvals."""
import copy
from pathlib import Path
import sys
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / 'tools/delivery'))
import route_release_lab_tag as route


class LabTagRoutingTests(unittest.TestCase):
    def setUp(self):
        self.tag, self.source = 'v1.20.0-rc.1', 'a' * 40
        self.policy = route.lab.load_policy()
        self.record = {'candidate_tag': self.tag, 'version': '1.20.0',
                       'source_sha': self.source, 'release_branch': 'release/1.20.0',
                       'policy_digest': route.lab.digest(self.policy),
                       'status': 'prepared', 'evaluation_run_id': None}
        self.state = {'schema': 1, 'active': self.tag,
                      'candidates': {self.tag: self.record}}

    def classify(self, state=None, resolved=None):
        with patch.object(route.lab, 'state_read', return_value=(state or self.state, 'b' * 40)), \
                patch.object(route.lab, 'resolve_tag', return_value=resolved or self.source), \
                patch.object(route.lab, 'state_write') as write, \
                patch.object(route.lab, 'api') as api:
            result = route.classify(self.tag, self.source)
            write.assert_not_called()
            api.assert_not_called()
            return result

    def test_registered_active_lab_candidate_continues_without_mutation(self):
        self.assertTrue(self.classify()['allow_lab'])

    def test_delivery_v2_tag_without_lab_registration_skips_all_lab_work(self):
        state = {'schema': 1, 'active': 'v1.19.0-rc.1', 'candidates': {
            'v1.19.0-rc.1': {'status': 'completed'}}}
        with patch.object(route.lab, 'resolve_tag') as resolve:
            result = self.classify(state)
            self.assertFalse(result['allow_lab'])
            self.assertEqual(result['reason'], 'no_registered_lab_candidate')
            resolve.assert_not_called()

    def test_orphan_tag_fails_closed_without_entering_lab(self):
        result = self.classify({'schema': 1, 'active': None, 'candidates': {}})
        self.assertFalse(result['allow_lab'])

    def test_existing_record_cannot_adopt_another_source_policy_or_prior_run(self):
        for field, value in [('source_sha', 'c' * 40), ('policy_digest', 'd' * 64),
                             ('status', 'evaluating'), ('evaluation_run_id', '42'),
                             ('release_branch', 'release/2.0.0'),
                             ('candidate_tag', 'v1.20.0-rc.2')]:
            state = copy.deepcopy(self.state)
            state['candidates'][self.tag][field] = value
            with self.subTest(field=field), self.assertRaises(route.lab.LabError):
                self.classify(state)

    def test_registered_but_moved_tag_and_inactive_candidate_are_blocked(self):
        with self.assertRaises(route.lab.LabError):
            self.classify(resolved='c' * 40)
        state = copy.deepcopy(self.state)
        state['active'] = 'v1.20.0-rc.2'
        with self.assertRaises(route.lab.LabError):
            self.classify(state)

    def test_absent_or_malformed_journal_never_authorizes_lab(self):
        for state in ({'schema': 1, 'candidates': []}, {'schema': 1}):
            with self.subTest(state=state), self.assertRaises(route.lab.LabError):
                self.classify(state)

    def test_workflow_call_remains_available_and_tag_route_gates_preflight(self):
        workflow = Path('.github/workflows/release-lab-evaluate.yml').read_text()
        self.assertIn('  workflow_call:', workflow)
        self.assertIn("      - 'v*-rc.*'", workflow)
        self.assertIn("if: github.event_name != 'push'", workflow)
        self.assertIn('    needs: route_tag\n    if: needs.route_tag.outputs.allow_lab == \'true\'', workflow)
        self.assertIn('      contents: read\n    outputs:', workflow)


if __name__ == '__main__':
    unittest.main()
