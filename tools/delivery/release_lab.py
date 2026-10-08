"""Two real approval gates and a separate command for a GitHub-only LAB release.

GitHub contents SHA provides optimistic concurrency for the journal. Publication
intents precede every external effect; retries reconcile rather than overwrite.
No mobile publisher, bot approval, store upload or Shorebird command exists here.
"""
import argparse
import base64
from datetime import datetime, timezone
import hashlib
import html
import json
import os
from pathlib import Path
import re
import subprocess
import time
from urllib.parse import quote

REPOSITORY = 'israelhudson/flutter_code_push_example'
ROOT = Path(__file__).resolve().parents[2]
POLICY_PATH = ROOT / 'delivery/release-lab-policy.json'
STATE_PATH = 'release-lab/state.json'
SHA = re.compile(r'[0-9a-f]{40}\Z')
VERSION = re.compile(r'(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)\Z')
TAG = re.compile(r'v((?:0|[1-9][0-9]*)\.(?:0|[1-9][0-9]*)\.(?:0|[1-9][0-9]*))-rc\.([1-9][0-9]*)\Z')
STABLE_TAG = re.compile(r'v((?:0|[1-9][0-9]*)\.(?:0|[1-9][0-9]*)\.(?:0|[1-9][0-9]*))\Z')


class LabError(ValueError):
    pass


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(',', ':'), ensure_ascii=False, allow_nan=False)


def digest(value):
    return hashlib.sha256(canonical(value).encode()).hexdigest()


def now():
    return datetime.now(timezone.utc).isoformat()


def api(path, data=None, method='GET', missing=False):
    if not (path == 'repos/' + REPOSITORY or path.startswith('repos/' + REPOSITORY + '/')):
        raise LabError('Endpoint fora do laboratório autorizado.')
    args = ['gh', 'api', '--hostname', 'github.com', path, '--method', method,
            '-H', 'Accept: application/vnd.github+json']
    if data is not None:
        args += ['--input', '-']
    try:
        result = subprocess.run(args, input=None if data is None else canonical(data),
                                text=True, capture_output=True, timeout=60)
    except subprocess.TimeoutExpired as error:
        raise LabError('Resposta do GitHub perdida ou indisponível; reconciliar o efeito antes de repetir.') from error
    if result.returncode:
        if missing and '(HTTP 404)' in result.stderr:
            return None
        raise LabError('GitHub recusou a operação; confira permissões e conflito no journal. Nenhum token foi registrado.')
    return json.loads(result.stdout) if result.stdout.strip() else None


def endpoint(path):
    return 'repos/' + REPOSITORY + '/' + path


def git(*args):
    result = subprocess.run(['git', '-C', str(ROOT), *args], text=True, capture_output=True, timeout=60)
    if result.returncode:
        raise LabError('Referência Git ausente ou operação recusada; histórico preservado.')
    return result.stdout.strip()


def identity(person):
    return person.get('id'), person.get('login', '').lower()


def publication_mode(policy):
    # Absence is accepted only for explicitly simulated historical policies.
    mode = policy.get('publication_mode', 'simulation' if policy.get('result_simulated') is True else None)
    if (mode not in ('simulation', 'github_release_only')
            or policy.get('result_simulated') is not (mode == 'simulation')
            or policy.get('distribution_performed') is not False):
        raise LabError('Modo de publicação deve distinguir GitHub real de resultado simulado; distribuição mobile permanece bloqueada.')
    return mode


def validate_policy(policy):
    if (policy.get('schema') != 1 or policy.get('repository') != REPOSITORY
            or policy.get('state_branch') != 'codex/release-lab-state'
            or policy.get('distribution_performed') is not False):
        raise LabError('Política fora do laboratório sem distribuição.')
    publication_mode(policy)
    approvers, publishers, operators = (policy.get(k, []) for k in ('approvers', 'publishers', 'operators'))
    for person in [*approvers, *publishers, *operators]:
        if (not isinstance(person.get('id'), int) or person['id'] <= 0
                or not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9-]{0,38}', person.get('login', ''))):
            raise LabError('Identidade GitHub precisa de login e ID real.')
    if (len(approvers) != 2 or len({identity(p) for p in approvers}) != 2
            or len({p['id'] for p in approvers}) != 2
            or {p.get('role') for p in approvers} != {'first', 'second'}
            or len({p.get('environment') for p in approvers}) != 2
            or not operators or {identity(p) for p in publishers} != {identity(p) for p in approvers}
            or len(publishers) != 2):
        raise LabError('Exigir duas pessoas distintas; publicadores são as mesmas duas identidades.')
    environments = [p.get('environment') for p in approvers] + [policy.get('final_environment')]
    if len(set(environments)) != 3 or any(not isinstance(e, str) or not re.fullmatch(r'[a-z0-9-]+', e) for e in environments):
        raise LabError('Três ambientes exclusivos de responsabilidade são obrigatórios.')
    return policy


def load_policy():
    return validate_policy(json.loads(POLICY_PATH.read_text()))


def validate_context(policy, operation, env):
    if env.get('GITHUB_REPOSITORY') != REPOSITORY:
        raise LabError('Execução aceita somente neste repositório.')
    if env.get('GITHUB_RUN_ATTEMPT') != '1' or not str(env.get('GITHUB_RUN_ID', '')).isdigit():
        raise LabError('Reexecução não reaproveita avais. Prepare uma nova RC para tentar novamente.')
    actor = (int(env.get('GITHUB_ACTOR_ID', '0')), env.get('GITHUB_ACTOR', '').lower())
    if (actor not in {identity(p) for p in policy['operators']}
            or env.get('GITHUB_TRIGGERING_ACTOR', '').lower() != actor[1]):
        raise LabError('Iniciador/reexecutor não é operador autorizado; aprovação é outro papel.')
    ref = env.get('GITHUB_REF', '')
    if ref != 'refs/heads/main' and not (ref.startswith('refs/tags/') and TAG.fullmatch(ref[10:])):
        raise LabError('Use main para preparar, ou a tag RC conhecida para avaliar.')
    if operation in ('prepare', 'recover', 'recovery-inspect') and ref != 'refs/heads/main':
        raise LabError('Preparação e recuperação manual exigem a main.')


def ensure_current(state, tag, source_sha=None):
    record = state.get('candidates', {}).get(tag)
    if state.get('active') != tag or not record or record.get('status') == 'superseded':
        raise LabError('Candidata substituída ou desconhecida; seus avais não autorizam a RC atual.')
    if source_sha is not None and record.get('source_sha') != source_sha:
        raise LabError('Código da candidata diverge da identidade congelada.')
    return record


def review_for(reviews, environment, env_id, allowed):
    decisions = [r for r in reviews if any(e.get('name') == environment and e.get('id') == env_id
                                         for e in r.get('environments', []))]
    if not decisions:
        raise LabError('Aprovação humana ainda ausente: ' + environment)
    # The REST API does not specify history ordering. A single attempt and
    # one gate per environment require exactly one unambiguous decision.
    if len(decisions) != 1:
        raise LabError('Histórico de decisões ambíguo; prepare nova RC: ' + environment)
    review = decisions[0]
    user = review.get('user', {})
    if (review.get('state') != 'approved' or user.get('type') != 'User'
            or identity(user) not in {identity(p) for p in allowed}):
        raise LabError('Decisão recusada ou identidade inesperada: ' + environment)
    return {'environment': environment, 'environment_id': env_id,
            'reviewer': {'id': user['id'], 'login': user['login']},
            'state': 'approved', 'comment': review.get('comment', '')}


def validate_reviews(reviews, policy, environment_ids, stage='approvals'):
    approvers = [review_for(reviews, p['environment'], environment_ids[p['environment']], [p])
                 for p in policy['approvers']]
    if len({p['reviewer']['id'] for p in approvers}) != 2:
        raise LabError('Dois cliques da mesma pessoa não satisfazem dois avais.')
    result = {'approvers': approvers}
    if stage == 'final':
        result['publisher'] = review_for(reviews, policy['final_environment'],
                                         environment_ids[policy['final_environment']], policy['publishers'])
    elif stage != 'approvals':
        raise LabError('Etapa de review inválida.')
    return result


def classify_paths(paths, base):
    if not base or not SHA.fullmatch(str(base.get('source_sha', ''))) or not base.get('release_version'):
        return {'classification': 'Inconclusivo — alvo bloqueado', 'reason': 'Release-base mobile real não configurada.', 'target_blocked': True}
    native = any(p.startswith(('android/', 'ios/', 'assets/')) or p in ('shorebird.yaml', 'delivery/build-inputs.json')
                 or p.endswith(('.java', '.kt', '.swift', '.m', '.mm', '.xcconfig', '.pbxproj')) for p in paths)
    if native:
        return {'classification': 'Loja / nova release nativa', 'reason': 'Alteração nativa, asset empacotado, SDK ou configuração desde a base.', 'target_blocked': True}
    if any(p in ('pubspec.yaml', 'pubspec.lock') for p in paths):
        return {'classification': 'Inconclusivo — alvo bloqueado', 'reason': 'Dependências/assets requerem avaliação de conteúdo e transitivas; não inferir pela extensão.', 'target_blocked': True}
    relevant = [p for p in paths if not p.startswith(('docs/', 'referencias/', 'tests/', 'test/', '.github/', 'tools/', 'deploy/', 'delivery/')) and p not in ('README.md', 'AGENTS.md')]
    if all(p.endswith('.dart') for p in relevant):
        return {'classification': 'Patch possível', 'reason': 'Previsão por diff acumulado; patch não compilado nem validado pelo Shorebird.', 'target_blocked': True}
    return {'classification': 'Inconclusivo — alvo bloqueado', 'reason': 'Mudanças sem evidência suficiente de compatibilidade.', 'target_blocked': True}


def state_read(policy):
    value = api(endpoint('contents/' + STATE_PATH) + '?ref=' + quote(policy['state_branch'], safe=''), missing=True)
    if value is None:
        return {'schema': 1, 'active': None, 'candidates': {}, 'events': []}, None
    state = json.loads(base64.b64decode(value['content']))
    if state.get('schema') != 1:
        raise LabError('Journal desconhecido; não sobrescrever.')
    return state, value['sha']


def state_write(policy, state, old_sha, message):
    data = {'branch': policy['state_branch'], 'message': message,
            'content': base64.b64encode((canonical(state) + '\n').encode()).decode()}
    if old_sha:
        data['sha'] = old_sha
    return api(endpoint('contents/' + STATE_PATH), data, 'PUT')


def journal_change(policy, callback, action, tag):
    # Retries recompute ONLY the journal operation from current state. No tag,
    # branch, app delivery or external publication is repeated here.
    for attempt in range(5):
        state, sha = state_read(policy)
        result = callback(state)
        state['events'].append({'at': now(), 'action': action, 'candidate': tag,
                                'run_id': os.environ['GITHUB_RUN_ID'], 'result': digest(result)})
        try:
            state_write(policy, state, sha, 'lab: ' + action + ' ' + tag)
            return result
        except LabError:
            if attempt == 4:
                raise
            time.sleep(.3)
    raise LabError('Journal em conflito; manter bloqueado.')


def mutate(policy, tag, callback, action):
    return journal_change(policy, lambda state: callback(state, ensure_current(state, tag)), action, tag)


def output(folder, name, value):
    folder = Path(folder); folder.mkdir(parents=True, exist_ok=True)
    (folder / name).write_text(json.dumps(value, indent=2, ensure_ascii=False) + '\n')


def outputs(values):
    if os.environ.get('GITHUB_OUTPUT'):
        with open(os.environ['GITHUB_OUTPUT'], 'a') as stream:
            for key, value in values.items():
                if '\n' in str(value) or '\r' in str(value):
                    raise LabError('Saída multiline não autorizada.')
                stream.write(f'{key}={value}\n')
    print(json.dumps(values, ensure_ascii=False))


def environments(policy):
    ids = {}
    expected = {p['environment']: [p] for p in policy['approvers']}
    expected[policy['final_environment']] = policy['publishers']
    for name, people in expected.items():
        env = api(endpoint('environments/' + name))
        rules = [r for r in env.get('protection_rules', []) if r.get('type') == 'required_reviewers']
        if (len(rules) != 1 or rules[0].get('prevent_self_review') is not False
                or env.get('can_admins_bypass') is not False
                or {identity(r['reviewer']) for r in rules[0].get('reviewers', [])} != {identity(p) for p in people}
                or any(r.get('type') != 'User' for r in rules[0].get('reviewers', []))):
            raise LabError('Proteção real diverge da política: ' + name)
        policy_ref = env.get('deployment_branch_policy')
        if policy_ref != {'protected_branches': False, 'custom_branch_policies': True}:
            raise LabError('Ambiente sem restrição de referências confiáveis: ' + name)
        patterns = api(endpoint('environments/' + name + '/deployment-branch-policies'))['branch_policies']
        if {(p['name'], p['type']) for p in patterns} != {('main', 'branch'), ('v*-rc.*', 'tag')}:
            raise LabError('Refs do ambiente divergentes: ' + name)
        ids[name] = env['id']
    return ids


def resolve_tag(tag):
    ref = api(endpoint('git/ref/tags/' + quote(tag, safe='')))
    obj = ref['object']
    for _ in range(4):
        if obj['type'] == 'commit':
            return obj['sha']
        if obj['type'] != 'tag':
            break
        obj = api(endpoint('git/tags/' + obj['sha']))['object']
    raise LabError('Tag não aponta a commit.')


def trusted_source(source_sha):
    git('fetch', '--no-tags', 'origin', source_sha)
    trusted = git('rev-parse', 'HEAD')
    paths = ['.github', 'deploy', 'tools/delivery/release_lab.py', 'delivery/release-lab-policy.json']
    for path in paths:
        if git('rev-parse', source_sha + ':' + path) != git('rev-parse', trusted + ':' + path):
            raise LabError('Pipeline/política da candidata difere das ferramentas confiáveis; revisão específica necessária.')
    return trusted


def protections(policy):
    required = {
        'LAB - novas RCs imutaveis': ('tag', ['refs/tags/v*-rc.*'], {'update', 'deletion'}),
        'LAB - journal append-only': ('branch', ['refs/heads/' + policy['state_branch']], {'non_fast_forward', 'deletion'}),
        'LAB - main e release revisadas': ('branch', ['refs/heads/main', 'refs/heads/release/**'], {'pull_request', 'required_status_checks', 'non_fast_forward', 'deletion'})
    }
    if publication_mode(policy) == 'github_release_only':
        required['LAB - tags estaveis imutaveis'] = ('tag', ['refs/tags/v*'], {'update', 'deletion'})
    rules = api(endpoint('rulesets'))
    for name, (target, patterns, kinds) in required.items():
        matching = [r for r in rules if r['name'] == name]
        if len(matching) != 1:
            raise LabError('Proteção obrigatória ausente: ' + name)
        rule = api(endpoint('rulesets/' + str(matching[0]['id'])))
        excluded = ['refs/tags/v*-rc.*'] if name == 'LAB - tags estaveis imutaveis' else []
        if (rule.get('enforcement') != 'active' or rule.get('target') != target or rule.get('bypass_actors')
                or rule.get('conditions', {}).get('ref_name') != {'include': patterns, 'exclude': excluded}
                or not kinds <= {r['type'] for r in rule.get('rules', [])}):
            raise LabError('Proteção efetiva divergente: ' + name)
        if target == 'branch' and 'pull_request' in kinds:
            for r in rule['rules']:
                if r['type'] == 'pull_request' and r['parameters'].get('required_approving_review_count', 0) < 1:
                    raise LabError('Revisão técnica obrigatória ausente.')
                if r['type'] == 'required_status_checks' and 'Flutter analyze e test' not in {s['context'] for s in r['parameters']['required_status_checks']}:
                    raise LabError('Verificações Flutter obrigatórias ausentes.')


def assert_record(policy, record):
    if record['policy_digest'] != digest(policy) or resolve_tag(record['candidate_tag']) != record['source_sha']:
        raise LabError('Tag ou política foi alterada após o corte.')
    branch = api(endpoint('git/ref/heads/' + quote(record['release_branch'], safe='')))
    if branch['object']['sha'] != record['source_sha']:
        raise LabError('Release avançou; prepare RC nova antes de continuar.')
    return environments(policy)


def stable_version(version):
    if not VERSION.fullmatch(str(version)):
        raise LabError('Versão estável deve usar major.minor.patch sem prefixo ou sufixo.')
    return tuple(int(part) for part in version.split('.'))


def published_versions(state):
    values = []
    if state.get('last_stable_version'):
        values.append(stable_version(state['last_stable_version']))
    for record in state.get('candidates', {}).values():
        receipt = record.get('receipt', {})
        if receipt.get('publication_mode') == 'github_release_only' and receipt.get('github_release_published') is True:
            values.append(stable_version(record['version']))
    return values


def validate_version_available(policy, state, version, owned_intent=False):
    """Remote stable refs, not RC counts or a simulated receipt, reserve versions."""
    requested = stable_version(version)
    if publication_mode(policy) == 'simulation':
        return
    values = published_versions(state)
    refs = api(endpoint('git/matching-refs/tags/v'))
    for ref in refs:
        matched = STABLE_TAG.fullmatch(ref.get('ref', '')[10:])
        if matched and not (owned_intent and matched[1] == version):
            values.append(stable_version(matched[1]))
    for page in range(1, 101):
        releases = api(endpoint('releases?per_page=100&page=' + str(page)))
        for release in releases:
            matched = STABLE_TAG.fullmatch(release.get('tag_name', ''))
            if matched and not (owned_intent and matched[1] == version):
                values.append(stable_version(matched[1]))
        if len(releases) < 100:
            break
    else:
        raise LabError('Histórico de releases excede a janela de consulta; não assumir versão livre.')
    if values and requested <= max(values):
        raise LabError('Versão já usada/reservada ou anterior à estável; informe uma versão maior.')


def incomplete_publications(state):
    return [record for record in state.get('candidates', {}).values()
            if record.get('publication') and record['publication'].get('status') != 'completed']


def verify_preparation(policy, preparation):
    state, _ = state_read(policy)
    active = state.get('preparation')
    if not active or active.get('intent_id') != preparation['intent_id']:
        raise LabError('Intenção de corte mudou; não produzir referências sem journal correspondente.')
    if incomplete_publications(state):
        raise LabError('Publicação parcial exige recuperação antes de cortar outra candidata.')


def create_ref_verified(ref, source_sha):
    """Create-only reference effect, including reconciliation of a lost response."""
    path = endpoint('git/ref/' + quote(ref, safe='/'))
    existing = api(path, missing=True)
    if existing is None:
        try:
            api(endpoint('git/refs'), {'ref': 'refs/' + ref, 'sha': source_sha}, 'POST')
        except LabError:
            existing = api(path, missing=True)
            if existing is None:
                raise
    observed = api(path)
    if observed['object'].get('type', 'commit') != 'commit' or observed['object']['sha'] != source_sha:
        raise LabError('Referência existente diverge do commit esperado; não mover nem excluir.')
    return observed


def prepare(policy, version, title, folder):
    if not VERSION.fullmatch(version) or not title.strip() or len(title) > 120 or any(ord(c) < 32 for c in title):
        raise LabError('Informe versão sem prefixo e título de 1 a 120 caracteres, em uma linha.')
    environments(policy)
    protections(policy)
    state, _ = state_read(policy)
    if incomplete_publications(state):
        raise LabError('Há publicação parcial; recupere a intenção existente antes de outra RC.')
    pending = state.get('preparation')
    if pending and (pending.get('version') != version or pending.get('title') != title
                    or pending.get('policy_digest') != digest(policy)):
        raise LabError('Corte parcial preservado. Repita a preparação com a mesma versão, título e política para reconciliar.')
    validate_version_available(policy, state, version)
    branch = 'release/' + version
    ref = api(endpoint('git/ref/heads/' + quote(branch, safe='')), missing=True)
    if ref is None:
        source_sha = api(endpoint('commits/main'))['sha']
        trusted_source(source_sha)
    else:
        source_sha = ref['object']['sha']
        trusted_source(source_sha)
    refs = api(endpoint('git/matching-refs/tags/v' + version + '-rc.'))
    numbers = [int(TAG.fullmatch(r['ref'][10:])[2]) for r in refs if TAG.fullmatch(r['ref'][10:]) and TAG.fullmatch(r['ref'][10:])[1] == version]
    tag = pending['candidate_tag'] if pending else 'v' + version + '-rc.' + str(max(numbers, default=0) + 1)
    if pending and pending['source_sha'] != source_sha:
        raise LabError('Release/main mudou durante o corte parcial; referências preservadas para inspeção.')
    baseline_key = 'last_stable_source_sha' if publication_mode(policy) == 'github_release_only' else 'last_completed_source_sha'
    baseline = state.get(baseline_key) or resolve_tag(policy['changelog_initial_tag'])
    record = {'candidate_tag': tag, 'version': version, 'title': title,
              'source_sha': source_sha, 'release_branch': branch,
              'tooling_sha': git('rev-parse', 'HEAD'), 'policy_digest': digest(policy),
              'publication_mode': publication_mode(policy), 'stable_tag': 'v' + version,
              'changelog_base_sha': baseline, 'created_at': now(),
              'preparer': {'login': os.environ['GITHUB_ACTOR'], 'id': int(os.environ['GITHUB_ACTOR_ID'])},
              'status': 'prepared', 'evaluation_run_id': None}
    preparation = pending or {**record, 'intent_id': digest({'candidate': tag, 'source_sha': source_sha,
                                                           'policy_digest': digest(policy),
                                                           'run_id': os.environ['GITHUB_RUN_ID']})}
    def reserve(current):
        if incomplete_publications(current):
            raise LabError('PUBLICAR já possui uma intenção. Não substituir a candidata durante efeitos externos.')
        other = current.get('preparation')
        if other and other['intent_id'] != preparation['intent_id']:
            raise LabError('Outro corte em andamento; não criar branch ou tag concorrente.')
        if not other and tag in current.get('candidates', {}):
            raise LabError('A RC já foi registrada; nova preparação deve usar o próximo número.')
        validate_version_available(policy, current, version)
        current['preparation'] = preparation
        return preparation
    journal_change(policy, reserve, 'preparation_intent', tag)
    verify_preparation(policy, preparation)
    create_ref_verified('heads/' + branch, source_sha)
    verify_preparation(policy, preparation)
    create_ref_verified('tags/' + tag, source_sha)
    def freeze(current):
        existing = current.get('candidates', {}).get(tag)
        if (not current.get('preparation') and current.get('active') == tag
                and existing == record):
            return dict(existing)  # Journal PUT committed but its response was lost.
        if current.get('preparation', {}).get('intent_id') != preparation['intent_id'] or incomplete_publications(current):
            raise LabError('Corte/publicação concorrente; não trocar a candidata ativa.')
        if current.get('active'):
            old = current['candidates'][current['active']]
            if old.get('status') != 'completed':
                old['status'] = 'superseded'
        current['active'] = tag
        current['candidates'][tag] = record
        del current['preparation']
        return record
    journal_change(policy, freeze, 'prepare', tag)
    output(folder, 'candidate.json', record)
    outputs({k: record[k] for k in ('candidate_tag', 'source_sha', 'tooling_sha')})


def preflight(policy, tag, folder):
    if not TAG.fullmatch(tag):
        raise LabError('Tag RC inválida; prepare pela Action Preparar candidata.')
    def claim(state, record):
        assert_record(policy, record)
        protections(policy)
        tooling = trusted_source(record['source_sha'])
        if record.get('evaluation_run_id') is not None:
            raise LabError('Esta RC já tem avaliação. Prepare nova RC; não repetir/reaproveitar avais.')
        record.update(evaluation_run_id=os.environ['GITHUB_RUN_ID'], tooling_sha=tooling, status='evaluating')
        return dict(record)
    record = mutate(policy, tag, claim, 'evaluation_started')
    output(folder, 'candidate.json', record)
    values = {k: record[k] for k in ('candidate_tag', 'source_sha', 'tooling_sha')}
    for p in policy['approvers']:
        values[p['role'] + '_environment'] = p['environment']
        values[p['role'] + '_login'] = p['login']
    values['final_environment'] = policy['final_environment']
    outputs(values)


def same_run(record):
    if record.get('evaluation_run_id') != os.environ['GITHUB_RUN_ID']:
        raise LabError('Run diferente da avaliação congelada; sem transporte de avais.')


def report(policy, tag, smoke_path, metadata_path, folder):
    smoke, metadata = (json.loads(Path(p).read_text()) for p in (smoke_path, metadata_path))
    def register(state, record):
        same_run(record); assert_record(policy, record)
        sha = record['source_sha']
        if (smoke.get('success') is not True or smoke.get('source_sha') != sha
                or metadata.get('source_sha') != sha
                or any(smoke.get(k) != metadata.get(k) for k in ('web_content_sha256', 'snapshot_manifest_sha256'))
                or smoke.get('snapshot_url') != 'https://israelhudson.github.io/flutter_code_push_example/snapshots/' + sha + '/'):
            raise LabError('Preview HTTP diverge da candidata; gate bloqueado.')
        git('fetch', '--no-tags', 'origin', sha, record['changelog_base_sha'])
        paths = git('diff', '--name-only', record['changelog_base_sha'], sha).splitlines()
        changes = git('log', '--format=%s', record['changelog_base_sha'] + '..' + sha).splitlines()
        platforms = {}
        for platform, base in policy.get('mobile_bases', {}).items():
            base_paths = paths
            if base:
                git('fetch', '--no-tags', 'origin', base['source_sha'])
                base_paths = git('diff', '--name-only', base['source_sha'], sha).splitlines()
            platforms[platform] = {**classify_paths(base_paths, base), 'base': base,
                                   'evidence': 'Git diff acumulado; nenhuma compilação mobile ou comparação Shorebird.'}
        value = {'schema': 1, 'candidate_tag': tag, 'version': record['version'], 'title': record['title'],
                 'source_sha': sha, 'policy_digest': record['policy_digest'], 'run_id': record['evaluation_run_id'],
                 'preview': smoke, 'build_inputs': metadata['source_build_inputs'],
                 'pubspec_version': metadata['version'], 'changelog_base_sha': record['changelog_base_sha'],
                 'changes': changes, 'changed_paths': paths, 'platforms': platforms,
                 'publication_mode': publication_mode(policy), 'stable_tag': record.get('stable_tag', 'v' + record['version']),
                 'result_simulated': publication_mode(policy) == 'simulation', 'distribution_performed': False}
        if record.get('publication_mode', 'simulation') != publication_mode(policy):
            raise LabError('Modo do corte diverge do relatório; prepare outra RC sob a política atual.')
        if record.get('report_digest'):
            raise LabError('Relatório já congelado; nova avaliação requer nova RC.')
        record.update(report=value, report_digest=digest(value), status='awaiting_approvals')
        return value
    value = mutate(policy, tag, register, 'report_frozen')
    output(folder, 'report.json', value)
    report_url = 'https://github.com/' + REPOSITORY + '/actions/runs/' + os.environ['GITHUB_RUN_ID']
    target = 'resultado final SIMULADO' if value['result_simulated'] else 'tag estável **' + value['stable_tag'] + '** + Release GitHub reais; aplicativo não distribuído'
    lines = ['# ' + value['version'] + ' — ' + html.escape(value['title']), '',
             '**' + tag + '** · preview real · ' + target, '',
             '[Abrir preview](' + value['preview']['snapshot_url'] + ')', '', '## Mudanças', '']
    lines += ['- ' + html.escape(c) for c in value['changes']] or ['- Sem commits adicionais desde a base registrada.']
    lines += ['', '## Previsão mobile — não é patch validado', '', '| Plataforma | Base | Previsão | Motivo |', '|---|---|---|---|']
    for platform, item in value['platforms'].items():
        lines += ['| ' + platform + ' | ' + str(item['base'] or 'não configurada') + ' | ' + item['classification'] + ' | ' + item['reason'] + ' |']
    people = ' E '.join(p['login'] for p in policy['approvers'])
    publishers = ' OU '.join(p['login'] for p in policy['publishers'])
    journal_url = 'https://github.com/' + REPOSITORY + '/blob/' + policy['state_branch'] + '/' + STATE_PATH
    lines += ['', '**' + people + '** devem aprovar esta RC. Depois, **' + publishers + '** dá PUBLICAR em um terceiro gate. Nenhum app será distribuído.', '', '[Journal e identidade completa](' + journal_url + ')']
    Path(folder, 'report.md').write_text('\n'.join(lines) + '\n')
    if os.environ.get('GITHUB_STEP_SUMMARY'):
        with open(os.environ['GITHUB_STEP_SUMMARY'], 'a') as stream:
            stream.write('\n'.join(lines) + '\n')
    outputs({'report_digest': digest(value), 'report_url': report_url, 'preview_url': value['preview']['snapshot_url']})


def current_reviews(policy, record, run_id=None):
    if run_id is None:
        same_run(record)
        run_id = os.environ['GITHUB_RUN_ID']
    elif str(run_id) != str(record.get('evaluation_run_id')):
        raise LabError('Reviews só podem vir da avaliação original desta candidata.')
    if not record.get('report') or digest(record['report']) != record.get('report_digest'):
        raise LabError('Relatório congelado foi alterado; não reutilizar avais.')
    ids = assert_record(policy, record)
    run = api(endpoint('actions/runs/' + str(run_id)))
    if run.get('run_attempt') != 1 or identity(run['actor']) != identity(record['preparer']):
        raise LabError('Run/ator não corresponde à avaliação original.')
    reviews = api(endpoint('actions/runs/' + str(run_id) + '/approvals'))
    return reviews, ids


def approval(policy, tag, role, report_digest, folder):
    def record_decision(state, record):
        if not record.get('report_digest') or record['report_digest'] != report_digest:
            raise LabError('Relatório aprovado não corresponde à RC.')
        reviews, ids = current_reviews(policy, record)
        person = next(p for p in policy['approvers'] if p['role'] == role)
        review = review_for(reviews, person['environment'], ids[person['environment']], [person])
        value = {'candidate_tag': tag, 'source_sha': record['source_sha'], 'report_digest': report_digest,
                 'run_id': record['evaluation_run_id'], 'run_attempt': 1, 'review': review}
        record.setdefault('approval_receipts', {})[role] = value
        return value
    value = mutate(policy, tag, record_decision, 'approval_' + role)
    output(folder, 'approval.json', value)
    outputs({'reviewer': value['review']['reviewer']['login'], 'report_digest': report_digest})


def frozen_publication(policy, record):
    mode = publication_mode(policy)
    value = record.get('report', {})
    expected_tag = 'v' + record['version']
    if (mode != 'github_release_only' or record.get('publication_mode') != mode
            or value.get('publication_mode') != mode
            or record.get('stable_tag') != expected_tag or value.get('stable_tag') != expected_tag
            or value.get('source_sha') != record['source_sha']
            or value.get('candidate_tag') != record['candidate_tag']
            or value.get('result_simulated') is not False or value.get('distribution_performed') is not False):
        raise LabError('Tag/destino real não estavam congelados antes dos avais. Uma decisão simulada não autoriza uma Release real.')
    return expected_tag


def final_authorization(policy, record, report_digest, original_run=False):
    if not record.get('report_digest') or record['report_digest'] != report_digest:
        raise LabError('Relatório final divergente.')
    kwargs = {'run_id': record['evaluation_run_id']} if original_run else {}
    reviews, ids = current_reviews(policy, record, **kwargs)
    result = validate_reviews(reviews, policy, ids, stage='final')
    receipts = record.get('approval_receipts', {})
    if set(receipts) != {'first', 'second'} or any(r.get('report_digest') != report_digest for r in receipts.values()):
        raise LabError('Os dois jobs obrigatórios ainda não registraram sucesso.')
    if publication_mode(policy) == 'github_release_only':
        for person in policy['approvers']:
            item = receipts[person['role']]
            review = next(r for r in result['approvers'] if r['environment'] == person['environment'])
            if (item.get('candidate_tag') != record['candidate_tag'] or item.get('source_sha') != record['source_sha']
                    or str(item.get('run_id')) != str(record['evaluation_run_id']) or item.get('run_attempt') != 1
                    or item.get('review') != review):
                raise LabError('Recibo de gate não corresponde à candidata e à review oficial do run original.')
    jobs = api(endpoint('actions/runs/' + str(record['evaluation_run_id']) + '/jobs?per_page=100'))['jobs']
    for role in ('first', 'second'):
        matches = [j for j in jobs if j['name'].endswith('Gate ' + role)]
        if len(matches) != 1 or matches[0].get('conclusion') != 'success':
            raise LabError('Gate obrigatório rejeitado, ignorado, cancelado ou ainda sem sucesso.')
    return result


def publication_identity(record):
    return {'candidate_tag': record['candidate_tag'], 'stable_tag': record['stable_tag'],
            'source_sha': record['source_sha'], 'report_digest': record['report_digest'],
            'policy_digest': record['policy_digest'], 'authorized_run_id': str(record['evaluation_run_id']),
            'publication_mode': 'github_release_only'}


def release_payload(record, decision, intent_id):
    report_url = 'https://github.com/' + REPOSITORY + '/actions/runs/' + str(record['evaluation_run_id'])
    lines = ['# ' + record['version'] + ' — ' + html.escape(record['title']), '',
             'Registro de versão do laboratório no GitHub. **Nenhum aplicativo ou patch foi distribuído.**', '',
             '- Candidata aprovada: `' + record['candidate_tag'] + '` (preservada).',
             '- Tag estável: `' + record['stable_tag'] + '`.',
             '- Código aprovado: `' + record['source_sha'] + '`.',
             '- Aprovações verificadas nas contas: ' + ' e '.join(r['reviewer']['login'] for r in decision['approvers']) + '.',
             '- Comando final: ' + decision['publisher']['reviewer']['login'] + '.',
             '- [Preview avaliado](' + record['report']['preview']['snapshot_url'] + ').',
             '- [Relatório e execução aprovados](' + report_url + ').', '', '## Changelog aprovado', '']
    lines += ['- ' + html.escape(change) for change in record['report'].get('changes', [])] or ['- Sem commits adicionais desde a base registrada.']
    lines += ['', 'Reviews de contas verificadas não demonstram independência das pessoas que operaram essas contas.', '',
              '<!-- release-lab-intent:' + intent_id + ' -->',
              '<!-- release-lab-report:' + record['report_digest'] + ' -->']
    return {'tag_name': record['stable_tag'], 'target_commitish': record['source_sha'],
            'name': record['version'] + ' — ' + record['title'], 'body': '\n'.join(lines) + '\n',
            'draft': False, 'prerelease': False, 'generate_release_notes': False, 'make_latest': 'true'}


def verify_intent(policy, record, intent):
    frozen_publication(policy, record)
    expected = publication_identity(record)
    if (any(intent.get(key) != value for key, value in expected.items())
            or intent.get('decision_digest') != digest(intent.get('decision'))
            or intent.get('intent_id') != digest({**expected, 'decision_digest': intent.get('decision_digest')})
            or intent.get('release_payload') != release_payload(record, intent['decision'], intent['intent_id'])):
        raise LabError('Intenção de publicação diverge da identidade aprovada; não reutilizar autorização.')


def live_intent(policy, tag, intent_id):
    state, _ = state_read(policy)
    record = ensure_current(state, tag)
    intent = record.get('publication', {})
    if state.get('preparation') or intent.get('intent_id') != intent_id:
        raise LabError('Corte/intenção concorrente; não executar outro efeito externo.')
    verify_intent(policy, record, intent)
    assert_record(policy, record)
    protections(policy)
    return state, record, intent


def publication_checkpoint(policy, tag, intent_id, status, **details):
    def checkpoint(state, record):
        intent = record.get('publication', {})
        if intent.get('intent_id') != intent_id or state.get('preparation'):
            raise LabError('Journal mudou durante a publicação; não registrar sucesso para outra intenção.')
        verify_intent(policy, record, intent)
        if intent.get('status') != 'completed':
            intent.update(status=status, updated_at=now(), **details)
            record['status'] = 'publishing' if status != 'failed' else 'publication_failed'
        return dict(intent)
    return mutate(policy, tag, checkpoint, 'publication_' + status)


def verify_release(release, intent):
    expected = intent['release_payload']
    expected_url = 'https://github.com/' + REPOSITORY + '/releases/tag/' + intent['stable_tag']
    if (not isinstance(release, dict) or any(release.get(k) != expected[k] for k in ('tag_name', 'target_commitish', 'name', 'body', 'draft', 'prerelease'))
            or not isinstance(release.get('id'), int) or release['id'] <= 0
            or not release.get('published_at') or release.get('html_url') != expected_url):
        raise LabError('Release existente diverge da intenção ou ainda não foi publicada; não sobrescrever.')
    return {'id': release['id'], 'url': release['html_url'], 'tag_name': release['tag_name'],
            'published_at': release['published_at'], 'payload_digest': digest(expected)}


def promote_effects(policy, tag, intent_id):
    """Only create-and-GET effects. This function never runs inside mutate."""
    state, record, intent = live_intent(policy, tag, intent_id)
    tag_path = endpoint('git/ref/tags/' + quote(intent['stable_tag'], safe=''))
    release_path = endpoint('releases/tags/' + quote(intent['stable_tag'], safe=''))
    # A preexisting matching effect is owned only by the previously persisted
    # intent. No absent-intent caller can adopt a hand-created stable release.
    ref = api(tag_path, missing=True)
    release = api(release_path, missing=True)
    if ref is None:
        if release is not None:
            raise LabError('Release existe sem a tag esperada; não fabricar outro vínculo.')
        validate_version_available(policy, state, record['version'])
        live_intent(policy, tag, intent_id)
        create_ref_verified('tags/' + intent['stable_tag'], intent['source_sha'])
    if resolve_tag(intent['stable_tag']) != intent['source_sha']:
        raise LabError('Tag estável aponta a outro código; não mover ou apagar referências.')
    publication_checkpoint(policy, tag, intent_id, 'tag_verified', stable_tag_verified=True)
    state, record, intent = live_intent(policy, tag, intent_id)
    release = api(release_path, missing=True)
    if release is None:
        validate_version_available(policy, state, record['version'], owned_intent=True)
        live_intent(policy, tag, intent_id)
        try:
            api(endpoint('releases'), intent['release_payload'], 'POST')
        except LabError:
            release = api(release_path, missing=True)
            if release is None:
                raise
    # Never declare completed from POST success alone or from an old receipt.
    release = api(release_path)
    release_value = verify_release(release, intent)
    if resolve_tag(intent['stable_tag']) != intent['source_sha'] or resolve_tag(tag) != intent['source_sha']:
        raise LabError('Tag estável/RC divergiu após a publicação; recibo bloqueado.')
    publication_checkpoint(policy, tag, intent_id, 'release_verified', github_release=release_value)
    def complete(state, record):
        active = record['publication']
        verify_intent(policy, record, active)
        if active['intent_id'] != intent_id or state.get('preparation'):
            raise LabError('A intenção mudou antes de gravar o recibo.')
        if active.get('receipt'):
            return active['receipt']
        value = {'schema': 1, 'candidate_tag': tag, 'version': record['version'], 'title': record['title'],
                 'stable_tag': intent['stable_tag'], 'source_sha': record['source_sha'],
                 'report_digest': record['report_digest'], 'intent_id': intent_id,
                 'run_id': record['evaluation_run_id'], 'run_attempt': 1, 'preparer': record['preparer'],
                 **active['decision'], 'recorded_at': now(),
                 'recovery_authorizations': active.get('recovery_authorizations', []),
                 'platforms': record['report']['platforms'], 'preview': record['report']['preview'],
                 'account_review_verified': True, 'approval_evidence_kind': 'github_account_review',
                 'review_independence_verified': False, 'publication_mode': 'github_release_only',
                 'result_simulated': False, 'distribution_performed': False, 'patch_generated': False,
                 'stable_tag_created': True, 'github_release_published': True,
                 'github_release': release_value, 'release_url': release_value['url']}
        active.update(status='completed', receipt=value, updated_at=now())
        record.update(receipt=value, status='completed')
        state['last_completed_source_sha'] = record['source_sha']
        state['last_stable_version'] = record['version']
        state['last_stable_tag'] = intent['stable_tag']
        state['last_stable_source_sha'] = record['source_sha']
        return value
    return mutate(policy, tag, complete, 'github_release_completed')


def preserve_publication_failure(policy, tag, intent_id, error):
    try:
        publication_checkpoint(policy, tag, intent_id, 'failed',
                               last_error={'message': str(error), 'at': now(), 'run_id': os.environ['GITHUB_RUN_ID']})
    except LabError:
        # The original persisted intent is the recovery anchor even if the
        # journal is temporarily unavailable. Do not mask the initial failure.
        pass


def write_real_receipt(policy, tag, folder, value):
    output(folder, 'receipt.json', value)
    state, _ = state_read(policy)
    output(folder, 'publication.json', state['candidates'][tag]['publication'])
    Path(folder, 'events.jsonl').write_text(''.join(canonical(event) + '\n' for event in state['events'] if event['candidate'] == tag))
    message = ('# Tag estável e Release GitHub confirmadas\n\n'
               '[' + value['stable_tag'] + '](' + value['release_url'] + ') foi publicada a partir da candidata aprovada. '
               'A tag RC foi preservada. Nenhum aplicativo ou patch foi distribuído.\n\n'
               'Os registros confirmam reviews das contas GitHub; a independência das pessoas não foi comprovada.\n')
    if os.environ.get('GITHUB_STEP_SUMMARY'):
        with open(os.environ['GITHUB_STEP_SUMMARY'], 'a') as stream:
            stream.write(message)
    outputs({'status': 'completed', 'stable_tag': value['stable_tag'], 'release_url': value['release_url'],
             'result_simulated': 'false', 'distribution_performed': 'false'})


def finish_real(policy, tag, report_digest, folder):
    def authorize(state, record):
        if state.get('preparation'):
            raise LabError('Nova preparação em andamento; a decisão desta RC não inicia efeitos concorrentes.')
        frozen_publication(policy, record)
        protections(policy)
        decision = final_authorization(policy, record, report_digest)
        expected = publication_identity(record)
        existing = record.get('publication')
        if existing:
            verify_intent(policy, record, existing)
            if existing['decision'] != decision:
                raise LabError('A decisão do run original mudou; não substituir o publicador aprovado.')
            return dict(existing)
        if incomplete_publications(state):
            raise LabError('Outra intenção parcial impede publicar esta candidata.')
        validate_version_available(policy, state, record['version'])
        decision_digest = digest(decision)
        intent = {**expected, 'decision_digest': decision_digest,
                  'intent_id': digest({**expected, 'decision_digest': decision_digest}), 'decision': decision,
                  'created_at': now(), 'status': 'intent_recorded', 'recovery_authorizations': []}
        intent['release_payload'] = release_payload(record, decision, intent['intent_id'])
        record.update(publication=intent, status='publishing')
        return dict(intent)
    intent = mutate(policy, tag, authorize, 'publication_intent')
    output(folder, 'publication-intent.json', intent)
    try:
        value = promote_effects(policy, tag, intent['intent_id'])
    except (LabError, KeyError, ValueError) as error:
        preserve_publication_failure(policy, tag, intent['intent_id'], error)
        state, _ = state_read(policy)
        output(folder, 'publication-failure.json', state['candidates'][tag]['publication'])
        raise
    write_real_receipt(policy, tag, folder, value)


def recovery_inspect(policy, tag, folder):
    state, _ = state_read(policy)
    record = ensure_current(state, tag)
    intent = record.get('publication')
    if not intent or state.get('preparation'):
        raise LabError('Recuperação exige uma intenção real já autorizada, sem corte concorrente.')
    verify_intent(policy, record, intent)
    assert_record(policy, record)
    output(folder, 'publication.json', intent)
    report_url = 'https://github.com/' + REPOSITORY + '/actions/runs/' + str(record['evaluation_run_id'])
    outputs({'candidate_tag': tag, 'report_digest': record['report_digest'],
             'tooling_sha': record['tooling_sha'], 'final_environment': policy['final_environment'],
             'report_url': report_url, 'stable_tag': record['stable_tag']})


def recover(policy, tag, folder, report_digest=None):
    def authorize(state, record):
        if state.get('preparation'):
            raise LabError('Corte concorrente impede recuperar uma publicação.')
        intent = record.get('publication')
        if not intent:
            raise LabError('Recuperação não inicia outra publicação nem adota uma tag externa.')
        verify_intent(policy, record, intent)
        if str(record['evaluation_run_id']) == os.environ['GITHUB_RUN_ID']:
            raise LabError('Recuperação exige nova execução manual, com nova decisão no gate final.')
        if report_digest is not None and report_digest != record['report_digest']:
            raise LabError('Relatório da recuperação diverge da intenção original.')
        original = final_authorization(policy, record, record['report_digest'], original_run=True)
        if original != intent['decision']:
            raise LabError('Decisões originais divergiram; não reaproveitar avais de outra candidata.')
        ids = environments(policy)
        run_id = os.environ['GITHUB_RUN_ID']
        run = api(endpoint('actions/runs/' + run_id))
        actor = (int(os.environ['GITHUB_ACTOR_ID']), os.environ['GITHUB_ACTOR'].lower())
        if run.get('run_attempt') != 1 or identity(run['actor']) != actor or git('rev-parse', 'HEAD') != record['tooling_sha']:
            raise LabError('Recuperação deve partir das ferramentas aprovadas e de operador autorizado, em tentativa nova.')
        reviews = api(endpoint('actions/runs/' + run_id + '/approvals'))
        review = review_for(reviews, policy['final_environment'], ids[policy['final_environment']], policy['publishers'])
        authorization = {'run_id': run_id, 'review': review, 'recorded_at': now()}
        prior = [a for a in intent.get('recovery_authorizations', []) if a['run_id'] == run_id]
        if prior:
            if len(prior) != 1 or prior[0]['review'] != review:
                raise LabError('Decisão de recuperação ambígua; não substituir autoria.')
        else:
            intent.setdefault('recovery_authorizations', []).append(authorization)
        return dict(intent)
    intent = mutate(policy, tag, authorize, 'recovery_authorized')
    output(folder, 'recovery-intent.json', intent)
    try:
        value = promote_effects(policy, tag, intent['intent_id'])
    except (LabError, KeyError, ValueError) as error:
        preserve_publication_failure(policy, tag, intent['intent_id'], error)
        state, _ = state_read(policy)
        output(folder, 'publication-failure.json', state['candidates'][tag]['publication'])
        raise
    write_real_receipt(policy, tag, folder, value)


def finish(policy, tag, report_digest, folder):
    if publication_mode(policy) == 'github_release_only':
        return finish_real(policy, tag, report_digest, folder)
    def final_decision(state, record):
        if not record.get('report_digest') or record['report_digest'] != report_digest:
            raise LabError('Relatório final divergente.')
        reviews, ids = current_reviews(policy, record)
        result = validate_reviews(reviews, policy, ids, stage='final')
        receipts = record.get('approval_receipts', {})
        if set(receipts) != {'first', 'second'} or any(r['report_digest'] != report_digest for r in receipts.values()):
            raise LabError('Os dois jobs obrigatórios ainda não registraram sucesso.')
        jobs = api(endpoint('actions/runs/' + os.environ['GITHUB_RUN_ID'] + '/jobs?per_page=100'))['jobs']
        for role in ('first', 'second'):
            if not any(j['name'].endswith('Gate ' + role) and j.get('conclusion') == 'success' for j in jobs):
                raise LabError('Gate obrigatório rejeitado, ignorado, cancelado ou ainda sem sucesso.')
        if record.get('receipt'):
            return record['receipt']
        value = {'schema': 1, 'candidate_tag': tag, 'version': record['version'], 'title': record['title'],
                 'source_sha': record['source_sha'], 'report_digest': report_digest,
                 'run_id': record['evaluation_run_id'], 'run_attempt': 1,
                 'preparer': record['preparer'], **result, 'recorded_at': now(),
                 'platforms': record['report']['platforms'], 'preview': record['report']['preview'],
                 'human_decision_real': True, 'result_simulated': True,
                 'distribution_performed': False, 'patch_generated': False}
        record.update(receipt=value, status='completed')
        state['last_completed_source_sha'] = record['source_sha']
        return value
    value = mutate(policy, tag, final_decision, 'human_command_simulated_result')
    output(folder, 'receipt.json', value)
    state, _ = state_read(policy)
    folder = Path(folder)
    (folder / 'events.jsonl').write_text(''.join(canonical(e) + '\n' for e in state['events'] if e['candidate'] == tag))
    message = '# Decisão real registrada; resultado SIMULADO\n\nAs duas contas aprovaram e ' + value['publisher']['reviewer']['login'] + ' deu PUBLICAR. Nenhum patch gerado ou app distribuído.\n'
    if os.environ.get('GITHUB_STEP_SUMMARY'):
        with open(os.environ['GITHUB_STEP_SUMMARY'], 'a') as stream:
            stream.write(message)
    outputs({'status': 'completed', 'result_simulated': 'true', 'distribution_performed': 'false'})


def merge_preview(policy, tag, incoming, site, folder):
    """Fresh privileged runner accepts only validated static bytes, never app code."""
    import shutil
    import sys
    sys.path.insert(0, str(ROOT / 'deploy'))
    import pages_preview as pages
    state, _ = state_read(policy)
    record = ensure_current(state, tag)
    same_run(record); assert_record(policy, record)
    sha = record['source_sha']
    original_incoming = Path(incoming)
    if original_incoming.is_symlink() or any('.git' in p.relative_to(original_incoming).parts for p in original_incoming.rglob('*')):
        raise LabError('Artifact deve conter somente site estático, sem Git ou symlinks.')
    incoming, site = original_incoming.resolve(), Path(site).resolve()
    if incoming == site or incoming in site.parents or site in incoming.parents:
        raise LabError('Site e entrada precisam de pastas separadas.')
    if pages.validate_site(incoming) != [sha]:
        raise LabError('Artifact contém snapshot diferente ou extra.')
    metadata = pages.json_file(incoming / 'snapshots' / sha / 'metadata.json')
    git('fetch', '--no-tags', 'origin', sha)
    inputs = json.loads(git('show', sha + ':delivery/build-inputs.json'))
    command = ['flutter', 'build', 'web', '--release', '--base-href=' + pages.PROJECT_BASE + 'snapshots/' + sha + '/app/']
    version = re.search(r'^version:\s*(\S+)', git('show', sha + ':pubspec.yaml'), re.M)[1]
    if (metadata['source_tree'] != git('rev-parse', sha + '^{tree}')
            or metadata['source_build_inputs'] != inputs
            or metadata['pages_build_inputs'] != {**inputs, 'command': command}
            or metadata['version'] != version
            or metadata['fingerprint'] != pages.snapshots.build_fingerprint(ROOT, sha, {**inputs, 'command': command})
            or metadata['source_fingerprint'] != pages.source_fingerprint(ROOT, sha, inputs)):
        raise LabError('Artifact não corresponde ao código/inputs confiáveis.')
    existing = pages.validate_site(site)
    target = site / 'snapshots' / sha
    if sha in existing:
        prior = pages.json_file(target / 'metadata.json')
        for key in ('source_sha', 'source_tree', 'source_build_inputs', 'pages_build_inputs', 'source_fingerprint'):
            if prior[key] != metadata[key]:
                raise LabError('Snapshot histórico divergente; não sobrescrever.')
        metadata = prior
    else:
        shutil.copytree(incoming / 'snapshots' / sha, target)
    (site / '.nojekyll').write_text('')
    (site / 'index.html').write_text('<!doctype html><meta charset="utf-8"><a href="snapshots/' + sha + '/">Abrir preview</a>')
    pages.validate_site(site)
    metadata = {**metadata, 'snapshot_manifest_sha256': pages.digest(pages.json_file(target / 'files.json'))}
    output(folder, 'preview-metadata.json', metadata)
    outputs({'web_content_sha256': metadata['web_content_sha256'], 'snapshot_manifest_sha256': metadata['snapshot_manifest_sha256']})


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest='command', required=True)
    p = sub.add_parser('prepare'); p.add_argument('--version', required=True); p.add_argument('--title', required=True)
    for name in ('preflight', 'report', 'approval', 'finish', 'merge-preview', 'recovery-inspect', 'recover'):
        p = sub.add_parser(name); p.add_argument('--candidate-tag', required=True)
        if name == 'report':
            p.add_argument('--preview-report', required=True); p.add_argument('--preview-metadata', required=True)
        if name in ('approval', 'finish'):
            p.add_argument('--report-digest', required=True)
        if name == 'recover':
            p.add_argument('--report-digest')
        if name == 'approval':
            p.add_argument('--role', choices=('first', 'second'), required=True)
        if name == 'merge-preview':
            p.add_argument('--incoming', required=True); p.add_argument('--site', required=True)
    for p in sub.choices.values():
        p.add_argument('--output', required=True)
    args = parser.parse_args()
    policy = load_policy(); validate_context(policy, args.command, os.environ)
    if args.command == 'prepare':
        prepare(policy, args.version, args.title, args.output)
    elif args.command == 'preflight':
        preflight(policy, args.candidate_tag, args.output)
    elif args.command == 'report':
        report(policy, args.candidate_tag, args.preview_report, args.preview_metadata, args.output)
    elif args.command == 'approval':
        approval(policy, args.candidate_tag, args.role, args.report_digest, args.output)
    elif args.command == 'merge-preview':
        merge_preview(policy, args.candidate_tag, args.incoming, args.site, args.output)
    elif args.command == 'recovery-inspect':
        recovery_inspect(policy, args.candidate_tag, args.output)
    elif args.command == 'recover':
        recover(policy, args.candidate_tag, args.output, args.report_digest)
    else:
        finish(policy, args.candidate_tag, args.report_digest, args.output)


if __name__ == '__main__':
    try:
        main()
    except (LabError, KeyError, ValueError) as error:
        print('LAB bloqueado: ' + str(error))
        raise SystemExit(1)
