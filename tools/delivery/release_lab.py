"""Two real native approval gates, then a separate human command; LAB receipt only.

GitHub contents SHA provides optimistic concurrency for the journal. No app
publisher, bot approval, store upload or Shorebird command exists in this module.
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
    result = subprocess.run(args, input=None if data is None else canonical(data),
                            text=True, capture_output=True, timeout=60)
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


def validate_policy(policy):
    if (policy.get('schema') != 1 or policy.get('repository') != REPOSITORY
            or policy.get('state_branch') != 'codex/release-lab-state'
            or policy.get('result_simulated') is not True
            or policy.get('distribution_performed') is not False):
        raise LabError('Política fora do laboratório sem distribuição.')
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
    if operation == 'prepare' and ref != 'refs/heads/main':
        raise LabError('Preparar candidata exige a main.')


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


def mutate(policy, tag, callback, action):
    # Retries recompute ONLY the journal operation from current state. No tag,
    # branch, app delivery or external publication is repeated here.
    for attempt in range(5):
        state, sha = state_read(policy)
        record = ensure_current(state, tag)
        result = callback(state, record)
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
    rules = api(endpoint('rulesets'))
    for name, (target, patterns, kinds) in required.items():
        matching = [r for r in rules if r['name'] == name]
        if len(matching) != 1:
            raise LabError('Proteção obrigatória ausente: ' + name)
        rule = api(endpoint('rulesets/' + str(matching[0]['id'])))
        if (rule.get('enforcement') != 'active' or rule.get('target') != target or rule.get('bypass_actors')
                or rule.get('conditions', {}).get('ref_name') != {'include': patterns, 'exclude': []}
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


def prepare(policy, version, title, folder):
    if not VERSION.fullmatch(version) or not title.strip() or len(title) > 120 or any(ord(c) < 32 for c in title):
        raise LabError('Informe versão sem prefixo e título de 1 a 120 caracteres, em uma linha.')
    environments(policy)
    protections(policy)
    state, old_sha = state_read(policy)
    branch = 'release/' + version
    ref = api(endpoint('git/ref/heads/' + quote(branch, safe='')), missing=True)
    if ref is None:
        source_sha = api(endpoint('commits/main'))['sha']
        trusted_source(source_sha)
        api(endpoint('git/refs'), {'ref': 'refs/heads/' + branch, 'sha': source_sha}, 'POST')
    else:
        source_sha = ref['object']['sha']
        trusted_source(source_sha)
    refs = api(endpoint('git/matching-refs/tags/v' + version + '-rc.'))
    numbers = [int(TAG.fullmatch(r['ref'][10:])[2]) for r in refs if TAG.fullmatch(r['ref'][10:]) and TAG.fullmatch(r['ref'][10:])[1] == version]
    tag = 'v' + version + '-rc.' + str(max(numbers, default=0) + 1)
    api(endpoint('git/refs'), {'ref': 'refs/tags/' + tag, 'sha': source_sha}, 'POST')
    baseline = state.get('last_completed_source_sha') or resolve_tag(policy['changelog_initial_tag'])
    record = {'candidate_tag': tag, 'version': version, 'title': title,
              'source_sha': source_sha, 'release_branch': branch,
              'tooling_sha': git('rev-parse', 'HEAD'), 'policy_digest': digest(policy),
              'changelog_base_sha': baseline, 'created_at': now(),
              'preparer': {'login': os.environ['GITHUB_ACTOR'], 'id': int(os.environ['GITHUB_ACTOR_ID'])},
              'status': 'prepared', 'evaluation_run_id': None}
    if state.get('active'):
        state['candidates'][state['active']]['status'] = 'superseded'
    state['active'] = tag
    state['candidates'][tag] = record
    state['events'].append({'at': now(), 'action': 'prepare', 'candidate': tag,
                            'run_id': os.environ['GITHUB_RUN_ID'], 'source_sha': source_sha})
    state_write(policy, state, old_sha, 'lab: freeze ' + tag)
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
                 'result_simulated': True, 'distribution_performed': False}
        if record.get('report_digest'):
            raise LabError('Relatório já congelado; nova avaliação requer nova RC.')
        record.update(report=value, report_digest=digest(value), status='awaiting_approvals')
        return value
    value = mutate(policy, tag, register, 'report_frozen')
    output(folder, 'report.json', value)
    report_url = 'https://github.com/' + REPOSITORY + '/actions/runs/' + os.environ['GITHUB_RUN_ID']
    lines = ['# ' + value['version'] + ' — ' + html.escape(value['title']), '',
             '**' + tag + '** · preview real · resultado final SIMULADO', '',
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


def current_reviews(policy, record):
    same_run(record)
    if not record.get('report') or digest(record['report']) != record.get('report_digest'):
        raise LabError('Relatório congelado foi alterado; não reutilizar avais.')
    ids = assert_record(policy, record)
    run = api(endpoint('actions/runs/' + os.environ['GITHUB_RUN_ID']))
    if run.get('run_attempt') != 1 or identity(run['actor']) != identity(record['preparer']):
        raise LabError('Run/ator não corresponde à avaliação original.')
    reviews = api(endpoint('actions/runs/' + os.environ['GITHUB_RUN_ID'] + '/approvals'))
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


def finish(policy, tag, report_digest, folder):
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
    for name in ('preflight', 'report', 'approval', 'finish', 'merge-preview'):
        p = sub.add_parser(name); p.add_argument('--candidate-tag', required=True)
        if name == 'report':
            p.add_argument('--preview-report', required=True); p.add_argument('--preview-metadata', required=True)
        if name in ('approval', 'finish'):
            p.add_argument('--report-digest', required=True)
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
    else:
        finish(policy, args.candidate_tag, args.report_digest, args.output)


if __name__ == '__main__':
    try:
        main()
    except (LabError, KeyError, ValueError) as error:
        print('LAB bloqueado: ' + str(error))
        raise SystemExit(1)
