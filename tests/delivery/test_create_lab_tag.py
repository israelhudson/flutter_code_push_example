"""Owner CLI tags are verified against remote fixtures; no real APIs are called."""
import copy
import json
from pathlib import Path
import sys
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / 'tools/delivery'))
import create_lab_tag as tags
import github_lab_release as release
from remote_state import GitDataAPIError, RemoteState
import test_github_lab_release as fixtures


class TagAPI:
    def __init__(self, fixture):
        self.fixture = fixture
        self.calls = []
        self.object = None
        self.ref_exists = False
        self.tag_sha = 'b' * 40
        self.lose_object_reply = self.lose_ref_reply = False
        self.bad_object = False

    def __call__(self, method, path, data=None):
        self.calls.append((method, path, copy.deepcopy(data)))
        if path.startswith(release.BASE + '/git/ref/tags/'):
            if not self.ref_exists:
                raise GitDataAPIError(404)
            return {'ref': 'refs/tags/' + self.object['tag'],
                    'object': {'type': 'tag', 'sha': self.tag_sha}}
        if path == release.BASE + '/git/tags/' + self.tag_sha:
            return copy.deepcopy(self.object)
        if path == release.BASE + '/git/tags' and method == 'POST':
            self.object = {'sha': self.tag_sha, 'tag': data['tag'], 'message': data['message'],
                           'object': {'type': data['type'], 'sha': data['object']}}
            if self.bad_object:
                self.object['object']['sha'] = 'a' * 40
            if self.lose_object_reply:
                raise GitDataAPIError()
            return copy.deepcopy(self.object)
        if path == release.BASE + '/git/refs' and method == 'POST':
            if self.ref_exists:
                raise GitDataAPIError(422)
            assert data == {'ref': 'refs/tags/' + self.object['tag'], 'sha': self.tag_sha}
            self.ref_exists = True
            if self.lose_ref_reply:
                raise GitDataAPIError()
            return {'ref': data['ref'], 'object': {'type': 'tag', 'sha': self.tag_sha}}
        return self.fixture.api(method, path, data)


class CreateLabTagTests(unittest.TestCase):
    def setUp(self):
        self.fixture = fixtures.GitHubLabReleaseTests('runTest')
        self.fixture.setUp()
        self.addCleanup(self.fixture.doCleanups)
        self.fixture.run_release()
        self.spec = json.loads((self.fixture.output / 'tag-spec.json').read_text())
        self.spec_path = self.fixture.folder / 'tag-spec.json'
        self.write_spec(self.spec)
        self.output = self.fixture.folder / 'tag-output'
        self.api = TagAPI(self.fixture)
        self.remote = RemoteState(api=self.api)
        self.fixture.git.calls.clear()
        self.user = {'login': 'israelhudson', 'id': 42}

    def write_spec(self, spec):
        self.spec_path.write_text(json.dumps(spec))

    def create(self, **kwargs):
        return tags.run(self.spec_path, self.output, {}, api=self.api,
                        remote=self.remote, get_user=lambda: self.user, **kwargs)

    def posts(self):
        return [call for call in self.api.calls if call[0] == 'POST']

    def test_creates_one_verified_object_and_ref_with_owner_audit_without_state_writes(self):
        state_head = self.fixture.git.head
        result = self.create()
        self.assertTrue(result['created'])
        self.assertTrue(result['verified'])
        self.assertEqual(result['tag_sha'], self.api.tag_sha)
        self.assertEqual(result['source_sha'], self.fixture.source)
        self.assertEqual(result['real_operator'], {'login': 'israelhudson', 'id': 42,
                                                   'identity_source': 'local_owner_cli'})
        self.assertEqual([path for _, path, _ in self.posts()],
                         [release.BASE + '/git/tags', release.BASE + '/git/refs'])
        self.assertEqual(self.posts()[0][2], {'tag': self.spec['tag_name'], 'message': self.spec['message'],
                                             'object': self.spec['source_sha'], 'type': 'commit'})
        self.assertTrue(all(call[0] == 'GET' for call in self.fixture.git.calls))
        self.assertEqual(self.fixture.git.head, state_head)
        self.assertFalse(list(self.output.rglob('*.sqlite')))
        events = [json.loads(line) for line in (self.output / 'release-events.jsonl').read_text().splitlines()]
        before = [e for e in events if e['event'] == 'mutation_before']
        self.assertEqual([e['operation'] for e in before], ['create_tag_object', 'create_tag_ref'])
        self.assertEqual(json.loads((self.output / 'checkpoint.json').read_text())['status'], 'confirmed')

    def test_tampered_source_message_ref_identity_and_extra_field_never_mutate(self):
        for key, value in [('source_sha', 'a' * 40), ('message', 'forged message'),
                           ('ref', 'refs/heads/main'), ('release_identity', 'a' * 64), ('extra', True)]:
            with self.subTest(key=key):
                self.write_spec({**self.spec, key: value})
                with self.assertRaisesRegex(release.ReleaseError, 'plano regenerado'):
                    self.create()
        self.assertEqual(self.posts(), [])

    def test_spec_cannot_substitute_another_manifest_hash(self):
        self.write_spec({**self.spec, 'manifest_hash': 'a' * 64})
        with self.assertRaisesRegex(release.ReleaseError, 'Hash do manifesto'):
            self.create()
        self.assertEqual(self.posts(), [])

    def test_wrong_owner_login_or_id_and_actions_identity_are_rejected(self):
        for user in ({'login': 'someone', 'id': 42}, {'login': 'israelhudson', 'id': 99}):
            self.user = user
            with self.assertRaisesRegex(release.ReleaseError, 'Somente Israel'):
                self.create()
        self.user = {'login': 'israelhudson', 'id': 42}
        with self.assertRaisesRegex(release.ReleaseError, 'fora das Actions'):
            tags.run(self.spec_path, self.output, {'GITHUB_ACTIONS': 'true'}, api=self.api,
                     remote=self.remote, get_user=lambda: self.user)
        self.assertEqual(self.posts(), [])

    def test_existing_exact_tag_is_read_only_idempotent(self):
        first = self.create()
        self.api.calls.clear()
        second = self.create()
        self.assertFalse(second['created'])
        self.assertTrue(second['verified'])
        self.assertEqual(second['tag_sha'], first['tag_sha'])
        self.assertEqual(self.posts(), [])

    def test_existing_wrong_tag_is_never_replaced(self):
        self.create()
        self.api.calls.clear()
        self.api.object['message'] = 'another identity'
        with self.assertRaisesRegex(release.ReleaseError, 'outra fonte'):
            self.create()
        self.assertEqual(self.posts(), [])

    def test_unprotected_namespace_blocks_before_any_post(self):
        self.fixture.api.protected = False
        with self.assertRaisesRegex(release.ReleaseError, 'Proteção imutável'):
            self.create()
        self.assertEqual(self.posts(), [])

    def test_lost_tag_object_reply_preserves_uncertainty_without_creating_ref_or_retry(self):
        self.api.lose_object_reply = True
        with self.assertRaisesRegex(release.ReleaseError, 'Criação de tag incerta'):
            self.create()
        self.assertEqual(len(self.posts()), 1)
        self.assertIsNotNone(self.api.object)
        self.assertFalse(self.api.ref_exists)
        self.assertEqual(json.loads((self.output / 'checkpoint.json').read_text())['status'], 'uncertain')
        self.api.lose_object_reply = False
        with self.assertRaisesRegex(release.ReleaseError, 'tentativa anterior'):
            self.create()
        self.assertEqual(len(self.posts()), 1)

    def test_lost_ref_reply_manual_get_confirms_existing_tag_without_another_post(self):
        self.api.lose_ref_reply = True
        with self.assertRaisesRegex(release.ReleaseError, 'Criação de tag incerta'):
            self.create()
        self.assertEqual(len(self.posts()), 2)
        self.assertTrue(self.api.ref_exists)
        self.api.calls.clear()
        result = self.create()
        self.assertEqual(result['status'], 'already_exists')
        self.assertEqual(self.posts(), [])

    def test_wrong_tag_object_reply_blocks_ref_and_keeps_uncertain_checkpoint(self):
        self.api.bad_object = True
        with self.assertRaisesRegex(release.ReleaseError, 'Objeto de tag retornado'):
            self.create()
        self.assertEqual(len(self.posts()), 1)
        self.assertFalse(self.api.ref_exists)
        self.assertEqual(json.loads((self.output / 'checkpoint.json').read_text())['status'], 'uncertain')

    def test_user_api_error_is_sanitized_and_never_echoes_cli_stderr(self):
        with patch.object(tags.subprocess, 'run') as command:
            command.return_value.returncode = 1
            command.return_value.stderr = b'deliberately-secret-value'
            with self.assertRaises(release.ReleaseError) as error:
                tags.current_user()
            self.assertNotIn('deliberately-secret-value', str(error.exception))
            args = command.call_args.args[0]
            self.assertEqual(args[args.index('--hostname') + 1], 'github.com')
            self.assertIn('user', args)


if __name__ == '__main__':
    unittest.main()
