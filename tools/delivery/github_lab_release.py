"""Record one frozen laboratory candidate as a GitHub prerelease.

This is a separate owner-authorized archive, not the real two-review publisher.
The remote laboratory state is read only. Tags are bootstrapped separately by
the owner from tag-spec.json; this helper never creates or moves a Git ref.
"""
import argparse
import base64
from contextlib import closing
from datetime import datetime, timezone
import hashlib
import io
import json
import os
from pathlib import Path, PurePosixPath
import re
import sqlite3
import subprocess
import sys
import tempfile
from urllib.parse import quote
import zipfile

from policy import canonical, digest
from remote_state import GitDataAPIError, RemoteState, gh_api

REPO = 'israelhudson/flutter_code_push_example'
BASE = 'repos/' + REPO
URL = 'https://github.com/' + REPO
WORKFLOW = REPO + '/.github/workflows/github-lab-release.yaml@refs/heads/main'
ROLES = ['samuel', 'vinicius']
SCHEMA = 'github-lab-release-v1'
ASSETS = ('candidate.json', 'receipt.json', 'preview.zip', 'checksums.sha256')


class ReleaseError(ValueError):
    pass


def sha256(data):
    return hashlib.sha256(data).hexdigest()


def encode(value):
    return (canonical(value) + '\n').encode()


def atomic_json(path, value):
    path = Path(path)
    if path.is_symlink():
        raise ReleaseError('Arquivo de saída não pode ser symlink.')
    fd, temporary = tempfile.mkstemp(prefix='.release-json-', dir=path.parent)
    with os.fdopen(fd, 'wb') as stream:
        stream.write(encode(value)); stream.flush(); os.fsync(stream.fileno())
    os.replace(temporary, path)


class Audit:
    """Only deliberately selected identities/statuses enter the JSONL log."""
    FIELDS = {'candidate_id', 'source_sha', 'manifest_hash', 'release_identity', 'state_head',
              'run_id', 'actor_id', 'login', 'operation', 'release_id', 'asset', 'sha256',
              'size', 'status', 'http_status', 'published', 'tag_sha', 'simulated_count'}
    FIELDS |= {'reason', 'error_type', 'version', 'fingerprint'}

    def __init__(self, folder):
        self.folder = Path(folder)
        if self.folder.is_symlink():
            raise ReleaseError('Diretório de saída não pode ser symlink.')
        self.folder.mkdir(parents=True, exist_ok=True)
        if (self.folder / 'release-events.jsonl').is_symlink():
            raise ReleaseError('Log não pode ser symlink.')

    def event(self, event, **fields):
        if set(fields) - self.FIELDS:
            raise ReleaseError('Campo fora da lista permitida no log.')
        record = {'at': datetime.now(timezone.utc).isoformat(), 'event': event, **fields}
        with (self.folder / 'release-events.jsonl').open('ab') as stream:
            stream.write(encode(record)); stream.flush(); os.fsync(stream.fileno())

    def checkpoint(self, **fields):
        if set(fields) - self.FIELDS:
            raise ReleaseError('Campo fora da lista permitida no checkpoint.')
        atomic_json(self.folder / 'checkpoint.json', {'schema': SCHEMA, **fields})


def authenticate(environment, api):
    if (environment.get('GITHUB_ACTIONS') != 'true' or environment.get('GITHUB_REPOSITORY') != REPO
            or environment.get('GITHUB_EVENT_NAME') != 'workflow_dispatch'
            or environment.get('GITHUB_REF') != 'refs/heads/main'
            or environment.get('GITHUB_WORKFLOW_REF') != WORKFLOW):
        raise ReleaseError('Use somente Publicar registro do laboratório, manualmente na main pessoal.')
    repository = api('GET', BASE)
    owner = repository.get('owner', {})
    if (repository.get('full_name') != REPO or owner.get('login') != 'israelhudson'
            or environment.get('GITHUB_ACTOR') != owner.get('login')
            or environment.get('GITHUB_ACTOR_ID') != str(owner.get('id'))
            or environment.get('GITHUB_TRIGGERING_ACTOR') != owner.get('login')
            or environment.get('GITHUB_TRIGGERING_ACTOR_ID', str(owner.get('id'))) != str(owner.get('id'))):
        raise ReleaseError('A autorização real deve ser do proprietário Israel autenticado pelo GitHub.')
    run = environment.get('GITHUB_RUN_ID', '')
    if not re.fullmatch(r'[1-9]\d*', run):
        raise ReleaseError('Identidade da execução GitHub inválida.')
    return {'login': owner['login'], 'id': owner['id'], 'identity_source': 'github_actions',
            'run_id': run, 'run_url': URL + '/actions/runs/' + run}


def read_candidate(loaded, candidate, manifest_hash):
    with closing(sqlite3.connect(Path(loaded.paths['state_db']).as_uri() + '?mode=ro', uri=True)) as db:
        db.row_factory = sqlite3.Row
        row = db.execute('SELECT * FROM candidates WHERE id=?', (candidate,)).fetchone()
        if row is None:
            raise ReleaseError('Candidata inexistente no estado remoto.')
        manifest = json.loads(row['manifest'])
        if row['hash'] != manifest_hash or digest(manifest) != manifest_hash:
            raise ReleaseError('Hash do manifesto diverge da candidata congelada.')
        if (manifest.get('schema') != 2 or manifest.get('mode') != 'laboratory'
                or manifest.get('simulation') is not True or manifest.get('author') != 'local:israel'
                or manifest.get('required_roles') != ROLES or manifest.get('policy') != 'laboratory-v1'
                or manifest.get('candidate_id') != candidate or manifest.get('tag') != candidate
                or manifest.get('delivery_id') != candidate.rsplit('-rc.', 1)[0]
                or manifest.get('release_ref') != 'release/' + manifest.get('delivery_id', '')):
            raise ReleaseError('Manifesto não representa a identidade explícita do laboratório.')
        if row['state'] not in ('autorizada', 'concluida'):
            raise ReleaseError('Registro final exige candidata autorizada ou concluída.')
        approvals = db.execute('SELECT role,hash,active FROM approvals WHERE candidate=?', (candidate,)).fetchall()
        if (len(approvals) != 2 or sorted(a['role'] for a in approvals) != ROLES
                or any(a['hash'] != manifest_hash or a['active'] != 1 for a in approvals)):
            raise ReleaseError('Os dois papéis simulados precisam aprovar este mesmo hash.')
        if row['state'] == 'autorizada':
            production = db.execute("SELECT value FROM settings WHERE key='production'").fetchone()
            if production is None or json.loads(production[0]) != manifest.get('production'):
                raise ReleaseError('Base da candidata autorizada ficou obsoleta.')
    source = manifest.get('source_sha', '')
    if not re.fullmatch(r'[0-9a-f]{40}', source):
        raise ReleaseError('Fonte requer SHA40 congelado.')
    preview = manifest.get('preview', {})
    if (preview.get('kind') != 'flutter_web' or preview.get('source_sha') != source
            or preview.get('source_tree') != manifest.get('source_tree')
            or preview.get('inputs') != manifest.get('inputs')
            or not re.fullmatch(r'[0-9a-f]{64}', preview.get('fingerprint', ''))
            or not re.fullmatch(r'[0-9a-f]{64}', preview.get('sha256', ''))):
        raise ReleaseError('Preview não identifica o build Flutter congelado desta candidata.')
    path = loaded.paths['previews'].get(preview.get('path'))
    if path is None or Path(path).is_symlink() or not Path(path).is_file():
        raise ReleaseError('ZIP congelado ausente no snapshot remoto.')
    data = Path(path).read_bytes()
    if sha256(data) != preview['sha256']:
        raise ReleaseError('Hash do ZIP congelado divergente.')
    try:
        with zipfile.ZipFile(io.BytesIO(data)) as archive:
            entries = archive.infolist()
            if (not entries or len(entries) > 10000 or sum(e.file_size for e in entries) > 200 * 1024 * 1024
                    or 'index.html' not in archive.namelist()
                    or len(set(archive.namelist())) != len(entries)
                    or any(e.filename.startswith('/') or '..' in PurePosixPath(e.filename).parts
                           or '\\' in e.filename or (e.external_attr >> 16) & 0o170000 == 0o120000 for e in entries)
                    or archive.testzip() is not None):
                raise ReleaseError('ZIP web inválido/inseguro.')
    except (zipfile.BadZipFile, RuntimeError, OSError):
        raise ReleaseError('ZIP web congelado não é íntegro.') from None
    return manifest, data


def source_version(api, manifest):
    source = manifest['source_sha']
    commit = api('GET', BASE + '/git/commits/' + source)
    if commit.get('sha') != source or commit.get('tree', {}).get('sha') != manifest.get('source_tree'):
        raise ReleaseError('SHA/árvore GitHub divergem da fonte congelada.')
    file = api('GET', BASE + '/contents/pubspec.yaml?ref=' + source)
    try:
        data = base64.b64decode(re.sub(r'\s', '', file['content']), validate=True)
        match = re.search(r'^version:\s*(\d+\.\d+\.\d+\+\d+)\s*$', data.decode(), re.M)
    except (ValueError, KeyError, UnicodeDecodeError):
        raise ReleaseError('pubspec.yaml do SHA congelado inválido.') from None
    blob = hashlib.sha1(b'blob ' + str(len(data)).encode() + b'\0' + data).hexdigest()
    if file.get('encoding') != 'base64' or file.get('sha') != blob or match is None:
        raise ReleaseError('Versão explícita/bytes do pubspec congelado inválidos.')
    return match[1]


def optional(api, path):
    try:
        return api('GET', path)
    except GitDataAPIError as error:
        if error.status == 404:
            return None
        raise


def tag_protection(api):
    rules = api('GET', BASE + '/rulesets?per_page=100')
    for item in rules:
        rule = api('GET', BASE + '/rulesets/' + str(item['id']))
        if (rule.get('target') == 'tag' and rule.get('enforcement') == 'active' and not rule.get('bypass_actors')
                and 'refs/tags/entrega-*-rc.*' in rule.get('conditions', {}).get('ref_name', {}).get('include', [])
                and not rule.get('conditions', {}).get('ref_name', {}).get('exclude', [])
                and {'update', 'deletion'} <= {r['type'] for r in rule.get('rules', [])}):
            return
    raise ReleaseError('Proteção imutável das tags RC ausente; nenhuma regra será alterada.')


def verify_tag(api, spec, *, required=False):
    ref = optional(api, BASE + '/git/ref/tags/' + spec['tag_name'])
    if ref is None:
        if required:
            raise ReleaseError('Tag anotada ausente. O proprietário deve criá-la exatamente conforme tag-spec.json; não use latest/main.')
        return None
    obj = ref.get('object', {})
    if ref.get('ref') != spec['ref'] or obj.get('type') != 'tag' or not re.fullmatch(r'[0-9a-f]{40}', obj.get('sha', '')):
        raise ReleaseError('Ref da RC não é a tag anotada esperada.')
    tag = api('GET', BASE + '/git/tags/' + obj['sha'])
    if (tag.get('sha') != obj['sha'] or tag.get('tag') != spec['tag_name']
            or tag.get('object', {}).get('type') != 'commit'
            or tag.get('object', {}).get('sha') != spec['source_sha']
            or tag.get('message', '').strip() != spec['message'].strip()):
        raise ReleaseError('Tag aponta para outra fonte/manifesto/identidade; nunca sobrescrever.')
    return obj['sha']


def prepare_plan(manifest, preview, owner, state_head, api, folder):
    version = source_version(api, manifest)
    candidate, source = manifest['candidate_id'], manifest['source_sha']
    identity = digest({'schema': SCHEMA, 'candidate_id': candidate, 'source_sha': source,
                       'manifest_hash': digest(manifest)})
    operator = {key: owner[key] for key in ('login', 'id', 'identity_source')}
    receipt = {'schema': SCHEMA, 'mode': 'laboratory', 'simulation': True,
               'simulation_scope': 'approval_roles_and_laboratory_core',
               'distribution_performed': False, 'candidate_id': candidate, 'tag': candidate,
               'version': version, 'source_sha': source, 'manifest_hash': digest(manifest),
               'release_identity': identity, 'real_operator': operator,
               'simulated_approvals': {'roles': ROLES, 'count': 2, 'real_review_count': 0},
               'preview_sha256': manifest['preview']['sha256']}
    assets = {'preview.zip': preview, 'candidate.json': encode(manifest), 'receipt.json': encode(receipt)}
    assets['checksums.sha256'] = ''.join(sha256(assets[name]) + '  ' + name + '\n' for name in sorted(assets)).encode()
    for name, data in assets.items():
        path = Path(folder) / name
        if path.is_symlink() or path.exists() and path.read_bytes() != data:
            raise ReleaseError('Saída local contém asset diferente; preserve evidência e use outro diretório.')
        if not path.exists():
            path.write_bytes(data)
    pages_url = 'https://israelhudson.github.io/flutter_code_push_example/snapshots/' + source + '/'
    plan = {**receipt, 'state_head': state_head, 'preview': {'pages_url': pages_url,
            'sha256': manifest['preview']['sha256'], 'fingerprint': manifest['preview']['fingerprint']},
            'assets': [{'name': name, 'sha256': sha256(data), 'size': len(data)} for name, data in sorted(assets.items())],
            'authorization_run_url': owner['run_url'], 'build_run_urls': []}
    plan['build_run_links_scope'] = 'successful_build_workflows_with_same_head_sha_not_an_artifact_attestation'
    try:
        runs = api('GET', BASE + '/actions/runs?head_sha=' + source + '&status=success&per_page=100')
        plan['build_run_urls'] = [URL + '/actions/runs/' + str(r['id']) for r in runs.get('workflow_runs', [])
                                  if r.get('head_sha') == source and r.get('conclusion') == 'success'
                                  and r.get('path') in ('.github/workflows/mobile-build.yaml',
                                      '.github/workflows/delivery-preview.yml', '.github/workflows/web-preview-pages.yaml')
                                  and type(r.get('id')) is int and r['id'] > 0]
    except GitDataAPIError:
        plan['build_run_links_status'] = 'unavailable'
    spec = {'schema': 'github-lab-tag-v1', 'tag_name': candidate, 'source_sha': source,
            'manifest_hash': digest(manifest), 'release_identity': identity, 'object_type': 'commit',
            'ref': 'refs/tags/' + candidate,
            'message': 'LABORATORY ONLY\nsource-sha:' + source + '\nmanifest-sha256:' + digest(manifest)
                       + '\nrelease-identity:' + identity}
    atomic_json(Path(folder) / 'plan.json', plan)
    atomic_json(Path(folder) / 'tag-spec.json', spec)
    return plan, spec, assets


class AssetAPI:
    def upload(self, release_id, name, data):
        if type(release_id) is not int or release_id <= 0 or name not in ASSETS:
            raise ReleaseError('Identidade de upload fora do contrato.')
        path = 'https://uploads.github.com/' + BASE + '/releases/' + str(release_id) + '/assets?name=' + quote(name, safe='')
        # gh treats stdin as an unknown-size reader. The uploads endpoint requires
        # Content-Length, so set the byte length rather than sending chunked input.
        # Include headers only inside this captured subprocess to retain a safe
        # numeric HTTP status; raw headers/body/stderr never enter the audit log.
        args = ['gh', 'api', '--hostname', 'github.com', path, '--method', 'POST', '--input', '-', '--include',
                '-H', 'Content-Type: application/octet-stream', '-H', 'Content-Length: ' + str(len(data)),
                '-H', 'Accept: application/vnd.github+json']
        try:
            result = subprocess.run(args, input=data, capture_output=True, timeout=60, check=False)
        except (OSError, subprocess.TimeoutExpired):
            raise GitDataAPIError() from None
        status = re.search(rb'HTTP/[^\s]+\s+(\d{3})', result.stdout)
        code = int(status[1]) if status else None
        if result.returncode or code != 201:
            raise GitDataAPIError(code)  # Never expose gh stderr, response bytes or credentials.
        parts = re.split(rb'\r?\n\r?\n', result.stdout, maxsplit=1)
        if len(parts) != 2:
            raise GitDataAPIError(code)
        try:
            return json.loads(parts[1])
        except (ValueError, UnicodeDecodeError):
            raise GitDataAPIError(code) from None


def release_body(plan):
    return ('<!-- ' + SCHEMA + ' identity:' + plan['release_identity'] + ' -->\n'
            + 'Registro final do laboratório: **' + plan['version'] + '**, `' + plan['candidate_id'] + '`.\n\n'
            + 'SHA fonte: `' + plan['source_sha'] + '`\nManifesto SHA-256: `' + plan['manifest_hash'] + '`\n\n'
            + 'Autorização real: Israel (`' + plan['real_operator']['login'] + '`).\n'
            + 'Papéis Samuel e Vinícius: **2 aprovações simuladas**, representadas por Israel; **0 reviews reais**.\n\n'
            + '[Preview web por SHA](' + plan['preview']['pages_url'] + ')\n\n'
            + 'Somente pré-release GitHub de laboratório. Distribuição mobile: **false**. '
              'Não é release/patch Shorebird, upload para loja, TestFlight ou validação Android/iOS.\n')


def validate_release(release, plan):
    if (release.get('tag_name') != plan['tag'] or release.get('prerelease') is not True
            or release.get('name') != '[LAB] ' + plan['version'] + ' · ' + plan['tag']
            or release.get('body') != release_body(plan) or type(release.get('id')) is not int
            or release['id'] <= 0 or type(release.get('draft')) is not bool):
        raise ReleaseError('Release existente tem outra identidade/conteúdo; nunca sobrescrever.')


def find_release(api, tag):
    # The tag endpoint documents published releases only. Draft recovery must
    # inspect the authenticated releases list instead of trying another POST.
    published = optional(api, BASE + '/releases/tags/' + tag)
    if published is not None:
        return published
    for page in range(1, 11):
        batch = api('GET', BASE + '/releases?per_page=100&page=' + str(page))
        matches = [item for item in batch if item.get('tag_name') == tag]
        if len(matches) > 1:
            raise ReleaseError('Mais de um registro remoto da candidata; conferir manualmente.')
        if matches:
            return matches[0]
        if len(batch) < 100:
            return None
    raise ReleaseError('Lista de releases excede limite; não presumir ausência nem criar duplicata.')


def verify_asset(asset, name, data):
    if (asset.get('name') != name or asset.get('state') != 'uploaded'
            or asset.get('size') != len(data) or asset.get('digest') != 'sha256:' + sha256(data)
            or type(asset.get('id')) is not int or asset['id'] <= 0):
        raise ReleaseError('Asset remoto diferente/incompleto; não sobrescrever nem excluir: ' + name)


def assets_on_release(api, release, assets):
    found = {}
    for page in range(1, 11):
        batch = api('GET', BASE + '/releases/' + str(release['id']) + '/assets?per_page=100&page=' + str(page))
        for asset in batch:
            name = asset.get('name')
            if name not in assets or name in found:
                raise ReleaseError('Release contém assets extras/duplicados de outra identidade.')
            verify_asset(asset, name, assets[name]); found[name] = asset
        if len(batch) < 100:
            return found
    raise ReleaseError('Lista de assets excede limite do registro.')


def mutation(audit, identity, operation, call, **fields):
    audit.checkpoint(release_identity=identity, operation=operation, status='pending', **fields)
    audit.event('mutation_before', release_identity=identity, operation=operation, **fields)
    try:
        result = call()
    except Exception as error:
        status = error.status if isinstance(error, GitDataAPIError) else None
        audit.checkpoint(release_identity=identity, operation=operation, status='uncertain', **fields)
        audit.event('mutation_uncertain', operation=operation, http_status=status, **fields)
        raise ReleaseError('Efeito GitHub incerto. Preserve checkpoint/log; uma nova execução manual pode conferir a mesma identidade, sem retry automático.') from None
    audit.event('mutation_returned', operation=operation, status='returned', **fields)
    return result


def publish(api, uploader, remote, plan, spec, assets, audit):
    tag_protection(api)
    tag_sha = verify_tag(api, spec, required=True)
    audit.event('tag_verified', tag_sha=tag_sha, source_sha=plan['source_sha'])
    release = find_release(api, plan['tag'])
    if release is None:
        release = mutation(audit, plan['release_identity'], 'create_draft', lambda: api('POST', BASE + '/releases', {
            'tag_name': plan['tag'], 'name': '[LAB] ' + plan['version'] + ' · ' + plan['tag'],
            'body': release_body(plan), 'draft': True, 'prerelease': True, 'make_latest': 'false'}))
    validate_release(release, plan)
    existing = assets_on_release(api, release, assets)
    if release['draft']:
        for name, data in sorted(assets.items()):
            if name not in existing:
                asset = mutation(audit, plan['release_identity'], 'upload_asset',
                                 lambda: uploader.upload(release['id'], name, data),
                                 release_id=release['id'], asset=name, sha256=sha256(data), size=len(data))
                verify_asset(asset, name, data)
        existing = assets_on_release(api, release, assets)
        if set(existing) != set(assets):
            raise ReleaseError('Upload não confirmado; draft preservado.')
        # A changed state never silently reapplies approval to another manifest.
        with tempfile.TemporaryDirectory(prefix='github-lab-release-recheck-') as folder:
            current = remote.load(Path(folder) / 'state')
            read_candidate(current, plan['candidate_id'], plan['manifest_hash'])
            audit.event('approval_rechecked', state_head=current.head_sha, simulated_count=2)
        verify_tag(api, spec, required=True)
        release = api('GET', BASE + '/releases/' + str(release['id']))
        validate_release(release, plan)
        if set(assets_on_release(api, release, assets)) != set(assets):
            raise ReleaseError('Assets do draft mudaram antes da publicação; preserve evidência.')
        if release['draft']:
            mutation(audit, plan['release_identity'], 'publish_draft', lambda: api('PATCH', BASE + '/releases/' + str(release['id']),
                       {'draft': False, 'prerelease': True, 'make_latest': 'false'}), release_id=release['id'])
    if set(existing) != set(assets):
        raise ReleaseError('Release publicada incompleta; recuperação manual necessária.')
    final = api('GET', BASE + '/releases/' + str(release['id']))
    validate_release(final, plan)
    if set(assets_on_release(api, final, assets)) != set(assets):
        raise ReleaseError('Assets finais não confirmados; preserve evidência.')
    expected_url = URL + '/releases/tag/' + plan['tag']
    if final['draft'] or final.get('html_url') != expected_url:
        raise ReleaseError('Publicação final não confirmada; preserve log e confira manualmente.')
    audit.checkpoint(release_identity=plan['release_identity'], release_id=final['id'], status='published', published=True)
    audit.event('publication_confirmed', release_id=final['id'], published=True)
    return {'published': True, 'release_url': expected_url, 'release_id': final['id'], 'tag_sha': tag_sha}


def run(action, candidate, manifest_hash, output, environment=None, *, api=gh_api, remote=None, uploader=None):
    audit = Audit(output)
    try:
        if action not in ('plan', 'publish') or not re.fullmatch(r'entrega-\d{4,}-rc\.[1-9]\d*', candidate or ''):
            raise ReleaseError('Ação/candidata inválida; use ID neutro completo.')
        if not re.fullmatch(r'[0-9a-f]{64}', manifest_hash or ''):
            raise ReleaseError('Informe hash SHA-256 completo do manifesto.')
        owner = authenticate(environment or os.environ, api)
        audit.event('owner_authenticated', actor_id=owner['id'], login=owner['login'], run_id=owner['run_id'])
        def readonly(method, path, data=None):
            if method != 'GET' or data is not None:
                raise ReleaseError('Estado remoto é somente leitura neste helper.')
            return api(method, path)
        remote = remote or RemoteState(api=readonly)
        with tempfile.TemporaryDirectory(prefix='github-lab-release-state-') as folder:
            loaded = remote.load(Path(folder) / 'state')
            manifest, preview = read_candidate(loaded, candidate, manifest_hash)
            audit.event('candidate_verified', candidate_id=candidate, manifest_hash=manifest_hash,
                        source_sha=manifest['source_sha'], state_head=loaded.head_sha, simulated_count=2)
            plan, spec, assets = prepare_plan(manifest, preview, owner, loaded.head_sha, api, output)
            audit.event('source_snapshot_verified', source_sha=plan['source_sha'], version=plan['version'])
            audit.event('frozen_preview_verified', sha256=manifest['preview']['sha256'], size=len(preview),
                        fingerprint=manifest['preview']['fingerprint'])
        verify_tag(api, spec)
        result = {'schema': SCHEMA, 'action': action, 'candidate_id': candidate, 'tag': candidate,
                  'version': plan['version'], 'source_sha': plan['source_sha'], 'manifest_hash': manifest_hash,
                  'release_identity': plan['release_identity'], 'published': False, 'release_url': None,
                  'distribution_performed': False, 'simulation': True, 'status': 'plan_ready'}
        result['simulation_scope'] = 'approval_roles_and_laboratory_core'
        audit.event('plan_ready', release_identity=plan['release_identity'], status='plan_ready')
        audit.checkpoint(release_identity=plan['release_identity'], status='plan_ready', published=False)
        if action == 'publish':
            result.update(publish(api, uploader or AssetAPI(), remote, plan, spec, assets, audit), status='published')
        atomic_json(Path(output) / 'result.json', result)
        return result
    except Exception as error:
        reason = str(error) if isinstance(error, ReleaseError) else 'Falha de verificação/API; nenhum conteúdo de resposta registrado.'
        audit.event('failed', status='failed', error_type=type(error).__name__, reason=reason,
                    http_status=error.status if isinstance(error, GitDataAPIError) else None)
        atomic_json(Path(output) / 'result.json', {'schema': SCHEMA, 'status': 'failed', 'published': False,
                    'distribution_performed': False, 'error_type': type(error).__name__})
        if isinstance(error, ReleaseError):
            raise
        raise ReleaseError('Verificação falhou; detalhes permitidos preservados no log, sem conteúdo de credenciais.') from None


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--action', choices=('plan', 'publish'), default='plan')
    parser.add_argument('--candidate', required=True)
    parser.add_argument('--manifest-hash', required=True)
    parser.add_argument('--output', required=True)
    args = parser.parse_args()
    try:
        result = run(args.action, args.candidate, args.manifest_hash, args.output)
    except ReleaseError as error:
        print(str(error), file=sys.stderr); return 1
    print(json.dumps(result, ensure_ascii=False, indent=2)); return 0


if __name__ == '__main__':
    raise SystemExit(main())
