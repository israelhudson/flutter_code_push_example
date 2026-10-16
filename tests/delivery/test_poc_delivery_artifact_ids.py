"""Offline workflow contracts; fixtures do not claim a successful GitHub rerun."""
import os
from pathlib import Path
import re
import subprocess
import textwrap
import unittest


ROOT = Path(__file__).resolve().parents[2]
WORKFLOW = ROOT / '.github/workflows/delivery-prepare.yml'


def jobs():
    parts = re.split(r'(?m)^  ([a-z]+):\n', WORKFLOW.read_text().split('\njobs:\n', 1)[1])
    return dict(zip(parts[1::2], parts[2::2]))


def steps(job):
    return [part for part in re.split(r'(?m)(?=^      - )', job.split('    steps:\n', 1)[1])
            if part.strip()]


def field(step, key, indent=8):
    prefix = ' ' * indent
    if indent == 8:
        prefix = '(?:' + prefix + '|      - )'
    match = re.search(r'(?m)^' + prefix + re.escape(key) + r': (.+)$', step)
    return match[1] if match else None


def upload(job):
    return next(step for step in steps(job) if 'uses: actions/upload-artifact@' in step)


def run_script(step):
    block = re.search(r'(?m)^        run: \|\n((?:          .*\n)*)', step)
    if block:
        return textwrap.dedent(block[1])
    return field(step, 'run').strip("'")


class ArtifactWorkflowTests(unittest.TestCase):
    def test_producer_upload_ids_are_exported_and_consumed_without_name_selection(self):
        workflow = jobs()
        expected = [
            ('prepare', 'preparation_artifact', 'preparation_artifact_id', 'open'),
            ('build', 'preview_artifact', 'preview_artifact_id', 'web'),
            ('web', 'proof_artifact', 'proof_artifact_id', 'open'),
        ]
        downloads = [(job, step) for job, content in workflow.items() for step in steps(content)
                     if 'uses: actions/download-artifact@' in step]
        self.assertEqual(len(downloads), len(expected))
        for producer, step_id, output, consumer in expected:
            with self.subTest(producer=producer):
                producer_upload = upload(workflow[producer])
                self.assertIn('- id: ' + step_id + '\n', producer_upload)
                self.assertEqual(field(workflow[producer].split('    steps:', 1)[0], output, 6),
                                 '${{ steps.' + step_id + '.outputs.artifact-id }}')
                expression = '${{ needs.' + producer + '.outputs.' + output + ' }}'
                download = next(step for job, step in downloads
                                if job == consumer and field(step, 'artifact-ids', 10) == expression)
                self.assertIsNone(field(download, 'name', 10))
                self.assertIsNone(field(download, 'pattern', 10))
                self.assertNotIn('github.run_attempt', download)
                needs = field(workflow[consumer], 'needs', 4)
                self.assertIn(producer, re.findall(r'[a-z]+', needs))

    def test_all_named_uploads_have_attempt_suffix_to_avoid_sdk_latest_deduplication(self):
        expected = {'prepare': 'poc-preparation', 'build': 'poc-built-preview',
                    'web': 'poc-web-proof', 'open': 'poc-candidate-report'}
        for job, prefix in expected.items():
            with self.subTest(job=job):
                self.assertEqual(field(upload(jobs()[job]), 'name', 10),
                                 prefix + '-attempt-${{ github.run_attempt }}')

    def test_rerun_consumer_uses_producer_two_id_even_when_older_artifact_id_is_larger(self):
        # Model only the pinned SDK's latest:true name deduplication and ID filter.
        # Attempt 1 failed, producer 2 succeeded, and only its consumer reruns as 3.
        # IDs intentionally decrease with creation time, matching the observed bug.
        for producer, output in [('prepare', 'preparation_artifact_id'),
                                 ('build', 'preview_artifact_id'), ('web', 'proof_artifact_id')]:
            with self.subTest(producer=producer):
                template = field(upload(jobs()[producer]), 'name', 10)
                old = {'id': 100, 'name': template.replace('${{ github.run_attempt }}', '1'),
                       'files': ['blocked.json']}
                current = {'id': 90, 'name': template.replace('${{ github.run_attempt }}', '2'),
                           'files': ['producer-proof.json']}
                producer_outputs = {output: str(current['id'])}
                # The output is retained from producer 2; never reconstruct a name for 3.
                requested_id = int(producer_outputs[output])
                latest_by_name = {}
                for artifact in sorted([current, old], key=lambda item: -item['id']):
                    latest_by_name.setdefault(artifact['name'], artifact)
                selected = [item for item in latest_by_name.values() if item['id'] == requested_id]
                self.assertEqual(selected, [current])
                self.assertNotIn(old, selected)
                self.assertTrue(selected[0]['name'].endswith('-attempt-2'))
                self.assertNotEqual(selected[0]['name'], template.replace('${{ github.run_attempt }}', '3'))

    def test_empty_or_invalid_ids_fail_before_action_can_fall_back_to_all_artifacts(self):
        workflow = jobs()
        web_guard = next(step for step in steps(workflow['web'])
                         if field(step, 'name') == 'Confirmar ID do preview produzido')
        open_guard = next(step for step in steps(workflow['open'])
                          if field(step, 'name') == 'Confirmar IDs dos artefatos produzidos')
        for job, guard in [('web', web_guard), ('open', open_guard)]:
            first_download = next(step for step in steps(workflow[job])
                                  if 'uses: actions/download-artifact@' in step)
            self.assertLess(workflow[job].index(guard), workflow[job].index(first_download))
        for bad in ('', '0', '-1', '90,100', 'latest', '90\n100'):
            with self.subTest(value=bad):
                for guard, env in [
                    (web_guard, {'PREVIEW_ARTIFACT_ID': bad}),
                    (open_guard, {'PREPARATION_ARTIFACT_ID': bad, 'VALIDATION_MODE': 'controls_only'}),
                    (open_guard, {'PREPARATION_ARTIFACT_ID': '90', 'PROOF_ARTIFACT_ID': bad,
                                  'VALIDATION_MODE': 'full'}),
                ]:
                    result = subprocess.run(['bash', '-e', '-c', run_script(guard)],
                                            env={**os.environ, **env}, capture_output=True)
                    self.assertNotEqual(result.returncode, 0)
        for guard, env in [
            (web_guard, {'PREVIEW_ARTIFACT_ID': '90'}),
            (open_guard, {'PREPARATION_ARTIFACT_ID': '90', 'PROOF_ARTIFACT_ID': '',
                          'VALIDATION_MODE': 'controls_only'}),
            (open_guard, {'PREPARATION_ARTIFACT_ID': '90', 'PROOF_ARTIFACT_ID': '91',
                          'VALIDATION_MODE': 'full'}),
        ]:
            result = subprocess.run(['bash', '-e', '-c', run_script(guard)],
                                    env={**os.environ, **env}, capture_output=True)
            self.assertEqual(result.returncode, 0, result.stderr)

    def test_controls_only_does_not_require_skipped_preview_or_web_proof(self):
        workflow = jobs()
        self.assertEqual(field(workflow['build'], 'if', 4),
                         "needs.prepare.outputs.validation_mode == 'full'")
        proof_download = next(step for step in steps(workflow['open'])
                              if field(step, 'artifact-ids', 10) ==
                              '${{ needs.web.outputs.proof_artifact_id }}')
        self.assertEqual(field(proof_download, 'if'), "needs.prepare.outputs.validation_mode == 'full'")
        plan_download = next(step for step in steps(workflow['open'])
                             if field(step, 'artifact-ids', 10) ==
                             '${{ needs.prepare.outputs.preparation_artifact_id }}')
        self.assertIsNone(field(plan_download, 'if'))
        self.assertIn("needs.prepare.outputs.validation_mode == 'controls_only' && needs.web.result == 'skipped'",
                      workflow['open'])


if __name__ == '__main__':
    unittest.main()
