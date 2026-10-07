"""Persistent single-operator laboratory. No remote publication adapter exists here."""
from contextlib import closing, contextmanager
from datetime import datetime, timedelta, timezone
from pathlib import Path
import fcntl
import json
import re
import sqlite3
import uuid

from policy import canonical, digest
import snapshots

OPERATOR = 'local:israel'
ROLES = ('samuel', 'vinicius')
ACTIVE = ('em_aprovacao', 'autorizada', 'publicando', 'parcial')


def now():
    return datetime.now(timezone.utc).isoformat()


def copy(value):
    return json.loads(canonical(value))


def make_manifest(repo, ref, production, targets, preview, inputs, delivery_id, rc=1):
    if not re.fullmatch(r'entrega-\d{4,}', delivery_id) or rc < 1:
        raise ValueError('Entrega deve usar entrega-0042 e RC positiva.')
    sha = snapshots.resolve_commit(repo, ref)
    tag = f'{delivery_id}-rc.{rc}'
    return {
        'schema': 2, 'mode': 'laboratory', 'simulation': True,
        'repository_path': str(Path(repo).resolve()), 'candidate_id': tag,
        'delivery_id': delivery_id, 'tag': tag, 'release_ref': f'release/{delivery_id}',
        'source_sha': sha, 'source_tree': snapshots.source_tree(repo, sha),
        'author': OPERATOR, 'policy': 'laboratory-v1', 'required_roles': list(ROLES),
        'production': copy(production), 'targets': copy(targets),
        'inputs': copy(inputs), 'preview': copy(preview),
        'pre_analysis': snapshots.pre_analyze(repo, sha, targets, inputs),
        'changelog': snapshots.changelog(repo, production['source_sha'], sha),
        'expires_at': (datetime.now(timezone.utc) + timedelta(days=30)).isoformat(),
    }


class LabStore:
    def __init__(self, path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.connection() as db:
            db.executescript('''
                CREATE TABLE IF NOT EXISTS settings (key TEXT PRIMARY KEY, value TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS candidates (
                    seq INTEGER PRIMARY KEY AUTOINCREMENT, id TEXT UNIQUE NOT NULL,
                    manifest TEXT NOT NULL, hash TEXT NOT NULL, state TEXT NOT NULL,
                    version INTEGER NOT NULL DEFAULT 0);
                CREATE TABLE IF NOT EXISTS approvals (
                    candidate TEXT NOT NULL, role TEXT NOT NULL, hash TEXT NOT NULL,
                    active INTEGER NOT NULL, PRIMARY KEY(candidate, role));
                CREATE TABLE IF NOT EXISTS technical (sha TEXT PRIMARY KEY, actor TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS events (
                    seq INTEGER PRIMARY KEY AUTOINCREMENT, id TEXT UNIQUE NOT NULL,
                    at TEXT NOT NULL, actor TEXT NOT NULL, role TEXT, candidate TEXT,
                    sha TEXT, hash TEXT, action TEXT NOT NULL, payload TEXT NOT NULL,
                    result TEXT NOT NULL, request_id TEXT UNIQUE);
                CREATE TABLE IF NOT EXISTS commands (
                    id TEXT PRIMARY KEY, candidate TEXT NOT NULL, hash TEXT NOT NULL,
                    state TEXT NOT NULL, result TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS destinations (
                    candidate TEXT NOT NULL, destination TEXT NOT NULL, operation_key TEXT UNIQUE NOT NULL,
                    state TEXT NOT NULL, receipt TEXT, error TEXT,
                    PRIMARY KEY(candidate, destination));
                CREATE TABLE IF NOT EXISTS tags (name TEXT PRIMARY KEY, sha TEXT NOT NULL, simulation INTEGER NOT NULL);
                CREATE TRIGGER IF NOT EXISTS immutable_candidate BEFORE UPDATE OF manifest, hash ON candidates
                    BEGIN SELECT RAISE(ABORT, 'Manifesto imutável; prepare outra RC.'); END;
                CREATE TRIGGER IF NOT EXISTS immutable_events_update BEFORE UPDATE ON events
                    BEGIN SELECT RAISE(ABORT, 'Histórico somente acrescentado.'); END;
                CREATE TRIGGER IF NOT EXISTS immutable_events_delete BEFORE DELETE ON events
                    BEGIN SELECT RAISE(ABORT, 'Histórico somente acrescentado.'); END;
            ''')

    @contextmanager
    def connection(self):
        db = sqlite3.connect(self.path, timeout=30, isolation_level=None)
        db.row_factory = sqlite3.Row
        db.execute('PRAGMA foreign_keys=ON')
        try:
            yield db
        finally:
            db.close()

    def _get(self, db, key):
        row = db.execute('SELECT value FROM settings WHERE key=?', (key,)).fetchone()
        if not row:
            raise ValueError('Inicialize o laboratório antes desta ação.')
        return json.loads(row['value'])

    def _put(self, db, key, value):
        db.execute('INSERT OR REPLACE INTO settings VALUES (?,?)', (key, canonical(value)))

    def _event(self, db, action, payload, result, actor, candidate=None, role=None, request_id=None):
        row = db.execute('SELECT manifest, hash FROM candidates WHERE id=?', (candidate,)).fetchone()
        manifest = json.loads(row['manifest']) if row else {}
        db.execute('INSERT INTO events(id,at,actor,role,candidate,sha,hash,action,payload,result,request_id) '
                   'VALUES (?,?,?,?,?,?,?,?,?,?,?)',
                   (str(uuid.uuid4()), now(), actor, role, candidate,
                    manifest.get('source_sha') or payload.get('source_sha') or result.get('source_sha'),
                    row['hash'] if row else None, action, canonical(payload), canonical(result), request_id))

    def _write(self, action, payload, function, actor=OPERATOR, candidate=None, role=None, request_id=None):
        with self.connection() as db:
            db.execute('BEGIN IMMEDIATE')
            try:
                if actor != self._get(db, 'operator'):
                    raise ValueError('Operador não autorizado para o laboratório.')
                if request_id:
                    old = db.execute('SELECT * FROM events WHERE request_id=?', (request_id,)).fetchone()
                    if old:
                        if (old['action'], old['payload'], old['actor']) != (action, canonical(payload), actor):
                            raise ValueError('ID de solicitação já usado com outra ação ou conteúdo.')
                        db.commit()
                        return json.loads(old['result'])
                result = function(db)
                self._event(db, action, payload, result, actor, candidate, role, request_id)
                db.commit()
                return result
            except Exception as error:
                db.rollback()
                db.execute('BEGIN IMMEDIATE')
                self._event(db, action, {**payload, 'attempted_actor': actor},
                            {'accepted': False, 'reason': str(error)}, OPERATOR, candidate, role)
                db.commit()
                raise

    def initialize(self, production_sha, targets, operator=OPERATOR):
        if operator != OPERATOR or not re.fullmatch(r'[0-9a-f]{40}', production_sha):
            raise ValueError('Laboratório de Israel requer SHA completo da base escolhida.')
        if not targets or set(targets) - {'android', 'ios', 'web'}:
            raise ValueError('Destinos requeridos: android, ios ou web.')
        production = {'source_sha': production_sha, 'revision': 0, 'destinations': {},
                      'evidence': 'seed_laboratory', 'simulation': True}
        with self.connection() as db:
            db.execute('BEGIN IMMEDIATE')
            if db.execute("SELECT 1 FROM settings WHERE key='operator'").fetchone():
                if self._get(db, 'operator') != operator or self._get(db, 'seed') != {'sha': production_sha, 'targets': targets}:
                    db.rollback()
                    raise ValueError('Banco já inicializado; não sobrescrever a produção do ensaio.')
                db.commit()
                return self._get(db, 'production')
            self._put(db, 'operator', operator)
            self._put(db, 'seed', {'sha': production_sha, 'targets': targets})
            self._put(db, 'production', production)
            self._event(db, 'initialize', {'targets': targets}, production, operator)
            db.commit()
        return production

    def production(self):
        with self.connection() as db:
            return self._get(db, 'production')

    def technical_review(self, sha, role='ian', actor=OPERATOR):
        if role not in ('ian', 'yan') or not re.fullmatch(r'[0-9a-f]{40}', sha):
            raise ValueError('Revisão técnica requer papel Ian/Yan e SHA completo.')
        def apply(db):
            db.execute('INSERT OR REPLACE INTO technical VALUES (?,?)', (sha, actor))
            return {'simulation': True, 'source_sha': sha, 'technical_review': 'accepted', 'approvals': 0}
        return self._write('technical_review', {'source_sha': sha}, apply, actor, role=role)

    def _candidate(self, db, candidate):
        row = db.execute('SELECT * FROM candidates WHERE id=?', (candidate,)).fetchone()
        if not row:
            raise ValueError('Candidata não encontrada.')
        record = json.loads(row['manifest'])
        if digest(record) != row['hash']:
            raise ValueError('Manifesto alterado; publicação bloqueada.')
        return row, record

    def _valid(self, db, candidate, manifest_hash=None, check_preview=True):
        row, manifest = self._candidate(db, candidate)
        if manifest_hash is not None and manifest_hash != row['hash']:
            raise ValueError('Hash de outra candidata ou manifesto obsoleto.')
        if row['state'] not in ACTIVE:
            raise ValueError('Candidata inativa, substituída ou ainda na fila.')
        if datetime.fromisoformat(manifest['expires_at']) <= datetime.now(timezone.utc):
            raise ValueError('Candidata expirada; prepare nova RC.')
        if manifest['production'] != self._get(db, 'production'):
            raise ValueError('Base de produção mudou; candidata obsoleta.')
        if check_preview:
            snapshots.validate_preview(manifest['repository_path'], manifest['source_sha'], manifest['preview'], manifest['inputs'])
        return row, manifest

    def _status(self, db, candidate):
        row, manifest = self._candidate(db, candidate)
        approved = [r['role'] for r in db.execute('SELECT role FROM approvals WHERE candidate=? AND hash=? AND active=1 ORDER BY role', (candidate, row['hash']))]
        destinations = {}
        for r in db.execute('SELECT * FROM destinations WHERE candidate=? ORDER BY destination', (candidate,)):
            destinations[r['destination']] = {'state': r['state'], 'operation_key': r['operation_key'],
                                              'receipt': json.loads(r['receipt']) if r['receipt'] else None, 'error': r['error']}
        return {'candidate_id': candidate, 'manifest_hash': row['hash'], 'state': row['state'],
                'version': row['version'], 'simulation': True, 'mode': 'laboratory',
                'operator': {'id': OPERATOR, 'name': 'Israel', 'identity_source': 'local_session'},
                'source_sha': manifest['source_sha'], 'approved_roles': approved, 'count': len(approved),
                'required': 2, 'destinations': destinations, 'manifest': manifest}

    def status(self, candidate_id=None):
        with self.connection() as db:
            if candidate_id:
                return self._status(db, candidate_id)
            return {'mode': 'laboratory', 'simulation': True, 'production': self._get(db, 'production'),
                    'candidates': [self._status(db, r['id']) for r in db.execute('SELECT id FROM candidates ORDER BY seq')],
                    'tags': [dict(r) for r in db.execute('SELECT * FROM tags ORDER BY name')]}

    def events(self, candidate_id=None):
        with self.connection() as db:
            rows = db.execute('SELECT * FROM events' + (' WHERE candidate=?' if candidate_id else '') + ' ORDER BY seq',
                              (candidate_id,) if candidate_id else ()).fetchall()
            return [{**dict(r), 'payload': json.loads(r['payload']), 'result': json.loads(r['result']),
                     'mode': 'laboratory', 'simulation': True, 'simulated_role': r['role'],
                     'identity_source': 'local_session'} for r in rows]

    def _manifest(self, db, manifest):
        if (manifest.get('mode') != 'laboratory' or manifest.get('simulation') is not True
                or manifest.get('author') != OPERATOR or manifest.get('required_roles') != list(ROLES)
                or manifest.get('policy') != 'laboratory-v1'):
            raise ValueError('Somente manifestos explícitos do laboratório de Israel são aceitos.')
        candidate = manifest['candidate_id']
        if not re.fullmatch(r'entrega-\d{4,}-rc\.[1-9]\d*', candidate) or candidate != manifest['tag']:
            raise ValueError('Identidade inválida da RC.')
        if (candidate.rsplit('-rc.', 1)[0] != manifest['delivery_id']
                or manifest['release_ref'] != 'release/' + manifest['delivery_id']
                or manifest.get('schema') != 2):
            raise ValueError('Entrega, branch e tag não representam a mesma candidata.')
        if manifest['production'] != self._get(db, 'production'):
            raise ValueError('Prepare a partir da produção atual do laboratório.')
        repo, sha = manifest['repository_path'], manifest['source_sha']
        if not re.fullmatch(r'[0-9a-f]{40}', sha) or snapshots.resolve_commit(repo, sha) != sha:
            raise ValueError('Snapshot requer SHA completo e fixo.')
        if snapshots.source_tree(repo, sha) != manifest['source_tree']:
            raise ValueError('Árvore do snapshot divergente.')
        snapshots.require_ancestor(repo, manifest['production']['source_sha'], sha)
        snapshots.validate_preview(repo, sha, manifest['preview'], manifest['inputs'])
        expected = snapshots.pre_analyze(repo, sha, manifest['targets'], manifest['inputs'])
        if manifest['pre_analysis'] != expected:
            raise ValueError('Pré-análise divergente; prepare o manifesto novamente.')
        if manifest['changelog'] != snapshots.changelog(repo, manifest['production']['source_sha'], sha):
            raise ValueError('Changelog divergente do snapshot e da produção.')
        if not db.execute('SELECT 1 FROM technical WHERE sha=?', (sha,)).fetchone():
            raise ValueError('Registre a revisão técnica simulada de Ian/Yan antes da candidata.')
        expires = datetime.fromisoformat(manifest['expires_at'])
        if expires.tzinfo is None or expires <= datetime.now(timezone.utc):
            raise ValueError('Validade da candidata ausente ou expirada.')
        if set(manifest['targets']) != set(self._get(db, 'seed')['targets']):
            raise ValueError('Não reduzir ou trocar destinos requeridos silenciosamente.')

    def prepare(self, manifest, request_id, actor=OPERATOR, urgent=False):
        manifest = copy(manifest)
        candidate = manifest['candidate_id']
        def apply(db):
            self._manifest(db, manifest)
            existing = db.execute('SELECT * FROM candidates WHERE id=?', (candidate,)).fetchone()
            if existing:
                if existing['hash'] != digest(manifest):
                    raise ValueError('RC já reservada para outra foto; use novo número.')
                return self._status(db, candidate)
            current = db.execute("SELECT id,state FROM candidates WHERE state IN ('em_aprovacao','autorizada','publicando','parcial')").fetchone()
            revision = int(candidate.rsplit('.', 1)[1])
            previous = [json.loads(r['manifest']) for r in db.execute('SELECT manifest FROM candidates')
                        if json.loads(r['manifest'])['delivery_id'] == manifest['delivery_id']]
            if revision != 1 + max([int(p['candidate_id'].rsplit('.', 1)[1]) for p in previous] or [0]):
                raise ValueError('RC deve usar o próximo número disponível desta entrega.')
            # A revised queued delivery must not leave its older RC selectable.
            for queued in db.execute("SELECT id,manifest FROM candidates WHERE state='fila'").fetchall():
                if json.loads(queued['manifest'])['delivery_id'] == manifest['delivery_id']:
                    db.execute("UPDATE candidates SET state='substituida',version=version+1 WHERE id=?", (queued['id'],))
                    self._event(db, 'superseded_by_revision', {'replacement': candidate}, {'state': 'substituida'}, actor, queued['id'])
            replaces_current = current and self._candidate(db, current['id'])[1]['delivery_id'] == manifest['delivery_id']
            if replaces_current and not urgent:
                if current['state'] in ('publicando', 'parcial'):
                    raise ValueError('Reconcilie a publicação antes de substituir a foto.')
                db.execute("UPDATE candidates SET state='substituida',version=version+1 WHERE id=?", (current['id'],))
                self._event(db, 'superseded_by_revision', {'replacement': candidate}, {'state': 'substituida'}, actor, current['id'])
            if urgent:
                if current and current['state'] in ('publicando', 'parcial'):
                    raise ValueError('Reconcilie a publicação parcial/em andamento antes da urgência.')
                # _manifest already checks ancestry from the frozen production.
                if current:
                    db.execute("UPDATE candidates SET state='substituida',version=version+1 WHERE id=?", (current['id'],))
                    self._event(db, 'superseded_by_urgency', {'urgent': candidate}, {'state': 'substituida'}, actor, current['id'])
            state = 'em_aprovacao' if not current or urgent or replaces_current else 'fila'
            db.execute('INSERT INTO candidates(id,manifest,hash,state) VALUES (?,?,?,?)', (candidate, canonical(manifest), digest(manifest), state))
            db.execute('INSERT INTO tags VALUES (?,?,1)', (manifest['tag'], manifest['source_sha']))
            return self._status(db, candidate)
        return self._write('prepare_urgent' if urgent else 'prepare', {'manifest': manifest}, apply, actor, candidate, request_id=request_id)

    def _approval(self, candidate, role, manifest_hash, active, actor, request_id):
        if role not in ROLES:
            # Still audit wrong roles and unauthorized actors through the common transaction.
            def invalid(db):
                raise ValueError('Só Samuel e Vinícius contam para aprovação da versão.')
            return self._write('approve' if active else 'revoke', {'role': role}, invalid, actor, candidate, role)
        def apply(db):
            row, manifest = self._valid(db, candidate, manifest_hash)
            if row['state'] == 'publicando' and active:
                raise ValueError('Publicação já iniciada; não acrescentar novos avais nesta fase.')
            db.execute('INSERT OR REPLACE INTO approvals VALUES (?,?,?,?)', (candidate, role, row['hash'], int(active)))
            if row['state'] not in ('publicando', 'parcial'):
                count = db.execute('SELECT count(*) FROM approvals WHERE candidate=? AND active=1', (candidate,)).fetchone()[0]
                state = 'autorizada' if count == 2 else 'em_aprovacao'
                db.execute('UPDATE candidates SET state=?,version=version+1 WHERE id=?', (state, candidate))
            else:
                db.execute('UPDATE candidates SET version=version+1 WHERE id=?', (candidate,))
            return self._status(db, candidate)
        return self._write('approve' if active else 'revoke', {'role': role, 'hash': manifest_hash}, apply, actor, candidate, role, request_id)

    def approve(self, candidate_id, role, manifest_hash, actor=OPERATOR, request_id=None):
        return self._approval(candidate_id, role, manifest_hash, True, actor, request_id)

    def revoke(self, candidate_id, role, manifest_hash, actor=OPERATOR, request_id=None):
        return self._approval(candidate_id, role, manifest_hash, False, actor, request_id)

    def activate_next(self, actor=OPERATOR):
        def apply(db):
            if db.execute("SELECT 1 FROM candidates WHERE state IN ('em_aprovacao','autorizada','publicando','parcial')").fetchone():
                raise ValueError('Já existe uma candidata ativa; fila permanece serial.')
            row = db.execute("SELECT id,manifest FROM candidates WHERE state='fila' ORDER BY seq LIMIT 1").fetchone()
            if not row:
                return {'state': 'fila_vazia', 'simulation': True}
            record = json.loads(row['manifest'])
            state = 'em_aprovacao' if record['production'] == self._get(db, 'production') else 'bloqueada'
            db.execute('UPDATE candidates SET state=?,version=version+1 WHERE id=?', (state, row['id']))
            return self._status(db, row['id'])
        return self._write('activate_next', {}, apply, actor)

    def _publication_ready(self, db, candidate, manifest_hash):
        row, manifest = self._valid(db, candidate, manifest_hash)
        count = db.execute('SELECT count(*) FROM approvals WHERE candidate=? AND hash=? AND active=1', (candidate, manifest_hash)).fetchone()[0]
        if count != 2:
            raise ValueError(f'PUBLICAÇÃO BLOQUEADA: {count}/2 simulado.')
        if any(r['status'] not in ('patch_previsto', 'web') for r in manifest['pre_analysis'].values()):
            raise ValueError('Destino pendente ou loja necessária; sem fallback automático.')
        return row, manifest

    def _provider(self, db, candidate, adapter, allow_new=False):
        key = 'provider:' + candidate
        identity = str(adapter.db_path.resolve())
        row = db.execute('SELECT value FROM settings WHERE key=?', (key,)).fetchone()
        if row:
            if json.loads(row['value']) != identity:
                raise ValueError('Provedor diferente do início da publicação; preserve o mesmo journal.')
        elif allow_new:
            self._put(db, key, identity)
        else:
            raise ValueError('Publicação sem identidade do provedor; não presumir ausência de efeitos.')

    @contextmanager
    def _lease(self):
        with open(str(self.path) + '.publication.lock', 'a') as lease:
            try:
                fcntl.flock(lease.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
            except BlockingIOError:
                raise ValueError('Publicação/reconciliação já executando neste laboratório.')
            try:
                yield
            finally:
                fcntl.flock(lease.fileno(), fcntl.LOCK_UN)

    def publish(self, candidate_id, manifest_hash, command_id, repo, adapter, actor=OPERATOR):
        if not command_id:
            raise ValueError('Publicar agora requer identificador de comando.')
        with self._lease():
            return self._publish(candidate_id, manifest_hash, command_id, repo, adapter, actor)

    def _publish(self, candidate_id, manifest_hash, command_id, repo, adapter, actor):
        if not isinstance(adapter, FakePublisher):
            raise ValueError('Este laboratório só permite o publicador dry-run local.')
        # Claim in a transaction before any provider effect. SQLite serializes competing callers.
        with self.connection() as db:
            db.execute('BEGIN IMMEDIATE')
            try:
                if actor != self._get(db, 'operator'):
                    raise ValueError('Operador não autorizado para Publicar agora.')
                self._provider(db, candidate_id, adapter, allow_new=True)
                old = db.execute('SELECT * FROM commands WHERE id=?', (command_id,)).fetchone()
                if old:
                    if old['candidate'] != candidate_id or old['hash'] != manifest_hash:
                        raise ValueError('Comando já utilizado para outro registro.')
                    result = json.loads(old['result'])
                    db.commit()
                    return result
                row, manifest = self._publication_ready(db, candidate_id, manifest_hash)
                if Path(repo).resolve() != Path(manifest['repository_path']).resolve():
                    raise ValueError('Checkout de outro repositório.')
                if row['state'] == 'publicando':
                    raise ValueError('Publicação em andamento; reconcilie antes de retomar.')
                if db.execute("SELECT 1 FROM destinations WHERE candidate=? AND state IN ('executando','resultado_desconhecido')", (candidate_id,)).fetchone():
                    raise ValueError('Reconcilie resultados desconhecidos antes de repetir.')
                result = {'candidate_id': candidate_id, 'state': 'publicando', 'simulation': True, 'command_id': command_id}
                db.execute('INSERT INTO commands VALUES (?,?,?,?,?)', (command_id, candidate_id, manifest_hash, 'publicando', canonical(result)))
                db.execute("UPDATE candidates SET state='publicando',version=version+1 WHERE id=?", (candidate_id,))
                for dest in manifest['targets']:
                    key = digest({'candidate': candidate_id, 'manifest': manifest_hash, 'destination': dest})
                    db.execute("INSERT OR IGNORE INTO destinations VALUES (?,?,?,'pendente',NULL,NULL)", (candidate_id, dest, key))
                self._event(db, 'publish_now', {'command_id': command_id}, result, actor, candidate_id)
                db.commit()
            except Exception as error:
                db.rollback()
                self._event(db, 'publish_now', {'command_id': command_id, 'attempted_actor': actor},
                            {'accepted': False, 'reason': str(error)}, OPERATOR, candidate_id)
                raise
        try:
            with snapshots.isolated_checkout(repo, manifest['source_sha'], manifest['source_tree']) as checkout:
                for dest in sorted(manifest['targets']):
                    with self.connection() as db:
                        db.execute('BEGIN IMMEDIATE')
                        self._publication_ready(db, candidate_id, manifest_hash)
                        item = db.execute('SELECT * FROM destinations WHERE candidate=? AND destination=?', (candidate_id, dest)).fetchone()
                        if item['state'] == 'sucesso':
                            db.commit()
                            continue
                        db.execute("UPDATE destinations SET state='executando',error=NULL WHERE candidate=? AND destination=?", (candidate_id, dest))
                        db.commit()
                    try:
                        receipt = adapter.publish(item['operation_key'], dest, manifest, checkout)
                    except Exception as error:
                        state = 'resultado_desconhecido' if isinstance(error, TimeoutError) else 'falha'
                        with self.connection() as db:
                            db.execute('UPDATE destinations SET state=?,error=? WHERE candidate=? AND destination=?', (state, str(error), candidate_id, dest))
                        break
                    self._confirm(candidate_id, dest, receipt, actor)
        except Exception as error:
            with self.connection() as db:
                self._event(db, 'publication_blocked', {}, {'reason': str(error)}, actor, candidate_id)
        return self._finish(candidate_id, command_id, actor)

    def _confirm(self, candidate, dest, receipt, actor):
        with self.connection() as db:
            db.execute('BEGIN IMMEDIATE')
            row, manifest = self._candidate(db, candidate)
            item = db.execute('SELECT * FROM destinations WHERE candidate=? AND destination=?', (candidate, dest)).fetchone()
            if (receipt.get('operation_key') != item['operation_key'] or receipt.get('source_sha') != manifest['source_sha']
                    or receipt.get('manifest_hash') != row['hash'] or receipt.get('destination') != dest
                    or receipt.get('dry_run') is not True or receipt.get('distribution_performed') is not False):
                db.rollback()
                raise ValueError('Recibo incompatível com o snapshot e destino aprovados.')
            db.execute("UPDATE destinations SET state='sucesso',receipt=?,error=NULL WHERE candidate=? AND destination=?", (canonical(receipt), candidate, dest))
            tag = receipt['result_tag']
            old = db.execute('SELECT sha FROM tags WHERE name=?', (tag,)).fetchone()
            if old and old['sha'] != manifest['source_sha']:
                db.rollback()
                raise ValueError('Tag já aponta para outra foto; não mover.')
            db.execute('INSERT OR IGNORE INTO tags VALUES (?,?,1)', (tag, manifest['source_sha']))
            self._event(db, 'destination_confirmed', {'destination': dest}, receipt, actor, candidate)
            db.commit()

    def _finish(self, candidate, command_id=None, actor=OPERATOR):
        with self.connection() as db:
            db.execute('BEGIN IMMEDIATE')
            row, manifest = self._candidate(db, candidate)
            items = db.execute('SELECT * FROM destinations WHERE candidate=?', (candidate,)).fetchall()
            complete = len(items) == len(manifest['targets']) and all(i['state'] == 'sucesso' for i in items)
            # If approvals were revoked after provider effect, preserve partial recovery explicitly.
            approved = db.execute('SELECT count(*) FROM approvals WHERE candidate=? AND active=1', (candidate,)).fetchone()[0]
            complete = complete and approved == 2
            state = 'concluida' if complete else 'parcial'
            if complete:
                production = {'source_sha': manifest['source_sha'], 'revision': manifest['production']['revision'] + 1,
                              'destinations': {i['destination']: json.loads(i['receipt']) for i in items},
                              'evidence': 'dry_run_receipts', 'simulation': True}
                self._put(db, 'production', production)
                db.execute('INSERT OR IGNORE INTO tags VALUES (?,?,1)', (manifest['delivery_id'], manifest['source_sha']))
            db.execute('UPDATE candidates SET state=?,version=version+1 WHERE id=?', (state, candidate))
            result = self._status(db, candidate)
            db.execute('UPDATE commands SET state=?,result=? WHERE candidate=?', (state, canonical(result), candidate))
            self._event(db, 'publication_result', {}, {'state': state, 'dry_run': True, 'distribution_performed': False}, actor, candidate)
            db.commit()
            return result

    def reconcile(self, candidate_id, repo, adapter, actor=OPERATOR):
        with self._lease():
            return self._reconcile(candidate_id, repo, adapter, actor)

    def _reconcile(self, candidate_id, repo, adapter, actor):
        if actor != OPERATOR or not isinstance(adapter, FakePublisher):
            raise ValueError('Reconciliação só aceita operador e publicador do laboratório.')
        with self.connection() as db:
            row, manifest = self._candidate(db, candidate_id)
            if row['state'] not in ('publicando', 'parcial') or Path(repo).resolve() != Path(manifest['repository_path']).resolve():
                raise ValueError('Reconcilie somente a publicação ativa no repositório correto.')
            self._provider(db, candidate_id, adapter)
            items = db.execute('SELECT * FROM destinations WHERE candidate=?', (candidate_id,)).fetchall()
        for item in items:
            if item['state'] == 'sucesso':
                continue
            receipt = adapter.lookup(item['operation_key'])
            if receipt:
                self._confirm(candidate_id, item['destination'], receipt, actor)
            elif item['state'] in ('executando', 'resultado_desconhecido'):
                # The local fake provider has authoritative negative lookup; a real provider might not.
                with self.connection() as db:
                    db.execute("UPDATE destinations SET state='pendente',error=NULL WHERE candidate=? AND destination=?", (candidate_id, item['destination']))
        return self._finish(candidate_id, actor=actor)

    def abandon(self, candidate_id, repo, adapter, actor=OPERATOR):
        """Close a failed attempt only after authoritative zero-effect lookup.

        This proof is available in the synchronous fake provider, not presumed
        for an external provider with delayed/uncertain results.
        """
        if not isinstance(adapter, FakePublisher):
            raise ValueError('Encerrar sem efeitos só aceita o provedor local do laboratório.')
        with self._lease():
            def apply(db):
                row, manifest = self._candidate(db, candidate_id)
                if (row['state'] not in ('publicando', 'parcial')
                        or Path(repo).resolve() != Path(manifest['repository_path']).resolve()):
                    raise ValueError('Encerre somente a tentativa ativa no repositório correto.')
                self._provider(db, candidate_id, adapter)
                items = db.execute('SELECT * FROM destinations WHERE candidate=?', (candidate_id,)).fetchall()
                if len(items) != len(manifest['targets']) or not items:
                    raise ValueError('Registro incompleto de destinos; ausência de efeitos não comprovada.')
                if any(i['state'] == 'sucesso' or adapter.lookup(i['operation_key']) for i in items):
                    raise ValueError('Há efeito confirmado no provedor; reconcilie e retome, sem substituir a RC.')
                db.execute("UPDATE destinations SET state='nao_publicado' WHERE candidate=?", (candidate_id,))
                db.execute('UPDATE approvals SET active=0 WHERE candidate=?', (candidate_id,))
                db.execute("UPDATE candidates SET state='encerrada_sem_efeito',version=version+1 WHERE id=?", (candidate_id,))
                result = self._status(db, candidate_id)
                db.execute('UPDATE commands SET state=?,result=? WHERE candidate=?',
                           ('encerrada_sem_efeito', canonical(result), candidate_id))
                return result
            return self._write('abandon_no_effect', {'provider_lookup': 'authoritative_local_journal'},
                               apply, actor, candidate_id)


class FakePublisher:
    """Idempotent provider journal; outputs describe simulated tags, never Git refs."""
    def __init__(self, directory, failures=None):
        self.directory = Path(directory)
        self.directory.mkdir(parents=True, exist_ok=True)
        self.failures = failures or {}
        self.db_path = self.directory / 'provider.sqlite'
        with closing(sqlite3.connect(self.db_path)) as db:
            db.execute('CREATE TABLE IF NOT EXISTS receipts (key TEXT PRIMARY KEY, destination TEXT, base TEXT, receipt TEXT)')

    def lookup(self, key):
        with closing(sqlite3.connect(self.db_path)) as db:
            row = db.execute('SELECT receipt FROM receipts WHERE key=?', (key,)).fetchone()
            return json.loads(row[0]) if row else None

    def publish(self, operation_key, destination, manifest, checkout):
        old = self.lookup(operation_key)
        if old:
            return old
        if snapshots.resolve_commit(checkout, 'HEAD') != manifest['source_sha'] or snapshots.source_tree(checkout, manifest['source_sha']) != manifest['source_tree']:
            raise ValueError('Publicador recebeu outra foto de código.')
        failure = self.failures.get(destination)
        if failure == 'warning':
            raise ValueError('Comparação final simulada encontrou incompatibilidade; não ignorar warning.')
        if failure == 'before':
            raise ValueError('Falha simulada antes do efeito no destino.')
        target = manifest['targets'][destination]
        base = target.get('release_version', target.get('version', 'web'))
        with closing(sqlite3.connect(self.db_path, timeout=30, isolation_level=None)) as db:
            db.execute('BEGIN IMMEDIATE')
            row = db.execute('SELECT receipt FROM receipts WHERE key=?', (operation_key,)).fetchone()
            if row:
                db.commit()
                return json.loads(row[0])
            number = 1 + db.execute('SELECT count(*) FROM receipts WHERE destination=? AND base=?', (destination, base)).fetchone()[0]
            tag = (f'web/{base}/{manifest["delivery_id"]}' if destination == 'web'
                   else f'{destination}/{base}/patch-{number}')
            receipt = {'dry_run': True, 'distribution_performed': False, 'simulation': True,
                       'operation_key': operation_key, 'destination': destination,
                       'source_sha': manifest['source_sha'], 'manifest_hash': digest(manifest),
                       'release_version': base, 'patch_number': number if destination != 'web' else None,
                       'result_tag': tag, 'provider_record_id': 'fixture:' + operation_key, 'confirmed_at': now()}
            db.execute('INSERT INTO receipts VALUES (?,?,?,?)', (operation_key, destination, base, canonical(receipt)))
            db.commit()
        if failure == 'after':
            raise TimeoutError('Timeout simulado após efeito; consulte o provedor antes de repetir.')
        return receipt


def run_demo(folder):
    """Create a fresh disposable Git fixture, then exercise approvals and partial recovery."""
    from lab_demo import run
    return run(folder)
