"""Fixed Git snapshots and conservative, offline patch pre-analysis.

``patch_previsto`` is a prediction from versioned files and declared inputs. It
does not examine the native binaries stored by Shorebird, fetch dependencies,
verify a provider release or run a build. A later authorized Shorebird comparison
must still block unsupported differences. Unknown dependency/manifest changes
fail closed as ``pendente``; no decision falls back automatically to a store.
"""

from contextlib import contextmanager
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import re
import subprocess
import tempfile
import zipfile


_SHA = re.compile(r"(?:[0-9a-f]{40}|[0-9a-f]{64})\Z")
_DIGEST = re.compile(r"[0-9a-f]{64}\Z")
_DOC_PREFIXES = ("docs/", "referencias/", "delivery/candidates/")
_DOC_FILES = ("README.md", "AGENTS.md")
_TOOLCHAIN_FIELDS = ("flutter_version", "flutter_revision", "flavor", "entrypoint")


def _canonical(value):
    try:
        return json.dumps(value, sort_keys=True, separators=(",", ":"),
                          ensure_ascii=False, allow_nan=False)
    except (TypeError, ValueError) as error:
        raise ValueError("Os inputs devem ser JSON completo e finito.") from error


def _environment():
    # A local clone must not inherit an injected Git dir, global hooks or filters.
    env = {key: value for key, value in os.environ.items()
           if not key.startswith("GIT_")}
    env.update(GIT_CONFIG_NOSYSTEM="1", GIT_CONFIG_GLOBAL=os.devnull,
               GIT_ATTR_NOSYSTEM="1", GIT_TERMINAL_PROMPT="0",
               GIT_LFS_SKIP_SMUDGE="1")
    return env


def _git(repo, *args):
    command = ["git", "-c", "core.hooksPath=" + os.devnull,
               "-c", "maintenance.auto=false", "-c", "gc.auto=0",
               "-C", str(Path(repo).resolve()), *args]
    result = subprocess.run(command, check=False, stdout=subprocess.PIPE,
                            stderr=subprocess.PIPE, env=_environment())
    if result.returncode:
        detail = result.stderr.decode("utf-8", "replace").strip()
        raise ValueError("Não foi possível conferir o snapshot Git: " + detail)
    return result.stdout


def resolve_commit(repo, ref):
    """Resolve a ref once, peeling annotated tags, and return its full commit SHA."""
    if (not isinstance(ref, str) or not ref.strip() or ref != ref.strip()
            or ref.lower() == "latest" or "\x00" in ref or "\n" in ref):
        raise ValueError("Escolha uma referência explícita; latest é proibido.")
    value = _git(repo, "rev-parse", "--verify", "--end-of-options",
                 ref + "^{commit}").decode("ascii").strip()
    if not _SHA.fullmatch(value):
        raise ValueError("O Git não devolveu um SHA completo de commit.")
    return value


def _exact_commit(repo, sha):
    if not isinstance(sha, str) or not _SHA.fullmatch(sha):
        raise ValueError("A base deve usar um SHA completo, nunca uma branch/latest.")
    if resolve_commit(repo, sha) != sha:
        raise ValueError("O SHA informado não corresponde ao commit.")
    return sha


def source_tree(repo, sha):
    """Identify the complete versioned tree, not a diff or a mutable checkout."""
    commit = _exact_commit(repo, sha)
    return _git(repo, "rev-parse", commit + "^{tree}").decode("ascii").strip()


def require_ancestor(repo, base_sha, source_sha):
    """Require an exact candidate to descend from the fixed production snapshot.

    This guard belongs to candidate preparation, not the patch comparison: each
    platform's release-base can legitimately differ from current production.
    Equal SHAs are permitted; older, divergent and orphan snapshots are rejected.
    """
    baseline = _exact_commit(repo, base_sha)
    candidate = _exact_commit(repo, source_sha)
    result = subprocess.run(
        ["git", "-c", "core.hooksPath=" + os.devnull, "-C", str(Path(repo).resolve()),
         "merge-base", "--is-ancestor", baseline, candidate],
        check=False, stdout=subprocess.PIPE, stderr=subprocess.PIPE, env=_environment())
    if result.returncode == 1:
        raise ValueError("O snapshot candidato é antigo, divergente ou órfão: deve descender "
                         "do SHA completo da produção confirmada.")
    if result.returncode:
        detail = result.stderr.decode("utf-8", "replace").strip()
        raise ValueError("Não foi possível conferir ancestralidade da produção: " + detail)


def _entries(repo, sha):
    records = _git(repo, "ls-tree", "-r", "--full-tree", "-z", sha).split(b"\x00")
    entries = []
    for record in records:
        if not record:
            continue
        identity, path = record.split(b"\t", 1)
        mode, kind, oid = identity.decode("ascii").split(" ")
        try:
            filename = path.decode("utf-8")
        except UnicodeDecodeError as error:
            raise ValueError("Nome de arquivo não UTF-8 requer revisão explícita.") from error
        entries.append((mode, kind, oid, filename))
    return entries


def build_fingerprint(repo, sha, inputs):
    """Hash build inputs plus every tree entry except the explicit doc allowlist.

    Scripts, CI, lockfiles, modes, submodule IDs and build configuration remain in
    the identity. Its format is versioned and intentionally differs from the old
    POC fingerprint; old metadata must be regenerated rather than silently trusted.
    """
    commit = _exact_commit(repo, sha)
    if not isinstance(inputs, dict):
        raise ValueError("Inputs de build devem ser um objeto JSON explícito.")
    files = [list(entry) for entry in _entries(repo, commit)
             if not entry[3].startswith(_DOC_PREFIXES)
             and entry[3] not in _DOC_FILES]
    value = {"schema": "delivery-snapshot-v1", "files": files, "inputs": inputs}
    return hashlib.sha256(_canonical(value).encode("utf-8")).hexdigest()


def changelog(repo, base, sha):
    """List candidate commits absent from the explicit production baseline."""
    baseline, commit = _exact_commit(repo, base), _exact_commit(repo, sha)
    output = _git(repo, "log", "--reverse", "--format=%H%x00%s%x00",
                  baseline + ".." + commit)
    parts = output.decode("utf-8").split("\x00")
    return [{"sha": parts[index].strip(), "subject": parts[index + 1]}
            for index in range(0, len(parts) - 1, 2)]


def _blob(repo, sha, path):
    exists = _git(repo, "ls-tree", "-z", sha, "--", path)
    if not exists:
        return None
    try:
        return _git(repo, "show", sha + ":" + path).decode("utf-8")
    except UnicodeDecodeError as error:
        raise ValueError("Manifesto não UTF-8; classificação pendente.") from error


def _changed_paths(repo, base, sha):
    output = _git(repo, "diff", "--name-only", "--no-renames", "-z", base, sha, "--")
    return sorted(path.decode("utf-8") for path in output.split(b"\x00") if path)


def _yaml_scalar(text):
    """Read only simple YAML path scalars; unknown syntax is not guessed."""
    text = text.strip()
    if text.startswith('"'):
        try:
            value = json.loads(text)
        except ValueError as error:
            raise ValueError("Declaração de asset não reconhecida.") from error
    elif text.startswith("'"):
        if not text.endswith("'"):
            raise ValueError("Declaração de asset não reconhecida.")
        value = text[1:-1].replace("''", "'")
    else:
        value = re.split(r"\s+#", text, maxsplit=1)[0].rstrip()
    if (not isinstance(value, str) or not value or value.startswith(("/", "~"))
            or any(token in value for token in ("*", "&", "!", "${", "[", "{", "\\"))
            or ".." in PurePosixPath(value).parts):
        raise ValueError("Declaração de asset exige classificação manual.")
    return value.removeprefix("./")


def _flutter_sections(text):
    if text is None:
        raise ValueError("pubspec.yaml ausente.")
    lines = [line.rstrip() for line in text.splitlines()
             if line.strip() and not line.lstrip().startswith("#")]
    sections, active, inside = {}, None, False
    for line in lines:
        if "\t" in line[:len(line) - len(line.lstrip())]:
            raise ValueError("Indentação YAML não reconhecida.")
        indent = len(line) - len(line.lstrip())
        if indent == 0:
            inside = line.strip() == "flutter:"
            active = None
            if line.startswith("flutter:") and not inside:
                raise ValueError("Seção Flutter inline requer análise manual.")
            continue
        if not inside:
            continue
        match = re.match(r"  ([a-zA-Z][\w-]*):(?:\s.*)?$", line)
        if match:
            active = match.group(1)
            sections[active] = [line.strip()]
        elif active:
            sections[active].append(line.strip())
        else:
            raise ValueError("Seção Flutter não reconhecida.")
    return sections


def _assets(sections):
    paths = []
    for key in ("assets", "shaders"):
        section = sections.get(key, [])
        if section and section[0] != key + ":":
            if section[0] in (key + ": []", key + ": null"):
                continue
            raise ValueError("Lista de assets inline requer análise manual.")
        for line in section[1:]:
            if not line.startswith("- "):
                raise ValueError("Asset com atributos requer análise manual.")
            paths.append(_yaml_scalar(line[2:]))
    fonts = sections.get("fonts", [])
    if fonts and fonts[0] not in ("fonts:", "fonts: []", "fonts: null"):
        raise ValueError("Lista de fontes inline requer análise manual.")
    for line in fonts[1:]:
        match = re.match(r"(?:-\s*)?asset:\s*(.+)$", line)
        if match:
            paths.append(_yaml_scalar(match.group(1)))
    return paths


def _matches_asset(path, assets):
    current = PurePosixPath(path)
    for asset in assets:
        if path == asset or (asset.endswith("/") and path.startswith(asset)):
            return True
        declared = PurePosixPath(asset)
        # Flutter also packages resolution variants of a declared image.
        if current.name == declared.name and current.parent.parent == declared.parent:
            if re.fullmatch(r"\d+(?:\.\d+)?x", current.parent.name):
                return True
    return False


def _platform_inputs(inputs, platform):
    if not isinstance(inputs, dict):
        return {}
    if "targets" in inputs:
        section = inputs["targets"]
        value = section.get(platform, {}) if isinstance(section, dict) else {}
        return value if isinstance(value, dict) else {}
    if platform in inputs:
        return inputs[platform] if isinstance(inputs[platform], dict) else {}
    return inputs


def _evidence_reasons(target, platform):
    reasons = []
    for field in ("app_id", "environment", "release_version", "release_sha",
                  "flutter_version", "flutter_revision", "entrypoint"):
        value = target.get(field)
        if not isinstance(value, str) or not value.strip() or value.lower() == "latest":
            reasons.append("Base sem " + field + " explícito (latest não é aceito).")
    if target.get("platform") != platform:
        reasons.append("A plataforma declarada não corresponde ao destino.")
    if ("flavor" not in target
            or target["flavor"] is not None and not isinstance(target["flavor"], str)
            or isinstance(target.get("flavor"), str) and target["flavor"].lower() == "latest"):
        reasons.append("Flavor da release-base não declarado (null significa padrão).")
    evidence = target.get("base_evidence")
    if not isinstance(evidence, dict) or evidence.get("kind") not in ("laboratory", "verified_release"):
        reasons.append("Evidência da base ausente; declarar laboratório ou release verificada.")
    else:
        for field in ("release_sha", "release_version", "app_id", "environment", "platform"):
            if evidence.get(field) != target.get(field):
                reasons.append("Evidência não corresponde ao alvo: " + field + ".")
        if evidence["kind"] == "verified_release" and not evidence.get("provider_record_id"):
            reasons.append("Release verificada sem identificador do registro do provedor.")
    return reasons


def pre_analyze(repo, sha, targets, inputs):
    """Classify each mobile target against its own exact release-base snapshot.

    Evidence is declared, not authenticated here. ``laboratory`` remains explicit
    in the target manifest; this function never changes an authorization policy.
    Only known Dart changes and non-mobile/documentation/tooling paths are clear
    predictions. Unsupported YAML, lockfiles, dependency declarations, gitlinks
    and unknown files require more evidence instead of guessing compatibility.
    """
    commit = _exact_commit(repo, sha)
    if not isinstance(targets, dict) or not targets:
        raise ValueError("Informe os destinos explícitos da candidata.")
    results = {}
    for platform, target in targets.items():
        if platform == "web":
            results[platform] = {"status": "web", "reasons": [
                "Preview web não comprova compatibilidade de patch mobile."], "changed_paths": []}
            continue
        if platform not in ("android", "ios") or not isinstance(target, dict):
            results[platform] = {"status": "pendente", "reasons": [
                "Destino ou contrato não reconhecido."], "changed_paths": []}
            continue
        pending = _evidence_reasons(target, platform)
        changed = []
        try:
            base = _exact_commit(repo, target.get("release_sha"))
            changed = _changed_paths(repo, base, commit)
        except ValueError as error:
            pending.append(str(error))
            results[platform] = {"status": "pendente", "reasons": pending, "changed_paths": changed}
            continue
        candidate_inputs = _platform_inputs(inputs, platform)
        stores = []
        for field in _TOOLCHAIN_FIELDS:
            if field not in candidate_inputs:
                pending.append("Input da candidata ausente: " + field + ".")
            elif (field == "flavor" and candidate_inputs[field] is not None
                  and not isinstance(candidate_inputs[field], str)
                  or field != "flavor" and (not isinstance(candidate_inputs[field], str)
                                             or not candidate_inputs[field].strip())
                  or isinstance(candidate_inputs[field], str)
                  and candidate_inputs[field].lower() == "latest"):
                pending.append("Input da candidata inválido/não fixado: " + field + ".")
            elif candidate_inputs[field] != target.get(field):
                stores.append("Input diferente da release-base: " + field + ".")
        if pending:
            # Do not label an unverified/missing base as a verified store decision.
            results[platform] = {"status": "pendente", "reasons": pending + stores, "changed_paths": changed}
            continue
        before, after, assets = {}, {}, []
        try:
            before = _flutter_sections(_blob(repo, base, "pubspec.yaml"))
            after = _flutter_sections(_blob(repo, commit, "pubspec.yaml"))
            assets = _assets(before) + _assets(after)
        except ValueError as error:
            pending.append(str(error))
        for path in changed:
            if path.startswith(_DOC_PREFIXES) or path in _DOC_FILES:
                continue
            if path.startswith(("tools/", "test/", "tests/", ".github/", "web/")):
                continue
            if path.startswith(("macos/", "linux/", "windows/")):
                continue
            if path.startswith(("android/", "ios/")):
                if path.startswith(platform + "/"):
                    stores.append("Mudança nativa/empacotada: " + path + ".")
                continue
            if path.startswith(("plugins/", "assets/", "fonts/")) or _matches_asset(path, assets):
                stores.append("Plugin ou asset empacotado alterado: " + path + ".")
            elif path == "pubspec.yaml":
                packaged = ("assets", "fonts", "shaders", "uses-material-design")
                if any(before.get(key) != after.get(key) for key in packaged):
                    stores.append("Declaração de assets/fontes/shaders alterada no pubspec.yaml.")
                else:
                    pending.append("Mudança no pubspec.yaml exige examinar dependências/build.")
            elif path == "pubspec.lock":
                pending.append("Lockfile alterado: dependências nativas/assets não classificadas.")
            elif path.startswith("lib/") and path.endswith(".dart"):
                continue
            elif path in (".gitignore", "analysis_options.yaml"):
                continue
            elif PurePosixPath(path).suffix.lower() in (
                    ".c", ".h", ".cc", ".cpp", ".m", ".mm", ".swift", ".kt",
                    ".java", ".gradle", ".kts", ".so", ".dylib", ".dll", ".a"):
                stores.append("Código/binário nativo alterado: " + path + ".")
            else:
                pending.append("Arquivo não classificado: " + path + ".")
        before_entries = {entry[3]: entry for entry in _entries(repo, base)}
        after_entries = {entry[3]: entry for entry in _entries(repo, commit)}
        for path in changed:
            for entry in (before_entries.get(path), after_entries.get(path)):
                if entry and entry[0] in ("120000", "160000"):
                    pending.append("Symlink/submódulo requer exame dos inputs: " + path + ".")
                    break
        status = "loja_necessaria" if stores else "pendente" if pending else "patch_previsto"
        reasons = stores + pending or [
            "Nenhuma incompatibilidade conhecida encontrada; comparação final Shorebird obrigatória."]
        results[platform] = {"status": status, "reasons": reasons, "changed_paths": changed}
    return results


def _file_digest(path):
    result = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            result.update(block)
    return result.hexdigest()


def validate_preview(repo, sha, preview, inputs):
    """Check bytes, expiry, declared source and full build equivalence.

    Import metadata only from a trusted producer. These consistency checks alone
    are not an attestation that a compiler produced the supplied bytes. The core
    must allow ``fixture_web`` only in explicit laboratory mode.
    """
    commit = _exact_commit(repo, sha)
    if not isinstance(preview, dict):
        raise ValueError("Preview deve conter metadados explícitos.")
    required = ("kind", "path", "source_sha", "fingerprint", "sha256", "inputs", "expires_at")
    if any(field not in preview for field in required):
        raise ValueError("Metadados de preview incompletos.")
    if preview["kind"] not in ("fixture_web", "flutter_web"):
        raise ValueError("Tipo de preview não reconhecido.")
    source = _exact_commit(repo, preview["source_sha"])
    if _canonical(preview["inputs"]) != _canonical(inputs):
        raise ValueError("Inputs do preview divergem da candidata.")
    expected = build_fingerprint(repo, commit, inputs)
    if (preview["fingerprint"] != expected
            or build_fingerprint(repo, source, preview["inputs"]) != expected):
        raise ValueError("Código/origem ou fingerprint do preview diverge da candidata.")
    try:
        expiry = datetime.fromisoformat(preview["expires_at"].replace("Z", "+00:00"))
    except (ValueError, TypeError, AttributeError) as error:
        raise ValueError("Validade do preview inválida.") from error
    if expiry.tzinfo is None or expiry <= datetime.now(timezone.utc):
        raise ValueError("Preview expirado ou sem fuso explícito.")
    if not isinstance(preview["path"], str) or not preview["path"]:
        raise ValueError("Caminho do preview inválido.")
    path = Path(preview["path"])
    if not path.is_absolute():
        path = Path(repo) / path
    if path.is_symlink() or not path.is_file():
        raise ValueError("Arquivo do preview ausente ou é symlink.")
    if not isinstance(preview["sha256"], str) or not _DIGEST.fullmatch(preview["sha256"]):
        raise ValueError("Hash dos bytes do preview divergente.")
    try:
        if _file_digest(path) != preview["sha256"]:
            raise ValueError("Hash dos bytes do preview divergente.")
    except OSError as error:
        raise ValueError("Não foi possível ler os bytes do preview.") from error
    if preview["kind"] == "flutter_web":
        try:
            with zipfile.ZipFile(path) as archive:
                names = archive.namelist()
                if "index.html" not in names or any(
                        name.startswith("/") or ".." in PurePosixPath(name).parts
                        or "\\" in name for name in names):
                    raise ValueError("ZIP web inválido ou com caminhos inseguros.")
        except (zipfile.BadZipFile, OSError) as error:
            raise ValueError("O preview Flutter deve ser um ZIP web real.") from error


@contextmanager
def isolated_checkout(repo, sha, expected_tree):
    """Yield an independent, detached, clean checkout; never mutate source refs.

    Submodules and tracked symlinks require a separate audited strategy and are
    refused here. The clone has no inherited hooks/global filters or hardlinks.
    Ignored compiler outputs may exist after the build; tracked changes and new
    non-ignored files are rejected. The temporary directory is always removed.
    """
    source = Path(repo).resolve()
    commit = _exact_commit(source, sha)
    if source_tree(source, commit) != expected_tree:
        raise ValueError("Árvore aprovada diferente do snapshot selecionado.")
    if any(entry[0] in ("120000", "160000") for entry in _entries(source, commit)):
        raise ValueError("Checkout isolado não admite symlinks/submódulos sem estratégia auditada.")
    with tempfile.TemporaryDirectory(prefix="delivery-snapshot-") as folder:
        checkout = Path(folder) / "source"
        _git(source, "clone", "--quiet", "--no-local", "--no-hardlinks", "--no-checkout",
             "--no-recurse-submodules", str(source), str(checkout))
        _git(checkout, "checkout", "--quiet", "--detach", commit)

        def verify(include_ignored=False):
            if resolve_commit(checkout, "HEAD") != commit or source_tree(checkout, commit) != expected_tree:
                raise ValueError("O checkout deixou de usar o snapshot aprovado.")
            # HEAD must stay detached, even if a local branch happens to name this SHA.
            symbolic = subprocess.run(["git", "-C", str(checkout), "symbolic-ref", "-q", "HEAD"],
                                      stdout=subprocess.PIPE, stderr=subprocess.PIPE, env=_environment())
            if symbolic.returncode != 1:
                raise ValueError("O checkout de publicação deve estar em detached HEAD.")
            flags = ["status", "--porcelain=v1", "--untracked-files=all"]
            if include_ignored:
                flags.append("--ignored=matching")
            if _git(checkout, *flags):
                raise ValueError("O checkout contém alterações ou arquivos inesperados.")

        verify(include_ignored=True)
        try:
            yield checkout
        except BaseException:
            raise
        else:
            verify()
