"""GitHub-native controls for the persistent, single-owner delivery laboratory.

GitHub authenticates Israel; the two approval roles remain explicit simulations.
Only FakePublisher is available. Mobile artifacts and hosted web previews do not
constitute a Shorebird release, patch, store upload or tester distribution.
"""
import argparse
from contextlib import closing
from datetime import datetime, timedelta, timezone
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import sqlite3
import subprocess
import sys
import zipfile

from lab_engine import FakePublisher, LabStore, OPERATOR, make_manifest
from policy import canonical, digest
from remote_state import RemoteState, StateError, create_empty_databases, export_bundle, gh_api
import slack_notify
import snapshots

REPOSITORY = 'israelhudson/flutter_code_push_example'
ROOT = Path('/tmp/flutter-code-push-lab')
OPERATIONS = ('initialize', 'technical-review', 'prepare', 'approve', 'revoke',
              'publish', 'reconcile', 'abandon', 'next', 'status')


def authenticate(environment, api=gh_api):
    """Trust GitHub's runner identity, never a role/input claiming to be Israel."""
    if (environment.get('GITHUB_ACTIONS') != 'true'
            or environment.get('GITHUB_REPOSITORY') != REPOSITORY
            or environment.get('GITHUB_EVENT_NAME') != 'workflow_dispatch'
            or environment.get('GITHUB_REF') != 'refs/heads/main'):
        raise ValueError('Controle disponível somente por workflow_dispatch na main do repositório pessoal.')
    owner = api('GET', 'repos/' + REPOSITORY)['owner']
    actor = environment.get('GITHUB_ACTOR')
    if (str(owner['id']) != environment.get('GITHUB_ACTOR_ID')
            or actor != owner['login']
            or environment.get('GITHUB_TRIGGERING_ACTOR') != owner['login']):
        raise ValueError('Somente o proprietário autenticado pode representar os papéis do laboratório.')
    run_id = environment.get('GITHUB_RUN_ID', '')
    if not re.fullmatch(r'\d+', run_id):
        raise ValueError('Run GitHub inválido.')
    return {'id': 'github:' + str(owner['id']), 'login': actor,
            'identity_source': 'github_actions', 'run_id': run_id,
            'run_url': 'https://github.com/' + REPOSITORY + '/actions/runs/' + run_id}


def validate_request(request):
    if not isinstance(request, dict) or request.get('operation') not in OPERATIONS:
        raise ValueError('Comando de laboratório inválido.')
    allowed = {'operation', 'source_sha', 'candidate', 'role', 'manifest_hash',
               'delivery_id', 'rc', 'urgent', 'fail_destination'}
    if set(request) - allowed:
        raise ValueError('Input fora do contrato do laboratório.')
    for key, value in request.items():
        if key not in ('urgent', 'rc') and not isinstance(value, str):
            raise ValueError('Input textual inválido: ' + key + '.')
    result = {key: value for key, value in request.items() if value not in ('', None)}
    operation = result['operation']
    if operation in ('initialize', 'technical-review', 'prepare'):
        if not re.fullmatch(r'[0-9a-f]{40}', result.get('source_sha', '')):
            raise ValueError('Informe o SHA completo da fonte, nunca branch/latest.')
    if operation in ('approve', 'revoke', 'publish', 'reconcile', 'abandon'):
        if not re.fullmatch(r'entrega-\d{4,}-rc\.\d+', result.get('candidate', '')):
            raise ValueError('Informe a candidata exata, como entrega-0042-rc.1.')
    if operation in ('approve', 'revoke', 'publish'):
        if not re.fullmatch(r'[0-9a-f]{64}', result.get('manifest_hash', '')):
            raise ValueError('Informe o hash completo do manifesto aprovado.')
    if operation in ('approve', 'revoke') and result.get('role') not in ('samuel', 'vinicius'):
        raise ValueError('Aprovação requer papel simulado Samuel ou Vinícius.')
    if operation == 'technical-review' and result.get('role', 'ian') not in ('ian', 'yan'):
        raise ValueError('Revisão técnica requer papel simulado Ian/Yan.')
    if operation == 'prepare':
        if not re.fullmatch(r'entrega-\d{4,}', result.get('delivery_id', '')):
            raise ValueError('Informe uma entrega, como entrega-0042.')
        revision = result.get('rc', '1')
        if not (type(revision) is int or isinstance(revision, str) and re.fullmatch(r'\d+', revision)):
            raise ValueError('RC deve ser um inteiro positivo.')
        result['rc'] = int(revision)
        if result['rc'] < 1:
            raise ValueError('RC deve ser positiva.')
    urgent = result.get('urgent', False)
    if not (type(urgent) is bool or isinstance(urgent, str) and urgent in ('true', 'false')):
        raise ValueError('Urgência deve ser booleana.')
    result['urgent'] = urgent in (True, 'true')
    failure = result.get('fail_destination', 'none')
    if failure not in ('none', 'android-before', 'ios-after', 'web-before'):
        raise ValueError('Falha injetada fora do laboratório.')
    if failure != 'none' and operation != 'publish':
        raise ValueError('Injeção de falha somente em publish simulado.')
    return result


def build_inputs(repo, sha):
    value = json.loads(snapshots._git(repo, 'show', sha + ':delivery/build-inputs.json'))
    # Trusted fixed invocation, not a command supplied by candidate metadata.
    return {**value, 'command': ['flutter', 'build', 'web', '--release', '--base-href=/'],
            'flavor': '', 'entrypoint': 'lib/main.dart'}


def seed_targets(repo, sha, inputs):
    text = snapshots._git(repo, 'show', sha + ':pubspec.yaml').decode()
    match = re.search(r'^version:\s*(\d+\.\d+\.\d+\+\d+)\s*$', text, re.M)
    if not match:
        raise ValueError('Versão Flutter explícita ausente na base do laboratório.')
    targets = {}
    for platform in ('android', 'ios'):
        target = {'platform': platform, 'app_id': 'flutter-code-push-example-lab',
                  'environment': 'laboratory', 'release_version': match[1], 'release_sha': sha,
                  **{key: inputs[key] for key in ('flutter_version', 'flutter_revision', 'flavor', 'entrypoint')}}
        target['base_evidence'] = {'kind': 'laboratory', **{key: target[key] for key in
            ('app_id', 'environment', 'platform', 'release_version', 'release_sha')}}
        targets[platform] = target
    targets['web'] = {'platform': 'web', 'version': match[1].split('+')[0], 'environment': 'laboratory'}
    return targets


def build_preview(repo, sha, output):
    """Called on a credential-free build runner by tooling from trusted main."""
    if not re.fullmatch(r'[0-9a-f]{40}', sha):
        raise ValueError('Fonte do build requer SHA40.')
    if snapshots.resolve_commit(repo, 'HEAD') != sha:
        raise ValueError('Checkout do build diverge da fonte congelada.')
    inputs = build_inputs(repo, sha)
    actual = json.loads(subprocess.check_output(['flutter', '--version', '--machine']))
    if (actual['frameworkVersion'], actual['frameworkRevision']) != (
            inputs['flutter_version'], inputs['flutter_revision']):
        raise ValueError('SDK diferente dos inputs fixados da candidata.')
    subprocess.run(['flutter', 'pub', 'get', '--enforce-lockfile'], cwd=repo, check=True)
    subprocess.run(inputs['command'], cwd=repo, check=True)
    if snapshots._git(repo, 'status', '--porcelain', '--untracked-files=no'):
        raise ValueError('Build modificou arquivos rastreados.')
    output = Path(output)
    output.mkdir(parents=True, exist_ok=True)
    archive = output / 'preview.zip'
    with zipfile.ZipFile(archive, 'w', zipfile.ZIP_DEFLATED) as zipped:
        for path in sorted((Path(repo) / 'build/web').rglob('*')):
            if path.is_symlink():
                raise ValueError('Build contém symlink não autorizado.')
            if path.is_file():
                zipped.write(path, path.relative_to(Path(repo) / 'build/web'))
    metadata = {'kind': 'flutter_web', 'source_sha': sha,
                'source_tree': snapshots.source_tree(repo, sha),
                'fingerprint': snapshots.build_fingerprint(repo, sha, inputs), 'inputs': inputs,
                'sha256': hashlib.sha256(archive.read_bytes()).hexdigest(),
                'expires_at': (datetime.now(timezone.utc) + timedelta(days=30)).isoformat()}
    (output / 'metadata.json').write_text(json.dumps(metadata, indent=2) + '\n')
    return metadata


class Coordinator:
    def __init__(self, remote, principal, root=ROOT):
        self.remote, self.principal, self.root = remote, principal, Path(root)
        self.repo = self.root / 'repository'
        self.folder = self.root / 'state'
        self.db = self.folder / 'state.sqlite'
        self.provider = self.folder / 'provider'
        self.outbox = self.folder / 'outbox.sqlite'
        self.head = None
        self.checkpoint_count = 0

    def restore(self, operation):
        self.head = self.remote.head()
        if self.head is None:
            if operation != 'initialize':
                raise ValueError('Execute initialize uma vez antes dos controles da entrega.')
            if self.folder.exists() and any(self.folder.iterdir()):
                raise ValueError('Bootstrap não sobrescreve estado local.')
            self.store = LabStore(self.db)
            create_empty_databases(self.provider / 'provider.sqlite', self.outbox)
        else:
            loaded = self.remote.load(self.folder, revision=self.head)
            expected = {'state_db': self.db, 'provider_db': self.provider / 'provider.sqlite',
                        'outbox_db': self.outbox}
            for key, location in expected.items():
                if loaded.path_plan[key]['original'] != str(location.resolve()):
                    raise ValueError('Estado requer os mesmos caminhos físicos do runner original.')
            if any(Path(path).resolve() != self.repo.resolve()
                   for path in loaded.path_plan['repositories']):
                raise ValueError('Snapshot remoto pertence a outro checkout físico.')
            for original, saved in loaded.paths['previews'].items():
                alias = Path(original)
                if (alias.parent.resolve() != (self.folder / 'previews').resolve()
                        or not re.fullmatch(r'[0-9a-f]{40}-[0-9a-f]{64}\.zip', alias.name)):
                    raise ValueError('Caminho de preview remoto fora da raiz canônica.')
                if alias != saved:
                    alias.parent.mkdir(parents=True, exist_ok=True)
                    shutil.copyfile(saved, alias)
            self.store = LabStore(self.db)
            # A release branch may diverge from main. Keep its exact commit
            # reachable when the publisher creates a --no-local frozen clone.
            for candidate in self.store.status()['candidates']:
                self._retain_commit(candidate['source_sha'])

    def _retain_commit(self, sha):
        snapshots.source_tree(self.repo, sha)
        snapshots._git(self.repo, 'update-ref', 'refs/heads/laboratory-snapshots/' + sha, sha)

    def save(self, phase):
        self.checkpoint_count += 1
        operation = 'github-' + self.principal['run_id'] + '-' + phase + '-' + str(self.checkpoint_count)
        bundle = export_bundle(self.db, self.provider / 'provider.sqlite', self.outbox,
                               repository_paths=[str(self.repo.resolve())])
        result = self.remote.save(bundle, self.head, operation,
                                  checkpoint=self.root / 'remote-commit-checkpoint.json')
        self.head = result.current_head
        return result

    def invoke(self, request, preview_folder=None):
        request = validate_request(request)
        operation = request['operation']
        audit_id = 'github:' + self.principal['run_id'] + ':operation'
        payload = {'request': request, 'authenticated_operator': self.principal,
                   'simulation': True, 'dry_run': True}
        with self.store.connection() as db:
            prior = db.execute('SELECT payload,result FROM events WHERE request_id=?', (audit_id,)).fetchone()
        if prior:
            if prior['payload'] != canonical(payload):
                raise ValueError('Run já usado para outro comando; não reaplicar automaticamente.')
            return json.loads(prior['result'])
        if 'source_sha' in request:
            self._retain_commit(request['source_sha'])
        accepted, error = True, None
        try:
            result = self._execute(request, preview_folder, audit_id + ':core')
        except (ValueError, RuntimeError) as exception:
            accepted, error = False, str(exception)
            result = {'error': error, 'accepted': False}
        wrapper = {'mode': 'laboratory', 'simulation': True, 'dry_run': True,
                   'distribution_performed': False, 'accepted': accepted,
                   'operation': operation, 'authenticated_operator': self.principal,
                   'result': result}
        with self.store.connection() as db:
            db.execute('BEGIN IMMEDIATE')
            self.store._event(db, 'github_operation', payload, wrapper, OPERATOR,
                              candidate=result.get('candidate_id'), role=request.get('role'), request_id=audit_id)
            db.commit()
        self.save('operation')
        return wrapper

    def _execute(self, request, preview_folder, request_id):
        operation = request['operation']
        sha = request.get('source_sha')
        candidate = request.get('candidate')
        if operation == 'initialize':
            inputs = build_inputs(self.repo, sha)
            return self.store.initialize(sha, seed_targets(self.repo, sha, inputs))
        if operation == 'technical-review':
            return self.store.technical_review(sha, role=request.get('role', 'ian'))
        if operation == 'prepare':
            if not preview_folder:
                raise ValueError('Prepare exige artifact do build Flutter desta execução.')
            metadata = json.loads((Path(preview_folder) / 'metadata.json').read_text())
            if metadata.get('kind') != 'flutter_web' or metadata.get('source_sha') != sha:
                raise ValueError('Artifact não corresponde ao SHA exato preparado.')
            location = self.folder / 'previews' / (sha + '-' + metadata['sha256'] + '.zip')
            location.parent.mkdir(parents=True, exist_ok=True)
            data = (Path(preview_folder) / 'preview.zip').read_bytes()
            if hashlib.sha256(data).hexdigest() != metadata['sha256']:
                raise ValueError('Bytes do build divergem dos metadados.')
            if location.exists() and location.read_bytes() != data:
                # A repeat build can differ in timestamps; never overwrite a frozen preview.
                raise ValueError('Preview desse SHA já congelado; reutilize a RC ou escolha outra fonte.')
            location.write_bytes(data)
            preview = {**metadata, 'path': str(location.resolve())}
            inputs = build_inputs(self.repo, sha)
            snapshots.validate_preview(self.repo, sha, preview, inputs)
            with self.store.connection() as db:
                targets = self.store._get(db, 'seed')['targets']
            manifest = make_manifest(self.repo, sha, self.store.production(), targets, preview,
                                     inputs, request['delivery_id'], rc=request['rc'])
            return self.store.prepare(manifest, request_id, urgent=request['urgent'])
        if operation in ('approve', 'revoke'):
            return getattr(self.store, operation)(candidate, request['role'], request['manifest_hash'],
                                                  request_id=request_id)
        if operation == 'status':
            return self.store.status(candidate)
        if operation == 'next':
            return self.store.activate_next()
        failure = request.get('fail_destination', 'none')
        failures = {} if failure == 'none' else dict([failure.split('-', 1)])
        publisher = FakePublisher(self.provider, failures)
        if operation == 'publish':
            return self.store.publish(candidate, request['manifest_hash'], request_id,
                                      self.repo, publisher)
        return getattr(self.store, operation)(candidate, self.repo, publisher)

    def notify(self, wrapper):
        if not os.environ.get('SLACK_BOT_TOKEN'):
            return {'state': 'not_configured', 'required_secret': 'SLACK_BOT_TOKEN'}
        result = wrapper['result']
        status = str(result.get('state', wrapper['operation']))
        if result.get('count') is not None:
            status += ' · ' + str(result['count']) + '/2 papéis simulados por Israel'
        if not wrapper['accepted']:
            status = 'Bloqueado: ' + result['error']
        source = result.get('source_sha') or self.store.production()['source_sha']
        notice = slack_notify.render_notice('lab', status, result.get('candidate_id', 'controle-do-laboratorio'),
            source, self.principal['run_url'], simulation=True,
            idempotency_key='github-' + self.principal['run_id'])
        return slack_notify.send_notice(notice, self.outbox,
                                        checkpoint=lambda phase: self.save('slack-' + phase))


def summary(coordinator, wrapper, notification):
    state = coordinator.store.status()
    lines = ['# Controle de entrega — laboratório', '',
             '**Israel autenticado pelo GitHub; Samuel/Vinícius são papéis simulados.**', '',
             'Estado persistido: `' + str(coordinator.head) + '` em `codex/delivery-state`.', '',
             'Comando: `' + wrapper['operation'] + '` · aceito: `' + str(wrapper['accepted']).lower() + '`.', '',
             'Slack: `' + notification.get('state', 'error') + '`.', '',
             '| Candidata | Estado | Aprovações simuladas | Fonte |', '|---|---|---|---|']
    for candidate in state['candidates']:
        sha = candidate['source_sha']
        lines.append('| ' + candidate['candidate_id'] + ' | ' + candidate['state'] + ' | '
                     + str(candidate['count']) + '/2 | `' + sha + '` |')
    for candidate in state['candidates']:
        sha = candidate['source_sha']
        url = 'https://israelhudson.github.io/flutter_code_push_example/snapshots/' + sha + '/'
        lines += ['', '[Preview desse SHA](' + url + ') — disponível após executar Web - preview Pages com esse SHA.',
                  '', 'Hash para approve/revoke/publish: `' + candidate['manifest_hash'] + '`.', '']
    lines += ['', 'Produção **simulada**: `' + state['production']['source_sha'] + '`.', '',
              '2/2 somente autoriza. `publish` é um comando separado e grava recibos fictícios.',
              'Sem patch Shorebird, upload de loja ou distribuição a testers.', '',
              '```json', json.dumps(wrapper, ensure_ascii=False, indent=2), '```']
    return '\n'.join(lines) + '\n'


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('command', choices=('preflight', 'control', 'build-preview'))
    parser.add_argument('--repo', type=Path)
    parser.add_argument('--source-sha')
    parser.add_argument('--output', type=Path)
    parser.add_argument('--preview-folder', type=Path)
    args = parser.parse_args(argv)
    try:
        if args.command == 'build-preview':
            print(json.dumps(build_preview(args.repo, args.source_sha, args.output)))
            return 0
        principal = authenticate(os.environ)
        request = validate_request(json.loads(os.environ['LAB_REQUEST']))
        if args.command == 'preflight':
            with open(os.environ['GITHUB_OUTPUT'], 'a') as stream:
                stream.write('operation=' + request['operation'] + '\n')
                stream.write('source_sha=' + request.get('source_sha', '') + '\n')
            return 0
        coordinator = Coordinator(RemoteState(), principal)
        coordinator.restore(request['operation'])
        wrapper = coordinator.invoke(request, args.preview_folder)
        notification = coordinator.notify(wrapper)
        result = {**wrapper, 'state_commit': coordinator.head, 'notification': notification,
                  'state': coordinator.store.status(), 'events': coordinator.store.events()}
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(result, ensure_ascii=False, indent=2) + '\n')
        with open(os.environ['GITHUB_STEP_SUMMARY'], 'a') as stream:
            stream.write(summary(coordinator, wrapper, notification))
        print(json.dumps({'accepted': wrapper['accepted'], 'state_commit': coordinator.head,
                          'notification': notification}))
        return 0 if wrapper['accepted'] else 1
    except (ValueError, StateError, OSError, sqlite3.Error) as error:
        # Never print HTTP bodies, process environments or credentials.
        print(json.dumps({'mode': 'laboratory', 'simulation': True, 'error': str(error)}), file=sys.stderr)
        return 1


if __name__ == '__main__':
    sys.exit(main())
