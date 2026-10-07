"""Executable teaching scenario in a disposable repository, never the user's refs."""
from datetime import datetime, timedelta, timezone
from pathlib import Path
import json
import subprocess
import uuid
import zipfile

import snapshots
from lab_engine import FakePublisher, LabStore, make_manifest
from policy import digest


def git(repo, *args):
    return subprocess.check_output(['git', '-C', str(repo), *args], stderr=subprocess.PIPE).decode().strip()


def write(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(value)


def commit(repo, subject):
    git(repo, 'add', '.')
    git(repo, 'commit', '-m', subject)
    return git(repo, 'rev-parse', 'HEAD')


def fixture(folder):
    folder = Path(folder)
    repo = folder / 'repo'
    repo.mkdir(parents=True)
    git(repo, 'init', '-b', 'main')
    git(repo, 'config', 'user.name', 'Israel Laboratory Fixture')
    git(repo, 'config', 'user.email', 'fixture@example.invalid')
    write(repo / 'lib/main.dart', "void main() { print('B'); }\n")
    write(repo / 'pubspec.yaml', 'name: lab_fixture\nversion: 1.1.0+2\nflutter:\n  assets:\n    - assets/logo.txt\n')
    write(repo / 'assets/logo.txt', 'fixture asset\n')
    write(repo / 'android/app/build.gradle', '// fixture only\n')
    write(repo / 'ios/Runner/Info.plist', 'fixture only\n')
    base = commit(repo, 'B: foto original')
    git(repo, 'branch', 'release/entrega-0042', base)
    write(repo / 'lib/feature_c.dart', '// Feature C\n')
    c = commit(repo, 'C: feature fora da candidata')
    write(repo / 'lib/feature_d.dart', '// Feature D\n')
    d = commit(repo, 'D: outra feature fora da candidata')
    write(repo / 'lib/main.dart', "void main() { print('B com conserto'); }\n")
    fix_main = commit(repo, 'F: conserto independente')
    git(repo, 'checkout', 'release/entrega-0042')
    git(repo, 'cherry-pick', fix_main)
    fixed = git(repo, 'rev-parse', 'HEAD')
    inputs = {'flutter_version': 'fixture-flutter', 'flutter_revision': 'fixture-revision',
              'flavor': '', 'entrypoint': 'lib/main.dart', 'runner': 'fixture', 'command': ['fixture-web']}
    targets = {}
    for platform in ('android', 'ios'):
        target = {'platform': platform, 'app_id': 'isolated-fixture', 'environment': 'laboratory',
                  'release_version': '1.1.0+2', 'release_sha': base,
                  'flutter_version': inputs['flutter_version'], 'flutter_revision': inputs['flutter_revision'],
                  'flavor': '', 'entrypoint': 'lib/main.dart'}
        target['base_evidence'] = {k: target[k] for k in ('app_id', 'environment', 'platform', 'release_version', 'release_sha')}
        target['base_evidence']['kind'] = 'laboratory'
        targets[platform] = target
    targets['web'] = {'platform': 'web', 'version': '1.1.0', 'environment': 'laboratory'}
    return repo, base, fixed, inputs, targets, {'B': base, 'C': c, 'D': d, 'F': fix_main, 'F_prime': fixed}


def preview(folder, repo, sha, inputs, name):
    path = Path(folder) / f'{name}.zip'
    with zipfile.ZipFile(path, 'w') as archive:
        archive.writestr('index.html', f'<h1>LABORATÓRIO — preview sintético</h1><p>Snapshot {sha}</p>')
    import hashlib
    return {'kind': 'fixture_web', 'path': str(path.resolve()), 'source_sha': sha,
            'fingerprint': snapshots.build_fingerprint(repo, sha, inputs), 'inputs': inputs,
            'sha256': hashlib.sha256(path.read_bytes()).hexdigest(),
            'expires_at': (datetime.now(timezone.utc) + timedelta(days=7)).isoformat()}


def run(folder):
    session = Path(folder).resolve() / ('session-' + uuid.uuid4().hex[:10])
    repo, base, fixed, inputs, targets, graph = fixture(session)
    store = LabStore(session / 'state.sqlite')
    production = store.initialize(base, targets)
    store.technical_review(base)
    store.technical_review(fixed)
    first = make_manifest(repo, base, production, targets, preview(session, repo, base, inputs, 'preview-rc1'), inputs, 'entrega-0042')
    rc1 = store.prepare(first, 'prepare-rc1')
    for role in ('samuel', 'vinicius'):
        store.approve(rc1['candidate_id'], role, rc1['manifest_hash'])
    second_preview = preview(session, repo, fixed, inputs, 'preview-rc2')
    second = make_manifest(repo, fixed, production, targets, second_preview, inputs, 'entrega-0042', rc=2)
    rc2 = store.prepare(second, 'prepare-rc2')
    candidate, manifest_hash = rc2['candidate_id'], rc2['manifest_hash']
    counts = [rc2['count']]
    blocked = []
    publisher = FakePublisher(session / 'provider')
    for expected in (0, 1):
        try:
            store.publish(candidate, manifest_hash, f'blocked-{expected}', repo, publisher)
        except ValueError as error:
            blocked.append(str(error))
        else:
            raise AssertionError('0/2 ou 1/2 publicou.')
        role = 'samuel' if expected == 0 else 'vinicius'
        counts.append(store.approve(candidate, role, manifest_hash)['count'])
    assert counts == [0, 1, 2]
    assert store.status(candidate)['state'] == 'autorizada'
    assert publisher.lookup(digest({'candidate': candidate, 'manifest': manifest_hash, 'destination': 'android'})) is None
    # Move the release branch after approval; publication must still compile the frozen F′.
    write(repo / 'lib/later.dart', '// alteração posterior fora da foto aprovada\n')
    commit(repo, 'G: release avança depois da aprovação')
    partial = store.publish(candidate, manifest_hash, 'publish-first', repo, FakePublisher(session / 'provider', {'ios': 'after'}))
    assert partial['state'] == 'parcial'
    reconciled = store.reconcile(candidate, repo, publisher)
    assert reconciled['state'] == 'parcial' and reconciled['destinations']['ios']['state'] == 'sucesso'
    completed = store.publish(candidate, manifest_hash, 'publish-resume', repo, publisher)
    assert completed['state'] == 'concluida'
    assert all(d['receipt']['source_sha'] == fixed for d in completed['destinations'].values())
    paths = git(repo, 'ls-tree', '-r', '--name-only', fixed).splitlines()
    assert 'lib/feature_c.dart' not in paths and 'lib/feature_d.dart' not in paths and 'lib/later.dart' not in paths
    output_files = {'targets.json': targets, 'inputs.json': inputs, 'preview.json': second_preview,
                    'manifest.json': second, 'events.json': store.events(), 'state.json': store.status()}
    for name, value in output_files.items():
        (session / name).write_text(json.dumps(value, ensure_ascii=False, indent=2) + '\n')
    report = {'mode': 'laboratory', 'simulation': True, 'dry_run': True, 'distribution_performed': False,
              'session_dir': str(session), 'repo': str(repo), 'db': str(store.path),
              'provider_dir': str(publisher.directory), 'candidate_id': candidate, 'manifest_hash': manifest_hash,
              'counts': counts, 'blocked': blocked, 'rc1_state': store.status(rc1['candidate_id'])['state'],
              'after_two_approvals': 'autorizada_sem_publicacao', 'partial': partial['state'],
              'final_state': completed['state'], 'snapshots': graph, 'features_c_d_absent': True,
              'release_head': git(repo, 'rev-parse', 'HEAD'), 'published_source_sha': fixed,
              'receipts': {d: r['receipt'] for d, r in completed['destinations'].items()},
              'tag_records': store.status()['tags']}
    (session / 'report.json').write_text(json.dumps(report, ensure_ascii=False, indent=2) + '\n')
    return report
