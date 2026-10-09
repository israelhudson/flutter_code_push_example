"""Ephemeral-runner Slack safety: synthetic GitHub/Slack only, no live sends."""
import base64
import copy
from concurrent.futures import ThreadPoolExecutor
from contextlib import closing, redirect_stdout
import hashlib
import io
import json
import os
from pathlib import Path
import sqlite3
import sys
import tempfile
from threading import Barrier, Event, Lock
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / 'tools/delivery'))
import release_lab
import slack_notify
import slack_outbox as outbox

TOKEN = 'xoxb-offline-fixture-token'
TS = '1760000000.000001'


def notice(event='candidate_available', **changes):
    identity = {'candidate_tag': 'v1.5.0-rc.1', 'source_sha': 'a' * 40,
                'snapshot_digest': 'b' * 64, 'run_id': '123',
                'run_url': 'https://github.com/' + outbox.REPOSITORY + '/actions/runs/123'}
    identity.update(changes.pop('identity', {}))
    key = outbox.logical_event_key(identity, event)
    value = slack_notify.render_notice('candidate', '0/2; comando final bloqueado',
                                      identity['candidate_tag'], identity['source_sha'],
                                      identity['run_url'], idempotency_key=key)
    value.update(event=event, identity=identity)
    value.update(changes)
    return value


class FakeGit:
    def __init__(self):
        self.document = None
        self.calls = []
        self.lock = Lock()
        self.fail_writes = False
        self.lose_reply = False
        self.forced_conflicts = 0
        self.other_state = {'active': 'v1.5.0-rc.1', 'approvals': ['first']}

    def bytes(self):
        return (outbox.canonical(self.document) + '\n').encode()

    def sha(self):
        raw = self.bytes()
        return hashlib.sha1(b'blob ' + str(len(raw)).encode() + b'\0' + raw).hexdigest()

    def __call__(self, path, data=None, method='GET', missing=False):
        with self.lock:
            self.calls.append((method, path, copy.deepcopy(data)))
            expected = release_lab.endpoint('contents/' + outbox.STATE_PATH)
            if method == 'GET' and path.startswith(expected + '?ref='):
                if self.document is None:
                    return None
                return {'encoding': 'base64', 'sha': self.sha(),
                        'content': base64.b64encode(self.bytes()).decode()}
            if method == 'GET' and path == release_lab.endpoint('git/ref/heads/' + outbox.STATE_BRANCH):
                return {'ref': 'refs/heads/' + outbox.STATE_BRANCH, 'object': {'sha': 'c' * 40}}
            if method == 'PUT' and path == expected:
                if self.fail_writes:
                    raise release_lab.LabError('Synthetic unavailable GitHub; no raw API/token')
                if self.forced_conflicts:
                    self.forced_conflicts -= 1
                    raise release_lab.LabError('Synthetic CAS conflict')
                if data.get('branch') != outbox.STATE_BRANCH:
                    raise AssertionError('Only authorized state branch')
                previous = self.sha() if self.document is not None else None
                if data.get('sha') != previous:
                    raise release_lab.LabError('Synthetic expected-SHA conflict')
                value = json.loads(base64.b64decode(data['content']))
                if self.document is not None and value['events'][:len(self.document['events'])] != self.document['events']:
                    raise AssertionError('Checkpoints must be append-only')
                self.document = value
                if self.lose_reply:
                    self.lose_reply = False
                    raise release_lab.LabError('Synthetic reply lost after commit')
                return {'content': {'sha': self.sha()}}
            raise AssertionError('Unexpected GitHub endpoint: ' + method + ' ' + path)


class FakeSlack:
    def __init__(self, git=None):
        self.calls = []
        self.user = outbox.BOT_USER_ID
        self.app_id = outbox.APP_ID
        self.channel = {'id': slack_notify.CHANNEL_ID, 'name': slack_notify.CHANNEL_NAME,
                        'is_private': True, 'is_archived': False}
        self.members = [slack_notify.ISRAEL_ID, outbox.BOT_USER_ID]
        self.history = []
        self.fail_post = False
        self.fail_history = False
        self.fail_sent_checkpoint = False
        self.git = git

    def message(self, payload):
        return {**copy.deepcopy(payload), 'user': outbox.BOT_USER_ID, 'bot_id': 'BTESTBOT',
                'bot_profile': {'app_id': outbox.APP_ID}, 'type': 'message', 'ts': TS}

    def __call__(self, method, data, token):
        if token != TOKEN:
            raise AssertionError('Credential only passes to Slack API')
        self.calls.append((method, copy.deepcopy(data)))
        if method == 'auth.test':
            return {'ok': True, 'user_id': self.user, 'bot_id': 'BTESTBOT', 'app_id': self.app_id}
        if method == 'conversations.info':
            return {'ok': True, 'channel': self.channel}
        if method == 'conversations.members':
            return {'ok': True, 'members': self.members, 'response_metadata': {'next_cursor': ''}}
        if method == 'conversations.history':
            if self.fail_history:
                raise slack_notify.SlackAPIError('Synthetic missing_scope')
            return {'ok': True, 'messages': self.history, 'response_metadata': {'next_cursor': ''}}
        if method == 'chat.postMessage':
            if self.git:
                self.assert_remote_unknown(data)
            if self.fail_post:
                raise slack_notify.SlackAPIError('Synthetic timeout; outcome uncertain')
            self.history.append(self.message(data))
            if self.fail_sent_checkpoint:
                self.git.fail_writes = True
            return {'ok': True, 'channel': slack_notify.CHANNEL_ID, 'ts': TS}
        raise AssertionError('Unexpected Slack method: ' + method)

    def assert_remote_unknown(self, payload):
        if (self.git.document is None or not any(e['state'] == 'unknown'
                    and e['client_msg_id'] == payload['client_msg_id'] for e in self.git.document['events'])):
            raise AssertionError('Remote unknown must be committed before post')

    def posts(self):
        return sum(method == 'chat.postMessage' for method, _ in self.calls)


class DurableSlackTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix='slack-durable-test-')
        self.addCleanup(self.temporary.cleanup)
        self.env = patch.dict(os.environ, {'SLACK_BOT_TOKEN': TOKEN}, clear=True)
        self.env.start()
        self.addCleanup(self.env.stop)
        self.git = FakeGit()
        self.store = outbox.SlackJournalStore(self.git)
        self.slack = FakeSlack(self.git)
        self.sequence = 0

    def send(self, value=None, api=None):
        self.sequence += 1
        return outbox.send_frozen_notice(value or notice(), Path(self.temporary.name) / str(self.sequence),
                                        store=self.store, slack_api=api or self.slack)

    def reserve(self, value=None):
        descriptor = outbox.validate_notice(value or notice())
        return self.store.append(descriptor, 'unknown', 'c148b356-a2c4-4b7c-b8e1-4f253c1327e6')

    def test_success_is_unknown_before_post_then_sent_with_exact_receipt(self):
        result = self.send()
        self.assertEqual(result['state'], 'sent')
        self.assertFalse(result['duplicate'])
        self.assertEqual(result['receipt']['ts'], TS)
        self.assertEqual([e['state'] for e in self.git.document['events']], ['unknown', 'sent'])
        self.assertEqual(self.slack.posts(), 1)
        self.assertEqual(self.git.other_state, {'active': 'v1.5.0-rc.1', 'approvals': ['first']})
        with closing(sqlite3.connect(Path(self.temporary.name) / '1/slack-outbox.sqlite3')) as db:
            self.assertEqual(db.execute('SELECT state,slack_ts FROM notices').fetchone(), ('sent', TS))

    def test_sent_on_fresh_runner_skips_every_slack_call_and_restores_sqlite(self):
        self.send()
        previous = len(self.slack.calls)
        result = self.send()
        self.assertEqual(result['state'], 'sent')
        self.assertTrue(result['duplicate'])
        self.assertEqual(len(self.slack.calls), previous)
        self.assertEqual(len(self.git.document['events']), 2)
        with closing(sqlite3.connect(Path(self.temporary.name) / '2/slack-outbox.sqlite3')) as db:
            self.assertEqual(db.execute('SELECT state,slack_ts FROM notices').fetchone(), ('sent', TS))

    def test_missing_or_malformed_secret_skips_without_remote_or_slack_calls(self):
        for token in (None, '', 'not-a-bot-token', 'xoxb-with whitespace', 'xoxp-user-token'):
            environment = {} if token is None else {'SLACK_BOT_TOKEN': token}
            with self.subTest(token=token), patch.dict(os.environ, environment, clear=True):
                self.assertEqual(self.send()['state'], 'skipped')
        self.assertEqual(self.slack.calls, [])
        self.assertEqual(self.git.calls, [])

    def test_wrong_exact_bot_or_app_never_reserves_or_posts(self):
        for field, value in [('user', 'UOTHERBOT'), ('user', slack_notify.ISRAEL_ID), ('app_id', 'AOTHERAPP')]:
            api = FakeSlack(self.git)
            setattr(api, field, value)
            with self.subTest(field=field):
                self.assertEqual(self.send(api=api)['state'], 'blocked')
                self.assertEqual(api.posts(), 0)
                self.assertIsNone(self.git.document)

    def test_public_or_shared_channel_or_extra_member_never_reserves(self):
        for field, value in [('is_private', False), ('is_shared', True), ('id', 'COTHER')]:
            api = FakeSlack(self.git)
            api.channel[field] = value
            with self.subTest(field=field):
                self.assertEqual(self.send(api=api)['state'], 'blocked')
                self.assertEqual(api.posts(), 0)
        api = FakeSlack(self.git)
        api.members.append('UOTHER')
        self.assertEqual(self.send(api=api)['state'], 'blocked')
        self.assertEqual(api.posts(), 0)
        self.assertIsNone(self.git.document)

    def test_checkpoint_persistence_failure_never_posts(self):
        self.git.fail_writes = True
        result = self.send()
        self.assertEqual(result['state'], 'blocked')
        self.assertEqual(self.slack.posts(), 0)
        self.assertIsNone(self.git.document)
        self.assertLessEqual(sum(m == 'PUT' for m, _, _ in self.git.calls), 3)

    def test_lost_unknown_write_reply_rechecks_exact_checkpoint_before_post(self):
        self.git.lose_reply = True
        result = self.send()
        self.assertEqual(result['state'], 'sent')
        self.assertEqual(self.slack.posts(), 1)
        self.assertEqual([e['state'] for e in self.git.document['events']], ['unknown', 'sent'])

    def test_post_timeout_remains_remote_unknown_and_fresh_retry_never_posts(self):
        self.slack.fail_post = True
        self.assertEqual(self.send()['state'], 'blocked')
        self.assertEqual(self.slack.posts(), 1)
        self.slack.fail_post = False
        self.assertEqual(self.send()['state'], 'blocked')
        self.assertEqual(self.slack.posts(), 1)
        self.assertEqual([e['state'] for e in self.git.document['events']], ['unknown'])

    def test_remote_unknown_with_positive_history_reconciles_without_post(self):
        value = notice()
        self.reserve(value)
        message = self.slack.message(value['payload'])
        message['blocks'][0]['block_id'] = 'server-added-id'
        self.slack.history.append(message)
        result = self.send(value)
        self.assertEqual(result['state'], 'sent')
        self.assertTrue(result['duplicate'])
        self.assertTrue(result['receipt']['reconciled'])
        self.assertEqual(self.slack.posts(), 0)
        self.assertEqual([e['state'] for e in self.git.document['events']], ['unknown', 'sent'])

    def test_unknown_empty_history_or_missing_scope_never_authorizes_resend(self):
        self.reserve()
        for fail in (False, True):
            self.slack.fail_history = fail
            with self.subTest(fail=fail):
                self.assertEqual(self.send()['state'], 'blocked')
                self.assertEqual(self.slack.posts(), 0)
        self.assertEqual([e['state'] for e in self.git.document['events']], ['unknown'])

    def test_unknown_client_id_with_wrong_hash_bot_app_or_channel_blocks(self):
        value = notice()
        self.reserve(value)
        for field, replacement in [('text', 'mutated content'), ('user', 'UOTHER'),
                                   ('bot_profile', {'app_id': 'AOTHER'}), ('channel', 'COTHER')]:
            message = self.slack.message(value['payload'])
            message[field] = replacement
            self.slack.history = [message]
            with self.subTest(field=field):
                self.assertEqual(self.send(value)['state'], 'blocked')
                self.assertEqual(self.slack.posts(), 0)
        self.assertEqual(len(self.git.document['events']), 1)

    def test_history_pagination_is_bounded_and_positive_later_page_reconciles(self):
        value = notice()
        self.reserve(value)
        histories = []

        def api(method, data, token):
            if method == 'conversations.history':
                histories.append(data.copy())
                if data.get('cursor') == 'page2':
                    return {'ok': True, 'messages': [self.slack.message(value['payload'])],
                            'response_metadata': {'next_cursor': ''}}
                return {'ok': True, 'messages': [], 'response_metadata': {'next_cursor': 'page2'}}
            return self.slack(method, data, token)

        self.assertEqual(self.send(value, api)['state'], 'sent')
        self.assertEqual(len(histories), 2)
        self.assertEqual(self.slack.posts(), 0)

    def test_unbounded_history_without_evidence_stops_at_three_pages(self):
        self.reserve()
        calls = []

        def api(method, data, token):
            if method == 'conversations.history':
                calls.append(data.copy())
                return {'ok': True, 'messages': [], 'response_metadata': {'next_cursor': 'page' + str(len(calls))}}
            return self.slack(method, data, token)

        self.assertEqual(self.send(api=api)['state'], 'blocked')
        self.assertEqual(len(calls), 3)
        self.assertEqual(self.slack.posts(), 0)

    def test_sent_checkpoint_lost_requires_history_on_fresh_runner(self):
        self.slack.fail_sent_checkpoint = True
        self.assertEqual(self.send()['state'], 'blocked')
        self.assertEqual(self.slack.posts(), 1)
        self.assertEqual([e['state'] for e in self.git.document['events']], ['unknown'])
        self.git.fail_writes = False
        result = self.send()
        self.assertEqual(result['state'], 'sent')
        self.assertTrue(result['receipt']['reconciled'])
        self.assertEqual(self.slack.posts(), 1)

    def test_same_logical_key_different_payload_blocks_before_slack_read(self):
        value = notice()
        self.send(value)
        changed = copy.deepcopy(value)
        changed['payload']['text'] += '\nChanged'
        calls = len(self.slack.calls)
        self.assertEqual(self.send(changed)['state'], 'blocked')
        self.assertEqual(len(self.slack.calls), calls)
        self.assertEqual(len(self.git.document['events']), 2)

    def test_two_fresh_runners_same_event_only_one_may_post(self):
        posting, release = Event(), Event()

        def delayed(method, data, token):
            if method == 'chat.postMessage':
                posting.set()
                if not release.wait(5):
                    raise AssertionError('Synthetic synchronization timeout')
            return self.slack(method, data, token)

        with ThreadPoolExecutor(max_workers=1) as pool:
            first = pool.submit(self.send, None, delayed)
            try:
                self.assertTrue(posting.wait(5))
                second = self.send()
                self.assertEqual(second['state'], 'blocked')
            finally:
                release.set()
            self.assertEqual(first.result(timeout=5)['state'], 'sent')
        self.assertEqual(self.slack.posts(), 1)

    def test_competing_different_events_preserve_both_and_candidate_journal(self):
        self.git.forced_conflicts = 1
        value = notice()
        self.send(value)
        self.send(notice('approval_first'))
        projection = outbox._project(self.git.document)
        self.assertEqual(len(projection), 2)
        self.assertTrue(all(e['state'] == 'sent' for e in projection.values()))
        self.assertEqual(self.slack.posts(), 2)
        self.assertTrue(all(outbox.STATE_PATH in path or '/git/ref/' in path
                            for _, path, _ in self.git.calls))

    def test_actual_concurrent_writers_append_different_events_without_lost_updates(self):
        self.reserve(notice('candidate_available'))
        barrier, guard = Barrier(2), Lock()
        first_reads = 0

        def racing(path, data=None, method='GET', missing=False):
            nonlocal first_reads
            response = self.git(path, data, method, missing)
            wait = False
            if method == 'GET' and '/contents/' in path:
                with guard:
                    if first_reads < 2:
                        first_reads += 1
                        wait = True
                if wait:
                    barrier.wait(timeout=5)
            return response

        store = outbox.SlackJournalStore(racing)
        first = outbox.validate_notice(notice('approval_first'))
        second = outbox.validate_notice(notice('approval_second'))
        with ThreadPoolExecutor(max_workers=2) as pool:
            futures = [pool.submit(store.append, first, 'unknown', 'ff96947a-258a-46d9-bb02-d35b01dba659'),
                       pool.submit(store.append, second, 'unknown', '520da679-5011-4450-84b7-ee3224f9c572')]
            for future in futures:
                self.assertEqual(future.result(timeout=5)['state'], 'unknown')
        projection = outbox._project(self.git.document)
        self.assertEqual(set(projection), {notice()['event_key'], first['event_key'], second['event_key']})
        self.assertEqual(self.slack.posts(), 0)

    def test_receipts_logs_and_remote_checkpoints_exclude_secrets_and_full_payload(self):
        result = self.send()
        raw = json.dumps(self.git.document) + json.dumps(result)
        self.assertNotIn(TOKEN, raw)
        self.assertNotIn('Authorization', raw)
        self.assertNotIn('blocks', raw)
        for path in Path(self.temporary.name).rglob('*'):
            if path.is_file():
                self.assertNotIn(TOKEN.encode(), path.read_bytes())

    def test_evaluation_run_change_keeps_key_but_blocks_frozen_provenance_replacement(self):
        original = notice()
        identity = {**original['identity'], 'run_id': '456',
                    'run_url': 'https://github.com/' + outbox.REPOSITORY + '/actions/runs/456'}
        self.assertEqual(outbox.logical_event_key(original['identity']), outbox.logical_event_key(identity))
        self.send(original)
        copied = copy.deepcopy(original)
        copied['identity'] = identity
        with self.assertRaises(outbox.OutboxError):
            self.send(copied)
        descriptor = outbox.validate_notice(original)
        descriptor['identity'] = identity
        with self.assertRaises(outbox.OutboxError):
            self.store.get(descriptor)
        self.assertEqual(self.slack.posts(), 1)

    def test_only_preview_for_exact_frozen_source_is_allowed(self):
        value = notice()
        value['payload']['blocks'].insert(1, {'type': 'section', 'text': {'type': 'mrkdwn',
            'text': '<https://israelhudson.github.io/flutter_code_push_example/snapshots/'
                    + value['identity']['source_sha'] + '/|Abrir preview>', 'verbatim': True}})
        self.assertEqual(self.send(value)['state'], 'sent')
        invalid = copy.deepcopy(value)
        invalid['payload']['blocks'][1]['text']['text'] = invalid['payload']['blocks'][1]['text']['text'].replace('a' * 40, 'f' * 40)
        with self.assertRaises(outbox.OutboxError):
            self.send(invalid)
        self.assertEqual(self.slack.posts(), 1)

    def test_cli_invalid_frozen_notice_is_optional_and_no_raw_content_is_printed(self):
        path = Path(self.temporary.name) / 'invalid.json'
        path.write_text(json.dumps({'secret': TOKEN}))
        stdout = io.StringIO()
        with redirect_stdout(stdout):
            code = outbox.main(['--notice', str(path), '--output-dir', self.temporary.name])
        self.assertEqual(code, 0)
        self.assertEqual(json.loads(stdout.getvalue())['state'], 'blocked')
        self.assertNotIn(TOKEN, stdout.getvalue())
        self.assertEqual(self.slack.calls, [])


if __name__ == '__main__':
    unittest.main()
