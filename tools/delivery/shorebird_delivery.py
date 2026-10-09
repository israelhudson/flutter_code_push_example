"""Local POC evidence bridge; never generates or promotes a Shorebird patch.

The operator executes the CLI separately after begin-upload. Provider observations
and local AAB hashes bind the receipt; ambiguous uploads are never retried here.
The GitHub report, original publication intent and original receipt stay frozen.
"""
import argparse
import copy
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
from urllib.parse import quote
import zipfile

import release_lab as lab
import version_manifest

APP_ID = 'bc6a30bd-0768-4326-8885-8be69c59aed2'
HASH = re.compile(r'[0-9a-f]{64}\Z')
ARCHES = {'arm': 'armeabi-v7a', 'aarch64': 'arm64-v8a', 'x86_64': 'x86_64'}
EXECUTION = 'authorized_local_lab_after_final_command'
OBSERVATION_KEYS = {'schema', 'kind', 'target', 'argv', 'exit_code', 'captured_at', 'provider_cli_version', 'data'}
COMMAND_KEYS = {'schema', 'target', 'source_sha', 'argv', 'exit_code', 'stdout_sha256', 'stderr_sha256',
                'aab_sha256', 'local_artifacts', 'captured_at', 'intent_id', 'evidence_kind'}
DEVICE_KEYS = {'schema', 'intent_id', 'source_sha', 'target', 'track', 'patch_number', 'observed_patch_number',
               'cold_restart', 'device', 'pid_before', 'pid_after', 'screenshot_sha256', 'sdk_log_sha256'}
RECEIPT_KEYS = {'schema', 'intent_id', 'source_sha', 'target', 'generation', 'patches_after', 'staging_info',
                'provider_patch', 'patch_generated', 'staging_confirmed', 'device_execution_verified', 'device_proof',
                'stable_confirmed', 'stable_info', 'evidence_kind', 'provider_git_sha_verified',
                'store_delivery_performed', 'receipt_digest'}


def exact_keys(value, keys, name):
    require(isinstance(value, dict) and set(value) == keys, name + ': campos extras ou ausentes; não gravar dados privados.')


def validate_executor(snapshot, operators):
    exact_keys(snapshot, {'id', 'login', 'type'}, 'Executor')
    require(type(snapshot.get('id')) is int and snapshot['id'] > 0
            and isinstance(snapshot.get('login'), str)
            and re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9-]{0,38}', snapshot['login'])
            and snapshot.get('type') == 'User'
            and lab.identity(snapshot) in {lab.identity(p) for p in operators},
            'Conta executora real não é operador humano autorizado.')
    return snapshot


def authenticated_executor(policy):
    """Never trust local GITHUB_ACTOR variables as authentication evidence."""
    try:
        result = subprocess.run(['gh', 'api', '--hostname', 'github.com', 'user',
                                 '--jq', '{id,login,type}'], text=True, capture_output=True, timeout=60)
    except subprocess.TimeoutExpired as error:
        raise lab.LabError('Não foi possível confirmar a conta GitHub executora.') from error
    require(result.returncode == 0, 'Conta GitHub executora não confirmada; nenhum efeito autorizado.')
    return validate_executor(json.loads(result.stdout), policy['operators'])


def require(condition, message):
    if not condition:
        raise lab.LabError(message)


def validate_target(target):
    lab.validate_mobile_plan(target)
    require(isinstance(target, dict), 'Plano mobile ausente.')
    require(target.get('schema') == 1 and target.get('app_id') == APP_ID
            and target.get('platform') == 'android' and target.get('execution') == EXECUTION
            and target.get('generation_track') == 'staging'
            and target.get('promotion_track') == 'stable'
            and target.get('device_validation_required') is True
            and target.get('patch_number') is None and target.get('base_git_sha') is None
            and type(target.get('provider_release_id')) is int and target['provider_release_id'] > 0
            and lab.SHA.fullmatch(str(target.get('flutter_revision', ''))),
            'Plano deve congelar POC, base exata, revisão, staging e prova antes de stable.')
    try:
        version_manifest.split_app_version(target.get('release_version'))
    except ValueError as error:
        raise lab.LabError(str(error)) from error
    return target


def target_identity(target):
    validate_target(target)
    return {k: target[k] for k in ('app_id', 'platform', 'release_version',
                                   'provider_release_id', 'flutter_revision')}


def verify_local_checkout(source_sha=None):
    require(Path.cwd().resolve() == lab.ROOT.resolve(), 'Execute somente no checkout isolado desta POC.')
    text = (lab.ROOT / 'shorebird.yaml').read_text()
    require(re.search(r'^app_id:\s*' + APP_ID + r'\s*$', text, re.M) is not None,
            'shorebird.yaml não identifica a POC autorizada.')
    if source_sha is not None:
        require(lab.git('rev-parse', 'HEAD') == source_sha, 'HEAD diverge do SHA aprovado.')
        require(not lab.git('status', '--porcelain', '--untracked-files=no'),
                'Checkout com alteração rastreada; não vincular outro código ao aval.')
        require(not lab.git('ls-files', '--others', '--exclude-standard', '--',
                            'lib', 'android', 'ios', 'assets', 'pubspec.yaml', 'pubspec.lock',
                            'pubspec_overrides.yaml', 'shorebird.yaml'),
                'Entrada de build não rastreada; evidência do SHA insuficiente.')
        require(not lab.git('ls-files', '--others', '--', 'lib', 'assets'),
                'Código/asset ignorado fora do SHA aprovado; checkout deve ser isolado.')
        root_inputs = ('pubspec.yaml', 'pubspec.lock', 'pubspec_overrides.yaml', 'shorebird.yaml')
        tracked = set(lab.git('ls-files', '--', *root_inputs).splitlines())
        require(not any((lab.ROOT / name).exists() and name not in tracked for name in root_inputs),
                'Override/configuração local fora do SHA; não vincular dependências ocultas ao aval.')


def provider_argv(target, kind, number=None):
    validate_target(target)
    if kind == 'release':
        return ['shorebird', 'releases', 'info', '--app-id', APP_ID,
                '--release-version', target['release_version'], '--json']
    require(kind in ('list', 'info'), 'Consulta Shorebird não permitida.')
    args = ['shorebird', 'patches', 'list' if kind == 'list' else 'info',
            '--app-id', APP_ID, '--release-version', target['release_version']]
    if kind == 'info':
        require(type(number) is int and number > 0, 'Consulta exige número confirmado.')
        args += ['--patch-number', str(number)]
    return args + ['--json']


def clean_patch(value):
    require(isinstance(value, dict) and type(value.get('id')) is int and value['id'] > 0
            and type(value.get('number')) is int and value['number'] > 0
            and value.get('channel') in ('staging', 'stable')
            and value.get('is_rolled_back') is False, 'Patch inválido, revertido ou track inesperado.')
    artifacts = value.get('artifacts')
    require(isinstance(artifacts, list) and len(artifacts) == len(ARCHES),
            'Exigir todos os artefatos Android desta base.')
    cleaned = []
    for item in artifacts:
        require(isinstance(item, dict) and item.get('platform') == 'android'
                and item.get('arch') in ARCHES and item.get('patch_id') == value['id']
                and type(item.get('id')) is int and item['id'] > 0
                and type(item.get('size')) is int and item['size'] > 0
                and HASH.fullmatch(str(item.get('hash', ''))), 'Artefato do patch divergente.')
        cleaned.append({k: item[k] for k in ('id', 'patch_id', 'arch', 'platform', 'hash', 'size')})
    require(len({a['arch'] for a in cleaned}) == len(ARCHES), 'Arquiteturas duplicadas ou ausentes.')
    return {'id': value['id'], 'number': value['number'], 'channel': value['channel'],
            'is_rolled_back': False, 'artifacts': sorted(cleaned, key=lambda a: a['arch'])}


def observation(target, kind, response, number=None):
    """Wrap only whitelisted query data; no account/email/token/signed URL fields."""
    require(isinstance(response, dict) and response.get('status') == 'success',
            'Consulta Shorebird não confirmou sucesso.')
    command = {'release': 'releases info', 'list': 'patches list', 'info': 'patches info'}[kind]
    require(response.get('meta', {}).get('command') == command, 'Envelope de outra consulta.')
    data = response.get('data', {})
    if kind == 'release':
        item = data.get('release', {})
        require(item.get('id') == target['provider_release_id'] and item.get('app_id') == APP_ID
                and item.get('version') == target['release_version']
                and item.get('flutter_revision') == target['flutter_revision']
                and item.get('flutter_version') == target['flutter_version']
                and item.get('platform_statuses', {}).get('android') == 'active',
                'Release-base, plataforma ou revisão divergente no provedor.')
        data = {k: item[k] for k in ('id', 'app_id', 'version', 'flutter_revision', 'flutter_version')}
        data['platform_statuses'] = {'android': 'active'}
    elif kind == 'list':
        require(isinstance(data.get('patches'), list), 'Lista de patches ausente.')
        data = [clean_patch(p) for p in data['patches']]
        require(len({p['id'] for p in data}) == len(data)
                and len({p['number'] for p in data}) == len(data), 'Lista de patches ambígua.')
    else:
        data = clean_patch(data.get('patch'))
        require(data['number'] == number, 'Info confirmou outro número de patch.')
    return {'schema': 1, 'kind': kind, 'target': target_identity(target),
            'argv': provider_argv(target, kind, number), 'exit_code': 0,
            'captured_at': lab.now(), 'provider_cli_version': response.get('meta', {}).get('version'),
            'data': data}


def validate_observation(value, target, kind, number=None):
    exact_keys(value, OBSERVATION_KEYS, 'Consulta')
    require(isinstance(value, dict) and type(value.get('schema')) is int and value['schema'] == 1 and value.get('kind') == kind
            and value.get('target') == target_identity(target)
            and type(value.get('exit_code')) is int and value['exit_code'] == 0
            and value.get('argv') == provider_argv(target, kind, number)
            and isinstance(value.get('captured_at'), str)
            and re.fullmatch(r'\d{4}-\d\d-\d\dT\d\d:\d\d:\d\d(?:\.\d{1,6})?\+00:00', value['captured_at'])
            and isinstance(value.get('provider_cli_version'), str)
            and re.fullmatch(r'\d+\.\d+\.\d+', value['provider_cli_version']),
            'Prova de consulta sem alvo/comando exatos.')
    response = {'status': 'success', 'meta': {'command': {'release': 'releases info', 'list': 'patches list', 'info': 'patches info'}[kind]},
                'data': {'release' if kind == 'release' else 'patches' if kind == 'list' else 'patch': value.get('data')}}
    require(observation(target, kind, response, number)['data'] == value['data'],
            'Consulta inclui dados não autorizados; não transportar resposta privada ao journal.')
    return value['data']


def capture_provider(target, kind, number=None):
    verify_local_checkout()
    args = provider_argv(target, kind, number)
    try:
        result = subprocess.run(args, text=True, capture_output=True, timeout=120)
    except subprocess.TimeoutExpired as error:
        raise lab.LabError('Consulta indisponível; nenhum upload foi executado.') from error
    require(result.returncode == 0, 'Consulta Shorebird recusada; saída privada não foi divulgada.')
    return observation(target, kind, json.loads(result.stdout), number)


def patch_argv(target, dry_run):
    args = ['shorebird', 'patch', 'android', '--release-version', target['release_version'],
            '--track', 'staging']
    return args + (['--dry-run'] if dry_run else []) + ['--json']


def aab_artifacts(path):
    """Provider artifact.hash is SHA256(full libapp.so), NOT SHA256(binary diff)."""
    with zipfile.ZipFile(path) as archive:
        return [{'arch': arch, 'platform': 'android',
                 'hash': hashlib.sha256(archive.read('base/lib/' + abi + '/libapp.so')).hexdigest()}
                for arch, abi in sorted(ARCHES.items())]


def command_proof(target, source_sha, dry_run, exit_code, stdout, stderr, aab, intent_id=None):
    verify_local_checkout(source_sha)
    value = {'schema': 1, 'target': target_identity(target), 'source_sha': source_sha,
             'argv': patch_argv(target, dry_run), 'exit_code': exit_code,
             'stdout_sha256': hashlib.sha256(Path(stdout).read_bytes()).hexdigest(),
             'stderr_sha256': hashlib.sha256(Path(stderr).read_bytes()).hexdigest(),
             'aab_sha256': hashlib.sha256(Path(aab).read_bytes()).hexdigest(),
             'local_artifacts': aab_artifacts(aab), 'captured_at': lab.now(),
             'intent_id': intent_id, 'evidence_kind': 'local_operator_cli_and_aab'}
    validate_command(value, target, source_sha, dry_run, intent_id)
    return value


def validate_command(value, target, source_sha, dry_run, intent_id=None):
    exact_keys(value, COMMAND_KEYS, 'CLI')
    require(isinstance(value, dict) and type(value.get('schema')) is int and value['schema'] == 1
            and value.get('target') == target_identity(target) and value.get('source_sha') == source_sha
            and value.get('argv') == patch_argv(target, dry_run)
            and type(value.get('exit_code')) is int and value['exit_code'] == 0
            and value.get('intent_id') == intent_id
            and value.get('evidence_kind') == 'local_operator_cli_and_aab'
            and isinstance(value.get('captured_at'), str)
            and re.fullmatch(r'\d{4}-\d\d-\d\dT\d\d:\d\d:\d\d(?:\.\d{1,6})?\+00:00', value['captured_at'])
            and all(HASH.fullmatch(str(value.get(k, ''))) for k in ('stdout_sha256', 'stderr_sha256', 'aab_sha256')),
            'CLI sem sucesso comprovado, SHA divergente ou flags não autorizados; não repetir upload.')
    artifacts = value.get('local_artifacts', [])
    require(isinstance(artifacts, list) and len(artifacts) == len(ARCHES)
            and {a.get('arch') for a in artifacts} == set(ARCHES)
            and all(set(a) == {'arch', 'platform', 'hash'} and a.get('platform') == 'android'
                    and HASH.fullmatch(str(a.get('hash', ''))) for a in artifacts),
            'Prova exige hashes reais de cada libapp.so do AAB final.')


def authorized_record(policy, state, tag):
    require(not state.get('preparation'), 'Nova preparação concorrente; não iniciar entrega mobile.')
    record = lab.ensure_current(state, tag)
    require(lab.digest(policy) == record.get('policy_digest'),
            'Política/operadores mudaram após os avais; não usar outro executor.')
    publication = record.get('publication', {})
    require(record.get('status') == 'completed' and publication.get('status') == 'completed'
            and publication.get('receipt') == record.get('receipt')
            and record.get('receipt', {}).get('github_release_published') is True,
            'Exigir Release GitHub concluída antes de qualquer intenção mobile.')
    lab.verify_intent(policy, record, publication)
    require(lab.digest(record.get('report')) == record.get('report_digest'), 'Relatório aprovado foi alterado.')
    decision = publication.get('decision', {})
    require(len(decision.get('approvers', [])) == 2
            and {lab.identity(a.get('reviewer', {})) for a in decision['approvers']}
            == {lab.identity(p) for p in policy['approvers']}
            and lab.identity(decision.get('publisher', {}).get('reviewer', {}))
            in {lab.identity(p) for p in policy['publishers']}, 'Exigir dois avais e comando final autorizado.')
    return record


def mobile_identity(record):
    target = validate_target(record.get('report', {}).get('mobile_execution_plan'))
    publication = record['publication']
    return {'schema': 1, 'candidate_tag': record['candidate_tag'], 'stable_tag': record['stable_tag'],
            'source_sha': record['source_sha'], 'report_digest': record['report_digest'],
            'github_intent_id': publication['intent_id'], 'decision_digest': publication['decision_digest'],
            'plan': copy.deepcopy(target), 'plan_digest': lab.digest(target), 'execution_kind': EXECUTION}


def verify_mobile_intent(policy, record, intent):
    lab.verify_intent(policy, record, record['publication'])
    expected = mobile_identity(record)
    require(isinstance(intent, dict) and all(intent.get(k) == v for k, v in expected.items()),
            'Intenção mobile diverge da identidade/decisão congelada.')
    target = expected['plan']
    validate_observation(intent.get('release'), target, 'release')
    validate_observation(intent.get('patches_before'), target, 'list')
    validate_command(intent.get('dry_run'), target, record['source_sha'], True)
    validate_executor(intent.get('executor'), policy['operators'])
    hashed = {**expected, 'executor': intent['executor'], 'release': intent['release'], 'patches_before': intent['patches_before'], 'dry_run': intent['dry_run']}
    require(intent.get('intent_id') == lab.digest(hashed), 'Hash da intenção mobile divergente.')
    verify_intent_binding(record['publication'], intent, record['report']['mobile_execution_plan'], policy['operators'])


def verify_intent_binding(github_intent, intent, approved_plan, approved_operators):
    """Pure verifier used by release readers; approved_plan comes from frozen report."""
    validate_target(approved_plan)
    require(isinstance(intent, dict), 'Intenção mobile ausente no leitor da Release.')
    expected = {'schema': 1, 'candidate_tag': github_intent['candidate_tag'],
                'stable_tag': github_intent['stable_tag'], 'source_sha': github_intent['source_sha'],
                'report_digest': github_intent['report_digest'], 'github_intent_id': github_intent['intent_id'],
                'decision_digest': github_intent['decision_digest'], 'plan': approved_plan,
                'plan_digest': lab.digest(approved_plan), 'execution_kind': EXECUTION,
                'executor': validate_executor(intent.get('executor'), approved_operators)}
    require(isinstance(intent, dict) and type(intent.get('schema')) is int
            and all(intent.get(k) == v for k, v in expected.items())
            and set(intent) == set(expected) | {'release', 'patches_before', 'dry_run', 'intent_id'},
            'Anexo mobile não pertence à intenção GitHub e ao plano aprovado.')
    validate_observation(intent['release'], approved_plan, 'release')
    validate_observation(intent['patches_before'], approved_plan, 'list')
    validate_command(intent['dry_run'], approved_plan, github_intent['source_sha'], True)
    hashed = {**expected, 'release': intent['release'], 'patches_before': intent['patches_before'], 'dry_run': intent['dry_run']}
    require(intent['intent_id'] == lab.digest(hashed), 'Intenção mobile adulterada no leitor da Release.')


def plan(policy, tag, release, patches_before, dry_run):
    executor = authenticated_executor(policy)
    def reserve(state, record):
        authorized_record(policy, state, tag)
        lab.assert_record(policy, record); lab.protections(policy)
        require(lab.final_authorization(policy, record, record['report_digest'], original_run=True)
                == record['publication']['decision'], 'As reviews oficiais mudaram após a publicação.')
        verify_local_checkout(record['source_sha'])
        identity = mobile_identity(record); target = identity['plan']
        validate_observation(release, target, 'release')
        validate_observation(patches_before, target, 'list')
        validate_command(dry_run, target, record['source_sha'], True)
        for other in state['candidates'].values():
            mobile = other.get('mobile_delivery')
            if other is not record and mobile and mobile.get('status') != 'completed':
                raise lab.LabError('Outra intenção mobile incompleta; reconciliar sem novo upload.')
        hashed = {**identity, 'executor': executor, 'release': release, 'patches_before': patches_before, 'dry_run': dry_run}
        intent = {**hashed, 'intent_id': lab.digest(hashed)}
        existing = record.get('mobile_delivery')
        if existing:
            verify_mobile_intent(policy, record, existing['intent'])
            require(existing['intent'] == intent, 'Outra intenção já ocupa esta entrega mobile.')
            return {'intent': copy.deepcopy(intent), 'new_intent_recorded': False, 'upload_permitted': False}
        release_value = lab.api(lab.endpoint('releases/tags/' + quote(record['stable_tag'], safe='')))
        lab.verify_release(release_value, record['publication'])
        record['mobile_delivery'] = {'schema': 1, 'intent': intent, 'status': 'intent_recorded', 'created_at': lab.now()}
        return {'intent': copy.deepcopy(intent), 'new_intent_recorded': True, 'upload_permitted': False}
    return lab.mutate(policy, tag, reserve, 'mobile_intent')


def begin_upload(policy, tag, intent_id):
    """Durably mark UNKNOWN before the operator invokes the external upload once."""
    executor = authenticated_executor(policy)
    def begin(state, record):
        authorized_record(policy, state, tag)
        lab.assert_record(policy, record); lab.protections(policy)
        require(lab.final_authorization(policy, record, record['report_digest'], original_run=True)
                == record['publication']['decision'], 'Reviews oficiais mudaram antes do upload.')
        mobile = record.get('mobile_delivery', {})
        verify_mobile_intent(policy, record, mobile.get('intent'))
        require(mobile['intent']['intent_id'] == intent_id and mobile.get('status') == 'intent_recorded',
                'Upload já pode ter ocorrido; consultar provedor, não repetir.')
        verify_local_checkout(record['source_sha'])
        mobile.update(status='upload_response_unknown', upload_started_at=lab.now(), last_executor=executor)
        return {'intent_id': intent_id, 'upload_permitted_once': True, 'next': 'execute CLI once; reconcile via provider observations'}
    return lab.mutate(policy, tag, begin, 'mobile_upload_started')


def validate_device(proof, intent, patch):
    exact_keys(proof, DEVICE_KEYS, 'Dispositivo')
    require(isinstance(proof, dict) and type(proof.get('schema')) is int and proof['schema'] == 1
            and proof.get('intent_id') == intent['intent_id'] and proof.get('source_sha') == intent['source_sha']
            and proof.get('target') == target_identity(intent['plan'])
            and proof.get('track') == 'staging'
            and type(proof.get('patch_number')) is int and proof['patch_number'] == patch['number']
            and type(proof.get('observed_patch_number')) is int and proof['observed_patch_number'] == patch['number']
            and proof.get('cold_restart') is True
            and isinstance(proof.get('device'), str)
            and re.fullmatch(r'[A-Za-z0-9_:-]{1,100}', proof['device'])
            and type(proof.get('pid_before')) is int and type(proof.get('pid_after')) is int
            and proof['pid_before'] > 0 and proof['pid_after'] > 0 and proof['pid_before'] != proof['pid_after']
            and all(HASH.fullmatch(str(proof.get(k, ''))) for k in ('screenshot_sha256', 'sdk_log_sha256')),
            'Instalação exige patch observado em staging após cold restart e provas locais.')


def verify_receipt(intent, receipt):
    exact_keys(receipt, RECEIPT_KEYS, 'Recibo')
    require(isinstance(receipt, dict) and type(receipt.get('schema')) is int and receipt['schema'] == 1
            and receipt.get('intent_id') == intent['intent_id'] and receipt.get('source_sha') == intent['source_sha']
            and receipt.get('target') == target_identity(intent['plan']), 'Recibo mobile de outra intenção.')
    payload = {k: v for k, v in receipt.items() if k != 'receipt_digest'}
    require(receipt.get('receipt_digest') == lab.digest(payload), 'Hash do recibo mobile divergente.')
    validate_command(receipt.get('generation'), intent['plan'], intent['source_sha'], False, intent['intent_id'])
    patch = clean_patch(receipt.get('provider_patch'))
    require(receipt['provider_patch'] == patch
            and receipt.get('evidence_kind') == 'provider_queries_and_local_cli_aab_device'
            and receipt.get('provider_git_sha_verified') is False
            and receipt.get('store_delivery_performed') is False, 'Recibo inclui dados extra ou alegação de prova indevida.')
    after = validate_observation(receipt.get('patches_after'), intent['plan'], 'list')
    before = validate_observation(intent['patches_before'], intent['plan'], 'list')
    old = {(p['id'], p['number']) for p in before}
    new = [p for p in after if (p['id'], p['number']) not in old]
    require(len(new) == 1 and new[0]['id'] == patch['id'] and new[0]['number'] == patch['number']
            and old <= {(p['id'], p['number']) for p in after}, 'Zero/vários novos patches ou histórico alterado; resultado desconhecido.')
    require({a['arch']: a['hash'] for a in patch['artifacts']}
            == {a['arch']: a['hash'] for a in receipt['generation']['local_artifacts']},
            'Patch do provedor não corresponde ao AAB local desta geração.')
    staging = validate_observation(receipt.get('staging_info'), intent['plan'], 'info', patch['number'])
    require(staging['channel'] == 'staging' and staging['id'] == patch['id']
            and staging['artifacts'] == patch['artifacts'], 'Primeira confirmação deve ser staging exato.')
    require(receipt.get('patch_generated') is True and receipt.get('staging_confirmed') is True,
            'Geração e staging devem ter provas separadas.')
    device = receipt.get('device_proof')
    require(receipt.get('device_execution_verified') is (device is not None), 'Status do dispositivo divergente.')
    if device is not None:
        validate_device(device, intent, patch)
    stable = receipt.get('stable_info')
    require(receipt.get('stable_confirmed') is (stable is not None), 'Status stable divergente.')
    if stable is not None:
        confirmed = validate_observation(stable, intent['plan'], 'info', patch['number'])
        require(device is not None and confirmed['channel'] == 'stable'
                and confirmed['id'] == patch['id'] and confirmed['artifacts'] == patch['artifacts'],
                'Stable exige prova anterior no dispositivo e o mesmo patch.')
    return receipt


def record_receipt(policy, tag, patches_after, staging_info, generation, device=None, stable_info=None):
    executor = authenticated_executor(policy)
    def register(state, record):
        authorized_record(policy, state, tag)
        mobile = record.get('mobile_delivery', {})
        intent = mobile.get('intent'); verify_mobile_intent(policy, record, intent)
        require(mobile.get('status') in ('upload_response_unknown', 'staging_confirmed', 'device_verified', 'stable_confirmed', 'completed'),
                'Intenção não passou pelo checkpoint anterior ao upload.')
        patch = staging_info.get('data', {})
        value = {'schema': 1, 'intent_id': intent['intent_id'], 'source_sha': intent['source_sha'],
                 'target': target_identity(intent['plan']), 'generation': generation,
                 'patches_after': patches_after, 'staging_info': staging_info, 'provider_patch': patch,
                 'patch_generated': True, 'staging_confirmed': True,
                 'device_execution_verified': device is not None, 'device_proof': device,
                 'stable_confirmed': stable_info is not None, 'stable_info': stable_info,
                 'evidence_kind': 'provider_queries_and_local_cli_aab_device',
                 'provider_git_sha_verified': False, 'store_delivery_performed': False}
        value['receipt_digest'] = lab.digest(value); verify_receipt(intent, value)
        prior = mobile.get('receipt')
        if stable_info is not None:
            require(prior is not None and prior.get('device_execution_verified') is True
                    and prior.get('device_proof') == device,
                    'Registrar prova do dispositivo antes de confirmar promoção stable.')
        if prior:
            verify_receipt(intent, prior)
            fixed = ('generation', 'patches_after', 'staging_info', 'provider_patch')
            require(all(prior[k] == value[k] for k in fixed)
                    and (prior.get('device_proof') is None or prior['device_proof'] == device)
                    and (prior.get('stable_info') is None or prior['stable_info'] == stable_info),
                    'Não substituir prova já registrada ou regredir o recibo.')
        mobile['receipt'] = value; mobile['last_executor'] = executor
        if mobile.get('status') != 'completed':
            mobile['status'] = 'stable_confirmed' if stable_info else 'device_verified' if device else 'staging_confirmed'
        return copy.deepcopy(value)
    return lab.mutate(policy, tag, register, 'mobile_receipt')


def receipt_section(intent, receipt):
    verify_receipt(intent, receipt)
    require(receipt.get('stable_confirmed') is True and receipt.get('device_execution_verified') is True,
            'Anexo público exige geração, dispositivo e stable confirmados.')
    target, patch = intent['plan'], receipt['provider_patch']
    lines = ['', '## Atualização Android confirmada no laboratório', '',
             '| Entrega | App Android / base Shorebird | Patch confirmado | Track |',
             '|---|---|---|---|',
             '| ' + intent['stable_tag'] + ' | ' + target['release_version'] + ' | '
             + str(patch['number']) + ' | stable |', '',
             'O patch foi gerado em staging, executado após reiniciar o app no dispositivo de laboratório e confirmado em stable.',
             'Este resultado não representa distribuição em loja nem publicação do Amulets.', '',
             '<details><summary>Evidência técnica do patch</summary>', '',
             '- App Shorebird: `' + APP_ID + '`; plataforma: Android.',
             '- Código da entrega: `' + intent['source_sha'] + '`.',
             '- Release-base do provedor: `' + str(target['provider_release_id']) + '`; SHA Git original da base não confirmado.',
             '- Flutter da base: `' + target['flutter_revision'] + '`.',
             '- Patch ID: `' + str(patch['id']) + '`.',
             '- Intenção mobile: `' + intent['intent_id'] + '`.',
             '- Recibo mobile: `' + receipt['receipt_digest'] + '`.',
             '- Número executado em staging: `' + str(receipt['device_proof']['observed_patch_number']) + '`.',
             '- Vínculo código/artefato: CLI local no SHA aprovado e hashes de libapp.so conferidos no provedor; o provedor não atesta SHA Git.',
             '', '| Arquitetura | SHA-256 de libapp.so confirmado |', '|---|---|']
    lines += ['| ' + a['arch'] + ' | `' + a['hash'] + '` |' for a in patch['artifacts']]
    lines += ['', '</details>', '', '<!-- release-lab-mobile:' + receipt['receipt_digest'] + ' -->']
    return '\n'.join(lines) + '\n'


def expected_extension(intent, github_intent, receipt, approved_plan, approved_operators):
    verify_intent_binding(github_intent, intent, approved_plan, approved_operators)
    body = github_intent['release_payload']['body'] + receipt_section(intent, receipt)
    return {'schema': 1, 'receipt_digest': receipt['receipt_digest'],
            'original_body_sha256': hashlib.sha256(github_intent['release_payload']['body'].encode()).hexdigest(),
            'extended_body_sha256': hashlib.sha256(body.encode()).hexdigest(),
            'body': body, 'cas_supported': False}


def verify_mobile_release_extension(release, github_intent, mobile, approved_plan, approved_operators):
    """Root verify_release can delegate here for an owned, completed extension."""
    require(isinstance(mobile, dict) and isinstance(mobile.get('intent'), dict), 'Intenção mobile ausente.')
    extension = expected_extension(mobile['intent'], github_intent, mobile.get('receipt'), approved_plan, approved_operators)
    stored = mobile.get('release_extension', {})
    require(stored.get('status') == 'completed'
            and all(stored.get(k) == v for k, v in extension.items()), 'Anexo não confirmado no journal.')
    expected = github_intent['release_payload']
    require(isinstance(release, dict) and release.get('body') == extension['body']
            and all(release.get(k) == expected[k] for k in ('tag_name', 'target_commitish', 'name', 'draft', 'prerelease'))
            and release.get('id') == stored.get('release_id') and bool(release.get('published_at'))
            and release.get('html_url') == 'https://github.com/' + lab.REPOSITORY + '/releases/tag/' + github_intent['stable_tag'],
            'Release diverge do body original acrescido da prova auditada.')
    return {'id': release['id'], 'url': release['html_url'], 'tag_name': release['tag_name'],
            'published_at': release['published_at'], 'payload_digest': lab.digest(expected),
            'mobile_receipt_digest': mobile['receipt']['receipt_digest'],
            'extended_body_sha256': extension['extended_body_sha256']}


def append_release(policy, tag):
    executor = authenticated_executor(policy)
    state, _ = lab.state_read(policy); record = authorized_record(policy, state, tag)
    mobile = record.get('mobile_delivery', {}); verify_mobile_intent(policy, record, mobile.get('intent'))
    approved_plan = record['report']['mobile_execution_plan']
    extension = expected_extension(mobile['intent'], record['publication'], mobile.get('receipt'), approved_plan, policy['operators'])
    path = lab.endpoint('releases/tags/' + quote(record['stable_tag'], safe=''))
    current = lab.api(path)
    def allowed(value):
        original = record['publication']['release_payload']
        require(isinstance(value, dict) and type(value.get('id')) is int
                and value.get('id') == record['publication']['receipt']['github_release']['id']
                and bool(value.get('published_at'))
                and value.get('html_url') == 'https://github.com/' + lab.REPOSITORY + '/releases/tag/' + record['stable_tag']
                and all(value.get(k) == original[k] for k in ('tag_name', 'target_commitish', 'name', 'draft', 'prerelease'))
                and value.get('body') in (original['body'], extension['body']),
                'Release editada ou body divergente; não sobrescrever.')
    allowed(current)
    def checkpoint(state, record):
        authorized_record(policy, state, tag)
        latest = record['mobile_delivery']; verify_mobile_intent(policy, record, latest['intent'])
        require(expected_extension(latest['intent'], record['publication'], latest['receipt'], record['report']['mobile_execution_plan'], policy['operators']) == extension,
                'Recibo mudou antes do anexo.')
        prior = latest.get('release_extension')
        if prior:
            require(all(prior.get(k) == v for k, v in extension.items()), 'Outro anexo já reservado.')
        else:
            latest['release_extension'] = {**extension, 'status': 'patch_response_unknown',
                                          'release_id': current['id'], 'created_at': lab.now()}
        latest['last_executor'] = executor
        return {'extension': copy.deepcopy(latest['release_extension']), 'newly_reserved': prior is None}
    owned_before = bool(mobile.get('release_extension'))
    require(current['body'] != extension['body'] or owned_before,
            'Body estendido sem intenção anterior; não adotar edição manual como efeito próprio.')
    claim = lab.mutate(policy, tag, checkpoint, 'mobile_release_extension_intent')
    # GitHub Release PATCH has no CAS. GET detects prior edits, but cannot prevent
    # an edit between this GET and PATCH. Serialize operators; document this gap.
    latest = lab.api(path); allowed(latest)
    if latest['body'] != extension['body']:
        require(claim['newly_reserved'], 'Outro writer possui a reserva ou resposta CAS foi perdida; não repetir PATCH.')
        try:
            lab.api(lab.endpoint('releases/' + str(latest['id'])), {'body': extension['body']}, 'PATCH')
        except lab.LabError:
            # Lost response: inspect once; never issue a second PATCH here.
            pass
    confirmed = lab.api(path); allowed(confirmed)
    require(confirmed['body'] == extension['body'], 'Anexo não confirmado; preservar unknown e reconciliar GET.')
    def complete(state, record):
        authorized_record(policy, state, tag)
        latest = record['mobile_delivery']
        require(expected_extension(latest['intent'], record['publication'], latest['receipt'], record['report']['mobile_execution_plan'], policy['operators']) == extension,
                'Recibo mudou durante o anexo.')
        latest['release_extension'].update(status='completed', confirmed_at=lab.now())
        latest['status'] = 'completed'
        return verify_mobile_release_extension(confirmed, record['publication'], latest, record['report']['mobile_execution_plan'], policy['operators'])
    return lab.mutate(policy, tag, complete, 'mobile_release_extension_completed')


def read(path):
    return json.loads(Path(path).read_text())


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest='command', required=True)
    capture = sub.add_parser('capture-provider'); capture.add_argument('--target', required=True)
    capture.add_argument('--kind', choices=('release', 'list', 'info'), required=True)
    capture.add_argument('--patch-number', type=int)
    proof = sub.add_parser('command-proof'); proof.add_argument('--target', required=True)
    proof.add_argument('--source-sha', required=True); proof.add_argument('--dry-run', action='store_true')
    proof.add_argument('--exit-code', type=int, required=True); proof.add_argument('--stdout', required=True)
    proof.add_argument('--stderr', required=True); proof.add_argument('--aab', required=True)
    proof.add_argument('--intent-id')
    for command in ('plan', 'begin-upload', 'record-receipt', 'append-release'):
        item = sub.add_parser(command); item.add_argument('--candidate-tag', required=True)
        if command == 'plan':
            for name in ('release-info', 'patches-before', 'dry-run-proof'):
                item.add_argument('--' + name, required=True)
        elif command == 'begin-upload':
            item.add_argument('--intent-id', required=True)
        elif command == 'record-receipt':
            for name in ('patches-after', 'staging-info', 'generation-proof'):
                item.add_argument('--' + name, required=True)
            item.add_argument('--device-proof'); item.add_argument('--stable-info')
    for item in sub.choices.values():
        item.add_argument('--output', required=True)
    args = parser.parse_args()
    try:
        if args.command == 'capture-provider':
            result = capture_provider(read(args.target), args.kind, args.patch_number)
        elif args.command == 'command-proof':
            result = command_proof(read(args.target), args.source_sha, args.dry_run, args.exit_code,
                                   args.stdout, args.stderr, args.aab, args.intent_id)
        else:
            verify_local_checkout()
            policy = lab.load_policy()
            state, _ = lab.state_read(policy)
            record = lab.ensure_current(state, args.candidate_tag)
            # This is an explicitly local executor, not a new Actions review.
            os.environ['GITHUB_RUN_ID'] = str(record['evaluation_run_id'])
            if args.command == 'plan':
                result = plan(policy, args.candidate_tag, read(args.release_info),
                              read(args.patches_before), read(args.dry_run_proof))
            elif args.command == 'begin-upload':
                result = begin_upload(policy, args.candidate_tag, args.intent_id)
            elif args.command == 'record-receipt':
                result = record_receipt(policy, args.candidate_tag, read(args.patches_after),
                                        read(args.staging_info), read(args.generation_proof),
                                        read(args.device_proof) if args.device_proof else None,
                                        read(args.stable_info) if args.stable_info else None)
            else:
                result = append_release(policy, args.candidate_tag)
        lab.output(Path(args.output).parent, Path(args.output).name, result)
        print(lab.canonical({'status': 'success', 'output': args.output,
                             'remote_shorebird_mutation_performed_by_bridge': False}))
    except (lab.LabError, ValueError, KeyError, TypeError, OSError, zipfile.BadZipFile) as error:
        print(lab.canonical({'status': 'blocked', 'message': str(error)}))
        raise SystemExit(1) from error


if __name__ == '__main__':
    main()
