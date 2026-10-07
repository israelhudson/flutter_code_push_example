"""Offline owner authorization, immutable release identity and draft recovery."""
import base64
from contextlib import closing
import copy
import hashlib
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import os
from pathlib import Path
import sqlite3
import shutil
import subprocess
import sys
import tempfile
import threading
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / 'tools/delivery'))
import github_lab_release as release
from lab_demo import fixture, preview
from lab_engine import LabStore, make_manifest
from remote_state import RemoteState, GitDataAPIError, create_empty_databases, export_bundle
import snapshots
from test_remote_state import FakeGitData


class FakeReleaseAPI:
    def __init__(self, git_data, repo, source, tree):
        self.git_data, self.repo, self.source, self.tree = git_data, repo, source, tree
        self.calls, self.uploads = [], []
        self.tag, self.release, self.assets = None, None, {}
        self.protected = True
        self.ambiguous_upload = self.ambiguous_publish = False
        self.after_upload = None

    def tag_from_spec(self, spec):
        self.tag = {'sha': 'b' * 40, 'tag': spec['tag_name'], 'message': spec['message'],
                    'object': {'type': 'commit', 'sha': spec['source_sha'], 'url': 'not part of identity'}}

    def __call__(self, method, path, data=None):
        self.calls.append((method, path, copy.deepcopy(data)))
        if path == release.BASE:
            return {'full_name': release.REPO, 'owner': {'login': 'israelhudson', 'id': 42}}
        endpoint = path[len(release.BASE):]
        if endpoint == '/git/commits/' + self.source:
            return {'sha': self.source, 'tree': {'sha': self.tree}}
        if endpoint == '/contents/pubspec.yaml?ref=' + self.source:
            content = (self.repo / 'pubspec.yaml').read_bytes()
            sha = hashlib.sha1(b'blob ' + str(len(content)).encode() + b'\0' + content).hexdigest()
            return {'encoding': 'base64', 'content': base64.b64encode(content).decode(), 'sha': sha}
        if endpoint.startswith('/actions/runs?'):
            return {'workflow_runs': []}
        if endpoint.startswith('/git/ref/tags/'):
            if not self.tag:
                raise GitDataAPIError(404)
            return {'ref': 'refs/tags/' + self.tag['tag'], 'object': {'sha': self.tag['sha'], 'type': 'tag'}}
        if endpoint == '/git/tags/' + 'b' * 40:
            return copy.deepcopy(self.tag)
        if endpoint == '/rulesets?per_page=100':
            return [{'id': 7}] if self.protected else []
        if endpoint == '/rulesets/7':
            return {'target': 'tag', 'enforcement': 'active', 'bypass_actors': [],
                    'conditions': {'ref_name': {'include': ['refs/tags/entrega-*-rc.*'], 'exclude': []}},
                    'rules': [{'type': 'update'}, {'type': 'deletion'}]}
        if endpoint.startswith('/releases/tags/'):
            if self.release is None or self.release['draft']:
                raise GitDataAPIError(404)
            return copy.deepcopy(self.release)
        if endpoint.startswith('/releases?per_page=100&page='):
            return [copy.deepcopy(self.release)] if self.release else []
        if endpoint == '/releases' and method == 'POST':
            assert 'target_commitish' not in data, 'Frozen existing tag, never default/main source substitution'
            assert data['draft'] and data['prerelease'] and data['make_latest'] == 'false'
            self.release = {**copy.deepcopy(data), 'id': 500,
                            'html_url': release.URL + '/releases/tag/' + data['tag_name']}
            return copy.deepcopy(self.release)
        if endpoint == '/releases/500':
            if method == 'PATCH':
                assert data == {'draft': False, 'prerelease': True, 'make_latest': 'false'}
                self.release.update(data)
                if self.ambiguous_publish:
                    self.ambiguous_publish = False
                    raise GitDataAPIError()
            return copy.deepcopy(self.release)
        if endpoint.startswith('/releases/500/assets?'):
            return list(copy.deepcopy(self.assets).values())
        return self.git_data(method, path, data)

    def upload(self, release_id, name, data):
        assert release_id == 500 and name not in self.assets, 'Never clobber existing assets'
        self.uploads.append(name)
        self.assets[name] = {'id': 600 + len(self.assets), 'name': name, 'state': 'uploaded',
                             'digest': 'sha256:' + release.sha256(data), 'size': len(data)}
        if self.after_upload:
            callback, self.after_upload = self.after_upload, None
            callback()
        if self.ambiguous_upload:
            self.ambiguous_upload = False
            raise GitDataAPIError()
        return copy.deepcopy(self.assets[name])


class GitHubLabReleaseTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='github-lab-release-test-')
        self.addCleanup(self.temp.cleanup)
        self.folder = Path(self.temp.name)
        repo, base, source, inputs, targets, _ = fixture(self.folder / 'fixture')
        self.repo, self.source = repo, source
        self.store = LabStore(self.folder / 'state.sqlite')
        production = self.store.initialize(base, targets)
        self.store.technical_review(source)
        preview_meta = preview(self.folder, repo, source, inputs, 'preview')
        preview_meta.update(kind='flutter_web', source_tree=snapshots.source_tree(repo, source))
        self.manifest = make_manifest(repo, source, production, targets, preview_meta, inputs, 'entrega-0042')
        status = self.store.prepare(self.manifest, 'prepare')
        self.candidate, self.hash = status['candidate_id'], status['manifest_hash']
        for role in release.ROLES:
            self.store.approve(self.candidate, role, self.hash)
        create_empty_databases(self.folder / 'provider.sqlite', self.folder / 'outbox.sqlite')
        self.git = FakeGitData()
        self.api = FakeReleaseAPI(self.git, repo, source, self.manifest['source_tree'])
        self.remote = RemoteState(api=self.api)
        self.save_state()
        self.api.calls.clear(); self.git.calls.clear()
        self.env = {'GITHUB_ACTIONS': 'true', 'GITHUB_REPOSITORY': release.REPO,
                    'GITHUB_EVENT_NAME': 'workflow_dispatch', 'GITHUB_REF': 'refs/heads/main',
                    'GITHUB_WORKFLOW_REF': release.WORKFLOW, 'GITHUB_ACTOR': 'israelhudson',
                    'GITHUB_ACTOR_ID': '42', 'GITHUB_TRIGGERING_ACTOR': 'israelhudson', 'GITHUB_RUN_ID': '123'}
        self.counter = 0

    def save_state(self):
        bundle = export_bundle(self.folder / 'state.sqlite', self.folder / 'provider.sqlite', self.folder / 'outbox.sqlite')
        if self.git.head is None:
            self.remote.bootstrap(bundle, 'fixture-bootstrap')
        else:
            self.remote.save(bundle, self.git.head, 'fixture-change-' + str(len(self.git.commits)))

    def run_release(self, action='plan', env=None, manifest_hash=None):
        self.counter += 1
        self.output = self.folder / ('output-' + str(self.counter))
        return release.run(action, self.candidate, manifest_hash or self.hash, self.output,
                           self.env if env is None else env, api=self.api, remote=self.remote, uploader=self.api)

    def prepare_tag(self):
        self.run_release()
        self.api.tag_from_spec(json.loads((self.output / 'tag-spec.json').read_text()))
        self.api.calls.clear()

    def mutations(self):
        return [call for call in self.api.calls if call[0] != 'GET']

    def test_owner_repository_main_workflow_and_triggering_identity_gates(self):
        for key, value in (('GITHUB_ACTIONS', 'false'), ('GITHUB_REPOSITORY', 'work/amulets'),
                           ('GITHUB_EVENT_NAME', 'push'), ('GITHUB_REF', 'refs/heads/feature'),
                           ('GITHUB_WORKFLOW_REF', release.REPO + '/.github/workflows/other.yaml@refs/heads/main'),
                           ('GITHUB_ACTOR_ID', '99'), ('GITHUB_ACTOR', 'someone'),
                           ('GITHUB_TRIGGERING_ACTOR', 'someone')):
            with self.subTest(key=key), self.assertRaises(release.ReleaseError):
                self.run_release(env={**self.env, key: value})
        self.assertEqual(self.mutations(), [])
        self.assertEqual(self.api.uploads, [])

    def test_plan_has_no_effects_or_database_assets_and_labels_two_simulated_zero_real(self):
        state_head = self.git.head
        result = self.run_release()
        self.assertFalse(result['published'])
        self.assertIsNone(result['release_url'])
        self.assertEqual(self.git.head, state_head)
        self.assertEqual(self.mutations(), [])
        self.assertEqual(self.api.uploads, [])
        plan = json.loads((self.output / 'plan.json').read_text())
        self.assertEqual(plan['version'], '1.1.0+2')
        self.assertEqual(plan['source_sha'], self.source)
        self.assertEqual(plan['simulated_approvals'], {'roles': release.ROLES, 'count': 2, 'real_review_count': 0})
        self.assertEqual(plan['real_operator']['login'], 'israelhudson')
        self.assertFalse(plan['distribution_performed'])
        self.assertEqual(set(a['name'] for a in plan['assets']), set(release.ASSETS))
        self.assertFalse(list(self.output.rglob('*.sqlite')))
        for asset in plan['assets']:
            self.assertEqual(asset['sha256'], release.sha256((self.output / asset['name']).read_bytes()))

    def test_wrong_manifest_hash_source_tree_and_missing_simulated_approval_fail(self):
        with self.assertRaisesRegex(release.ReleaseError, 'Hash do manifesto'):
            self.run_release(manifest_hash='a' * 64)
        self.api.tree = 'a' * 40
        with self.assertRaisesRegex(release.ReleaseError, 'SHA/árvore'):
            self.run_release()
        self.api.tree = self.manifest['source_tree']
        self.store.revoke(self.candidate, 'samuel', self.hash)
        self.save_state()
        with self.assertRaisesRegex(release.ReleaseError, 'autorizada|dois papéis'):
            self.run_release()

    def test_publish_requires_existing_owner_tag_and_existing_protection(self):
        with self.assertRaisesRegex(release.ReleaseError, 'Tag anotada ausente'):
            self.run_release('publish')
        self.assertEqual(self.mutations(), [])
        self.prepare_tag()
        self.api.protected = False
        with self.assertRaisesRegex(release.ReleaseError, 'Proteção imutável'):
            self.run_release('publish')
        self.assertEqual(self.mutations(), [])

    def test_wrong_tag_source_or_annotation_is_never_overwritten(self):
        self.prepare_tag()
        original = copy.deepcopy(self.api.tag)
        for field in ('source', 'message'):
            self.api.tag = copy.deepcopy(original)
            if field == 'source':
                self.api.tag['object']['sha'] = 'a' * 40
            else:
                self.api.tag['message'] = 'different manifest'
            with self.subTest(field=field), self.assertRaisesRegex(release.ReleaseError, 'outra fonte'):
                self.run_release('publish')
        self.assertEqual(self.mutations(), [])

    def test_publish_draft_uploads_confirmed_assets_then_records_prerelease(self):
        self.prepare_tag()
        result = self.run_release('publish')
        self.assertTrue(result['published'])
        self.assertEqual(result['release_url'], release.URL + '/releases/tag/' + self.candidate)
        self.assertFalse(self.api.release['draft'])
        self.assertTrue(self.api.release['prerelease'])
        self.assertEqual(set(self.api.uploads), set(release.ASSETS))
        self.assertEqual([m[0] for m in self.mutations()], ['POST', 'PATCH'])
        self.assertTrue(all(call[0] == 'GET' for call in self.git.calls))
        self.assertEqual(json.loads((self.output / 'checkpoint.json').read_text())['status'], 'published')

    def test_published_matching_identity_is_read_only_idempotent_across_runs(self):
        self.prepare_tag(); first = self.run_release('publish')
        self.api.calls.clear(); previous_uploads = list(self.api.uploads)
        self.env['GITHUB_RUN_ID'] = '124'
        result = self.run_release('publish')
        self.assertEqual(result['release_identity'], first['release_identity'])
        self.assertTrue(result['published'])
        self.assertEqual(self.mutations(), [])
        self.assertEqual(self.api.uploads, previous_uploads)

    def test_ambiguous_upload_is_not_retried_and_manual_run_recovers_same_draft(self):
        self.prepare_tag(); self.api.ambiguous_upload = True
        with self.assertRaisesRegex(release.ReleaseError, 'Efeito GitHub incerto'):
            self.run_release('publish')
        self.assertEqual(len(self.api.uploads), 1)
        self.assertTrue(self.api.release['draft'])
        self.assertEqual(json.loads((self.output / 'checkpoint.json').read_text())['status'], 'uncertain')
        result = self.run_release('publish')
        self.assertTrue(result['published'])
        self.assertEqual(len(self.api.uploads), 4)

    def test_wrong_existing_draft_asset_fails_without_overwrite_or_delete(self):
        self.prepare_tag(); self.api.ambiguous_upload = True
        with self.assertRaises(release.ReleaseError):
            self.run_release('publish')
        self.api.assets[self.api.uploads[0]]['digest'] = 'sha256:' + 'a' * 64
        before = len(self.api.uploads)
        with self.assertRaisesRegex(release.ReleaseError, 'Asset remoto diferente'):
            self.run_release('publish')
        self.assertEqual(len(self.api.uploads), before)
        self.assertTrue(self.api.release['draft'])

    def test_lost_publication_reply_preserves_checkpoint_then_manual_read_confirms(self):
        self.prepare_tag(); self.api.ambiguous_publish = True
        with self.assertRaisesRegex(release.ReleaseError, 'Efeito GitHub incerto'):
            self.run_release('publish')
        self.assertFalse(self.api.release['draft'])
        self.assertEqual(json.loads((self.output / 'checkpoint.json').read_text())['status'], 'uncertain')
        self.api.calls.clear()
        self.assertTrue(self.run_release('publish')['published'])
        self.assertEqual(self.mutations(), [])

    def test_revocation_during_upload_keeps_draft_unpublished(self):
        self.prepare_tag()
        def revoke():
            self.store.revoke(self.candidate, 'vinicius', self.hash)
            self.save_state()
        self.api.after_upload = revoke
        with self.assertRaisesRegex(release.ReleaseError, 'autorizada|dois papéis'):
            self.run_release('publish')
        self.assertTrue(self.api.release['draft'])
        self.assertFalse(any(method == 'PATCH' and path.endswith('/releases/500') for method, path, _ in self.api.calls))

    def test_unsafe_zip_or_wrong_zip_bytes_are_rejected_before_release_creation(self):
        self.prepare_tag()
        loaded = self.remote.load(self.folder / 'loaded')
        location = loaded.paths['previews'][self.manifest['preview']['path']]
        original = Path(location).read_bytes()
        Path(location).write_bytes(b'wrong zip bytes')
        with self.assertRaisesRegex(release.ReleaseError, 'Hash do ZIP'):
            release.read_candidate(loaded, self.candidate, self.hash)
        Path(location).write_bytes(original)
        self.manifest['preview']['source_sha'] = 'a' * 40
        db_path = loaded.paths['state_db']
        with closing(sqlite3.connect(db_path)) as db:
            db.execute('DROP TRIGGER immutable_candidate')
            db.execute('UPDATE candidates SET manifest=?,hash=? WHERE id=?',
                       (release.canonical(self.manifest), release.digest(self.manifest), self.candidate))
            db.execute('UPDATE approvals SET hash=? WHERE candidate=?', (release.digest(self.manifest), self.candidate))
            db.commit()
        with self.assertRaisesRegex(release.ReleaseError, 'Preview não'):
            release.read_candidate(loaded, self.candidate, release.digest(self.manifest))

    def test_upload_uses_absolute_github_uploads_url_and_sanitizes_cli_errors(self):
        with patch.object(release.subprocess, 'run') as command:
            command.return_value.returncode = 0
            command.return_value.stdout = b'HTTP/2.0 201 Created\r\nContent-Type: application/json\r\n\r\n{"id":601}'
            release.AssetAPI().upload(500, 'preview.zip', b'frozen zip')
            args = command.call_args.args[0]
            self.assertEqual(args[args.index('--hostname') + 1], 'github.com')
            self.assertIn('https://uploads.github.com/repos/' + release.REPO + '/releases/500/assets?name=preview.zip', args)
            self.assertFalse(any('/api/v3/' in arg for arg in args))
            self.assertEqual(command.call_args.kwargs['input'], b'frozen zip')
            self.assertIn('Content-Length: 10', args)
            self.assertIn('--include', args)
            command.return_value.returncode = 1
            command.return_value.stderr = b'deliberately-secret-value'
            command.return_value.stdout = b'HTTP/2.0 411 Length Required\r\nX-Private: deliberately-secret-value\r\n\r\n{}'
            with self.assertRaises(GitDataAPIError) as error:
                release.AssetAPI().upload(500, 'preview.zip', b'frozen zip')
            self.assertEqual(error.exception.status, 411)
            self.assertNotIn('deliberately-secret-value', str(error.exception))

    @unittest.skipUnless(shutil.which('gh'), 'Wire regression needs the GitHub CLI, offline localhost only')
    def test_real_gh_stdin_upload_requires_explicit_byte_length_and_preserves_bytes(self):
        data = '{"nota":"versão congelada · laboratório"}'.encode('utf-8')
        received = []
        class LocalUpload(BaseHTTPRequestHandler):
            def log_message(self, *args):
                pass  # No HTTP headers or credentials printed by the stub.

            def do_POST(self):
                length = self.headers.get('Content-Length')
                record = {'length': length, 'transfer_encoding': self.headers.get('Transfer-Encoding'),
                          'path': self.path, 'body': None}
                received.append(record)
                if length is None:
                    self.send_response(411)
                    payload = b'{"message":"Content-Length required"}'
                else:
                    record['body'] = self.rfile.read(int(length))
                    self.send_response(201)
                    payload = json.dumps({'id': 601, 'name': 'candidate.json', 'state': 'uploaded',
                                          'size': len(record['body']), 'digest': 'sha256:' + release.sha256(record['body'])}).encode()
                self.send_header('Content-Type', 'application/json')
                self.send_header('Content-Length', str(len(payload)))
                self.send_header('Connection', 'close')
                self.end_headers(); self.wfile.write(payload)

        server = ThreadingHTTPServer(('127.0.0.1', 0), LocalUpload)
        server.daemon_threads = True
        worker = threading.Thread(target=server.serve_forever, daemon=True)
        worker.start()
        self.addCleanup(server.server_close)
        self.addCleanup(server.shutdown)
        config = self.folder / 'empty-gh-config'
        config.mkdir()
        environment = {'PATH': os.environ.get('PATH', ''), 'GH_CONFIG_DIR': str(config),
                       'GH_TOKEN': 'offline-synthetic-token', 'GH_PROMPT_DISABLED': '1',
                       'GH_TELEMETRY': 'disabled', 'GH_NO_UPDATE_NOTIFIER': '1',
                       'GH_NO_EXTENSION_UPDATE_NOTIFIER': '1',
                       'XDG_STATE_HOME': str(self.folder / 'gh-state'),
                       'XDG_DATA_HOME': str(self.folder / 'gh-data'),
                       'XDG_CACHE_HOME': str(self.folder / 'gh-cache'),
                       'NO_PROXY': '127.0.0.1'}
        endpoint = '/repos/' + release.REPO + '/releases/500/assets?name=candidate.json'
        local_url = 'http://127.0.0.1:' + str(server.server_port) + endpoint
        native_run = subprocess.run
        old = native_run(['gh', 'api', '--hostname', 'github.com', local_url, '--method', 'POST',
                          '--input', '-', '--include', '-H', 'Content-Type: application/octet-stream'],
                         input=data, capture_output=True, env=environment, timeout=10, check=False)
        self.assertNotEqual(old.returncode, 0)
        self.assertIn(b'411', old.stdout)
        self.assertIsNone(received[0]['length'])

        def localhost_only(args, **kwargs):
            args = list(args)
            remote = 'https://uploads.github.com' + endpoint
            self.assertIn(remote, args)
            args[args.index(remote)] = local_url
            kwargs['env'] = environment
            return native_run(args, **kwargs)
        with patch.object(release.subprocess, 'run', side_effect=localhost_only):
            asset = release.AssetAPI().upload(500, 'candidate.json', data)
        release.verify_asset(asset, 'candidate.json', data)
        self.assertEqual(len(received), 2)
        self.assertEqual(received[1]['length'], str(len(data)))
        self.assertIsNone(received[1]['transfer_encoding'])
        self.assertEqual(received[1]['body'], data)
        self.assertEqual(received[1]['path'], endpoint)


if __name__ == '__main__':
    unittest.main()
