"""Slack notice safety and outbox tests. Every API call is mocked offline."""
from concurrent.futures import ThreadPoolExecutor
from contextlib import closing, redirect_stdout
import io
import json
import os
from pathlib import Path
import sqlite3
import sys
import tempfile
from threading import Event
import unittest
from unittest.mock import patch
from urllib.error import HTTPError, URLError

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / 'tools/delivery'))
import slack_notify as slack

SHA = 'a' * 40
BOT_USER = 'U0TESTBOT1'
TOKEN = 'xoxb-offline-fixture-token'
GITHUB_URL = 'https://github.com/israelhudson/flutter_code_push_example/pull/3'


def notice(**kwargs):
    return slack.render_notice('candidate', '0/2; comando final bloqueado',
                               'entrega-0042-rc.1', SHA, GITHUB_URL, **kwargs)


class FakeSlack:
    def __init__(self):
        self.calls = []
        self.auth = {'ok': True, 'user_id': BOT_USER, 'bot_id': 'B0TESTBOT1'}
        self.channel = {'id': slack.CHANNEL_ID, 'name': slack.CHANNEL_NAME,
                        'is_private': True, 'is_archived': False}
        self.members = [slack.ISRAEL_ID, BOT_USER]
        self.reply = {'ok': True, 'channel': slack.CHANNEL_ID, 'ts': '1760000000.000001'}

    def __call__(self, method, data, token):
        self.calls.append((method, data.copy()))
        if token != TOKEN:
            raise AssertionError('Credential must come from env and only reach the API')
        if method == 'auth.test':
            return self.auth
        if method == 'conversations.info':
            return {'ok': True, 'channel': self.channel}
        if method == 'conversations.members':
            return {'ok': True, 'members': self.members, 'response_metadata': {'next_cursor': ''}}
        if method == 'chat.postMessage':
            return self.reply
        raise AssertionError('Unexpected Slack operation: ' + method)


class RenderTests(unittest.TestCase):
    def test_default_cli_renders_without_token_network_or_outbox(self):
        output = io.StringIO()
        with tempfile.TemporaryDirectory() as folder, patch.dict(os.environ, {}, clear=True), patch.object(slack, 'request_url') as request, patch.object(slack, '_open_outbox') as outbox, redirect_stdout(output):
            code = slack.main(['--event', 'lab', '--status', '2/2 simulados',
                               '--candidate', 'entrega-0042-rc.1', '--source-sha', SHA,
                               '--url', GITHUB_URL, '--outbox', folder + '/not-created.sqlite3'])
            self.assertEqual(code, 0)
            request.assert_not_called()
            outbox.assert_not_called()
        rendered = json.loads(output.getvalue())
        self.assertTrue(rendered['simulation'])
        self.assertTrue(rendered['dry_run'])
        self.assertEqual(rendered['payload']['channel'], slack.CHANNEL_ID)
        self.assertIn('não aprova nem publica', rendered['payload']['text'])
        self.assertNotIn('actions', json.dumps(rendered['payload']['blocks']))

    def test_client_id_is_stable_and_bound_to_candidate_and_content(self):
        first = notice()
        self.assertEqual(first, notice())
        changed = slack.render_notice('candidate', '0/2', 'entrega-0042-rc.2', SHA, GITHUB_URL)
        self.assertNotEqual(first['payload']['client_msg_id'], changed['payload']['client_msg_id'])
        explicit = notice(idempotency_key='candidate:delivery-42:rc1')
        self.assertEqual(explicit['payload']['client_msg_id'], notice(idempotency_key='candidate:delivery-42:rc1')['payload']['client_msg_id'])

    def test_lab_flags_are_explicit_and_real_notice_cannot_claim_distribution(self):
        self.assertFalse(notice()['simulation'])
        self.assertTrue(notice()['dry_run'])
        with self.assertRaises(slack.NoticeError):
            notice(dry_run=False)
        with self.assertRaises(slack.NoticeError):
            slack.render_notice('lab', 'status', 'candidate', SHA, GITHUB_URL, simulation=False)

    def test_github_links_cannot_redirect_to_other_repositories_or_mentions(self):
        for value in ['https://github.com.evil.invalid/israelhudson/flutter_code_push_example/pull/3',
                      'http://github.com/israelhudson/flutter_code_push_example/pull/3',
                      'https://github.com/other/project/pull/3',
                      GITHUB_URL + '?token=do-not-render', GITHUB_URL + '|<!channel>',
                      'https://user@github.com/israelhudson/flutter_code_push_example/pull/3']:
            with self.subTest(url=value), self.assertRaises(slack.NoticeError):
                slack.github_url(value)

    def test_status_uses_plain_text_and_does_not_enable_mentions(self):
        rendered = slack.render_notice('approval', '<@U123> <!channel> *Approve*',
                                      'entrega-0042-rc.1', SHA, GITHUB_URL)
        self.assertEqual(rendered['payload']['blocks'][0]['text']['type'], 'plain_text')
        self.assertFalse(rendered['payload']['mrkdwn'])
        self.assertFalse(rendered['payload']['link_names'])
        self.assertEqual(rendered['payload']['blocks'][1]['text']['text'], f'<{GITHUB_URL}|Abrir no GitHub>')


class DestinationTests(unittest.TestCase):
    def test_only_exact_private_channel_and_bot_plus_israel_are_accepted(self):
        api = FakeSlack()
        self.assertEqual(slack.verify_destination(TOKEN, api), BOT_USER)
        self.assertEqual([method for method, _ in api.calls],
                         ['auth.test', 'conversations.info', 'conversations.members'])
        self.assertTrue(all(data.get('channel', slack.CHANNEL_ID) == slack.CHANNEL_ID
                            for _, data in api.calls))

    def test_wrong_public_shared_archived_or_renamed_channel_has_no_post(self):
        for field, value in [('id', 'COTHER'), ('name', 'app-deploy-official'),
                             ('is_private', False), ('is_archived', True),
                             ('is_ext_shared', True), ('is_im', True)]:
            api = FakeSlack()
            api.channel[field] = value
            with self.subTest(field=field), self.assertRaises(slack.NoticeError):
                slack.verify_destination(TOKEN, api)
            self.assertFalse(any(method == 'chat.postMessage' for method, _ in api.calls))

    def test_extra_human_or_another_bot_or_missing_israel_blocks(self):
        for members in [[slack.ISRAEL_ID, BOT_USER, 'UOTHERHUMAN'],
                        [slack.ISRAEL_ID, BOT_USER, 'UOTHERBOT'], [BOT_USER]]:
            api = FakeSlack()
            api.members = members
            with self.subTest(members=members), self.assertRaises(slack.NoticeError):
                slack.verify_destination(TOKEN, api)

    def test_user_token_cannot_impersonate_israel(self):
        for auth in [{'ok': True, 'user_id': slack.ISRAEL_ID},
                     {'ok': True, 'bot_id': 'B1', 'user_id': slack.ISRAEL_ID}]:
            api = FakeSlack()
            api.auth = auth
            with self.assertRaises(slack.NoticeError):
                slack.verify_destination(TOKEN, api)
            self.assertEqual(len(api.calls), 1)

    def test_membership_is_checked_through_all_pages(self):
        api = FakeSlack()
        def paged(method, data, token):
            if method == 'conversations.members':
                return ({'ok': True, 'members': [slack.ISRAEL_ID, BOT_USER],
                         'response_metadata': {'next_cursor': 'page2'}} if not data.get('cursor') else
                        {'ok': True, 'members': ['UOTHERHUMAN'], 'response_metadata': {'next_cursor': ''}})
            return api(method, data, token)
        with self.assertRaisesRegex(slack.NoticeError, 'outros membros'):
            slack.verify_destination(TOKEN, paged)

    def test_repeated_or_malformed_cursor_fails_closed(self):
        for cursor in ['same', None]:
            api = FakeSlack()
            def paged(method, data, token):
                if method == 'conversations.members':
                    return {'ok': True, 'members': [slack.ISRAEL_ID, BOT_USER],
                            'response_metadata': {'next_cursor': cursor}}
                return api(method, data, token)
            with self.subTest(cursor=cursor), self.assertRaises(slack.NoticeError):
                slack.verify_destination(TOKEN, paged)


class OutboxTests(unittest.TestCase):
    def test_confirmed_send_is_persisted_and_retry_has_no_api_call(self):
        api = FakeSlack()
        with tempfile.TemporaryDirectory() as folder, patch.dict(os.environ, {'SLACK_BOT_TOKEN': TOKEN}, clear=True):
            path = Path(folder) / 'outbox.sqlite3'
            first = slack.send_notice(notice(), path, api)
            self.assertEqual(first['state'], 'sent')
            self.assertFalse(first['duplicate'])
            calls_before = len(api.calls)
            second = slack.send_notice(notice(), path, api)
            self.assertTrue(second['duplicate'])
            self.assertEqual(len(api.calls), calls_before)
            self.assertNotIn(TOKEN.encode(), path.read_bytes())
            with closing(sqlite3.connect(path)) as db:
                self.assertEqual(db.execute('SELECT state,slack_ts FROM notices').fetchone(),
                                 ('sent', api.reply['ts']))

    def test_transport_uncertainty_stays_unknown_and_never_retries(self):
        api = FakeSlack()
        def fail_post(method, data, token):
            if method == 'chat.postMessage':
                raise slack.SlackAPIError('Sem confirmação')
            return api(method, data, token)
        with tempfile.TemporaryDirectory() as folder, patch.dict(os.environ, {'SLACK_BOT_TOKEN': TOKEN}, clear=True):
            path = Path(folder) / 'outbox.sqlite3'
            with self.assertRaises(slack.SlackAPIError):
                slack.send_notice(notice(), path, fail_post)
            with closing(sqlite3.connect(path)) as db:
                self.assertEqual(db.execute('SELECT state FROM notices').fetchone()[0], 'unknown')
            with patch.object(slack, 'slack_api') as never:
                with self.assertRaisesRegex(slack.NoticeError, 'unknown'):
                    slack.send_notice(notice(), path, never)
                never.assert_not_called()

    def test_post_response_without_exact_channel_ts_is_unknown(self):
        for reply in [{'ok': True, 'channel': 'COTHER', 'ts': '1.01'},
                      {'ok': True, 'channel': slack.CHANNEL_ID},
                      {'ok': False, 'channel': slack.CHANNEL_ID, 'ts': '1.01'}]:
            api = FakeSlack()
            api.reply = reply
            with self.subTest(reply=reply), tempfile.TemporaryDirectory() as folder, patch.dict(os.environ, {'SLACK_BOT_TOKEN': TOKEN}, clear=True):
                path = Path(folder) / 'outbox.sqlite3'
                with self.assertRaisesRegex(slack.NoticeError, 'unknown'):
                    slack.send_notice(notice(), path, api)
                with closing(sqlite3.connect(path)) as db:
                    self.assertEqual(db.execute('SELECT state FROM notices').fetchone()[0], 'unknown')

    def test_failed_destination_check_creates_no_attempt_and_never_posts(self):
        api = FakeSlack()
        api.members.append('UOTHER')
        with tempfile.TemporaryDirectory() as folder, patch.dict(os.environ, {'SLACK_BOT_TOKEN': TOKEN}, clear=True):
            path = Path(folder) / 'outbox.sqlite3'
            with self.assertRaises(slack.NoticeError):
                slack.send_notice(notice(), path, api)
            with closing(sqlite3.connect(path)) as db:
                self.assertEqual(db.execute('SELECT COUNT(*) FROM notices').fetchone()[0], 0)
        self.assertFalse(any(method == 'chat.postMessage' for method, _ in api.calls))

    def test_same_key_with_changed_payload_blocks_repetition(self):
        api = FakeSlack()
        with tempfile.TemporaryDirectory() as folder, patch.dict(os.environ, {'SLACK_BOT_TOKEN': TOKEN}, clear=True):
            path = Path(folder) / 'outbox.sqlite3'
            slack.send_notice(notice(idempotency_key='fixed'), path, api)
            changed = slack.render_notice('approval', '1/2', 'entrega-0042-rc.1', SHA,
                                           GITHUB_URL, idempotency_key='fixed')
            count = len(api.calls)
            with self.assertRaisesRegex(slack.NoticeError, 'outro conteúdo'):
                slack.send_notice(changed, path, api)
            self.assertEqual(len(api.calls), count)

    def test_concurrent_attempt_is_blocked_while_first_post_is_in_flight(self):
        api = FakeSlack()
        posting, release_post = Event(), Event()
        def delayed(method, data, token):
            if method == 'chat.postMessage':
                posting.set()
                if not release_post.wait(5):
                    raise AssertionError('Test coordination timed out')
            return api(method, data, token)
        with tempfile.TemporaryDirectory() as folder, patch.dict(os.environ, {'SLACK_BOT_TOKEN': TOKEN}, clear=True), ThreadPoolExecutor(max_workers=1) as pool:
            path = Path(folder) / 'outbox.sqlite3'
            first = pool.submit(slack.send_notice, notice(), path, delayed)
            try:
                self.assertTrue(posting.wait(5))
                with self.assertRaisesRegex(slack.NoticeError, 'unknown'):
                    slack.send_notice(notice(), path, api)
            finally:
                release_post.set()
            self.assertEqual(first.result(timeout=5)['state'], 'sent')
            self.assertEqual(sum(method == 'chat.postMessage' for method, _ in api.calls), 1)

    def test_missing_token_cannot_read_or_post_to_slack(self):
        api = FakeSlack()
        with tempfile.TemporaryDirectory() as folder, patch.dict(os.environ, {}, clear=True):
            with self.assertRaisesRegex(slack.NoticeError, 'SLACK_BOT_TOKEN'):
                slack.send_notice(notice(), Path(folder) / 'outbox.sqlite3', api)
        self.assertEqual(api.calls, [])


class TransportTests(unittest.TestCase):
    def test_token_is_header_only_and_write_is_json_to_fixed_slack_endpoint(self):
        class Response:
            def __enter__(self): return self
            def __exit__(self, *args): pass
            def read(self, limit): return b'{"ok":true,"channel":"C0C8DUJB52L","ts":"1.01"}'
        with patch.object(slack, 'request_url', return_value=Response()) as request:
            slack.slack_api('chat.postMessage', notice()['payload'], TOKEN)
        req = request.call_args.args[0]
        self.assertEqual(req.full_url, 'https://slack.com/api/chat.postMessage')
        self.assertEqual(req.get_header('Authorization'), 'Bearer ' + TOKEN)
        self.assertEqual(req.get_method(), 'POST')
        self.assertNotIn(TOKEN.encode(), req.data)
        self.assertEqual(request.call_args.kwargs['timeout'], 10)

    def test_unknown_method_does_not_call_network(self):
        with patch.object(slack, 'request_url') as request:
            with self.assertRaises(slack.SlackAPIError):
                slack.slack_api('conversations.invite', {}, TOKEN)
            request.assert_not_called()

    def test_network_errors_never_echo_token_or_raw_response(self):
        for error in [URLError(TOKEN), TimeoutError(TOKEN),
                      HTTPError('https://slack.com/api/chat.postMessage', 500, TOKEN, {}, None)]:
            with self.subTest(error=type(error).__name__), patch.object(slack, 'request_url', side_effect=error):
                with self.assertRaises(slack.SlackAPIError) as raised:
                    slack.slack_api('chat.postMessage', notice()['payload'], TOKEN)
                self.assertNotIn(TOKEN, str(raised.exception))

    def test_cross_host_redirect_is_never_followed(self):
        self.assertIsNone(slack.NoRedirect().redirect_request(None, None, 302, 'Found', {},
                                                             'https://evil.invalid/token'))


if __name__ == '__main__':
    unittest.main()
