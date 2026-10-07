"""Create the exact LAB annotated tag using the owner's existing gh CLI login.

Run outside GitHub Actions. The supplied tag-spec is compared with a fresh,
read-only laboratory snapshot; it is never accepted as authority by itself.
This command creates at most one tag object and one ref, without retries,
force, replacement or deletion. GitHub Release publication remains separate.
"""
import argparse
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import tempfile

from github_lab_release import (Audit, BASE, REPO, URL, ReleaseError, atomic_json,
                                prepare_plan, read_candidate, tag_protection, verify_tag)
from remote_state import GitDataAPIError, RemoteState, gh_api

SCHEMA = 'github-lab-tag-creation-v1'


def current_user():
    """The shared repo API deliberately does not allow the /user endpoint."""
    args = ['gh', 'api', '--hostname', 'github.com', 'user', '--method', 'GET',
            '-H', 'Accept: application/vnd.github+json']
    try:
        result = subprocess.run(args, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                                timeout=30, check=False)
    except (OSError, subprocess.TimeoutExpired):
        raise ReleaseError('Não foi possível conferir a autenticação existente do gh.') from None
    if result.returncode:
        raise ReleaseError('O gh precisa estar autenticado como proprietário; nenhum token será criado.')
    try:
        return json.loads(result.stdout)
    except (ValueError, UnicodeDecodeError):
        raise ReleaseError('Identidade retornada pelo gh inválida.') from None


def authenticate(environment, api, get_user):
    if environment.get('GITHUB_ACTIONS') == 'true':
        raise ReleaseError('Crie a tag fora das Actions, com a autenticação existente do proprietário.')
    user = get_user()
    repository = api('GET', BASE)
    owner = repository.get('owner', {})
    if (repository.get('full_name') != REPO or owner.get('login') != 'israelhudson'
            or not isinstance(user, dict) or user.get('login') != owner.get('login')
            or type(user.get('id')) is not int or user['id'] <= 0
            or type(owner.get('id')) is not int or user['id'] != owner['id']):
        raise ReleaseError('Somente Israel, proprietário autenticado pelo gh, pode criar esta tag.')
    return {'login': owner['login'], 'id': owner['id'],
            'identity_source': 'local_owner_cli', 'run_url': URL}


def load_spec(path):
    path = Path(path)
    if path.is_symlink() or not path.is_file() or path.stat().st_size > 64 * 1024:
        raise ReleaseError('tag-spec.json precisa ser um arquivo JSON regular de até 64 KiB.')
    def unique(pairs):
        result = {}
        for key, value in pairs:
            if key in result:
                raise ReleaseError('tag-spec.json contém chave duplicada.')
            result[key] = value
        return result
    try:
        spec = json.loads(path.read_bytes(), object_pairs_hook=unique)
    except (ValueError, UnicodeDecodeError):
        raise ReleaseError('tag-spec.json inválido.') from None
    if (not isinstance(spec, dict) or not isinstance(spec.get('tag_name'), str)
            or not re.fullmatch(r'entrega-\d{4,}-rc\.[1-9]\d*', spec['tag_name'])
            or not isinstance(spec.get('manifest_hash'), str)
            or not re.fullmatch(r'[0-9a-f]{64}', spec['manifest_hash'])):
        raise ReleaseError('Identidade de candidata/hash inválida no tag-spec.json.')
    return spec


def validate_tag_object(tag, spec):
    if (not isinstance(tag, dict) or not isinstance(tag.get('sha'), str)
            or not re.fullmatch(r'[0-9a-f]{40}', tag['sha'])
            or tag.get('tag') != spec['tag_name']
            or tag.get('object', {}).get('type') != 'commit'
            or tag.get('object', {}).get('sha') != spec['source_sha']
            or tag.get('message', '').strip() != spec['message'].strip()):
        raise ReleaseError('Objeto de tag retornado não corresponde à fonte/mensagem esperadas.')
    return tag['sha']


def mutation(audit, spec, operation, call, *, tag_sha=None):
    fields = {'candidate_id': spec['tag_name'], 'source_sha': spec['source_sha'],
              'manifest_hash': spec['manifest_hash'], 'release_identity': spec['release_identity'],
              'operation': operation}
    if tag_sha is not None:
        fields['tag_sha'] = tag_sha
    audit.checkpoint(**fields, status='pending')
    audit.event('mutation_before', **fields, status='pending')
    try:
        result = call()
    except Exception as error:
        audit.checkpoint(**fields, status='uncertain')
        audit.event('mutation_uncertain', **fields, status='uncertain',
                    http_status=error.status if isinstance(error, GitDataAPIError) else None)
        raise ReleaseError('Criação de tag incerta. Confira checkpoint e GitHub antes de outra tentativa; não houve retry automático.') from None
    audit.event('mutation_returned', **fields, status='returned')
    return result


def run(spec_path, output, environment=None, *, api=gh_api, remote=None, get_user=current_user):
    audit = Audit(output)
    attempted = False
    try:
        spec = load_spec(spec_path)
        owner = authenticate(os.environ if environment is None else environment, api, get_user)
        audit.event('tag_owner_authenticated', actor_id=owner['id'], login=owner['login'])
        def readonly(method, path, data=None):
            if method != 'GET' or data is not None:
                raise ReleaseError('Estado remoto somente leitura na criação da tag.')
            return api(method, path)
        remote = remote or RemoteState(api=readonly)
        with tempfile.TemporaryDirectory(prefix='github-lab-tag-state-') as folder:
            loaded = remote.load(Path(folder) / 'state')
            manifest, preview = read_candidate(loaded, spec['tag_name'], spec['manifest_hash'])
            _, expected, _ = prepare_plan(manifest, preview, owner, loaded.head_sha, api, folder)
            state_head = loaded.head_sha
        if spec != expected:
            raise ReleaseError('tag-spec.json difere do plano regenerado da candidata congelada; nenhuma tag criada.')
        saved_spec = Path(output) / 'tag-spec.json'
        if saved_spec.exists() and load_spec(saved_spec) != expected:
            raise ReleaseError('Pasta de saída pertence a outra tag; preserve a evidência e use outro diretório.')
        atomic_json(Path(output) / 'tag-spec.json', expected)
        tag_protection(api)
        tag_sha = verify_tag(api, expected)
        created = False
        if tag_sha is None:
            checkpoint = Path(output) / 'checkpoint.json'
            if checkpoint.exists():
                raise ReleaseError('Esta pasta conserva uma tentativa anterior sem ref confirmada. Confira o checkpoint; nenhum POST será repetido automaticamente.')
            attempted = True
            tag = mutation(audit, expected, 'create_tag_object', lambda: api('POST', BASE + '/git/tags', {
                'tag': expected['tag_name'], 'message': expected['message'],
                'object': expected['source_sha'], 'type': 'commit'}))
            tag_sha = validate_tag_object(tag, expected)
            audit.checkpoint(candidate_id=expected['tag_name'], release_identity=expected['release_identity'],
                             source_sha=expected['source_sha'], tag_sha=tag_sha,
                             operation='tag_object_verified', status='confirmed')
            ref = mutation(audit, expected, 'create_tag_ref', lambda: api('POST', BASE + '/git/refs', {
                'ref': expected['ref'], 'sha': tag_sha}), tag_sha=tag_sha)
            if (not isinstance(ref, dict) or ref.get('ref') != expected['ref']
                    or ref.get('object', {}).get('type') != 'tag'
                    or ref.get('object', {}).get('sha') != tag_sha):
                raise ReleaseError('Ref retornada não corresponde ao objeto da tag; confira a tentativa.')
            if verify_tag(api, expected, required=True) != tag_sha:
                raise ReleaseError('Objeto remoto final diverge da tag criada; nenhuma substituição será feita.')
            created = True
        result = {'schema': SCHEMA, 'status': 'created' if created else 'already_exists',
                  'created': created, 'verified': True, 'tag_name': expected['tag_name'],
                  'source_sha': expected['source_sha'], 'manifest_hash': expected['manifest_hash'],
                  'release_identity': expected['release_identity'], 'tag_sha': tag_sha,
                  'state_head': state_head, 'real_operator': {key: owner[key] for key in ('login', 'id', 'identity_source')},
                  'simulation': True, 'distribution_performed': False}
        audit.checkpoint(candidate_id=expected['tag_name'], release_identity=expected['release_identity'],
                         source_sha=expected['source_sha'], tag_sha=tag_sha,
                         operation='verify_tag', status='confirmed')
        audit.event('tag_confirmed', candidate_id=expected['tag_name'], tag_sha=tag_sha,
                    source_sha=expected['source_sha'], status=result['status'])
        atomic_json(Path(output) / 'result.json', result)
        return result
    except Exception as error:
        audit.event('tag_failed', status='uncertain' if attempted else 'failed',
                    http_status=error.status if isinstance(error, GitDataAPIError) else None)
        if attempted and (Path(output) / 'checkpoint.json').is_file():
            # Validation failure after a successful HTTP reply is also uncertain.
            previous = json.loads((Path(output) / 'checkpoint.json').read_text())
            audit.checkpoint(**{key: value for key, value in previous.items() if key in audit.FIELDS and key != 'status'},
                             status='uncertain')
        atomic_json(Path(output) / 'result.json', {'schema': SCHEMA, 'status': 'uncertain' if attempted else 'failed',
                    'verified': False, 'distribution_performed': False, 'error_type': type(error).__name__})
        if isinstance(error, ReleaseError):
            raise
        raise ReleaseError('Criação/verificação falhou; consulte os eventos permitidos, sem dados de credenciais.') from None


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--spec', required=True)
    parser.add_argument('--output', default='build/github-lab-tag')
    args = parser.parse_args(argv)
    try:
        result = run(args.spec, args.output)
    except ReleaseError as error:
        print(str(error), file=sys.stderr)
        return 1
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
