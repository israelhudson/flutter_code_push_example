"""Build and retain SHA-addressed Flutter web previews, never delivery state.

The static history branch only stores public build bytes and their identities.
Git history is appended with ordinary fast-forward pushes; no force is used.
"""
import argparse
import base64
import hashlib
import html
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys

TRUSTED_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(TRUSTED_ROOT / 'tools/delivery'))
import snapshots
from policy import digest

HISTORY_BRANCH = 'codex/pages-previews'
REPOSITORY = 'israelhudson/flutter_code_push_example'
PROJECT_BASE = '/flutter_code_push_example/'
MAX_SITE_BYTES = 800 * 1024 * 1024


def git(repo, *args, authenticated=False):
    env = {key: value for key, value in os.environ.items() if not key.startswith('GIT_')}
    env.update(GIT_TERMINAL_PROMPT='0', GIT_CONFIG_GLOBAL=os.devnull, GIT_CONFIG_NOSYSTEM='1')
    if authenticated:
        token = env.get('GH_TOKEN')
        if not token:
            raise ValueError('GH_TOKEN necessário somente para histórico/persistência.')
        encoded = base64.b64encode(('x-access-token:' + token).encode()).decode()
        env.update(GIT_CONFIG_COUNT='1', GIT_CONFIG_KEY_0='http.https://github.com/.extraheader',
                   GIT_CONFIG_VALUE_0='AUTHORIZATION: basic ' + encoded)
    result = subprocess.run(['git', '-c', 'core.hooksPath=' + os.devnull, '-C', str(repo), *args],
                            env=env, text=True, capture_output=True)
    if result.returncode:
        raise ValueError('Operação Git falhou; histórico preservado: ' + result.stderr.strip())
    return result.stdout.strip()


def json_file(path):
    return json.loads(Path(path).read_text(encoding='utf-8'))


def hashes(folder):
    result, total = {}, 0
    for path in sorted(Path(folder).rglob('*')):
        if '.git' in path.relative_to(folder).parts:
            continue
        if path.is_symlink():
            raise ValueError('Site não admite symlinks.')
        if not path.is_file():
            continue
        if path.stat().st_nlink != 1:
            raise ValueError('Site não admite hard links.')
        name = path.relative_to(folder).as_posix()
        if (any(part.startswith('.') for part in Path(name).parts) and name != '.nojekyll'):
            raise ValueError('Arquivo oculto fora do site permitido.')
        if path.suffix.lower() in ('.db', '.sqlite', '.sqlite3', '.env'):
            raise ValueError('Estado/segredo não pode entrar no site.')
        data = path.read_bytes()
        if data.startswith(b'SQLite format 3\x00'):
            raise ValueError('Banco SQLite não pode entrar no site.')
        total += len(data)
        if total > MAX_SITE_BYTES:
            raise ValueError('Histórico ultrapassa limite conservador de 800 MiB; revisar retenção.')
        result[name] = hashlib.sha256(data).hexdigest()
    return result


def validate_site(site):
    site = Path(site)
    all_files = hashes(site)
    snapshot_ids = set()
    for name in all_files:
        if name in ('index.html', '.nojekyll'):
            continue
        parts = name.split('/')
        if len(parts) < 3 or parts[0] != 'snapshots' or not re.fullmatch(r'[0-9a-f]{40}', parts[1]):
            raise ValueError('Histórico contém arquivo fora do namespace web permitido.')
        snapshot_ids.add(parts[1])
    for sha in snapshot_ids:
        folder = site / 'snapshots' / sha
        manifest = json_file(folder / 'files.json')
        actual = hashes(folder)
        actual.pop('files.json', None)
        if manifest != actual:
            raise ValueError('Snapshot web existente foi alterado; não sobrescrever.')
        metadata = json_file(folder / 'metadata.json')
        if metadata['source_sha'] != sha or metadata['schema'] != 'pages-preview-v1':
            raise ValueError('Identidade do snapshot web inválida.')
        if not (folder / 'index.html').is_file() or not (folder / 'app/index.html').is_file():
            raise ValueError('Snapshot web incompleto.')
        if metadata['web_content_sha256'] != digest(hashes(folder / 'app')):
            raise ValueError('Hash dos bytes Flutter não confere.')
    return sorted(snapshot_ids)


def history(site):
    site = Path(site).resolve()
    if site.exists() and any(site.iterdir()):
        raise ValueError('Histórico requer pasta inicialmente vazia.')
    site.mkdir(parents=True, exist_ok=True)
    git(site, 'init', '-b', HISTORY_BRANCH)
    remote = 'https://github.com/' + REPOSITORY + '.git'
    git(site, 'remote', 'add', 'origin', remote)
    refs = git(site, 'ls-remote', '--heads', 'origin', 'refs/heads/' + HISTORY_BRANCH, authenticated=True)
    if refs:
        git(site, 'fetch', '--depth=1', 'origin', 'refs/heads/' + HISTORY_BRANCH, authenticated=True)
        git(site, 'checkout', '-B', HISTORY_BRANCH, 'FETCH_HEAD')
        validate_site(site)
    return {'history_branch': HISTORY_BRANCH, 'existing': bool(refs)}


def source_fingerprint(repo, sha, inputs):
    # Same legacy identity as delivery-preview; Pages adds a distinct base href.
    entries = git(repo, 'ls-tree', '-r', sha).splitlines()
    entries = [entry for entry in entries if not entry.split('\t', 1)[1].startswith(
        ('docs/', 'referencias/', 'delivery/candidates/'))
        and entry.split('\t', 1)[1] not in ('README.md', 'AGENTS.md')]
    return digest({'files': entries, 'inputs': inputs})


def entry_page(sha, version):
    safe_version = html.escape(version)
    return f'''<!doctype html><html lang="pt-BR"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Preview {safe_version} · {sha[:12]}</title>
<style>html,body{{margin:0;height:100%;font-family:system-ui;background:#f5f5f5}}body{{display:flex;flex-direction:column}}header{{padding:8px 12px;font-size:13px;overflow-wrap:anywhere}}iframe{{width:100%;flex:1;border:0;background:white}}a{{color:#125dab}}</style>
</head><body><header>Preview web · versão {safe_version}<br>Snapshot
<a href="https://github.com/{REPOSITORY}/commit/{sha}">{sha}</a>
· <a href="metadata.json">identidade</a> · Android/iOS não validados por este preview.</header><iframe title="Aplicativo Flutter web" src="app/"></iframe></body></html>'''


def build(repo, sha, site):
    repo, site = Path(repo).resolve(), Path(site).resolve()
    if not re.fullmatch(r'[0-9a-f]{40}', sha) or snapshots.resolve_commit(repo, sha) != sha:
        raise ValueError('Preview exige SHA40 completo, nunca branch/latest.')
    symbolic = subprocess.run(['git', '-C', str(repo), 'symbolic-ref', '-q', 'HEAD'], capture_output=True)
    if snapshots.resolve_commit(repo, 'HEAD') != sha or symbolic.returncode != 1:
        raise ValueError('Checkout do aplicativo deve estar em detached HEAD no SHA escolhido.')
    if git(repo, 'status', '--porcelain', '--untracked-files=all'):
        raise ValueError('Checkout do aplicativo deve estar limpo antes do build.')
    inputs = json.loads(git(repo, 'show', sha + ':delivery/build-inputs.json'))
    original_fingerprint = source_fingerprint(repo, sha, inputs)
    site.mkdir(parents=True, exist_ok=True)
    existing = validate_site(site)
    folder = site / 'snapshots' / sha
    if sha in existing:
        metadata = json_file(folder / 'metadata.json')
        if metadata['source_fingerprint'] != original_fingerprint:
            raise ValueError('Snapshot SHA já existe com inputs diferentes.')
    else:
        version = re.search(r'^version:\s*(\S+)', git(repo, 'show', sha + ':pubspec.yaml'), re.M)[1]
        actual = json.loads(subprocess.check_output(['flutter', '--version', '--machine']))
        if (actual['frameworkVersion'] != inputs['flutter_version']
                or actual['frameworkRevision'] != inputs['flutter_revision']):
            raise ValueError('Toolchain diverge dos inputs aprovados.')
        base_href = PROJECT_BASE + 'snapshots/' + sha + '/app/'
        command = ['flutter', 'build', 'web', '--release', '--base-href=' + base_href]
        if inputs['command'] != ['flutter', 'build', 'web', '--release', '--base-href=/'] or inputs.get('dart_defines') != {}:
            raise ValueError('Inputs web diferentes exigem revisão do adaptador Pages.')
        env = {key: value for key, value in os.environ.items()
               if 'TOKEN' not in key.upper() and 'SECRET' not in key.upper()}
        subprocess.run(['flutter', 'pub', 'get', '--enforce-lockfile'], cwd=repo, env=env, check=True, stdout=sys.stderr)
        subprocess.run(command, cwd=repo, env=env, check=True, stdout=sys.stderr)
        if git(repo, 'status', '--porcelain', '--untracked-files=no'):
            raise ValueError('Build alterou arquivos versionados.')
        folder.mkdir(parents=True)
        shutil.copytree(repo / 'build/web', folder / 'app', symlinks=True)
        metadata = {'schema': 'pages-preview-v1', 'source_sha': sha,
                    'source_tree': snapshots.source_tree(repo, sha), 'version': version,
                    'source_fingerprint': original_fingerprint, 'source_build_inputs': inputs,
                    'pages_build_inputs': {**inputs, 'command': command},
                    'fingerprint': snapshots.build_fingerprint(repo, sha, {**inputs, 'command': command}),
                    'web_content_sha256': digest(hashes(folder / 'app')),
                    'snapshot_path': 'snapshots/' + sha + '/'}
        (folder / 'index.html').write_text(entry_page(sha, version), encoding='utf-8')
        (folder / 'metadata.json').write_text(json.dumps(metadata, ensure_ascii=False, indent=2) + '\n')
        (folder / 'files.json').write_text(json.dumps(hashes(folder), sort_keys=True, indent=2) + '\n')
    (site / '.nojekyll').write_text('')
    (site / 'index.html').write_text('<!doctype html><meta charset="utf-8"><meta http-equiv="refresh" content="0;url=snapshots/' + sha + '/"><a href="snapshots/' + sha + '/">Abrir último preview: ' + sha + '</a>')
    validate_site(site)
    return metadata


def persist(site):
    site = Path(site).resolve()
    snapshots_ids = validate_site(site)
    if not snapshots_ids:
        raise ValueError('Não publicar histórico vazio.')
    git(site, 'config', 'user.name', 'github-actions[bot]')
    git(site, 'config', 'user.email', '41898282+github-actions[bot]@users.noreply.github.com')
    git(site, 'add', '--', 'snapshots', 'index.html', '.nojekyll')
    if git(site, 'diff', '--cached', '--name-only'):
        git(site, 'commit', '-m', 'pages: preserve SHA-addressed web snapshots')
        git(site, 'push', 'origin', 'HEAD:refs/heads/' + HISTORY_BRANCH, authenticated=True)
    return {'history_branch': HISTORY_BRANCH, 'snapshots': snapshots_ids}


def export(site, output):
    site, output = Path(site).resolve(), Path(output).resolve()
    validate_site(site)
    if output == site or site in output.parents or output.exists():
        raise ValueError('Exportar para uma pasta nova fora do histórico Git.')
    output.mkdir(parents=True)
    for name in hashes(site):
        target = output / name
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(site / name, target)
    validate_site(output)
    return {'output': str(output), 'snapshots': validate_site(output)}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest='command', required=True)
    for name in ('history', 'persist'):
        sub.add_parser(name).add_argument('--site', required=True)
    p = sub.add_parser('build')
    p.add_argument('--site', required=True); p.add_argument('--repo', required=True); p.add_argument('--source-sha', required=True)
    p = sub.add_parser('export')
    p.add_argument('--site', required=True); p.add_argument('--output', required=True)
    args = parser.parse_args()
    if args.command == 'build':
        result = build(args.repo, args.source_sha, args.site)
    elif args.command == 'export':
        result = export(args.site, args.output)
    else:
        result = globals()[args.command](args.site)
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
