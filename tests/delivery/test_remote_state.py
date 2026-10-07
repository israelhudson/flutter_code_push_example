"""Offline Git Data endpoints; no test uses gh or mutates a real GitHub ref."""

import base64
from contextlib import closing
import copy
import hashlib
import json
from pathlib import Path
import sqlite3
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "tools/delivery"))
from lab_demo import fixture, preview
from lab_engine import LabStore, make_manifest
from remote_state import (Bundle, GitDataAPIError, RemoteState, StateConflict, StateError,
                          StateUncertain, create_empty_databases, export_bundle, import_bundle)
import remote_state


def blob_sha(content):
    return hashlib.sha1(b"blob " + str(len(content)).encode() + b"\0" + content).hexdigest()


class FakeGitData:
    """Models exact blobs, immutable trees/commits and fast-forward ref semantics."""
    def __init__(self):
        self.blobs, self.trees, self.commits = {}, {}, {}
        self.head = None
        self.calls = []
        self.before_update = None
        self.lose_reply = False
        self.ref_unavailable = False
        self.deny_update = False

    def contains(self, head, parent):
        while head is not None:
            if head == parent:
                return True
            parents = self.commits[head]["parents"]
            head = parents[0]["sha"] if parents else None
        return False

    def __call__(self, method, path, data=None):
        self.calls.append((method, path, copy.deepcopy(data)))
        base = "repos/israelhudson/flutter_code_push_example"
        assert path.startswith(base)
        endpoint = path[len(base):]
        if method == "GET" and endpoint == "/git/ref/heads/codex/delivery-state":
            if self.ref_unavailable:
                raise GitDataAPIError(503)
            if self.head is None:
                raise GitDataAPIError(404)
            return {"ref": "refs/heads/codex/delivery-state", "object": {"type": "commit", "sha": self.head}}
        if method == "POST" and endpoint == "/git/blobs":
            assert data["encoding"] == "base64"
            value = base64.b64decode(data["content"])
            sha = blob_sha(value)
            self.blobs[sha] = value
            return {"sha": sha}
        if method == "GET" and endpoint.startswith("/git/blobs/"):
            sha = endpoint.rsplit("/", 1)[1]
            return {"sha": sha, "encoding": "base64", "content": base64.b64encode(self.blobs[sha]).decode()}
        if method == "POST" and endpoint == "/git/trees":
            assert "base_tree" not in data, "Snapshot must not inherit application files"
            sha = hashlib.sha1(json.dumps(data, sort_keys=True).encode()).hexdigest()
            self.trees[sha] = [dict(entry, size=len(self.blobs[entry["sha"]])) for entry in data["tree"]]
            return {"sha": sha}
        if method == "GET" and endpoint.startswith("/git/trees/"):
            sha = endpoint.rsplit("/", 1)[1].split("?", 1)[0]
            return {"sha": sha, "tree": copy.deepcopy(self.trees[sha]), "truncated": False}
        if method == "POST" and endpoint == "/git/commits":
            sha = hashlib.sha1(json.dumps(data, sort_keys=True).encode()).hexdigest()
            self.commits[sha] = {"sha": sha, "tree": {"sha": data["tree"]},
                                 "parents": [{"sha": parent} for parent in data["parents"]]}
            return {"sha": sha}
        if method == "GET" and endpoint.startswith("/git/commits/"):
            return copy.deepcopy(self.commits[endpoint.rsplit("/", 1)[1]])
        if endpoint in ("/git/refs", "/git/refs/heads/codex/delivery-state"):
            if self.before_update:
                callback, self.before_update = self.before_update, None
                callback()
            if self.deny_update:
                raise GitDataAPIError(409)
            if method == "POST":
                assert data["ref"] == "refs/heads/codex/delivery-state"
                if self.head is not None:
                    raise GitDataAPIError(422)
            elif method == "PATCH":
                assert data["force"] is False
                if not self.contains(data["sha"], self.head):
                    raise GitDataAPIError(422)
            else:
                raise AssertionError("Unexpected mutation")
            self.head = data["sha"]
            if self.lose_reply:
                self.lose_reply = False
                raise TimeoutError("Lost reply after the ref was advanced")
            return {"object": {"sha": self.head}}
        raise AssertionError((method, path))


class RemoteStateTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix="remote-state-test-")
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.repo, self.base, self.fixed, self.inputs, self.targets, _ = fixture(self.root / "fixture")
        self.db = self.root / "session/state.sqlite"
        self.provider_db = self.root / "session/provider/provider.sqlite"
        self.outbox_db = self.root / "session/outbox.sqlite"
        self.store = LabStore(self.db)
        production = self.store.initialize(self.base, self.targets)
        self.store.technical_review(self.fixed)
        manifest = make_manifest(self.repo, self.fixed, production, self.targets,
                                 preview(self.root, self.repo, self.fixed, self.inputs, "candidate-preview"),
                                 self.inputs, "entrega-0042")
        self.candidate = self.store.prepare(manifest, "prepare-one")
        create_empty_databases(self.provider_db, self.outbox_db)
        self.api = FakeGitData()
        self.remote = RemoteState(api=self.api)
        self.checkpoint = self.root / "checkpoint.json"

    def bundle(self):
        return export_bundle(self.db, self.provider_db, self.outbox_db)

    def bootstrap(self, bundle=None):
        return self.remote.bootstrap(bundle or self.bundle(), "bootstrap", checkpoint=self.checkpoint)

    def test_round_trip_preserves_hash_approvals_all_journals_and_path_plan(self):
        self.store.approve(self.candidate["candidate_id"], "samuel", self.candidate["manifest_hash"])
        with closing(sqlite3.connect(self.outbox_db)) as db:
            db.execute("INSERT INTO notices VALUES ('event','hash','uuid','unknown',NULL,'now',NULL)")
            db.commit()
        result = self.bootstrap()
        loaded = self.remote.load(self.root / "different-runner/state",
                                  repository_map={str(self.repo.resolve()): "/tmp/fixed/repository"})
        restored = LabStore(loaded.paths["state_db"])
        candidate = restored.status(self.candidate["candidate_id"])
        self.assertEqual((candidate["count"], candidate["manifest_hash"]), (1, self.candidate["manifest_hash"]))
        self.assertEqual(candidate["manifest"]["repository_path"], str(self.repo.resolve()))
        self.assertEqual(loaded.path_plan["repositories"][str(self.repo.resolve())], "/tmp/fixed/repository")
        self.assertEqual(loaded.head_sha, result.commit_sha)
        old_preview = self.candidate["manifest"]["preview"]["path"]
        self.assertEqual(loaded.paths["previews"][old_preview].read_bytes(), Path(old_preview).read_bytes())
        with closing(sqlite3.connect(loaded.paths["outbox_db"])) as db:
            self.assertEqual(db.execute("SELECT state FROM notices").fetchone()[0], "unknown")
        all_paths = [entry["path"] for entry in self.api.trees[self.api.commits[result.commit_sha]["tree"]["sha"]]]
        self.assertFalse(any(path.startswith(("lib/", ".github/", "android/", "ios/")) for path in all_paths))

    def test_two_actions_advance_one_parent_without_force_and_preserve_zero_to_two(self):
        first = self.bootstrap()
        self.store.approve(self.candidate["candidate_id"], "samuel", self.candidate["manifest_hash"])
        second = self.remote.save(self.bundle(), first.commit_sha, "samuel", checkpoint=self.checkpoint)
        self.store.approve(self.candidate["candidate_id"], "vinicius", self.candidate["manifest_hash"])
        third = self.remote.save(self.bundle(), second.commit_sha, "vinicius", checkpoint=self.checkpoint)
        loaded = self.remote.load(self.root / "third-runner")
        self.assertEqual(LabStore(loaded.paths["state_db"]).status(self.candidate["candidate_id"])["count"], 2)
        self.assertEqual(self.api.commits[third.commit_sha]["parents"], [{"sha": second.commit_sha}])
        self.assertEqual(self.api.commits[first.commit_sha]["parents"], [])
        self.assertTrue(all(data["force"] is False for method, _, data in self.api.calls if method == "PATCH"))

    def test_concurrent_sibling_writer_is_conflict_never_rebased_or_reapplied(self):
        first = self.bootstrap()
        self.store.approve(self.candidate["candidate_id"], "samuel", self.candidate["manifest_hash"])
        waiting = self.bundle()
        winning_bundle = self.bundle()
        winner = []
        def concurrent():
            other = RemoteState(api=self.api)
            winner.append(other.save(winning_bundle, first.commit_sha, "winner", checkpoint=self.root / "winner.json"))
        self.api.before_update = concurrent
        with self.assertRaises(StateConflict):
            self.remote.save(waiting, first.commit_sha, "loser", checkpoint=self.checkpoint)
        self.assertEqual(self.api.head, winner[0].commit_sha)
        lost = json.loads(self.checkpoint.read_text())["proposed_head"]
        self.assertEqual(self.api.commits[lost]["parents"], [{"sha": first.commit_sha}])
        self.assertEqual(sum(method == "PATCH" for method, _, _ in self.api.calls), 2)

    def test_bootstrap_race_cannot_replace_another_initialized_ref(self):
        bundle = self.bundle()
        winner = []
        def concurrent():
            winner.append(RemoteState(api=self.api).bootstrap(bundle, "winner-bootstrap", checkpoint=self.root / "winner.json"))
        self.api.before_update = concurrent
        with self.assertRaises(StateConflict):
            self.remote.bootstrap(bundle, "loser-bootstrap", checkpoint=self.checkpoint)
        self.assertEqual(self.api.head, winner[0].commit_sha)

    def test_lost_ref_reply_is_reconciled_without_second_update(self):
        self.api.lose_reply = True
        result = self.bootstrap()
        self.assertEqual(result.commit_sha, self.api.head)
        self.assertEqual(json.loads(self.checkpoint.read_text())["status"], "committed")
        self.assertEqual(sum(method == "POST" and path.endswith("/git/refs") for method, path, _ in self.api.calls), 1)

    def test_unknown_confirmation_preserves_checkpoint_and_exact_proposal_for_retry(self):
        first = self.bootstrap()
        self.store.approve(self.candidate["candidate_id"], "samuel", self.candidate["manifest_hash"])
        bundle = self.bundle()
        def uncertain_update():
            self.api.ref_unavailable = True
        self.api.before_update = uncertain_update
        with self.assertRaises(StateUncertain):
            self.remote.save(bundle, first.commit_sha, "approve", checkpoint=self.checkpoint)
        checkpoint = json.loads(self.checkpoint.read_text())
        self.assertEqual(checkpoint["status"], "prepared")
        self.assertEqual(checkpoint["proposed_head"], self.api.head)
        self.api.ref_unavailable = False
        confirmed = self.remote.reconcile_commit(first.commit_sha, checkpoint["proposed_head"])
        self.assertEqual(confirmed.status, "already_committed")
        calls = len(self.api.calls)
        result = self.remote.save(bundle, first.commit_sha, "approve", checkpoint=self.checkpoint)
        self.assertEqual(result.status, "already_committed")
        self.assertFalse(any(method in ("POST", "PATCH") for method, _, _ in self.api.calls[calls:]))

    def test_denied_update_can_only_retry_same_proposal_with_same_payload(self):
        first = self.bootstrap()
        self.api.deny_update = True
        self.store.approve(self.candidate["candidate_id"], "samuel", self.candidate["manifest_hash"])
        bundle = self.bundle()
        with self.assertRaises(StateUncertain):
            self.remote.save(bundle, first.commit_sha, "approval", checkpoint=self.checkpoint)
        old = json.loads(self.checkpoint.read_text())["proposed_head"]
        self.assertEqual(self.remote.reconcile_commit(first.commit_sha, old).status, "not_committed")
        with self.assertRaises(StateUncertain):
            self.remote.save(bundle, first.commit_sha, "different-operation", checkpoint=self.checkpoint)
        self.api.deny_update = False
        result = self.remote.save(bundle, first.commit_sha, "approval", checkpoint=self.checkpoint)
        self.assertEqual(result.commit_sha, old)

    def test_confirmation_after_another_writer_advances_still_identifies_our_commit(self):
        first = self.bootstrap()
        self.store.approve(self.candidate["candidate_id"], "samuel", self.candidate["manifest_hash"])
        second = self.remote.save(self.bundle(), first.commit_sha, "samuel", checkpoint=self.checkpoint)
        self.store.approve(self.candidate["candidate_id"], "vinicius", self.candidate["manifest_hash"])
        third = self.remote.save(self.bundle(), second.commit_sha, "vinicius", checkpoint=self.checkpoint)
        result = self.remote.reconcile_commit(first.commit_sha, second.commit_sha)
        self.assertEqual((result.commit_sha, result.current_head, result.status),
                         (second.commit_sha, third.commit_sha, "already_committed"))

    def test_checksums_and_truncated_tree_or_extra_files_block_before_import(self):
        result = self.bootstrap()
        tree = self.api.trees[self.api.commits[result.commit_sha]["tree"]["sha"]]
        blob = next(entry["sha"] for entry in tree if entry["path"] == "state.sqlite")
        self.api.blobs[blob] = b"corrupted state bytes"
        with self.assertRaises(StateError):
            self.remote.load(self.root / "invalid-import")
        self.assertFalse((self.root / "invalid-import").exists())
        bundle = self.bundle()
        changed = dict(bundle.files, **{".github/evil.yml": b"unexpected"})
        with self.assertRaises(StateError):
            import_bundle(Bundle(changed, bundle.metadata), self.root / "extra-files", head_sha=result.commit_sha)

    def test_empty_directory_allowed_but_existing_state_is_not_overwritten(self):
        first = self.bootstrap()
        destination = self.root / "empty"
        destination.mkdir()
        self.remote.load(destination)
        before = (destination / "state.sqlite").read_bytes()
        with self.assertRaisesRegex(StateError, "novo ou vazio"):
            self.remote.load(destination)
        self.assertEqual((destination / "state.sqlite").read_bytes(), before)
        self.assertEqual(first.commit_sha, self.api.head)

    def test_absent_provider_is_not_silently_recreated_or_treated_as_negative(self):
        self.provider_db.unlink()
        with self.assertRaisesRegex(StateError, "ausente"):
            self.bundle()
        self.assertFalse(self.provider_db.exists())

    def test_sqlite_wal_is_exported_by_backup_and_remote_journal_remains_consistent(self):
        with closing(sqlite3.connect(self.provider_db)) as provider:
            provider.execute("PRAGMA journal_mode=WAL")
            provider.execute("INSERT INTO receipts VALUES ('operation','android','1.1.0+2','{}')")
            provider.commit()
            self.bootstrap()
            loaded = self.remote.load(self.root / "wal-import")
            with closing(sqlite3.connect(loaded.paths["provider_db"])) as restored:
                self.assertEqual(restored.execute("SELECT key FROM receipts").fetchone()[0], "operation")

    def test_secret_values_are_rejected_and_never_written_to_git(self):
        with closing(sqlite3.connect(self.db)) as db:
            db.execute("INSERT INTO settings VALUES ('accidental_credentials', ?)",
                       (json.dumps({"SLACK_BOT_TOKEN": "xoxb-" + "a" * 30}),))
            db.commit()
        with self.assertRaisesRegex(StateError, "Credencial|credencial"):
            self.bundle()
        self.assertEqual(self.api.calls, [])

    def test_opaque_credential_setting_or_unexpected_secret_column_is_rejected(self):
        with closing(sqlite3.connect(self.db)) as db:
            db.execute("INSERT INTO settings VALUES ('access_token', ?)", (json.dumps("opaque-value"),))
            db.commit()
        with self.assertRaisesRegex(StateError, "credencial"):
            self.bundle()
        with closing(sqlite3.connect(self.db)) as db:
            db.execute("DELETE FROM settings WHERE key='access_token'")
            db.commit()
        with closing(sqlite3.connect(self.outbox_db)) as db:
            db.execute("ALTER TABLE notices ADD COLUMN password TEXT")
            db.commit()
        with self.assertRaisesRegex(StateError, "Colunas"):
            self.bundle()
        self.assertEqual(self.api.calls, [])

    def test_restriction_to_personal_repository_and_dedicated_ref(self):
        with self.assertRaises(StateError):
            RemoteState(api=self.api, repo="amulets/mobile")
        with self.assertRaises(StateError):
            RemoteState(api=self.api, ref="main")

    def test_checkpoint_exists_before_ref_mutation(self):
        def inspect():
            checkpoint = json.loads(self.checkpoint.read_text())
            self.assertEqual(checkpoint["status"], "prepared")
            self.assertIn(checkpoint["proposed_head"], self.api.commits)
        self.api.before_update = inspect
        self.bootstrap()


if __name__ == "__main__":
    unittest.main()
