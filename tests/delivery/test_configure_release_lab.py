"""Offline configuration retries with real GitHub normalization represented explicitly."""
import copy
from contextlib import ExitStack, redirect_stdout
import io
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / 'tools/delivery'))
import configure_release_lab as configure
from rehearse_release_lab import ENV_IDS, offline_policy


class ConfigurationAPI:
    """No fallback: unknown requests fail instead of contacting GitHub."""
    def __init__(self):
        self.calls = []
        self.rules = [{'id': 11, 'name': 'Historical rule preserved',
                       'target': 'tag', 'enforcement': 'active',
                       'conditions': {'ref_name': {'include': ['refs/tags/entrega-*'], 'exclude': []}},
                       'rules': [{'type': 'deletion'}], 'bypass_actors': []}]

    def api(self, path, data=None, method='GET', missing=False):
        prefix = configure.endpoint('')
        if not path.startswith(prefix):
            raise AssertionError('Configuration emulator cannot leave the LAB repository')
        path = path[len(prefix):]
        self.calls.append({'path': path, 'method': method, 'data': copy.deepcopy(data)})
        if path.startswith('environments/'):
            if method == 'PUT':
                return copy.deepcopy(data)
            if path.endswith('/deployment-branch-policies'):
                return {'branch_policies': [{'id': 1, 'name': 'main', 'type': 'branch'},
                                           {'id': 2, 'name': 'v*-rc.*', 'type': 'tag'}]}
            return {'id': ENV_IDS[path.split('/')[1]], 'name': path.split('/')[1]}
        if path == 'rulesets' and method == 'GET':
            return [{'id': rule['id'], 'name': rule['name']} for rule in self.rules]
        if path == 'rulesets' and method == 'POST':
            created = {**copy.deepcopy(data), 'id': 100 + len(self.rules),
                       'source_type': 'Repository', 'node_id': 'OFFLINE-NORMALIZED'}
            for rule in created['rules']:
                if rule['type'] == 'pull_request':
                    rule['parameters'].update(required_reviewers=[],
                                              require_extra_approval_for_unattributed_changes=True)
            self.rules.append(created)
            return copy.deepcopy(created)
        if path.startswith('rulesets/') and method == 'GET':
            return copy.deepcopy(next(rule for rule in self.rules if rule['id'] == int(path.split('/')[-1])))
        if path == 'git/ref/heads/codex/release-lab-state':
            return {'object': {'type': 'commit', 'sha': 'a' * 40}}
        raise AssertionError('Unsupported configuration request: ' + method + ' ' + path)


class ConfigureIdempotenceTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='configure-release-lab-test-')
        self.addCleanup(self.temp.cleanup)
        self.server = ConfigurationAPI()

    def invoke(self):
        with ExitStack() as stack:
            stack.enter_context(patch.object(configure, 'load_policy', return_value=offline_policy()))
            stack.enter_context(patch.object(configure, 'api', side_effect=self.server.api))
            stack.enter_context(patch.object(configure, 'environments', return_value=ENV_IDS))
            stack.enter_context(redirect_stdout(io.StringIO()))
            configure.configure(self.temp.name, protect_branches=True)

    def branch_ruleset(self):
        return next(rule for rule in self.server.rules if rule['name'] == 'LAB - main e release revisadas')

    def test_repeated_configuration_accepts_safe_github_defaults_without_creating_more_rulesets(self):
        historical = copy.deepcopy(self.server.rules[0])
        self.invoke()
        self.assertEqual(len(self.server.rules), 5)
        normalized = copy.deepcopy(self.server.rules)
        self.server.calls.clear()
        self.invoke()
        self.assertEqual(self.server.rules, normalized)
        self.assertEqual(self.server.rules[0], historical)
        self.assertFalse(any(call['path'] == 'rulesets' and call['method'] == 'POST'
                             for call in self.server.calls))
        self.assertFalse(any(call['method'] in ('PATCH', 'DELETE') for call in self.server.calls))
        self.assertTrue(Path(self.temp.name, 'configuration.json').is_file())

    def test_real_required_review_count_divergence_remains_blocked_without_overwriting(self):
        self.invoke()
        rule = next(rule for rule in self.branch_ruleset()['rules'] if rule['type'] == 'pull_request')
        rule['parameters']['required_approving_review_count'] = 0
        before = copy.deepcopy(self.server.rules)
        with self.assertRaises(ValueError):
            self.invoke()
        self.assertEqual(self.server.rules, before)

    def test_admin_bypass_divergence_remains_blocked_without_overwriting(self):
        self.invoke()
        self.branch_ruleset()['bypass_actors'] = [{'actor_id': 5, 'actor_type': 'RepositoryRole',
                                                 'bypass_mode': 'always'}]
        before = copy.deepcopy(self.server.rules)
        with self.assertRaises(ValueError):
            self.invoke()
        self.assertEqual(self.server.rules, before)

    def test_unexpected_required_reviewer_defaults_are_not_silently_ignored(self):
        self.invoke()
        rule = next(rule for rule in self.branch_ruleset()['rules'] if rule['type'] == 'pull_request')
        rule['parameters']['required_reviewers'] = [{'reviewer_id': 999, 'reviewer_type': 'User'}]
        before = copy.deepcopy(self.server.rules)
        with self.assertRaises(ValueError):
            self.invoke()
        self.assertEqual(self.server.rules, before)

    def test_unsafe_extra_approval_default_is_not_treated_as_safe_normalization(self):
        self.invoke()
        rule = next(rule for rule in self.branch_ruleset()['rules'] if rule['type'] == 'pull_request')
        rule['parameters']['require_extra_approval_for_unattributed_changes'] = False
        before = copy.deepcopy(self.server.rules)
        with self.assertRaises(ValueError):
            self.invoke()
        self.assertEqual(self.server.rules, before)


if __name__ == '__main__':
    unittest.main()
