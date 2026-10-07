"""Atomic Git-backed snapshots of the single-operator delivery laboratory.

Only the personal repository and ``codex/delivery-state`` are writable. A commit
contains the three SQLite snapshots and required preview bytes; it never contains
the application checkout, credentials or a publication adapter. A single-parent
commit plus a non-force ref update rejects competing append-only writers. GitHub
does not offer an expected-old-SHA field on this endpoint: manual force pushes or
ref deletion are outside that guarantee and must be prohibited operationally.

Preserve the immutable manifest paths/hashes. ``load`` returns a path plan instead
of editing manifests, approvals or the fake provider's identity. Actions should
use constant physical roots and materialize preview aliases as ordinary files.

Git API references checked 2026-10-07:
https://docs.github.com/en/rest/git/refs
https://docs.github.com/en/rest/git/trees
https://docs.github.com/en/rest/git/commits
https://docs.github.com/en/rest/git/blobs
"""

import argparse
import base64
from contextlib import ExitStack, closing, contextmanager
from dataclasses import dataclass
from datetime import datetime, timezone
import fcntl
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import re
import shutil
import sqlite3
import subprocess
import sys
import tempfile


REPOSITORY = "israelhudson/flutter_code_push_example"
STATE_REF = "codex/delivery-state"
SCHEMA = 1
MAX_FILE_BYTES = 20 * 1024 * 1024
MAX_TOTAL_BYTES = 64 * 1024 * 1024
MAX_FILES = 1000
_SHA = re.compile(r"[0-9a-f]{40}\Z")
_TOKEN = re.compile(rb"(?:gh[pousr]_[A-Za-z0-9]{20,}|github_pat_[A-Za-z0-9_]{20,}"
                    rb"|xox[baprs]-[A-Za-z0-9-]{10,}|-----BEGIN [A-Z ]*PRIVATE KEY-----)")
_SECRET_KEY = re.compile(r"(?:^|_)(?:token|secret|password|authorization|credential|credentials|api_key)$", re.I)
_DBS = {"state.sqlite": {"settings", "candidates", "approvals", "technical", "events", "commands", "destinations", "tags"},
        "provider/provider.sqlite": {"receipts"}, "outbox.sqlite": {"notices"}}
_COLUMNS = {
    "settings": {"key", "value"},
    "candidates": {"seq", "id", "manifest", "hash", "state", "version"},
    "approvals": {"candidate", "role", "hash", "active"}, "technical": {"sha", "actor"},
    "events": {"seq", "id", "at", "actor", "role", "candidate", "sha", "hash", "action", "payload", "result", "request_id"},
    "commands": {"id", "candidate", "hash", "state", "result"},
    "destinations": {"candidate", "destination", "operation_key", "state", "receipt", "error"},
    "tags": {"name", "sha", "simulation"}, "receipts": {"key", "destination", "base", "receipt"},
    "notices": {"event_key", "payload_hash", "client_msg_id", "state", "slack_ts", "created_at", "sent_at"}}


def _json(value):
    try:
        return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False,
                          allow_nan=False)
    except (ValueError, TypeError) as error:
        raise StateError("Metadados de estado devem ser JSON finito.") from error


def _digest(data):
    return hashlib.sha256(data).hexdigest()


def _blob_sha(data):
    return hashlib.sha1(b"blob " + str(len(data)).encode() + b"\0" + data).hexdigest()


def _sha(value):
    if not isinstance(value, str) or not _SHA.fullmatch(value):
        raise StateError("O estado remoto requer um SHA completo GitHub.")
    return value


class StateError(ValueError):
    pass


class StateConflict(StateError):
    """Reload and review; never automatically reapply the operation to a new head."""


class StateUncertain(StateError):
    def __init__(self, expected_head, proposed_head):
        self.expected_head = expected_head
        self.proposed_head = proposed_head
        super().__init__("Confirmação do estado incerta; preserve o checkpoint e confira o MESMO commit "
                         + str(proposed_head) + " antes de qualquer novo efeito.")


class GitDataAPIError(StateError):
    def __init__(self, status=None):
        self.status = status
        super().__init__("GitHub Git Data indisponível" + (" (HTTP " + str(status) + ")." if status else "."))


def gh_api(method, path, data=None):
    """Use existing gh authentication; sanitize errors and never print API bytes."""
    metadata_read = method == "GET" and path == "repos/" + REPOSITORY
    if (not metadata_read and not path.startswith("repos/" + REPOSITORY + "/")
            or method not in ("GET", "POST", "PATCH")):
        raise StateError("Endpoint fora do repositório pessoal autorizado.")
    args = ["gh", "api", "--hostname", "github.com", path, "--include", "--method", method,
            "-H", "Accept: application/vnd.github+json", "-H", "X-GitHub-Api-Version: 2026-03-10"]
    if data is not None:
        args += ["--input", "-"]
    try:
        result = subprocess.run(args, input=None if data is None else _json(data).encode(),
                                stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=60, check=False)
    except (OSError, subprocess.TimeoutExpired):
        raise GitDataAPIError() from None
    status = re.search(rb"HTTP/[^\s]+\s+(\d{3})", result.stdout)
    code = int(status[1]) if status else None
    if result.returncode or code is None or code >= 400:
        raise GitDataAPIError(code)
    parts = re.split(rb"\r?\n\r?\n", result.stdout, maxsplit=1)
    if len(parts) != 2:
        raise GitDataAPIError(code)
    try:
        return json.loads(parts[1])
    except (ValueError, UnicodeDecodeError):
        raise GitDataAPIError(code) from None


def _check_secrets(value):
    if isinstance(value, dict):
        for key, child in value.items():
            if _SECRET_KEY.search(str(key)) and child not in (None, "", False):
                raise StateError("Campo de credencial encontrado; não persistir segredos.")
            _check_secrets(child)
    elif isinstance(value, list):
        for child in value:
            _check_secrets(child)
    elif isinstance(value, str) and _TOKEN.search(value.encode()):
        raise StateError("Credencial encontrada; não persistir segredos.")


def _validate_database(path, kind):
    try:
        with closing(sqlite3.connect(path)) as db:
            if db.execute("PRAGMA integrity_check").fetchall() != [("ok",)]:
                raise StateError("Snapshot SQLite corrompido.")
            tables = {row[0] for row in db.execute("SELECT name FROM sqlite_master WHERE type='table'")
                      if not row[0].startswith("sqlite_")}
            if tables != _DBS[kind]:
                raise StateError("Schema SQLite inesperado: " + kind + ".")
            for table in sorted(tables):
                columns = {row[1] for row in db.execute('PRAGMA table_info("' + table + '")')}
                if columns != _COLUMNS[table]:
                    raise StateError("Colunas SQLite fora do schema autorizado.")
                for row in db.execute('SELECT * FROM "' + table + '"'):
                    for cell in row:
                        if isinstance(cell, str):
                            _check_secrets(cell)
                            try:
                                _check_secrets(json.loads(cell))
                            except (json.JSONDecodeError, UnicodeDecodeError):
                                pass
            if kind == "state.sqlite":
                for key, value in db.execute("SELECT key,value FROM settings"):
                    if _SECRET_KEY.search(key) and value not in (None, "", "null", "false"):
                        raise StateError("Campo de credencial encontrado no estado; não persistir segredos.")
                operator = db.execute("SELECT value FROM settings WHERE key='operator'").fetchone()
                if operator and json.loads(operator[0]) != "local:israel":
                    raise StateError("Estado de outro operador; somente laboratório de Israel.")
                for row in db.execute("SELECT manifest,hash FROM candidates"):
                    manifest = json.loads(row[0])
                    if (manifest.get("mode") != "laboratory" or manifest.get("simulation") is not True
                            or manifest.get("author") != "local:israel"
                            or _digest(_json(manifest).encode()) != row[1]):
                        raise StateError("Manifesto/hash fora do laboratório; importação bloqueada.")
    except (sqlite3.Error, OSError, ValueError) as error:
        if isinstance(error, StateError):
            raise
        raise StateError("Não foi possível validar o snapshot SQLite.") from error


def create_empty_databases(provider_db, outbox_db):
    """Explicit bootstrap only; refuse to replace an existing provider/outbox."""
    if Path(provider_db).absolute() == Path(outbox_db).absolute():
        raise StateError("Provider e outbox requerem bancos distintos.")
    definitions = {
        Path(provider_db): "CREATE TABLE receipts (key TEXT PRIMARY KEY, destination TEXT, base TEXT, receipt TEXT)",
        Path(outbox_db): "CREATE TABLE notices (event_key TEXT PRIMARY KEY, payload_hash TEXT NOT NULL, "
                        "client_msg_id TEXT NOT NULL, state TEXT NOT NULL CHECK(state IN ('unknown','sent')), "
                        "slack_ts TEXT, created_at TEXT NOT NULL, sent_at TEXT)"}
    for path, sql in definitions.items():
        if path.exists():
            raise StateError("Bootstrap não sobrescreve um banco existente.")
    for path, sql in definitions.items():
        path.parent.mkdir(parents=True, exist_ok=True)
        with closing(sqlite3.connect(path)) as db:
            db.execute(sql)
            db.commit()


@contextmanager
def _freeze(paths):
    """Hold the publication lease and SQLite writers while taking all backups."""
    with ExitStack() as stack:
        lease = stack.enter_context(open(str(paths[0]) + ".publication.lock", "a"))
        try:
            fcntl.flock(lease.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            raise StateError("Publicação ativa; exportação do estado bloqueada.") from None
        guards = []
        try:
            for path in paths:
                if path.is_symlink() or not path.is_file():
                    raise StateError("Banco ausente/symlink; não presumir um journal vazio.")
                db = stack.enter_context(closing(sqlite3.connect(path, timeout=5, isolation_level=None)))
                db.execute("BEGIN IMMEDIATE")
                guards.append(db)
            yield
        finally:
            for db in reversed(guards):
                db.rollback()
            fcntl.flock(lease.fileno(), fcntl.LOCK_UN)


def _backup(source, destination):
    with closing(sqlite3.connect(source)) as db, closing(sqlite3.connect(destination)) as target:
        db.backup(target)
        # Repack to remove obsolete/deleted cell contents from the transport.
        target.execute("VACUUM")
    return destination.read_bytes()


@dataclass(frozen=True)
class Bundle:
    files: dict
    metadata: dict

    @property
    def payload_hash(self):
        stable = {key: value for key, value in self.metadata.items() if key != "created_at"}
        return _digest(_json(stable).encode())


def export_bundle(state_db, provider_db, outbox_db, *, actor="local:israel", previews=None,
                  repository_paths=None):
    """Backup all journals and collect previews without changing manifest hashes."""
    if actor != "local:israel":
        raise StateError("Snapshot remoto aceita somente o operador explícito do laboratório.")
    sources = [Path(path).absolute() for path in (state_db, provider_db, outbox_db)]
    if len(set(sources)) != 3:
        raise StateError("Estado, provider e outbox requerem bancos distintos.")
    files, preview_plan = {}, {}
    repositories = set(repository_paths or [])
    with _freeze(sources), tempfile.TemporaryDirectory(prefix="delivery-state-export-") as temporary:
        root = Path(temporary)
        for name, source in zip(_DBS, sources):
            destination = root / name
            destination.parent.mkdir(parents=True, exist_ok=True)
            files[name] = _backup(source, destination)
            _validate_database(destination, name)
        with closing(sqlite3.connect(root / "state.sqlite")) as db:
            manifests = [json.loads(row[0]) for row in db.execute("SELECT manifest FROM candidates")]
        selected = {str(path) for path in (previews or [])}
        for manifest in manifests:
            repositories.add(manifest["repository_path"])
            selected.add(manifest["preview"]["path"])
        for location in sorted(selected):
            path = Path(location)
            if not path.is_absolute() or path.is_symlink() or not path.is_file():
                raise StateError("Preview histórico ausente ou com caminho não fixado.")
            if path.stat().st_size > MAX_FILE_BYTES:
                raise StateError("Preview excede 20 MiB; não persistir neste transporte.")
            data = path.read_bytes()
            name = "previews/" + _digest(data) + ".zip"
            files[name] = data
            preview_plan[location] = name
        for manifest in manifests:
            data = files[preview_plan[manifest["preview"]["path"]]]
            if _digest(data) != manifest["preview"]["sha256"]:
                raise StateError("Bytes do preview divergem do manifesto imutável.")
    descriptors = {name: {"sha256": _digest(data), "size": len(data), "git_blob": _blob_sha(data)}
                   for name, data in sorted(files.items())}
    metadata = {"schema": SCHEMA, "mode": "laboratory", "simulation": True,
                "dry_run": True, "distribution_performed": False, "actor": actor,
                "created_at": datetime.now(timezone.utc).isoformat(), "files": descriptors,
                "sources": {"state_db": str(sources[0]), "provider_db": str(sources[1]),
                            "outbox_db": str(sources[2]), "repositories": sorted(repositories),
                            "previews": preview_plan}}
    bundle = Bundle(files, metadata)
    _validate_bundle(bundle)
    return bundle


def _allowed_path(path):
    return (path in _DBS or re.fullmatch(r"previews/[0-9a-f]{64}\.zip", path or "") is not None)


def _validate_bundle(bundle):
    metadata, files = bundle.metadata, bundle.files
    if not isinstance(metadata, dict) or not isinstance(files, dict):
        raise StateError("Snapshot requer arquivos e metadados explícitos.")
    if (metadata.get("schema") != SCHEMA or metadata.get("mode") != "laboratory"
            or metadata.get("simulation") is not True or metadata.get("dry_run") is not True
            or metadata.get("distribution_performed") is not False or metadata.get("actor") != "local:israel"):
        raise StateError("Schema/modo do snapshot remoto não autorizado.")
    if (not isinstance(metadata.get("files"), dict)
            or set(files) != set(metadata["files"]) or not set(_DBS) <= set(files)
            or len(files) > MAX_FILES or any(not _allowed_path(path) for path in files)):
        raise StateError("Conteúdo inesperado/incompleto na árvore do estado.")
    if sum(len(data) for data in files.values()) > MAX_TOTAL_BYTES:
        raise StateError("Snapshot excede 64 MiB.")
    for name, data in files.items():
        if not isinstance(data, bytes) or len(data) > MAX_FILE_BYTES:
            raise StateError("Arquivo de estado excede 20 MiB ou não contém bytes.")
        if metadata["files"][name] != {"sha256": _digest(data), "size": len(data), "git_blob": _blob_sha(data)}:
            raise StateError("Checksum/tamanho de arquivo do estado divergente.")
        if _TOKEN.search(data):
            raise StateError("Credencial encontrada nos bytes; exportação bloqueada.")
    _check_secrets(metadata)
    sources = metadata.get("sources", {})
    if (not isinstance(sources, dict) or not isinstance(sources.get("previews"), dict)
            or any(name not in files or not name.startswith("previews/")
                   for name in sources["previews"].values())
            or not isinstance(sources.get("repositories"), list)
            or any(not isinstance(path, str) or not Path(path).is_absolute()
                   for path in [sources.get(key) for key in ("state_db", "provider_db", "outbox_db")]
                   + list(sources["previews"]) + sources["repositories"])):
        raise StateError("Plano de caminhos do snapshot incompleto/inseguro.")


@dataclass(frozen=True)
class LoadedState:
    head_sha: str
    paths: dict
    metadata: dict
    path_plan: dict


def import_bundle(bundle, folder, *, head_sha, repository_map=None):
    """Validate into staging, then atomically install into a new/empty directory."""
    _validate_bundle(bundle)
    _sha(head_sha)
    target = Path(folder).absolute()
    if target.is_symlink() or target.exists() and (not target.is_dir() or any(target.iterdir())):
        raise StateError("Importação requer diretório novo ou vazio; não sobrescrever estado local.")
    target.parent.mkdir(parents=True, exist_ok=True)
    stage = Path(tempfile.mkdtemp(prefix=".delivery-state-import-", dir=target.parent))
    try:
        for name, data in bundle.files.items():
            destination = stage / name
            destination.parent.mkdir(parents=True, exist_ok=True)
            with destination.open("xb") as stream:
                stream.write(data)
                stream.flush()
                os.fsync(stream.fileno())
            destination.chmod(0o600)
            if name in _DBS:
                _validate_database(destination, name)
        if target.exists():
            target.rmdir()
        os.replace(stage, target)
    finally:
        if stage.exists():
            shutil.rmtree(stage)
    sources = bundle.metadata["sources"]
    paths = {"state_db": target / "state.sqlite", "provider_db": target / "provider/provider.sqlite",
             "outbox_db": target / "outbox.sqlite",
             "previews": {original: target / name for original, name in sources["previews"].items()}}
    plan = {"state_db": {"original": sources["state_db"], "materialized": str(paths["state_db"])},
            "provider_db": {"original": sources["provider_db"], "materialized": str(paths["provider_db"])},
            "outbox_db": {"original": sources["outbox_db"], "materialized": str(paths["outbox_db"])},
            "repositories": {path: str((repository_map or {}).get(path, path)) for path in sources["repositories"]},
            "previews": {path: str(destination) for path, destination in paths["previews"].items()}}
    return LoadedState(_sha(head_sha), paths, bundle.metadata, plan)


@dataclass(frozen=True)
class CommitResult:
    commit_sha: str
    current_head: str
    operation_id: str
    status: str = "committed"


def _atomic_json(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(prefix=".state-checkpoint-", dir=path.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as stream:
            stream.write(_json(value) + "\n")
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


class RemoteState:
    def __init__(self, api=None, repo=REPOSITORY, ref=STATE_REF):
        if repo != REPOSITORY or ref != STATE_REF:
            raise StateError("Persistência restrita ao ref dedicado do repositório pessoal.")
        self.api = api or gh_api
        self.base = "repos/" + repo
        self.ref_path = self.base + "/git/ref/heads/" + ref
        self.update_path = self.base + "/git/refs/heads/" + ref
        self.full_ref = "refs/heads/" + ref

    def head(self):
        try:
            response = self.api("GET", self.ref_path)
        except GitDataAPIError as error:
            if error.status == 404:
                return None
            raise
        if response.get("ref") != self.full_ref or response.get("object", {}).get("type") != "commit":
            raise StateError("Ref remoto não representa um commit de estado.")
        return _sha(response["object"]["sha"])

    def _read_bundle(self, head):
        commit = self.api("GET", self.base + "/git/commits/" + _sha(head))
        if commit.get("sha") != head or len(commit.get("parents", [])) > 1:
            raise StateError("Histórico do estado deve ser linear, sem merges.")
        tree = self.api("GET", self.base + "/git/trees/" + _sha(commit["tree"]["sha"]) + "?recursive=1")
        if tree.get("truncated") is not False:
            raise StateError("Árvore truncada; estado não pode ser importado parcialmente.")
        files = {}
        for entry in tree.get("tree", []):
            if entry.get("type") == "tree" and entry.get("mode") == "040000":
                continue
            path = entry.get("path")
            if (path != "snapshot.json" and not _allowed_path(path)
                    or entry.get("mode") != "100644" or entry.get("type") != "blob"
                    or path in files or entry.get("size", MAX_FILE_BYTES + 1) > MAX_FILE_BYTES):
                raise StateError("Arquivo/modo inesperado na árvore do estado.")
            blob = self.api("GET", self.base + "/git/blobs/" + _sha(entry["sha"]))
            try:
                data = base64.b64decode(re.sub(r"\s", "", blob["content"]), validate=True)
            except (KeyError, ValueError, TypeError):
                raise StateError("Blob de estado inválido.") from None
            if (blob.get("encoding") != "base64" or blob.get("sha") != entry["sha"]
                    or _blob_sha(data) != entry["sha"] or len(data) > MAX_FILE_BYTES):
                raise StateError("Identidade Git/tamanho dos bytes divergente.")
            files[path] = data
        try:
            envelope = json.loads(files.pop("snapshot.json"))
        except (KeyError, ValueError, UnicodeDecodeError):
            raise StateError("Metadados do estado ausentes/inválidos.") from None
        expected = envelope.pop("expected_head", None)
        parents = [parent["sha"] for parent in commit.get("parents", [])]
        if parents != ([] if expected is None else [_sha(expected)]):
            raise StateError("Commit não vincula o parent esperado do snapshot.")
        operation_id = envelope.pop("operation_id", None)
        payload_hash = envelope.pop("payload_hash", None)
        if not isinstance(operation_id, str) or not re.fullmatch(r"[A-Za-z0-9_.:-]{1,200}", operation_id):
            raise StateError("Operação do snapshot inválida.")
        bundle = Bundle(files, envelope)
        _validate_bundle(bundle)
        if bundle.payload_hash != payload_hash:
            raise StateError("Hash do snapshot completo divergente.")
        return bundle, {"operation_id": operation_id, "expected_head": expected,
                        "payload_hash": payload_hash, "commit_sha": head}

    def load(self, folder, *, revision=None, repository_map=None):
        head = _sha(revision) if revision is not None else self.head()
        if head is None:
            raise StateError("Ref de estado ausente; bootstrap explícito é necessário.")
        bundle, _ = self._read_bundle(head)
        return import_bundle(bundle, folder, head_sha=head, repository_map=repository_map)

    def _contains(self, current, proposed):
        for _ in range(10000):
            if current == proposed:
                return True
            commit = self.api("GET", self.base + "/git/commits/" + _sha(current))
            parents = commit.get("parents", [])
            if len(parents) > 1:
                raise StateError("Histórico remoto deixou de ser linear.")
            if not parents:
                return False
            current = parents[0]["sha"]
        raise StateError("Histórico excede limite; confirmar estado manualmente.")

    def reconcile_commit(self, expected_head, proposed_head):
        """Read only. A not-committed result permits retry of that exact proposal."""
        proposed = _sha(proposed_head)
        expected = _sha(expected_head) if expected_head is not None else None
        try:
            _, info = self._read_bundle(proposed)
            if info["expected_head"] != expected:
                raise StateConflict("Proposta não corresponde ao parent esperado.")
            current = self.head()
            if current is not None and self._contains(current, proposed):
                return CommitResult(proposed, current, info["operation_id"], "already_committed")
            if current == expected:
                return CommitResult(proposed, current, info["operation_id"], "not_committed")
            raise StateConflict("Snapshot remoto mudou; não repetir/reaplicar a operação automaticamente.")
        except (GitDataAPIError, OSError, TimeoutError):
            raise StateUncertain(expected, proposed) from None

    def bootstrap(self, bundle, operation_id, *, checkpoint=None):
        return self.save(bundle, None, operation_id, checkpoint=checkpoint)

    def save(self, bundle, expected_head, operation_id, *, checkpoint=None):
        """Build once, checkpoint before ref mutation, then CAS without force."""
        _validate_bundle(bundle)
        expected = _sha(expected_head) if expected_head is not None else None
        if not isinstance(operation_id, str) or not re.fullmatch(r"[A-Za-z0-9_.:-]{1,200}", operation_id):
            raise StateError("Use um identificador fixo da operação, sem texto arbitrário.")
        checkpoint = Path(checkpoint) if checkpoint else Path(bundle.metadata["sources"]["state_db"]).parent / "remote-commit-checkpoint.json"
        current = self.head()
        if current != expected:
            if current is not None:
                _, info = self._read_bundle(current)
                if info["operation_id"] == operation_id and info["payload_hash"] == bundle.payload_hash:
                    _atomic_json(checkpoint, {"schema": SCHEMA, "repository": REPOSITORY, "ref": STATE_REF,
                                             "expected_head": expected, "proposed_head": current,
                                             "operation_id": operation_id, "payload_hash": bundle.payload_hash,
                                             "status": "committed", "current_head": current})
                    return CommitResult(current, current, operation_id, "already_committed")
            raise StateConflict("Snapshot remoto mudou; recarregue e revise antes de outra operação.")
        proposal = None
        if checkpoint.exists():
            old = json.loads(checkpoint.read_text())
            if old.get("status") == "prepared":
                if (old.get("expected_head"), old.get("operation_id"), old.get("payload_hash")) != (expected, operation_id, bundle.payload_hash):
                    raise StateUncertain(old.get("expected_head"), old.get("proposed_head"))
                proposal = _sha(old["proposed_head"])
                previous, info = self._read_bundle(proposal)
                if previous.payload_hash != bundle.payload_hash or info["operation_id"] != operation_id or info["expected_head"] != expected:
                    raise StateError("Checkpoint não corresponde à proposta imutável.")
        if proposal is None:
            envelope = {**bundle.metadata, "expected_head": expected, "operation_id": operation_id,
                        "payload_hash": bundle.payload_hash}
            content = {**bundle.files, "snapshot.json": _json(envelope).encode()}
            tree_entries = []
            for path, data in sorted(content.items()):
                blob = self.api("POST", self.base + "/git/blobs", {"encoding": "base64", "content": base64.b64encode(data).decode()})
                if blob.get("sha") != _blob_sha(data):
                    raise StateError("GitHub não confirmou a identidade do blob criado.")
                tree_entries.append({"path": path, "mode": "100644", "type": "blob", "sha": blob["sha"]})
            tree = self.api("POST", self.base + "/git/trees", {"tree": tree_entries})
            commit = self.api("POST", self.base + "/git/commits", {
                "message": "LABORATORY state snapshot " + operation_id,
                "tree": _sha(tree["sha"]), "parents": [] if expected is None else [expected]})
            proposal = _sha(commit["sha"])
            _atomic_json(checkpoint, {"schema": SCHEMA, "repository": REPOSITORY, "ref": STATE_REF,
                                     "expected_head": expected, "proposed_head": proposal,
                                     "operation_id": operation_id, "payload_hash": bundle.payload_hash, "status": "prepared"})
        # A second read narrows races; non-force rejects a sibling writer that wins afterwards.
        if self.head() != expected:
            result = self.reconcile_commit(expected, proposal)
            if result.status == "not_committed":
                raise StateConflict("Estado mudou durante a preparação da proposta.")
        else:
            try:
                if expected is None:
                    self.api("POST", self.base + "/git/refs", {"ref": self.full_ref, "sha": proposal})
                else:
                    self.api("PATCH", self.update_path, {"sha": proposal, "force": False})
            except (GitDataAPIError, OSError, TimeoutError):
                # 409/422 and lost replies are reconciled identically. Never merge/rebase/reapply.
                result = self.reconcile_commit(expected, proposal)
                if result.status == "not_committed":
                    raise StateUncertain(expected, proposal) from None
            else:
                result = self.reconcile_commit(expected, proposal)
                if result.status == "not_committed":
                    raise StateUncertain(expected, proposal)
        _atomic_json(checkpoint, {"schema": SCHEMA, "repository": REPOSITORY, "ref": STATE_REF,
                                 "expected_head": expected, "proposed_head": proposal,
                                 "operation_id": operation_id, "payload_hash": bundle.payload_hash,
                                 "status": "committed", "current_head": result.current_head})
        return CommitResult(proposal, result.current_head, operation_id, "committed")


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    load = commands.add_parser("load")
    load.add_argument("--folder", required=True)
    load.add_argument("--revision")
    for name in ("save", "bootstrap"):
        command = commands.add_parser(name)
        command.add_argument("--db", required=True)
        command.add_argument("--provider-db", required=True)
        command.add_argument("--outbox-db", required=True)
        command.add_argument("--operation-id", required=True)
        command.add_argument("--checkpoint", required=True)
        if name == "save":
            command.add_argument("--expected-head", required=True)
    confirm = commands.add_parser("confirm")
    confirm.add_argument("--checkpoint", required=True)
    args = parser.parse_args(argv)
    try:
        remote = RemoteState()
        if args.command == "load":
            result = remote.load(args.folder, revision=args.revision)
            output = {"head_sha": result.head_sha, "paths": result.paths, "path_plan": result.path_plan}
        elif args.command == "confirm":
            checkpoint = json.loads(Path(args.checkpoint).read_text())
            result = remote.reconcile_commit(checkpoint["expected_head"], checkpoint["proposed_head"])
            output = result.__dict__
        else:
            bundle = export_bundle(args.db, args.provider_db, args.outbox_db)
            result = remote.save(bundle, args.expected_head if args.command == "save" else None,
                                 args.operation_id, checkpoint=args.checkpoint)
            output = result.__dict__
        print(json.dumps(output, ensure_ascii=False, indent=2, default=str))
        return 0
    except (StateError, OSError, sqlite3.Error) as error:
        message = str(error) if isinstance(error, StateError) else "Arquivos de estado indisponíveis; operação bloqueada."
        print(json.dumps({"mode": "laboratory", "simulation": True, "error": message}), file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
