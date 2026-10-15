"""Bot migration preserves frozen legacy receipts and never replays uncertainty."""
import copy
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from test_slack_outbox import FakeGit, FakeSlack, TOKEN, notice, readable_notice
import slack_notify as slack
import slack_outbox as outbox
from slack_preview import readable_payload


class SplitJournalGit:
    def __init__(self):
        self.legacy = FakeGit()
        self.poc = FakeGit()
        self.writes = []

    def __call__(self, path, data=None, method='GET', missing=False):
        if method == 'PUT':
            self.writes.append(path)
        if outbox.POC_STATE_PATH in path:
            return self.poc(path.replace(outbox.POC_STATE_PATH, outbox.STATE_PATH), data, method, missing)
        return self.legacy(path, data, method, missing)


def poc_notice():
    value = notice(notification_profile=slack.POC_PROFILE)
    payload, _ = readable_payload('LAB · Candidata pronta', ['Descrição breve.'], [],
        'Aprovações no GitHub.',
        'https://israelhudson.github.io/flutter_code_push_example/snapshots/' + value['identity']['source_sha'] + '/',
        value['identity']['run_url'], link_buttons=False)
    value['payload'].update(payload)
    return value


class ProjectBotMigrationTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.env = patch.dict(os.environ, {'SLACK_BOT_TOKEN': TOKEN, 'POC_SLACK_BOT_TOKEN': TOKEN}, clear=True)
        self.env.start(); self.addCleanup(self.env.stop)
        sleep = patch.object(outbox.time, 'sleep', return_value=None)
        sleep.start(); self.addCleanup(sleep.stop)
        self.git = SplitJournalGit()
        self.store = outbox.SlackJournalStore(self.git, profile=slack.POC_PROFILE)
        self.api = FakeSlack(self.git.poc)
        identity = slack.notification_identity(slack.POC_PROFILE)
        self.api.user, self.api.app_id = identity['bot_user_id'], identity['app_id']
        self.api.members = [slack.ISRAEL_ID, outbox.BOT_USER_ID, self.api.user]
        self.sequence = 0

    def send(self, value=None):
        self.sequence += 1
        return outbox.send_frozen_notice(value or poc_notice(), Path(self.temp.name) / str(self.sequence),
                                        store=self.store, slack_api=self.api)

    def test_new_bot_uses_separate_journal_and_retry_reuses_receipt(self):
        legacy_store = outbox.SlackJournalStore(self.git)
        old_notice = notice(identity={'candidate_tag': 'v1.4.0-rc.1'})
        old_api = FakeSlack(self.git.legacy)
        outbox.send_frozen_notice(old_notice, Path(self.temp.name) / 'old', store=legacy_store, slack_api=old_api)
        old_bytes = self.git.legacy.bytes()
        result = self.send()
        self.assertEqual(result['state'], 'sent')
        self.assertEqual(result['receipt']['bot_user_id'], self.api.user)
        calls = copy.deepcopy(self.api.calls)
        repeated = self.send()
        self.assertTrue(repeated['duplicate'])
        self.assertEqual(repeated['receipt'], result['receipt'])
        self.assertEqual(self.api.calls, calls)
        self.assertEqual(self.git.legacy.bytes(), old_bytes)
        self.assertEqual(self.api.posts(), 1)
        self.assertTrue(all(outbox.POC_STATE_PATH in path for path in self.git.writes[2:]))
        # The old reader remains able to consume its untouched old journal.
        self.assertEqual(legacy_store.get(outbox.validate_notice(old_notice))['state'], 'sent')

    def test_old_event_cannot_be_replayed_through_new_journal(self):
        old = notice()
        old_store = outbox.SlackJournalStore(self.git)
        old_store.append(outbox.validate_notice(old), 'unknown', 'c148b356-a2c4-4b7c-b8e1-4f253c1327e6')
        before = self.git.legacy.bytes()
        result = self.send()
        self.assertEqual(result['state'], 'blocked')
        self.assertEqual(self.api.posts(), 0)
        self.assertIsNone(self.git.poc.document)
        self.assertEqual(self.git.legacy.bytes(), before)

    def test_old_sent_receipt_cannot_be_republished_by_changing_only_sender_profile(self):
        value = notice()
        old_store = outbox.SlackJournalStore(self.git)
        old_api = FakeSlack(self.git.legacy)
        outbox.send_frozen_notice(value, Path(self.temp.name) / 'historical', store=old_store, slack_api=old_api)
        before = self.git.legacy.bytes()
        value['notification_profile'] = slack.POC_PROFILE
        self.assertEqual(self.send(value)['state'], 'blocked')
        self.assertEqual(self.api.posts(), 0)
        self.assertEqual(self.git.legacy.bytes(), before)
        self.assertIsNone(self.git.poc.document)

    def test_new_unknown_requires_manual_evidence_without_history_scope_or_repost(self):
        self.api.fail_post = True
        self.assertEqual(self.send()['state'], 'blocked')
        self.api.fail_post = False
        result = self.send()
        self.assertEqual(result['state'], 'blocked')
        self.assertEqual(result['reason'], 'manual_reconciliation_required')
        self.assertEqual(self.api.posts(), 1)
        self.assertFalse(any(method == 'conversations.history' for method, _ in self.api.calls))
        self.assertEqual([e['state'] for e in self.git.poc.document['events']], ['unknown'])

    def test_missing_poc_secret_never_uses_legacy_token(self):
        with patch.dict(os.environ, {'SLACK_BOT_TOKEN': TOKEN}, clear=True):
            self.assertEqual(self.send()['state'], 'skipped')
        self.assertFalse(self.api.calls)
        self.assertFalse(self.git.writes)

    def test_each_profile_selects_its_own_secret_without_fallback(self):
        with patch.dict(os.environ, {'SLACK_BOT_TOKEN': 'legacy-fixture',
                                    'POC_SLACK_BOT_TOKEN': 'poc-fixture'}, clear=True):
            self.assertEqual(slack.notification_token(slack.LEGACY_PROFILE), 'legacy-fixture')
            self.assertEqual(slack.notification_token(slack.POC_PROFILE), 'poc-fixture')

    def test_wrong_bot_extra_human_or_unknown_bot_prevents_reservation(self):
        for user, extra in [(outbox.BOT_USER_ID, None), (self.api.user, 'UOTHERHUMAN'),
                            (self.api.user, 'UOTHERBOT')]:
            with self.subTest(user=user, extra=extra):
                self.api.user = user
                self.api.members = [slack.ISRAEL_ID, outbox.BOT_USER_ID,
                    slack.notification_identity(slack.POC_PROFILE)['bot_user_id']] + ([extra] if extra else [])
                self.assertEqual(self.send()['state'], 'blocked')
        self.assertFalse(self.git.writes)
        self.assertEqual(self.api.posts(), 0)

    def test_unknown_profile_or_poc_buttons_are_refused(self):
        value = poc_notice(); value['notification_profile'] = 'other'
        with self.assertRaises(slack.NoticeError):
            self.send(value)
        value = readable_notice(); value['notification_profile'] = slack.POC_PROFILE
        with self.assertRaises(outbox.OutboxError):
            self.send(value)
        self.assertEqual(self.api.posts(), 0)

    def test_explicit_profile_identity_is_checked_and_only_known_bots_are_permitted(self):
        self.assertEqual(slack.verify_destination(TOKEN, self.api, profile=slack.POC_PROFILE), self.api.user)
        self.api.members = [slack.ISRAEL_ID, self.api.user]
        self.assertEqual(slack.verify_destination(TOKEN, self.api, profile=slack.POC_PROFILE), self.api.user)
        self.api.members = [self.api.user]
        with self.assertRaises(slack.NoticeError):
            slack.verify_destination(TOKEN, self.api, profile=slack.POC_PROFILE)

    def test_legacy_sender_coexists_with_poc_bot_without_changing_legacy_payload(self):
        old_api = FakeSlack(self.git.legacy)
        old_api.members.append(slack.notification_identity(slack.POC_PROFILE)['bot_user_id'])
        value = readable_notice()
        before = copy.deepcopy(value)
        old_store = outbox.SlackJournalStore(self.git)
        result = outbox.send_frozen_notice(value, Path(self.temp.name) / 'legacy-coexist',
                                          store=old_store, slack_api=old_api)
        self.assertEqual(result['state'], 'sent')
        self.assertEqual(value, before)
        self.assertEqual(result['receipt']['bot_user_id'], outbox.BOT_USER_ID)
        self.assertIsNone(self.git.poc.document)

    def test_unspecified_profile_rejects_arbitrary_authenticated_bot(self):
        self.api.user = 'UUNKNOWNBOT'
        self.api.members = [slack.ISRAEL_ID, self.api.user]
        with self.assertRaises(slack.NoticeError):
            slack.verify_destination(TOKEN, self.api)


if __name__ == '__main__':
    unittest.main()
