"""Exercise dispatch boundaries offline; never use real credentials or services."""
import contextlib
import io
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'tools/delivery'))
import delivery_scenarios as scenarios
import run_delivery as cli


class ScenarioTests(unittest.TestCase):
    def test_all_existing_supported_combinations_and_effects_are_preserved(self):
        expected = {
            'candidate_only': ('none', 'controls_only', 'none', False, False),
            'candidate_preview': ('none', 'full', 'none', True, False),
            'release_only': ('github_test', 'controls_only', 'none', False, True),
            'release_preview': ('github_test', 'full', 'none', True, True),
            'android_staging': ('github_test', 'full', 'android_staging', True, True),
        }
        self.assertEqual({s.id for s in scenarios.SCENARIOS}, set(expected))
        for identifier, (scope, validation, mobile, preview, final) in expected.items():
            with self.subTest(scenario=identifier):
                item = scenarios.by_id(identifier)
                self.assertIs(scenarios.by_label(item.label), item)
                self.assertEqual(item.configuration(), {
                    'scope': scope, 'validation_mode': validation, 'patch_mode': mobile})
                self.assertEqual(item.effects()['web_preview'], preview)
                self.assertEqual(item.effects()['github_release_after_acceptances_and_enabled_controls'], final)
                self.assertIs(item.effects()['creates_candidate_tag_and_prerelease'], True)
                self.assertIs(item.effects()['stable_publication'], False)
                self.assertEqual(item.effects()['android_patch'],
                                 'assisted_cli_after_github_release' if mobile != 'none' else 'none')

    def test_invalid_or_injected_choice_never_falls_back_or_writes_outputs(self):
        with tempfile.TemporaryDirectory() as folder:
            target = Path(folder, 'outputs')
            target.write_text('existing=value\n')
            for label in ('', 'release_only', 'production', 'Só avaliar a candidata\nscope=github_test'):
                with self.subTest(label=label), patch.dict(os.environ, {
                    'GITHUB_OUTPUT': str(target), 'DELIVERY_SCENARIO': label,
                }), contextlib.redirect_stderr(io.StringIO()):
                    self.assertEqual(scenarios.main(), 1)
                    self.assertEqual(target.read_text(), 'existing=value\n')
            with self.assertRaises(ValueError):
                scenarios.by_id('production')

    def test_workflow_resolver_writes_only_fixed_outputs_for_each_form_choice(self):
        for item in scenarios.SCENARIOS:
            with self.subTest(scenario=item.id), tempfile.TemporaryDirectory() as folder:
                target = Path(folder, 'outputs')
                result = subprocess.run([sys.executable, str(ROOT / 'tools/delivery/delivery_scenarios.py')],
                    env={**os.environ, 'GITHUB_OUTPUT': str(target), 'DELIVERY_SCENARIO': item.label},
                    capture_output=True, text=True, check=False)
                self.assertEqual(result.returncode, 0, result.stderr)
                self.assertEqual(dict(line.split('=', 1) for line in target.read_text().splitlines()),
                                 {'scenario_id': item.id, **item.configuration()})

    def test_form_and_cli_share_choices_and_all_jobs_use_the_resolved_mode(self):
        workflow = (ROOT / '.github/workflows/delivery-prepare.yml').read_text()
        inputs = workflow.split('    inputs:\n', 1)[1].split('\npermissions:', 1)[0]
        fields = [line.strip().removesuffix(':') for line in inputs.splitlines()
                  if line.startswith('      ') and not line.startswith('       ')]
        self.assertEqual(fields, ['scenario', 'version', 'title'])
        choices = [line.removeprefix('          - ') for line in inputs.splitlines()
                   if line.startswith('          - ')]
        self.assertEqual(choices, [item.label for item in scenarios.SCENARIOS])
        self.assertIn('        default: ' + scenarios.DEFAULT_SCENARIO.label, inputs)
        self.assertNotIn('default:', inputs.split('      version:', 1)[1])
        self.assertLess(workflow.index('- id: scenario'), workflow.index('- id: prepare'))
        self.assertIn('SCOPE: ${{ steps.scenario.outputs.scope }}', workflow)
        self.assertIn('DELIVERY_PATCH_MODE: ${{ steps.scenario.outputs.patch_mode }}', workflow)
        self.assertIn('validation_mode: ${{ steps.scenario.outputs.validation_mode }}', workflow)
        self.assertIn("if: needs.prepare.outputs.validation_mode == 'full'", workflow)
        self.assertIn("needs.prepare.outputs.validation_mode == 'controls_only' && needs.web.result == 'skipped'", workflow)
        self.assertIn("needs.prepare.outputs.validation_mode == 'full' && needs.web.result == 'success'", workflow)
        self.assertIn('VALIDATION_MODE: ${{ needs.prepare.outputs.validation_mode }}', workflow)
        for old in ('inputs.scope', 'inputs.validation_mode', 'inputs.patch_mode'):
            self.assertNotIn(old, workflow)
        self.assertNotIn('shorebird patch', workflow)


class CLITests(unittest.TestCase):
    def args(self, scenario='release_only', mode='--dry-run', title='Corrigir o login'):
        return ['prepare', '--scenario', scenario, '--version', '1.15.7', '--title', title, mode]

    def test_dry_run_of_every_scenario_never_starts_a_process(self):
        for item in scenarios.SCENARIOS:
            with self.subTest(scenario=item.id), patch.object(cli.subprocess, 'run') as process, \
                    contextlib.redirect_stdout(io.StringIO()) as out:
                self.assertEqual(cli.main(self.args(item.id)), 0)
                result = json.loads(out.getvalue())
                self.assertEqual(result['mode'], 'dry_run')
                self.assertIs(result['dispatched'], False)
                self.assertEqual(result['inputs']['scenario'], item.label)
                self.assertEqual(result['resolved'], item.configuration())
                process.assert_not_called()

    def test_mode_is_required_exclusive_and_scenarios_are_known(self):
        for args in (self.args()[:-1], self.args() + ['--execute'], self.args('production')):
            with self.subTest(args=args), patch.object(cli.subprocess, 'run') as process, \
                    contextlib.redirect_stderr(io.StringIO()), self.assertRaises(SystemExit) as error:
                cli.main(args)
            self.assertEqual(error.exception.code, 2)
            process.assert_not_called()

    def test_bad_version_or_title_blocks_before_dispatch(self):
        for version, title in [('v1.2.3', 'Login'), ('1.2.3-rc.2', 'Login'), ('01.2.3', 'Login'),
                               ('1.2', 'Login'), ('1.2.3', ''), ('1.2.3', 'x' * 121),
                               ('1.2.3', 'Linha\nextra')]:
            args = ['prepare', '--scenario', 'release_only', '--version', version,
                    '--title', title, '--execute']
            with self.subTest(version=version, title=title), patch.object(cli.subprocess, 'run') as process, \
                    contextlib.redirect_stderr(io.StringIO()):
                self.assertEqual(cli.main(args), 1)
                process.assert_not_called()

    def test_execute_uses_json_stdin_once_and_reports_only_submission(self):
        title = 'Token "expirado"; $(touch /tmp/not-a-command) `echo texto` \\ ok'
        with patch.object(cli.subprocess, 'run', return_value=subprocess.CompletedProcess([], 0)) as process, \
                contextlib.redirect_stdout(io.StringIO()) as out:
            self.assertEqual(cli.main(self.args(mode='--execute', title=title)), 0)
        process.assert_called_once()
        args, kwargs = process.call_args
        self.assertEqual(args[0], list(cli.DISPATCH_COMMAND))
        self.assertNotIn(title, args[0])
        self.assertNotIn('shell', kwargs)
        self.assertEqual(json.loads(kwargs['input']), {
            'scenario': scenarios.by_id('release_only').label, 'version': '1.15.7', 'title': title})
        result = json.loads(out.getvalue())
        self.assertIs(result['dispatch_submitted'], True)
        self.assertNotIn('release_created', result)

    def test_failures_do_not_retry_or_claim_success(self):
        outcomes = [FileNotFoundError(), OSError('network'),
                    subprocess.TimeoutExpired('gh', 45), subprocess.CompletedProcess([], 1)]
        for outcome in outcomes:
            kwargs = {'side_effect': outcome} if isinstance(outcome, Exception) else {'return_value': outcome}
            with self.subTest(outcome=outcome), patch.object(cli.subprocess, 'run', **kwargs) as process, \
                    contextlib.redirect_stderr(io.StringIO()), contextlib.redirect_stdout(io.StringIO()) as out:
                self.assertEqual(cli.main(self.args(mode='--execute')), 1)
                process.assert_called_once()
                self.assertEqual(out.getvalue(), '')

    def test_cli_process_round_trips_literal_title_and_dry_run_does_not_invoke_fake_gh(self):
        # This fake lives first on PATH: no real GitHub, browser or credentials.
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            capture = root / 'request.json'
            gh = root / 'gh'
            gh.write_text(f'#!{sys.executable}\nimport json, os, sys\n'
                          'from pathlib import Path\n'
                          'Path(os.environ["CAPTURE"]).write_text(json.dumps({"args":sys.argv[1:],'
                          '"input":json.load(sys.stdin)}))\n')
            gh.chmod(0o700)
            env = {**os.environ, 'PATH': str(root), 'CAPTURE': str(capture)}
            title = 'Token "ok"; $(touch bad) `touch bad` \\ texto'
            for mode in ('--dry-run', '--execute'):
                result = subprocess.run([sys.executable, str(ROOT / 'tools/delivery/run_delivery.py'),
                                         *self.args(mode=mode, title=title)], cwd=folder,
                                        env=env, capture_output=True, text=True, check=False)
                self.assertEqual(result.returncode, 0, result.stderr)
                self.assertEqual(capture.exists(), mode == '--execute')
                self.assertFalse((root / 'bad').exists())
            captured = json.loads(capture.read_text())
            self.assertEqual(captured['input']['title'], title)
            self.assertEqual(captured['args'], list(cli.DISPATCH_COMMAND)[1:])


if __name__ == '__main__':
    unittest.main()
