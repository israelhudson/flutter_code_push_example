"""Mobile build adapter tests use compiler fixtures, never Flutter or upload."""
from contextlib import ExitStack
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch
import zipfile

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / 'deploy'))
import mobile_build as mobile

SHA, TREE, REVISION, TOOLING_SHA = 'a' * 40, 'b' * 40, 'c' * 40, 'e' * 40
INPUTS = {'flutter_version': '3.44.1', 'flutter_revision': REVISION, 'dart_defines': {}}


class BuildFixture:
    def __init__(self, root, platform):
        self.repo = Path(root) / 'repository'
        self.repo.mkdir()
        self.output = Path(root) / 'artifact'
        self.platform = platform
        self.head = SHA
        self.dirty = False
        self.actual = {'frameworkVersion': INPUTS['flutter_version'], 'frameworkRevision': REVISION}
        self.inputs = INPUTS.copy()
        self.commands = []

    def git(self, repo, *args):
        if repo == mobile.TOOLING_REPOSITORY:
            return TOOLING_SHA
        if args[:2] == ('rev-parse', 'HEAD'):
            return self.head
        if args[0] == 'rev-parse':
            return TREE if args[1].endswith('^{tree}') else SHA
        if args[0] == 'status':
            return ' M pubspec.lock' if self.dirty else ''
        if args[0] == 'show':
            self.assert_show = args[1]
            return json.dumps(self.inputs)
        raise AssertionError(args)

    def run(self, args, cwd, check):
        self.commands.append(args)
        if args[:2] != ['flutter', 'build']:
            return
        product = mobile._product(self.repo, self.platform)
        if self.platform == 'android':
            product.parent.mkdir(parents=True)
            with zipfile.ZipFile(product, 'w') as archive:
                archive.writestr('BundleConfig.pb', b'fixture')
                archive.writestr('base/manifest/AndroidManifest.xml', b'fixture')
        else:
            app = product / 'Products/Applications/Runner.app'
            app.mkdir(parents=True)
            (product / 'Info.plist').write_bytes(b'fixture')
            (app / 'Info.plist').write_bytes(b'fixture')
            (app / 'Runner').write_bytes(b'fixture-native-binary')

    def mocks(self):
        return [patch.object(mobile, 'git', side_effect=self.git),
                patch.object(mobile.subprocess, 'check_output', return_value=json.dumps(self.actual).encode()),
                patch.object(mobile.subprocess, 'run', side_effect=self.run),
                patch.object(mobile.host_platform, 'system', return_value='Darwin' if self.platform == 'ios' else 'Linux')]

    def build(self):
        with ExitStack() as stack:
            for mock in self.mocks():
                stack.enter_context(mock)
            return mobile.build(self.repo, SHA, self.platform, self.output, tooling_sha=TOOLING_SHA)


class MobileBuildTests(unittest.TestCase):
    def test_android_packages_exact_snapshot_and_records_no_distribution_or_patch(self):
        with tempfile.TemporaryDirectory() as folder:
            fixture = BuildFixture(folder, 'android')
            metadata = fixture.build()
            self.assertEqual(metadata['source_sha'], SHA)
            self.assertEqual(metadata['source_tree'], TREE)
            self.assertEqual(metadata['tooling_sha'], TOOLING_SHA)
            self.assertEqual(metadata['artifact_kind'], 'android-aab-laboratory')
            self.assertFalse(metadata['distribution_performed'])
            self.assertFalse(metadata['store_upload_performed'])
            self.assertFalse(metadata['shorebird_artifact'])
            self.assertFalse(metadata['patch_compatibility_validated'])
            self.assertEqual(metadata['signing'], 'project-configuration-not-verified')
            self.assertEqual(metadata['sha256'], hashlib.sha256((fixture.output / 'mobile.zip').read_bytes()).hexdigest())
            self.assertEqual(fixture.assert_show, SHA + ':delivery/build-inputs.json')
            self.assertEqual(fixture.commands,
                             [['flutter', 'pub', 'get', '--enforce-lockfile'],
                              ['flutter', 'build', 'appbundle', '--release']])
            self.assertEqual(sorted(p.name for p in fixture.output.iterdir()), ['metadata.json', 'mobile.zip'])

    def test_ios_without_codesign_packages_xcarchive_and_does_not_claim_ipa(self):
        with tempfile.TemporaryDirectory() as folder:
            fixture = BuildFixture(folder, 'ios')
            metadata = fixture.build()
            self.assertEqual(metadata['artifact_kind'], 'ios-xcarchive-unsigned')
            self.assertEqual(metadata['signing'], 'unsigned')
            self.assertIn('--no-codesign', fixture.commands[-1])
            with zipfile.ZipFile(fixture.output / 'mobile.zip') as archive:
                self.assertIn('Runner.xcarchive/Products/Applications/Runner.app/Runner', archive.namelist())
                self.assertFalse(any(name.endswith('.ipa') for name in archive.namelist()))

    def test_mutable_ref_and_wrong_checkout_never_start_compiler(self):
        with tempfile.TemporaryDirectory() as folder:
            fixture = BuildFixture(folder, 'android')
            with patch.object(mobile, 'git', side_effect=fixture.git), patch.object(mobile.subprocess, 'run') as compiler:
                with self.assertRaisesRegex(ValueError, 'source_sha'):
                    mobile.build(fixture.repo, 'main', 'android', fixture.output)
                fixture.head = 'd' * 40
                with self.assertRaisesRegex(ValueError, 'snapshot'):
                    mobile.build(fixture.repo, SHA, 'android', fixture.output)
                compiler.assert_not_called()

    def test_wrong_sdk_version_or_revision_blocks_build(self):
        for field, value in [('frameworkVersion', '3.0.0'), ('frameworkRevision', 'd' * 40)]:
            with self.subTest(field=field), tempfile.TemporaryDirectory() as folder:
                fixture = BuildFixture(folder, 'android')
                fixture.actual[field] = value
                with self.assertRaisesRegex(ValueError, 'SDK instalado'):
                    fixture.build()
                self.assertEqual(fixture.commands, [])

    def test_tools_checkout_must_match_the_caller_commit(self):
        with tempfile.TemporaryDirectory() as folder:
            fixture = BuildFixture(folder, 'android')
            with patch.object(mobile, 'git', side_effect=fixture.git), patch.object(mobile.subprocess, 'run') as compiler:
                with self.assertRaisesRegex(ValueError, 'commit do caller'):
                    mobile.build(fixture.repo, SHA, 'android', fixture.output, tooling_sha='d' * 40)
                compiler.assert_not_called()

    def test_ios_linux_runner_is_rejected(self):
        with tempfile.TemporaryDirectory() as folder:
            fixture = BuildFixture(folder, 'ios')
            with patch.object(mobile, 'git', side_effect=fixture.git), patch.object(mobile.host_platform, 'system', return_value='Linux'), patch.object(mobile.subprocess, 'run') as compiler:
                with self.assertRaisesRegex(ValueError, 'macOS'):
                    mobile.build(fixture.repo, SHA, 'ios', fixture.output)
                compiler.assert_not_called()

    def test_build_cannot_package_artifact_left_by_prior_attempt(self):
        with tempfile.TemporaryDirectory() as folder:
            fixture = BuildFixture(folder, 'android')
            product = mobile._product(fixture.repo, 'android')
            product.parent.mkdir(parents=True)
            product.write_bytes(b'stale')
            with self.assertRaisesRegex(ValueError, 'Saída existente'):
                fixture.build()
            self.assertEqual(fixture.commands, [])

    def test_compiler_error_produces_no_metadata(self):
        with tempfile.TemporaryDirectory() as folder:
            fixture = BuildFixture(folder, 'android')
            with ExitStack() as stack:
                for mock in fixture.mocks():
                    stack.enter_context(mock)
                stack.enter_context(patch.object(mobile.subprocess, 'run', side_effect=subprocess.CalledProcessError(1, ['flutter', 'build'])))
                with self.assertRaises(subprocess.CalledProcessError):
                    mobile.build(fixture.repo, SHA, 'android', fixture.output)
            self.assertFalse((fixture.output / 'metadata.json').exists())

    def test_tracked_change_during_build_invalidates_result(self):
        with tempfile.TemporaryDirectory() as folder:
            fixture = BuildFixture(folder, 'android')
            def change(args, cwd, check):
                fixture.run(args, cwd, check)
                if args[:2] == ['flutter', 'build']:
                    fixture.dirty = True
            with ExitStack() as stack:
                for mock in fixture.mocks():
                    stack.enter_context(mock)
                stack.enter_context(patch.object(mobile.subprocess, 'run', side_effect=change))
                with self.assertRaisesRegex(ValueError, 'rastreados divergentes'):
                    mobile.build(fixture.repo, SHA, 'android', fixture.output)
            self.assertFalse((fixture.output / 'metadata.json').exists())

    def test_build_flags_are_fixed_and_defines_are_arguments_without_shell(self):
        command = mobile.build_command('android', {'Z': 'value with spaces', 'A': '$(not-executed)'})
        self.assertEqual(command[-2:], ['--dart-define=A=$(not-executed)', '--dart-define=Z=value with spaces'])
        self.assertFalse(any(arg.startswith('--allow-') for arg in command))
        with self.assertRaises(ValueError):
            mobile.build_command('web')
        with self.assertRaises(ValueError):
            mobile.build_command('android', {'--arbitrary-build-flag': 'x'})
        for invalid in ([], False, ''):
            with self.subTest(defines=invalid), self.assertRaises(ValueError):
                mobile.build_command('android', invalid)

    def test_bundle_cannot_reference_files_outside_itself(self):
        with tempfile.TemporaryDirectory() as folder:
            bundle = Path(folder) / 'Runner.xcarchive'
            bundle.mkdir()
            outside = Path(folder) / 'outside.txt'
            outside.write_text('must not be included')
            (bundle / 'external').symlink_to(outside)
            with self.assertRaisesRegex(ValueError, 'symlink'):
                mobile._package_product(bundle, Path(folder) / 'mobile.zip')


if __name__ == '__main__':
    unittest.main()
