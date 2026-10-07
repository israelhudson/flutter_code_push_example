"""Temporary Git repositories exercise snapshots without touching project refs."""

import copy
from datetime import datetime, timedelta, timezone
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
import zipfile

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "tools/delivery"))
from snapshots import (build_fingerprint, changelog, isolated_checkout,
                       pre_analyze, require_ancestor, resolve_commit, source_tree,
                       validate_preview)


INPUTS = {"flutter_version": "3.44.1", "flutter_revision": "f" * 40,
          "flavor": None, "entrypoint": "lib/main.dart", "renderer": "canvaskit",
          "command": ["flutter", "build", "web", "--release"], "dart_defines": {}}

PUBSPEC = """name: snapshot_fixture
version: 1.1.0+2
dependencies:
  flutter:
    sdk: flutter
flutter:
  uses-material-design: true
  assets:
    - gfx/icon.png
  fonts:
    - family: Fixture
      fonts:
        - asset: typography/body.ttf
"""


class Repository:
    def __init__(self, folder):
        self.path = Path(folder)
        self.path.mkdir(parents=True)
        self.git("init", "-b", "main")
        self.git("config", "user.name", "Synthetic Israel")
        self.git("config", "user.email", "fixture@example.invalid")
        self.write("lib/main.dart", "void main() {}\n")
        self.write("lib/service.dart", "// original B\n")
        self.write("pubspec.yaml", PUBSPEC)
        self.write("pubspec.lock", "packages: {}\n")
        self.write("gfx/icon.png", "base asset")
        self.write("typography/body.ttf", "base font")
        self.write("android/build.gradle", "// base Android\n")
        self.write("ios/Runner/Info.plist", "base iOS\n")
        self.write(".gitignore", "build/\n")
        self.base = self.commit("B original complete snapshot")

    def git(self, *args):
        return subprocess.check_output(["git", "-C", str(self.path), *args],
                                       stderr=subprocess.DEVNULL).decode().strip()

    def write(self, path, text):
        file = self.path / path
        file.parent.mkdir(parents=True, exist_ok=True)
        file.write_text(text)

    def commit(self, subject):
        self.git("add", ".")
        self.git("commit", "-m", subject)
        return self.git("rev-parse", "HEAD")

    def change(self, path, text, subject=None):
        self.write(path, text)
        return self.commit(subject or "change " + path)

    def target(self, platform="android", sha=None, **overrides):
        target = {"platform": platform, "app_id": "isolated-fixture-app",
                  "environment": "laboratory", "release_version": "1.1.0+2",
                  "release_sha": sha or self.base,
                  "flutter_version": INPUTS["flutter_version"],
                  "flutter_revision": INPUTS["flutter_revision"],
                  "flavor": None, "entrypoint": "lib/main.dart"}
        target.update(overrides)
        target["base_evidence"] = {"kind": "laboratory", **{
            key: target[key] for key in ("platform", "app_id", "environment",
                                        "release_version", "release_sha")}}
        return target

    def preview(self, sha, inputs=None, kind="fixture_web"):
        inputs = copy.deepcopy(INPUTS if inputs is None else inputs)
        path = self.path.parent / (self.path.name + "-preview.zip")
        with zipfile.ZipFile(path, "w") as archive:
            archive.writestr("index.html", "<h1>Explicit synthetic web fixture</h1>")
        return {"kind": kind, "path": str(path), "source_sha": sha,
                "fingerprint": build_fingerprint(self.path, sha, inputs),
                "sha256": hashlib.sha256(path.read_bytes()).hexdigest(), "inputs": inputs,
                "expires_at": (datetime.now(timezone.utc) + timedelta(days=1)).isoformat()}


class RepositoryTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix="snapshot-test-")
        self.addCleanup(self.temporary.cleanup)
        self.repo = Repository(Path(self.temporary.name) / "repository")


class SnapshotTests(RepositoryTests):
    def test_candidate_requires_production_ancestor_and_exact_shas(self):
        repo = self.repo
        child = repo.change("lib/feature_c.dart", "// main feature C\n")
        self.assertIsNone(require_ancestor(repo.path, repo.base, child))
        self.assertIsNone(require_ancestor(repo.path, child, child))
        with self.assertRaisesRegex(ValueError, "antigo, divergente ou órfão"):
            require_ancestor(repo.path, child, repo.base)
        repo.git("switch", "-c", "release/hotfix", repo.base)
        repair = repo.change("lib/service.dart", "// independent hotfix\n")
        self.assertIsNone(require_ancestor(repo.path, repo.base, repair))
        with self.assertRaisesRegex(ValueError, "divergente"):
            require_ancestor(repo.path, child, repair)
        with self.assertRaisesRegex(ValueError, "SHA completo"):
            require_ancestor(repo.path, "main", repair)
        with self.assertRaisesRegex(ValueError, "SHA completo"):
            require_ancestor(repo.path, repo.base, "release/hotfix")

    def test_orphan_history_is_rejected_even_with_similar_versioned_files(self):
        repo = self.repo
        repo.git("checkout", "--orphan", "orphan-history")
        orphan = repo.change("lib/service.dart", "// orphan fix\n")
        with self.assertRaisesRegex(ValueError, "órfão"):
            require_ancestor(repo.path, repo.base, orphan)

    def test_release_correction_does_not_import_main_features(self):
        repo = self.repo
        repo.git("tag", "-a", "entrega-0042-rc.1", repo.base, "-m", "RC1 fixed B")
        repo.change("lib/feature_c.dart", "// feature C\n", "C new feature")
        repo.change("lib/feature_d.dart", "// feature D\n", "D another feature")
        f = repo.change("lib/service.dart", "// corrected service\n", "F independent repair")
        main_head = resolve_commit(repo.path, "main")
        repo.git("switch", "-c", "release/entrega-0042", repo.base)
        repo.git("cherry-pick", f)
        fixed = resolve_commit(repo.path, "HEAD")
        repo.git("tag", "-a", "entrega-0042-rc.2", fixed, "-m", "RC2 fixed F prime")
        self.assertNotEqual(f, fixed)
        self.assertEqual(resolve_commit(repo.path, "entrega-0042-rc.1"), repo.base)
        self.assertEqual(resolve_commit(repo.path, "entrega-0042-rc.2"), fixed)
        self.assertEqual(resolve_commit(repo.path, "main"), main_head)
        self.assertEqual(repo.git("diff", "--name-only", repo.base, fixed), "lib/service.dart")
        changes = changelog(repo.path, repo.base, fixed)
        self.assertEqual(changes, [{"sha": fixed, "subject": "F independent repair"}])
        tree = source_tree(repo.path, fixed)
        refs = repo.git("show-ref")
        with isolated_checkout(repo.path, fixed, tree) as checkout:
            self.assertEqual(resolve_commit(checkout, "HEAD"), fixed)
            self.assertEqual((checkout / "lib/service.dart").read_text(), "// corrected service\n")
            self.assertFalse((checkout / "lib/feature_c.dart").exists())
            self.assertFalse((checkout / "lib/feature_d.dart").exists())
            self.assertEqual((checkout / "gfx/icon.png").read_text(), "base asset")
        self.assertFalse(checkout.exists())
        self.assertEqual(repo.git("show-ref"), refs)

    def test_snapshot_is_fixed_even_when_original_checkout_is_dirty(self):
        repo = self.repo
        repo.change("lib/feature_c.dart", "// newer main feature\n")
        repo.write("lib/main.dart", "// uncommitted local draft\n")
        repo.write("local-secret.txt", "local fixture never included")
        before = repo.git("status", "--porcelain")
        refs = repo.git("show-ref")
        with isolated_checkout(repo.path, repo.base, source_tree(repo.path, repo.base)) as checkout:
            self.assertEqual((checkout / "lib/main.dart").read_text(), "void main() {}\n")
            self.assertFalse((checkout / "lib/feature_c.dart").exists())
            self.assertFalse((checkout / "local-secret.txt").exists())
            (checkout / "build").mkdir()
            (checkout / "build/fixture.json").write_text("ignored compiler output")
        self.assertEqual(repo.git("status", "--porcelain"), before)
        self.assertEqual(repo.git("show-ref"), refs)

    def test_wrong_tree_or_mutating_checkout_blocks_and_cleans_up(self):
        repo = self.repo
        with self.assertRaisesRegex(ValueError, "Árvore aprovada"):
            with isolated_checkout(repo.path, repo.base, "0" * 40):
                self.fail("Wrong tree should never yield a checkout")
        with self.assertRaisesRegex(ValueError, "alterações"):
            with isolated_checkout(repo.path, repo.base, source_tree(repo.path, repo.base)) as checkout:
                (checkout / "lib/main.dart").write_text("unexpected mutation")
        self.assertFalse(checkout.exists())
        self.assertEqual(resolve_commit(repo.path, "HEAD"), repo.base)

    def test_returning_to_a_branch_or_new_commit_blocks_even_if_source_files_match(self):
        repo = self.repo
        with self.assertRaisesRegex(ValueError, "detached HEAD"):
            with isolated_checkout(repo.path, repo.base, source_tree(repo.path, repo.base)) as checkout:
                subprocess.run(["git", "-C", str(checkout), "switch", "-c", "mutable"],
                               check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        self.assertFalse(checkout.exists())
        with self.assertRaisesRegex(ValueError, "snapshot aprovado"):
            with isolated_checkout(repo.path, repo.base, source_tree(repo.path, repo.base)) as checkout:
                for key, value in (("user.name", "Fixture"), ("user.email", "fixture@example.invalid")):
                    subprocess.run(["git", "-C", str(checkout), "config", key, value], check=True)
                subprocess.run(["git", "-C", str(checkout), "commit", "--allow-empty", "-m", "another SHA"],
                               check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        self.assertFalse(checkout.exists())

    def test_exception_in_build_still_removes_clone(self):
        repo = self.repo
        with self.assertRaises(RuntimeError):
            with isolated_checkout(repo.path, repo.base, source_tree(repo.path, repo.base)) as checkout:
                raise RuntimeError("synthetic build failed")
        self.assertFalse(checkout.exists())

    def test_tracked_symlink_requires_audited_strategy(self):
        repo = self.repo
        (repo.path / "lib/link.dart").symlink_to("/outside/private/file")
        sha = repo.commit("unsupported external link")
        with self.assertRaisesRegex(ValueError, "symlinks"):
            with isolated_checkout(repo.path, sha, source_tree(repo.path, sha)):
                self.fail("External links must not reach a build")

    def test_latest_and_mutable_release_base_are_rejected(self):
        repo = self.repo
        with self.assertRaises(ValueError):
            resolve_commit(repo.path, "latest")
        with self.assertRaises(ValueError):
            source_tree(repo.path, "main")
        target = repo.target(release_sha="main")
        result = pre_analyze(repo.path, repo.base, {"android": target}, INPUTS)
        self.assertEqual(result["android"]["status"], "pendente")


class PreAnalysisTests(RepositoryTests):
    def analyze(self, sha, targets=None, inputs=None):
        targets = targets or {"android": self.repo.target(), "ios": self.repo.target("ios"), "web": {}}
        return pre_analyze(self.repo.path, sha, targets, INPUTS if inputs is None else inputs)

    def test_dart_prediction_is_distinct_from_web_and_native_validation(self):
        sha = self.repo.change("lib/main.dart", "void main() { print('fix'); }\n")
        result = self.analyze(sha)
        self.assertEqual(result["android"]["status"], "patch_previsto")
        self.assertEqual(result["ios"]["status"], "patch_previsto")
        self.assertEqual(result["web"]["status"], "web")
        self.assertIn("Shorebird obrigatória", result["android"]["reasons"][0])

    def test_each_platform_uses_its_own_release_base_not_last_rc(self):
        native = self.repo.change("android/build.gradle", "// accumulated native change\n")
        later = self.repo.change("lib/main.dart", "void main() { print('RC only Dart'); }\n")
        targets = {"android": self.repo.target(), "ios": self.repo.target("ios", sha=native)}
        result = self.analyze(later, targets)
        self.assertEqual(result["android"]["status"], "loja_necessaria")
        self.assertIn("android/build.gradle", result["android"]["changed_paths"])
        self.assertEqual(result["ios"]["status"], "patch_previsto")
        self.assertEqual(result["ios"]["changed_paths"], ["lib/main.dart"])

    def test_packaged_asset_and_resolution_variant_require_store(self):
        for path in ("gfx/icon.png", "gfx/2.0x/icon.png", "typography/body.ttf"):
            with self.subTest(path=path):
                sha = self.repo.change(path, "different packaged bytes " + path)
                result = self.analyze(sha)
                self.assertEqual(result["android"]["status"], "loja_necessaria")
                self.assertEqual(result["ios"]["status"], "loja_necessaria")

    def test_pubspec_asset_declarations_require_store(self):
        sha = self.repo.change("pubspec.yaml", PUBSPEC.replace("gfx/icon.png", "other/icon.png"))
        self.assertEqual(self.analyze(sha)["android"]["status"], "loja_necessaria")

    def test_dependency_manifest_lock_and_unknown_files_fail_closed(self):
        for path, content in (("pubspec.lock", "packages: { unknown_plugin: true }\n"),
                              ("pubspec.yaml", PUBSPEC.replace("dependencies:", "dependencies:\n  new_package: ^1.0.0")),
                              ("delivery/unknown-config.json", "{}")):
            with self.subTest(path=path):
                self.repo.git("reset", "--hard", self.repo.base)
                sha = self.repo.change(path, content)
                self.assertEqual(self.analyze(sha)["android"]["status"], "pendente")

    def test_toolchain_entrypoint_or_flavor_change_requires_store(self):
        for key, value in (("flutter_version", "3.45.0"), ("flutter_revision", "a" * 40),
                           ("flavor", "different"), ("entrypoint", "lib/other.dart")):
            with self.subTest(field=key):
                changed = {**INPUTS, key: value}
                result = self.analyze(self.repo.base, inputs=changed)
                self.assertEqual(result["android"]["status"], "loja_necessaria")

    def test_missing_or_mismatched_base_evidence_blocks_prediction(self):
        for evidence in (None, "laboratory", {"kind": "laboratory"},
                         {"kind": "unverified_release"}):
            with self.subTest(evidence=evidence):
                target = self.repo.target()
                target["base_evidence"] = evidence
                self.assertEqual(self.analyze(self.repo.base, {"android": target})["android"]["status"], "pendente")
        target = self.repo.target()
        target["base_evidence"]["release_sha"] = "a" * 40
        self.assertEqual(self.analyze(self.repo.base, {"android": target})["android"]["status"], "pendente")

    def test_verified_release_needs_provider_identifier(self):
        target = self.repo.target()
        target["base_evidence"]["kind"] = "verified_release"
        self.assertEqual(self.analyze(self.repo.base, {"android": target})["android"]["status"], "pendente")
        target["base_evidence"]["provider_record_id"] = "declared-provider-release-123"
        self.assertEqual(self.analyze(self.repo.base, {"android": target})["android"]["status"], "patch_previsto")

    def test_missing_candidate_input_is_pending_not_assumed_from_base(self):
        inputs = copy.deepcopy(INPUTS)
        del inputs["entrypoint"]
        self.assertEqual(self.analyze(self.repo.base, inputs=inputs)["android"]["status"], "pendente")

    def test_platform_inputs_are_separate(self):
        inputs = {"targets": {"android": dict(INPUTS), "ios": {**INPUTS, "flutter_version": "3.45.0"}}}
        result = self.analyze(self.repo.base, inputs=inputs)
        self.assertEqual(result["android"]["status"], "patch_previsto")
        self.assertEqual(result["ios"]["status"], "loja_necessaria")

    def test_docs_and_tools_do_not_force_store_but_do_affect_preview_identity(self):
        base_fp = build_fingerprint(self.repo.path, self.repo.base, INPUTS)
        docs = self.repo.change("docs/notes.md", "documented only")
        self.assertEqual(build_fingerprint(self.repo.path, docs, INPUTS), base_fp)
        tooling = self.repo.change("tools/build-helper.py", "# changed build tooling")
        result = self.analyze(tooling)
        self.assertEqual(result["android"]["status"], "patch_previsto")
        self.assertNotEqual(build_fingerprint(self.repo.path, tooling, INPUTS), base_fp)

    def test_complex_yaml_is_pending_instead_of_guessed(self):
        sha = self.repo.change("pubspec.yaml", PUBSPEC.replace("assets:\n    - gfx/icon.png", "assets: [gfx/icon.png]"))
        # A changed assets declaration is a known store issue, even while parser
        # support is missing; an unchanged unknown declaration is pending.
        result = self.analyze(sha)
        self.assertEqual(result["android"]["status"], "loja_necessaria")
        target = self.repo.target(sha=sha)
        result = self.analyze(sha, {"android": target})
        self.assertEqual(result["android"]["status"], "pendente")


class PreviewTests(RepositoryTests):
    def test_equal_tree_with_different_commit_and_docs_can_reuse(self):
        preview = self.repo.preview(self.repo.base)
        self.repo.git("commit", "--allow-empty", "-m", "same code different history")
        other = resolve_commit(self.repo.path, "HEAD")
        self.assertNotEqual(other, self.repo.base)
        validate_preview(self.repo.path, other, preview, INPUTS)
        docs = self.repo.change("referencias/note.md", "knowledge only")
        validate_preview(self.repo.path, docs, preview, INPUTS)

    def test_changed_code_or_build_inputs_refuses_reuse(self):
        preview = self.repo.preview(self.repo.base)
        changed = self.repo.change("lib/main.dart", "// new code\n")
        with self.assertRaisesRegex(ValueError, "fingerprint"):
            validate_preview(self.repo.path, changed, preview, INPUTS)
        with self.assertRaisesRegex(ValueError, "Inputs"):
            validate_preview(self.repo.path, self.repo.base, preview, {**INPUTS, "renderer": "different"})

    def test_cannot_substitute_origin_sha_even_with_claimed_candidate_fingerprint(self):
        changed = self.repo.change("lib/main.dart", "// new approved code\n")
        preview = self.repo.preview(changed)
        preview["source_sha"] = self.repo.base
        with self.assertRaisesRegex(ValueError, "origem"):
            validate_preview(self.repo.path, changed, preview, INPUTS)

    def test_hash_expiration_and_incomplete_metadata_block(self):
        preview = self.repo.preview(self.repo.base)
        invalids = [{**preview, "sha256": "0" * 64},
                    {**preview, "expires_at": "2000-01-01T00:00:00Z"},
                    {**preview, "expires_at": "2999-01-01T00:00:00"},
                    {**preview, "source_sha": "main"},
                    {key: value for key, value in preview.items() if key != "kind"}]
        for invalid in invalids:
            with self.subTest(invalid=invalid.keys()):
                with self.assertRaises(ValueError):
                    validate_preview(self.repo.path, self.repo.base, invalid, INPUTS)

    def test_fixture_format_is_explicit_and_flutter_zip_is_checked(self):
        preview = self.repo.preview(self.repo.base, kind="flutter_web")
        validate_preview(self.repo.path, self.repo.base, preview, INPUTS)
        path = Path(preview["path"])
        path.write_bytes(b"not a Flutter build ZIP")
        preview["sha256"] = hashlib.sha256(path.read_bytes()).hexdigest()
        with self.assertRaisesRegex(ValueError, "ZIP web"):
            validate_preview(self.repo.path, self.repo.base, preview, INPUTS)
        preview["kind"] = "fixture_web"
        validate_preview(self.repo.path, self.repo.base, preview, INPUTS)

    def test_flutter_zip_rejects_path_traversal(self):
        preview = self.repo.preview(self.repo.base, kind="flutter_web")
        path = Path(preview["path"])
        with zipfile.ZipFile(path, "w") as archive:
            archive.writestr("index.html", "fixture")
            archive.writestr("../unsafe", "fixture")
        preview["sha256"] = hashlib.sha256(path.read_bytes()).hexdigest()
        with self.assertRaisesRegex(ValueError, "inseguros"):
            validate_preview(self.repo.path, self.repo.base, preview, INPUTS)

    def test_build_fingerprint_is_conservative_and_json_is_finite(self):
        fp = build_fingerprint(self.repo.path, self.repo.base, INPUTS)
        self.assertEqual(fp, build_fingerprint(self.repo.path, self.repo.base, dict(reversed(list(INPUTS.items())))))
        for path in ("README.md", "AGENTS.md", "delivery/candidates/example.json"):
            changed = self.repo.change(path, "excluded exact documentation path")
            self.assertEqual(build_fingerprint(self.repo.path, changed, INPUTS), fp)
        changed = self.repo.change("delivery/build-inputs.json", json.dumps(INPUTS))
        self.assertNotEqual(build_fingerprint(self.repo.path, changed, INPUTS), fp)
        with self.assertRaises(ValueError):
            build_fingerprint(self.repo.path, changed, {"nan": float("nan")})


if __name__ == "__main__":
    unittest.main()
