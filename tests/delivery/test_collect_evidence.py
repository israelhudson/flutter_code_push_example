import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / 'tools/delivery'))
from collect_evidence import collect


class CollectorTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.output = Path(self.tmp.name) / 'capture'
        self.calls = []

    def requester(self, path, raw=False):
        self.calls.append((path, raw))
        if raw:
            return subprocess.CompletedProcess([], 0, b'\x1b[31moriginal log\x1b[0m\n', b'')
        if '/jobs?' in path:
            data = {'jobs': [{'id': 15, 'name': 'completed', 'status': 'completed', 'conclusion': 'failure', 'run_attempt': 1},
                             {'id': 16, 'name': 'skipped', 'status': 'completed', 'conclusion': 'skipped', 'run_attempt': 1}]}
        elif path.endswith('/approvals'):
            data = []
        else:
            data = {'id': 123, 'status': 'completed', 'conclusion': 'failure', 'run_attempt': 1}
        return subprocess.CompletedProcess([], 0, json.dumps(data).encode(), b'')

    def test_original_failure_and_ansi_preserved_without_claiming_scenario_pass(self):
        result = collect('123', self.output, requester=self.requester)
        self.assertEqual(result['collection_status'], 'complete')
        self.assertEqual(result['run_conclusion'], 'failure')
        self.assertEqual(result['scenario_result'], 'not_evaluated')
        self.assertEqual((self.output / 'job-15.log').read_bytes(), b'\x1b[31moriginal log\x1b[0m\n')
        self.assertEqual(result['jobs'][1]['log_status'], 'not_applicable_skipped')
        self.assertFalse(any('/jobs/16/logs' in p for p, _ in self.calls))

    def test_existing_capture_never_overwritten(self):
        collect('123', self.output, requester=self.requester)
        before = (self.output / 'collection-summary.json').read_bytes()
        with self.assertRaises(FileExistsError):
            collect('123', self.output, requester=self.requester)
        self.assertEqual((self.output / 'collection-summary.json').read_bytes(), before)

    def test_log_error_keeps_bytes_and_marks_partial(self):
        def failed(path, raw=False):
            if raw:
                return subprocess.CompletedProcess([], 1, b'partial log', b'HTTP error')
            return self.requester(path, raw)
        result = collect('123', self.output, requester=failed)
        self.assertEqual(result['collection_status'], 'partial')
        self.assertEqual((self.output / 'job-15.log').read_bytes(), b'partial log')
        self.assertEqual((self.output / 'job-15.stderr').read_bytes(), b'HTTP error')

    def test_pending_job_not_queried_for_unavailable_log(self):
        def pending(path, raw=False):
            if '/jobs?' in path:
                data = {'jobs': [{'id': 15, 'name': 'approval', 'status': 'waiting', 'conclusion': None}]}
                return subprocess.CompletedProcess([], 0, json.dumps(data).encode(), b'')
            return self.requester(path, raw)
        result = collect('123', self.output, requester=pending)
        self.assertEqual(result['collection_status'], 'pending')
        self.assertFalse(any(raw for _, raw in self.calls))

    def test_other_repository_or_non_numeric_run_refused_before_io(self):
        for identifier, repo in [('abc', 'israelhudson/flutter_code_push_example'), ('123', 'org/work')]:
            with self.assertRaises(ValueError):
                collect(identifier, self.output, repo, self.requester)
        self.assertFalse(self.output.exists())
        self.assertEqual(self.calls, [])


if __name__ == '__main__':
    unittest.main()
