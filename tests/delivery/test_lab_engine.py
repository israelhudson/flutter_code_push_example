"""Exercise durable policy transitions against disposable Git/provider journals."""
from copy import deepcopy
from contextlib import closing
from pathlib import Path
import sqlite3
import sys
import tempfile
import threading
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / 'tools/delivery'))
from lab_demo import fixture, preview, git, write, commit
from lab_engine import FakePublisher, LabStore, make_manifest
from policy import digest


class LaboratoryTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.folder = Path(self.tmp.name)
        self.repo, self.base, self.fixed, self.inputs, self.targets, self.graph = fixture(self.folder)
        self.store = LabStore(self.folder / 'state.sqlite')
        self.production = self.store.initialize(self.base, self.targets)
        self.publisher = FakePublisher(self.folder / 'provider')
        self.store.technical_review(self.base)
        self.store.technical_review(self.fixed)

    def manifest(self, delivery='entrega-0042', rc=1, sha=None, production=None, targets=None):
        sha = sha or self.fixed
        return make_manifest(self.repo, sha, production or self.store.production(), targets or self.targets,
                             preview(self.folder, self.repo, sha, self.inputs, delivery + '-' + str(rc)),
                             self.inputs, delivery, rc)

    def prepare(self, manifest=None, urgent=False):
        manifest = manifest or self.manifest()
        return self.store.prepare(manifest, 'prepare-' + manifest['candidate_id'], urgent=urgent)

    def approve_both(self, candidate):
        for role in ('samuel', 'vinicius'):
            self.store.approve(candidate['candidate_id'], role, candidate['manifest_hash'])

    def publish(self, candidate, command='publish', publisher=None):
        return self.store.publish(candidate['candidate_id'], candidate['manifest_hash'], command,
                                  self.repo, publisher or self.publisher)

    def receipt_count(self):
        with closing(sqlite3.connect(self.publisher.db_path)) as db:
            return db.execute('SELECT count(*) FROM receipts').fetchone()[0]

    def test_reopened_database_preserves_roles_gate_and_explicit_final_command(self):
        candidate = self.prepare()
        with self.assertRaisesRegex(ValueError, '0/2'):
            self.publish(candidate)
        self.store.technical_review(self.fixed, 'yan')
        with self.assertRaisesRegex(ValueError, 'Samuel'):
            self.store.approve(candidate['candidate_id'], 'ian', candidate['manifest_hash'])
        first = self.store.approve(candidate['candidate_id'], 'samuel', candidate['manifest_hash'])
        repeated = self.store.approve(candidate['candidate_id'], 'samuel', candidate['manifest_hash'])
        self.assertEqual((first['count'], repeated['count']), (1, 1))
        with self.assertRaisesRegex(ValueError, '1/2'):
            self.publish(candidate)
        self.store = LabStore(self.store.path)
        self.approve_both(candidate)
        self.assertEqual(self.store.status(candidate['candidate_id'])['state'], 'autorizada')
        self.assertEqual(self.receipt_count(), 0)
        completed = self.publish(candidate)
        self.assertEqual(completed['state'], 'concluida')
        self.assertEqual(self.store.production()['revision'], 1)
        self.assertTrue(all(e['actor'] == 'local:israel' and e['simulation'] for e in self.store.events()))
        reviews = [e for e in self.store.events() if e['action'] == 'technical_review']
        self.assertTrue(all(e['sha'] == e['payload']['source_sha'] for e in reviews))

    def test_revision_invalidates_old_hash_and_zeroes_approvals(self):
        first = self.prepare(self.manifest(sha=self.base))
        self.approve_both(first)
        second = self.prepare(self.manifest(rc=2))
        self.assertEqual(second['count'], 0)
        self.assertEqual(self.store.status(first['candidate_id'])['state'], 'substituida')
        with self.assertRaises(ValueError):
            self.publish(first)
        with self.assertRaisesRegex(ValueError, 'Hash'):
            self.store.approve(second['candidate_id'], 'samuel', first['manifest_hash'])
        changed = deepcopy(second['manifest'])
        changed['inputs']['extra'] = True
        with self.assertRaises(ValueError):
            self.store.prepare(changed, 'change-frozen-rc')
        self.assertEqual(self.receipt_count(), 0)

    def test_request_ids_are_idempotent_and_payload_bound(self):
        manifest = self.manifest()
        first = self.store.prepare(manifest, 'same-request')
        self.assertEqual(first, self.store.prepare(manifest, 'same-request'))
        approved = self.store.approve(first['candidate_id'], 'samuel', first['manifest_hash'], request_id='approve-once')
        self.assertEqual(approved, self.store.approve(first['candidate_id'], 'samuel', first['manifest_hash'], request_id='approve-once'))
        with self.assertRaisesRegex(ValueError, 'ID de solicitação'):
            self.store.approve(first['candidate_id'], 'vinicius', first['manifest_hash'], request_id='approve-once')
        self.assertEqual(self.store.status(first['candidate_id'])['count'], 1)

    def test_final_command_does_not_follow_advanced_branch_and_is_repeatable(self):
        candidate = self.prepare()
        self.approve_both(candidate)
        write(self.repo / 'lib/after.dart', '// not approved\n')
        advanced = commit(self.repo, 'advance release after approval')
        completed = self.publish(candidate)
        repeated = self.publish(candidate)
        self.assertEqual(completed, repeated)
        self.assertNotEqual(advanced, completed['source_sha'])
        self.assertEqual(self.receipt_count(), 3)
        for item in completed['destinations'].values():
            self.assertEqual(item['receipt']['source_sha'], self.fixed)
            self.assertFalse(item['receipt']['distribution_performed'])
        self.assertEqual(git(self.repo, 'rev-parse', 'HEAD'), advanced)
        with self.assertRaisesRegex(ValueError, 'outro registro'):
            self.store.publish(candidate['candidate_id'], 'a' * 64, 'publish', self.repo, self.publisher)

    def test_timeout_requires_lookup_before_resume_and_does_not_duplicate(self):
        candidate = self.prepare()
        self.approve_both(candidate)
        partial = self.publish(candidate, publisher=FakePublisher(self.publisher.directory, {'ios': 'after'}))
        self.assertEqual(partial['state'], 'parcial')
        self.assertEqual(partial['destinations']['ios']['state'], 'resultado_desconhecido')
        self.assertEqual(self.store.production(), self.production)
        with self.assertRaisesRegex(ValueError, 'Reconcilie'):
            self.publish(candidate, 'resume-too-soon')
        self.store.reconcile(candidate['candidate_id'], self.repo, self.publisher)
        self.assertEqual(self.receipt_count(), 2)
        completed = self.publish(candidate, 'resume')
        self.assertEqual(completed['state'], 'concluida')
        self.assertEqual(self.receipt_count(), 3)
        self.assertEqual(self.publish(candidate)['state'], 'concluida')

    def test_failure_after_effect_but_before_receipt_record_is_reconciled(self):
        candidate = self.prepare()
        self.approve_both(candidate)
        original = self.store._confirm
        def interrupted(*args, **kwargs):
            raise OSError('simulated crash recording the receipt')
        self.store._confirm = interrupted
        partial = self.publish(candidate)
        self.assertEqual(partial['destinations']['android']['state'], 'executando')
        self.assertEqual(self.receipt_count(), 1)
        self.store._confirm = original
        self.store.reconcile(candidate['candidate_id'], self.repo, self.publisher)
        self.assertEqual(self.publish(candidate, 'resume')['state'], 'concluida')
        self.assertEqual(self.receipt_count(), 3)

    def test_provider_warning_blocks_and_never_falls_back_to_store(self):
        candidate = self.prepare()
        self.approve_both(candidate)
        result = self.publish(candidate, publisher=FakePublisher(self.publisher.directory, {'android': 'warning'}))
        self.assertEqual(result['state'], 'parcial')
        self.assertEqual(result['destinations']['android']['state'], 'falha')
        self.assertIn('incompatibilidade', result['destinations']['android']['error'])
        self.assertEqual(self.receipt_count(), 0)

    def test_missing_base_evidence_and_native_change_block_publication(self):
        targets = deepcopy(self.targets)
        del targets['ios']['base_evidence']
        candidate = self.prepare(self.manifest(targets=targets))
        self.approve_both(candidate)
        with self.assertRaisesRegex(ValueError, 'pendente'):
            self.publish(candidate)
        write(self.repo / 'android/app/build.gradle', '// changed native build\n')
        native = commit(self.repo, 'native change')
        self.store.technical_review(native)
        second = self.prepare(self.manifest(rc=2, sha=native))
        self.assertEqual(second['manifest']['pre_analysis']['android']['status'], 'loja_necessaria')
        self.approve_both(second)
        with self.assertRaisesRegex(ValueError, 'loja necessária'):
            self.publish(second)
        self.assertEqual(self.receipt_count(), 0)

    def test_queue_revisions_replace_queued_rc_and_old_production_requires_new_rc(self):
        first = self.prepare()
        queued = self.prepare(self.manifest(delivery='entrega-0043'))
        revised = self.prepare(self.manifest(delivery='entrega-0043', rc=2))
        self.assertEqual(revised['state'], 'fila')
        self.assertEqual(self.store.status(queued['candidate_id'])['state'], 'substituida')
        with self.assertRaises(ValueError):
            self.store.activate_next()
        with self.assertRaises(ValueError):
            self.store.approve(revised['candidate_id'], 'samuel', revised['manifest_hash'])
        self.approve_both(first)
        self.publish(first)
        self.assertEqual(self.store.activate_next()['state'], 'bloqueada')
        fresh = self.prepare(self.manifest(delivery='entrega-0043', rc=3))
        self.assertEqual((fresh['state'], fresh['count']), ('em_aprovacao', 0))

    def test_urgent_fix_excludes_main_features_then_reintegration_gets_new_approvals(self):
        old = self.prepare(self.manifest(sha=self.base))
        self.approve_both(old)
        urgent = self.prepare(self.manifest(delivery='entrega-0099'), urgent=True)
        self.assertEqual(self.store.status(old['candidate_id'])['state'], 'substituida')
        self.assertEqual(urgent['count'], 0)
        self.approve_both(urgent)
        self.publish(urgent)
        paths = git(self.repo, 'ls-tree', '-r', '--name-only', urgent['source_sha'])
        self.assertNotIn('feature_c', paths)
        self.assertNotIn('feature_d', paths)
        git(self.repo, 'checkout', 'main')
        git(self.repo, 'merge', '--no-ff', 'release/entrega-0042', '-m', 'reintegrate approved hotfix')
        merged = git(self.repo, 'rev-parse', 'HEAD')
        self.store.technical_review(merged)
        resumed = self.prepare(self.manifest(rc=2, sha=merged))
        self.assertEqual(resumed['manifest']['production']['source_sha'], self.fixed)
        self.assertEqual(resumed['count'], 0)
        with self.assertRaisesRegex(ValueError, '0/2'):
            self.publish(resumed, 'resumed')

    def test_urgency_is_blocked_until_partial_result_is_reconciled(self):
        candidate = self.prepare()
        self.approve_both(candidate)
        self.publish(candidate, publisher=FakePublisher(self.publisher.directory, {'ios': 'after'}))
        with self.assertRaisesRegex(ValueError, 'Reconcilie'):
            self.prepare(self.manifest(delivery='entrega-0099'), urgent=True)
        self.assertEqual(self.store.status(candidate['candidate_id'])['state'], 'parcial')

    def test_concurrent_preparations_leave_exactly_one_active_candidate(self):
        records = [self.manifest(delivery='entrega-0042'), self.manifest(delivery='entrega-0043')]
        barrier = threading.Barrier(2)
        results, failures = [], []
        def prepare(record):
            try:
                barrier.wait(timeout=10)
                results.append(self.prepare(record))
            except Exception as error:
                failures.append(error)
        workers = [threading.Thread(target=prepare, args=(record,)) for record in records]
        for worker in workers:
            worker.start()
        for worker in workers:
            worker.join(10)
        self.assertFalse(any(worker.is_alive() for worker in workers))
        self.assertEqual(failures, [])
        self.assertEqual(sorted(r['state'] for r in results), ['em_aprovacao', 'fila'])

    def test_source_older_than_confirmed_production_is_rejected(self):
        first = self.prepare()
        self.approve_both(first)
        self.publish(first)
        stale = self.manifest(delivery='entrega-0043', sha=self.base)
        with self.assertRaisesRegex(ValueError, 'produção confirmada'):
            self.prepare(stale)
        self.assertEqual(self.store.production()['source_sha'], self.fixed)

    def test_two_publishers_cannot_run_and_revocation_stops_remaining_destinations(self):
        candidate = self.prepare()
        self.approve_both(candidate)
        entered, release = threading.Event(), threading.Event()
        failures = []
        results = []
        class PausedPublisher(FakePublisher):
            def publish(provider, *args):
                entered.set()
                if not release.wait(10):
                    raise AssertionError('test synchronization timeout')
                return super().publish(*args)
        def first():
            try:
                results.append(self.publish(candidate, publisher=PausedPublisher(self.publisher.directory)))
            except Exception as error:
                failures.append(error)
        worker = threading.Thread(target=first)
        worker.start()
        try:
            self.assertTrue(entered.wait(10))
            with self.assertRaisesRegex(ValueError, 'já executando'):
                self.publish(candidate, 'competing')
            self.store.revoke(candidate['candidate_id'], 'samuel', candidate['manifest_hash'])
        finally:
            release.set()
            worker.join(10)
        self.assertFalse(worker.is_alive())
        self.assertEqual(failures, [])
        self.assertEqual(results[0]['state'], 'parcial')
        self.assertEqual(self.receipt_count(), 1)
        with self.assertRaisesRegex(ValueError, '1/2'):
            self.publish(candidate, 'resume-without-approval')
        self.approve_both(candidate)
        self.assertEqual(self.publish(candidate, 'resume')['state'], 'concluida')
        self.assertEqual(self.receipt_count(), 3)

    def test_tampered_preview_wrong_identity_and_destination_reduction_block(self):
        manifest = self.manifest()
        fewer = deepcopy(manifest)
        del fewer['targets']['ios']
        fewer['pre_analysis'] = {k: v for k, v in fewer['pre_analysis'].items() if k != 'ios'}
        with self.assertRaisesRegex(ValueError, 'destinos'):
            self.prepare(fewer)
        candidate = self.prepare(manifest)
        with self.assertRaisesRegex(ValueError, 'Operador'):
            self.store.approve(candidate['candidate_id'], 'samuel', candidate['manifest_hash'], actor='samuelcamilo')
        rejected = self.store.events()[-1]
        self.assertEqual(rejected['actor'], 'local:israel')
        self.assertEqual(rejected['payload']['attempted_actor'], 'samuelcamilo')
        self.approve_both(candidate)
        Path(manifest['preview']['path']).write_bytes(b'changed zip')
        with self.assertRaises(ValueError):
            self.publish(candidate)
        self.assertEqual(self.receipt_count(), 0)

    def test_audit_history_and_manifests_are_immutable_and_seed_cannot_reset_production(self):
        candidate = self.prepare()
        with self.store.connection() as db:
            with self.assertRaises(sqlite3.IntegrityError):
                db.execute('DELETE FROM events')
            with self.assertRaises(sqlite3.IntegrityError):
                db.execute("UPDATE candidates SET manifest='{}' WHERE id=?", (candidate['candidate_id'],))
        self.approve_both(candidate)
        self.publish(candidate)
        current = self.store.production()
        self.assertEqual(self.store.initialize(self.base, self.targets), current)
        with self.assertRaisesRegex(ValueError, 'não sobrescrever'):
            self.store.initialize(self.fixed, self.targets)
        self.assertEqual(self.store.production(), current)


if __name__ == '__main__':
    unittest.main()
