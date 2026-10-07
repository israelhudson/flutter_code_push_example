"""Persistent control runs using offline GitHub/Slack endpoints and temporary Git."""

from contextlib import closing
import copy
import json
import os
from pathlib import Path
import shutil
import sqlite3
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "tools/delivery"))
sys.path.insert(0, str(Path(__file__).resolve().parent))
from lab_demo import fixture, commit, preview, write
from remote_state import RemoteState, StateUncertain, gh_api
from test_remote_state import FakeGitData
import runner
import slack_notify


class FakeSlack:
    def __init__(self):
        self.posts = []

    def __call__(self, method, data, token):
        if method == "auth.test":
            return {"ok": True, "bot_id": "B99", "user_id": "U99BOT"}
        if method == "conversations.info":
            return {"ok": True, "channel": {
                "id": slack_notify.CHANNEL_ID, "name": slack_notify.CHANNEL_NAME,
                "is_private": True, "is_archived": False}}
        if method == "conversations.members":
            return {"ok": True, "members": [slack_notify.ISRAEL_ID, "U99BOT"]}
        if method == "chat.postMessage":
            self.posts.append(data)
            return {"ok": True, "channel": slack_notify.CHANNEL_ID, "ts": "12345.123456"}
        raise AssertionError(method)


def principal(run):
    return {"id": "github:1234", "login": "israelhudson", "identity_source": "github_actions",
            "run_id": str(run), "run_url": "https://github.com/israelhudson/flutter_code_push_example/actions/runs/" + str(run)}


class RequestTests(unittest.TestCase):
    def test_only_authenticated_owner_on_personal_main_can_operate(self):
        environment = {"GITHUB_ACTIONS": "true", "GITHUB_REPOSITORY": runner.REPOSITORY,
                       "GITHUB_EVENT_NAME": "workflow_dispatch", "GITHUB_REF": "refs/heads/main",
                       "GITHUB_ACTOR": "israelhudson", "GITHUB_ACTOR_ID": "1234",
                       "GITHUB_TRIGGERING_ACTOR": "israelhudson", "GITHUB_RUN_ID": "42"}
        def api(method, path):
            self.assertEqual((method, path), ("GET", "repos/" + runner.REPOSITORY))
            return {"owner": {"id": 1234, "login": "israelhudson"}}
        self.assertEqual(runner.authenticate(environment, api)["id"], "github:1234")
        for field, value in (("GITHUB_REPOSITORY", "amulets/mobile"),
                             ("GITHUB_ACTOR_ID", "9999"), ("GITHUB_ACTOR", "samuelcamilo"),
                             ("GITHUB_TRIGGERING_ACTOR", "other"), ("GITHUB_REF", "refs/heads/evil"),
                             ("GITHUB_EVENT_NAME", "pull_request")):
            with self.subTest(field=field):
                with self.assertRaises(ValueError):
                    runner.authenticate({**environment, field: value}, api)

    def test_metadata_read_is_allowed_but_repo_root_mutation_is_rejected(self):
        response = b'HTTP/2.0 200 OK\r\ncontent-type: application/json\r\n\r\n{"owner":{"id":1234}}'
        class Result:
            stdout, stderr, returncode = response, b"", 0
        with patch("remote_state.subprocess.run", return_value=Result()):
            self.assertEqual(gh_api("GET", "repos/" + runner.REPOSITORY)["owner"]["id"], 1234)
        with self.assertRaises(ValueError):
            gh_api("PATCH", "repos/" + runner.REPOSITORY, {"private": False})

    def test_rc_and_urgency_do_not_silently_coerce_other_json_types(self):
        request = {"operation": "prepare", "source_sha": "a" * 40, "delivery_id": "entrega-0042"}
        self.assertEqual(runner.validate_request({**request, "rc": "2", "urgent": "true"})["rc"], 2)
        for rc in (True, 1.2, [], {}, "1.2", "0"):
            with self.subTest(rc=rc):
                with self.assertRaises(ValueError):
                    runner.validate_request({**request, "rc": rc})
        for urgent in (1, 0, [], {}, "yes"):
            with self.subTest(urgent=urgent):
                with self.assertRaises(ValueError):
                    runner.validate_request({**request, "urgent": urgent})

    def test_sha_candidate_and_hash_require_text_before_regex_checks(self):
        for request in ({"operation": "initialize", "source_sha": 123},
                        {"operation": "initialize", "source_sha": []},
                        {"operation": "approve", "candidate": {}, "manifest_hash": "a" * 64, "role": "samuel"},
                        {"operation": "approve", "candidate": "entrega-0042-rc.1", "manifest_hash": [], "role": "samuel"}):
            with self.subTest(request=request):
                with self.assertRaises(ValueError):
                    runner.validate_request(request)


class CoordinatorTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix="runner-test-")
        self.addCleanup(self.tmp.cleanup)
        self.folder = Path(self.tmp.name).resolve()
        self.root = self.folder / "canonical-root"
        self.root.mkdir()
        repo, _, _, inputs, _, _ = fixture(self.folder / "fixture")
        self.repo = self.root / "repository"
        shutil.move(repo, self.repo)
        write(self.repo / "delivery/build-inputs.json", json.dumps(inputs))
        self.base = commit(self.repo, "Pinned laboratory inputs")
        self.api = FakeGitData()
        self.remote = RemoteState(api=self.api)
        self.coordinator = None

    def action(self, run, request, preview_folder=None):
        if self.coordinator is not None:
            shutil.rmtree(self.root / "state")
        coordinator = runner.Coordinator(self.remote, principal(run), root=self.root)
        coordinator.restore(request["operation"])
        self.coordinator = coordinator
        return coordinator.invoke(request, preview_folder)

    def initialize(self):
        wrapper = self.action(1, {"operation": "initialize", "source_sha": self.base})
        self.assertTrue(wrapper["accepted"])
        return wrapper

    def build_artifact(self, sha):
        output = self.folder / ("artifact-" + sha)
        output.mkdir(exist_ok=True)
        inputs = runner.build_inputs(self.repo, sha)
        metadata = preview(self.folder, self.repo, sha, inputs, "transport-preview")
        shutil.copyfile(metadata.pop("path"), output / "preview.zip")
        metadata["kind"] = "flutter_web"
        metadata["source_tree"] = runner.snapshots.source_tree(self.repo, sha)
        (output / "metadata.json").write_text(json.dumps(metadata))
        return output

    def prepare(self):
        self.initialize()
        write(self.repo / "lib/main.dart", "void main() { print('approved runner snapshot'); }\n")
        self.source = commit(self.repo, "Candidate Dart correction")
        review = self.action(2, {"operation": "technical-review", "source_sha": self.source, "role": "ian"})
        self.assertTrue(review["accepted"])
        return self.action(3, {"operation": "prepare", "source_sha": self.source,
                               "delivery_id": "entrega-0042", "rc": 1}, self.build_artifact(self.source))

    def test_reopened_actions_preserve_zero_one_two_and_publish_exact_snapshot_once(self):
        prepared = self.prepare()
        self.assertTrue(prepared["accepted"])
        record = prepared["result"]
        self.assertEqual(record["count"], 0)
        request = {"candidate": record["candidate_id"], "manifest_hash": record["manifest_hash"]}
        one = self.action(4, {"operation": "approve", **request, "role": "samuel"})
        two = self.action(5, {"operation": "approve", **request, "role": "vinicius"})
        self.assertEqual((one["result"]["count"], two["result"]["count"]), (1, 2))
        self.assertEqual(two["result"]["state"], "autorizada")
        with closing(sqlite3.connect(self.coordinator.provider / "provider.sqlite")) as db:
            self.assertEqual(db.execute("SELECT count(*) FROM receipts").fetchone()[0], 0)
        write(self.repo / "lib/later.dart", "// unapproved later source\n")
        later = commit(self.repo, "Advance branch after approval")
        published = self.action(6, {"operation": "publish", **request})
        self.assertTrue(published["accepted"])
        self.assertEqual(published["result"]["state"], "concluida")
        self.assertNotEqual(self.source, later)
        for destination in published["result"]["destinations"].values():
            self.assertEqual(destination["receipt"]["source_sha"], self.source)
            self.assertFalse(destination["receipt"]["distribution_performed"])
        repeated = self.action(6, {"operation": "publish", **request})
        self.assertEqual(repeated, published)
        with closing(sqlite3.connect(self.coordinator.provider / "provider.sqlite")) as db:
            self.assertEqual(db.execute("SELECT count(*) FROM receipts").fetchone()[0], 3)
        with self.coordinator.store.connection() as db:
            identities = [json.loads(row[0]) for row in db.execute("SELECT value FROM settings WHERE key LIKE 'provider:%'")]
        self.assertEqual(identities, [str((self.coordinator.provider / "provider.sqlite").resolve())])
        events = self.coordinator.store.events()
        self.assertTrue(any(event["action"] == "github_operation" and event["payload"]["authenticated_operator"]["id"] == "github:1234" for event in events))

    def test_slack_checkpoint_failure_prevents_post_and_keeps_unknown_locally(self):
        wrapper = self.initialize()
        fake_slack = FakeSlack()
        original = slack_notify.send_notice
        def send(notice, outbox, checkpoint):
            return original(notice, outbox, api=fake_slack, checkpoint=checkpoint)
        self.api.deny_update = True
        with patch.dict(os.environ, {"SLACK_BOT_TOKEN": "xoxb-" + "t" * 30}), patch.object(slack_notify, "send_notice", side_effect=send):
            with self.assertRaises(StateUncertain):
                self.coordinator.notify(wrapper)
        self.assertEqual(fake_slack.posts, [])
        with closing(sqlite3.connect(self.coordinator.outbox)) as db:
            self.assertEqual(db.execute("SELECT state FROM notices").fetchone()[0], "unknown")

    def test_slack_unknown_checkpoint_is_remote_before_post_and_sent_rerun_does_not_duplicate(self):
        wrapper = self.initialize()
        fake_slack = FakeSlack()
        original = slack_notify.send_notice
        def api(method, data, token):
            if method == "chat.postMessage":
                loaded = self.remote.load(self.folder / "inspect-before-slack")
                with closing(sqlite3.connect(loaded.paths["outbox_db"])) as db:
                    self.assertEqual(db.execute("SELECT state FROM notices").fetchone()[0], "unknown")
            return fake_slack(method, data, token)
        def send(notice, outbox, checkpoint):
            return original(notice, outbox, api=api, checkpoint=checkpoint)
        with patch.dict(os.environ, {"SLACK_BOT_TOKEN": "xoxb-" + "t" * 30}), patch.object(slack_notify, "send_notice", side_effect=send):
            first = self.coordinator.notify(wrapper)
            self.assertEqual(first["state"], "sent")
            repeated_wrapper = self.action(1, {"operation": "initialize", "source_sha": self.base})
            repeated = self.coordinator.notify(repeated_wrapper)
        self.assertTrue(repeated["duplicate"])
        self.assertEqual(len(fake_slack.posts), 1)


if __name__ == "__main__":
    unittest.main()
