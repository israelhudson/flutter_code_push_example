"""Local Android staging bridge for Delivery v2, independent of the LAB journal.

GitHub's immutable manifest/events authorize one attempted upload. Provider
queries and the final AAB bind its result. No stable promotion, store upload,
iOS operation, automatic retry or claim of device execution exists here.
"""
import argparse
import base64
import hashlib
import json
from pathlib import Path
import re
import subprocess
import uuid

import delivery_v2 as delivery
import release_lab as lab
import shorebird_delivery as mobile

HISTORY = 'codex/delivery-history'
OPERATOR = {'id': 18661493, 'login': 'israelhudson', 'type': 'User'}
ID = re.compile(r'delivery-[a-f0-9]{32}\Z')
STAMP = re.compile(r'\d{4}-\d\d-\d\dT\d\d:\d\d:\d\d(?:\.\d{1,6})?(?:\+00:00|Z)\Z')
ASSET = 'platform-receipt-android.json'
INTENT = 'android-staging-intent.json'
RECEIPT = 'android-staging-receipt.json'


def require(condition, message):
    mobile.require(condition, message)


def expected_plan():
    target = json.loads((lab.ROOT / 'delivery/shorebird-lab-target.json').read_text())
    mobile.validate_target(target)
    require(target['release_version'] == '1.1.0+2' and target['provider_release_id'] == 776887,
            'Esta ponte permite somente a base Android 1.1.0+2/776887.')
    return {'schema': 'delivery-android-staging-v1', 'target': target,
            'execution': 'local_operator_after_github_publication',
            'track': 'staging', 'stable_authorized': False}


def private_output(value):
    output = Path(value).expanduser().resolve()
    require(not output.is_relative_to(lab.ROOT.resolve()), 'Logs privados devem ficar fora do repositório.')
    output.mkdir(parents=True, exist_ok=True, mode=0o700)
    output.chmod(0o700)
    return output


def save(output, name, value):
    path = output / name
    path.write_text(lab.canonical(value) + '\n')
    path.chmod(0o600)
    return path


def json_record(path, ref, missing=False):
    record = lab.api(lab.endpoint('contents/' + path + '?ref=' + ref), missing=missing)
    if record is None:
        return None
    require(record.get('encoding') == 'base64', 'Journal não retornou um arquivo JSON completo.')
    content = base64.b64decode(record['content'], validate=False)
    require(len(content) <= 131072, 'Registro excede o limite de evidência.')
    return json.loads(content)


def history_head():
    head = lab.api(lab.endpoint('git/ref/heads/' + HISTORY))['object']
    require(head.get('type') == 'commit' and lab.SHA.fullmatch(head.get('sha', '')),
            'Histórico não aponta para commit imutável.')
    return head['sha']


def verify_authorization(manifest, events, run, release, rc, final):
    """Pure validation of real API observations; solo means two role decisions."""
    require(isinstance(manifest, dict) and ID.fullmatch(str(manifest.get('id', '')))
            and manifest.get('repository') == lab.REPOSITORY
            and lab.VERSION.fullmatch(str(manifest.get('version', '')))
            and lab.SHA.fullmatch(str(manifest.get('source_sha', '')))
            and manifest.get('publication_scope') == 'github_test'
            and manifest.get('validation_mode') == 'full'
            and manifest.get('validation_only') is not True,
            'Manifesto não autoriza entrega real v2 nesta POC.')
    delivery.require_reviewers(manifest.get('reviewers'))
    require(manifest.get('mobile_execution_plan') == expected_plan(),
            'O plano Android staging precisa estar congelado antes dos aceites.')
    require(manifest['mobile_execution_plan'].get('stable_authorized') is False,
            'Promoção stable não faz parte desta autorização.')
    version, source = manifest['version'], manifest['source_sha']
    require(type(manifest.get('rc_number')) is int and manifest['rc_number'] > 0
            and manifest.get('rc_tag') == f'poc-v{version}-rc.{manifest["rc_number"]}',
            'Tag RC não corresponde à candidata aprovada.')
    require(isinstance(events, list) and events and len(events) <= 100,
            'Histórico de decisões ausente ou excessivo.')
    previous = None
    for revision, event in enumerate(events):
        require(isinstance(event, dict) and type(event.get('revision')) is int and event['revision'] == revision
                and event.get('candidate') == manifest['id'] and event.get('source_sha') == source
                and event.get('solo') is manifest['reviewers']['solo']
                and event.get('reviewers') == manifest['reviewers']
                and event.get('status') in ('pending', 'approved', 'publishing', 'published')
                and event.get('rejected_role') is None and event.get('rejected_at') is None,
                'Journal incompleto, rejeitado, cancelado ou de outra autorização.')
        if previous:
            for role in ('technical', 'business'):
                if previous.get(role + '_at') is not None:
                    require(event.get(role + '_at') == previous[role + '_at'],
                            'Aceite histórico foi alterado.')
            order = {'pending': 0, 'approved': 1, 'publishing': 2, 'published': 3}
            require(order[event['status']] >= order[previous['status']], 'Estado histórico regrediu.')
            if previous.get('publication_run') is not None:
                require(event.get('publication_run') == previous['publication_run'], 'Execução de publicação foi substituída.')
        if event['status'] != 'pending':
            require(all(STAMP.fullmatch(str(event.get(role + '_at', '')))
                        for role in ('technical', 'business')), 'Estado avançou sem os dois aceites.')
        previous = event
    final_event = events[-1]
    require(events[0]['status'] == 'pending'
            and {'approved', 'publishing', 'published'} <= {event['status'] for event in events},
            'Histórico não comprova aprovação, início e conclusão separados.')
    require(final_event['status'] == 'published'
            and all(STAMP.fullmatch(str(final_event.get(role + '_at', '')))
                    for role in ('technical', 'business'))
            and re.fullmatch(r'[1-9][0-9]*', str(final_event.get('publication_run', ''))),
            'Exigir dois aceites reais e publicação GitHub concluída no journal.')
    require(type(run.get('id')) is int and str(run['id']) == str(final_event['publication_run'])
            and run.get('repository', {}).get('full_name') == lab.REPOSITORY
            and run.get('event') == 'workflow_dispatch' and run.get('head_branch') == 'main'
            and run.get('path') == '.github/workflows/delivery-publish.yml'
            and run.get('status') == 'completed' and run.get('conclusion') == 'success',
            'A execução real da publicação v2 na main não concluiu com sucesso.')
    require(all(ref.get('object', {}).get('type') == 'commit'
                and ref['object'].get('sha') == source for ref in (rc, final)),
            'Tag RC/final diverge do SHA aprovado; nenhuma tag será movida.')
    require(type(release.get('id')) is int and release['id'] > 0
            and release.get('tag_name') == 'poc-v' + version and release.get('draft') is False
            and release.get('prerelease') is False
            and release.get('html_url') == f'https://github.com/{lab.REPOSITORY}/releases/tag/poc-v{version}',
            'Release final não confirma a versão aprovada.')
    return {'candidate_id': manifest['id'], 'source_sha': source,
            'report_digest': lab.digest(manifest), 'publication_run': str(run['id']),
            'release_id': release['id'], 'github_tag': 'poc-v' + version,
            'rc_tag': manifest['rc_tag'], 'version': version}


def authorization(candidate):
    require(ID.fullmatch(candidate or ''), 'ID de candidata v2 inválido.')
    delivery.require_history_protection()
    commit = history_head()
    folder = 'candidates/' + candidate
    manifest = json_record(folder + '/manifest.json', commit)
    require(manifest.get('id') == candidate, 'Manifesto de outra candidata.')
    entries = lab.api(lab.endpoint('contents/' + folder + '?ref=' + commit))
    require(isinstance(entries, list), 'Pasta da candidata indisponível.')
    numbered = []
    for entry in entries:
        match = re.fullmatch(r'event-(0|[1-9][0-9]*)\.json', entry.get('name', ''))
        if match:
            numbered.append((int(match[1]), entry['name']))
    numbered.sort()
    require([n for n, _ in numbered] == list(range(len(numbered))) and numbered,
            'Há lacunas no histórico; espere o worker antes de enviar patch.')
    events = [json_record(folder + '/' + name, commit) for _, name in numbered]
    publication_run = str(events[-1].get('publication_run', ''))
    require(re.fullmatch(r'[1-9][0-9]*', publication_run), 'Publicação GitHub ainda não registrada.')
    run = lab.api(lab.endpoint('actions/runs/' + publication_run))
    version = manifest.get('version', '')
    require(lab.VERSION.fullmatch(version), 'Versão inválida.')
    rc_tag = manifest.get('rc_tag', '')
    require(re.fullmatch(r'poc-v\d+\.\d+\.\d+-rc\.[1-9][0-9]*', rc_tag), 'Tag RC inválida.')
    release = lab.api(lab.endpoint('releases/tags/poc-v' + version))
    rc = lab.api(lab.endpoint('git/ref/tags/' + rc_tag))
    final = lab.api(lab.endpoint('git/ref/tags/poc-v' + version))
    proof = verify_authorization(manifest, events, run, release, rc, final)
    proof['history_commit'] = commit
    return manifest, proof, release


def readiness(candidate, output):
    operator = mobile.authenticated_executor({'operators': [OPERATOR]})
    manifest, proof, release = authorization(candidate)
    mobile.verify_local_checkout(manifest['source_sha'])
    require(not lab.git('status', '--porcelain'), 'Checkout deve estar limpo, inclusive arquivos não rastreados.')
    plan = expected_plan()
    observation = mobile.capture_provider(plan['target'], 'release')
    mobile.validate_observation(observation, plan['target'], 'release')
    save(output, 'authorization.json', {'proof': proof, 'operator': operator,
                                     'mobile_execution_plan': plan, 'release_base': observation})
    return manifest, proof, release, operator


def run_patch(target, source, output, dry, intent_id=None):
    mobile.verify_local_checkout(source)
    argv = mobile.patch_argv(target, dry)
    stdout, stderr = output / ('dry-run.stdout.log' if dry else 'upload.stdout.log'), output / ('dry-run.stderr.log' if dry else 'upload.stderr.log')
    for path in (stdout, stderr):
        require(not path.exists(), 'Logs desta tentativa já existem; preserve-os e reconcilie.')
        path.touch(mode=0o600)
    try:
        with stdout.open('w') as out, stderr.open('w') as err:
            result = subprocess.run(argv, stdout=out, stderr=err, timeout=3600)
        exit_code = result.returncode
    except subprocess.TimeoutExpired as error:
        save(output, 'dry-run-result.json' if dry else 'upload-result.json',
             {'exit_code': None, 'response_unknown': True, 'argv': argv})
        raise lab.LabError('CLI sem resposta; não repetir upload. Preserve os logs e reconcilie.') from error
    save(output, 'dry-run-result.json' if dry else 'upload-result.json',
         {'exit_code': exit_code, 'response_unknown': exit_code != 0, 'argv': argv})
    require(exit_code == 0, 'CLI não concluiu com sucesso; não repetir upload automaticamente.')
    proof = mobile.command_proof(target, source, dry, exit_code, stdout, stderr,
                                lab.ROOT / 'build/app/outputs/bundle/release/app-release.aab', intent_id)
    save(output, 'dry-run-proof.json' if dry else 'upload-proof.json', proof)
    return proof


def create_once(path, value):
    """An existing record, racing writer or lost response never permits upload."""
    require(json_record(path, history_head(), missing=True) is None,
            'Intenção/recibo já existe; use reconcile, nunca outro upload.')
    try:
        result = lab.api(lab.endpoint('contents/' + path), {
            'message': 'delivery: record Android staging ' + path,
            'branch': HISTORY, 'content': base64.b64encode(lab.canonical(value).encode()).decode()}, 'PUT')
    except lab.LabError as error:
        raise lab.LabError('Reserva GitHub não confirmada; upload proibido, mesmo se o registro apareceu depois.') from error
    commit = result.get('commit', {}).get('sha', '')
    require(lab.SHA.fullmatch(commit) and json_record(path, commit) == value,
            'Reserva não confirmada byte a byte; não executar upload.')
    return commit


def other_pending(candidate):
    commit = history_head()
    tree = lab.api(lab.endpoint('git/trees/' + commit + '?recursive=1'))
    require(tree.get('truncated') is False, 'Árvore truncada; não confirmar concorrência da base.')
    paths = {entry['path'] for entry in tree['tree'] if entry.get('type') == 'blob'}
    for path in paths:
        match = re.fullmatch(r'candidates/(delivery-[a-f0-9]{32})/' + INTENT, path)
        if match and match[1] != candidate:
            require(f'candidates/{match[1]}/{RECEIPT}' in paths,
                    'Outra intenção Android está sem recibo; reconciliar a base antes de enviar.')


def make_receipt(manifest, proof, intent, generation, after, info):
    target = expected_plan()['target']
    require(intent.get('candidate_id') == manifest['id'] and intent.get('source_sha') == manifest['source_sha']
            and intent.get('report_digest') == lab.digest(manifest)
            and all(intent.get('authorization', {}).get(k) == value
                    for k, value in proof.items() if k != 'history_commit')
            and intent.get('mobile_execution_plan') == expected_plan()
            and intent.get('operator') == OPERATOR,
            'Intenção não pertence ao código, à publicação e ao operador autorizados.')
    unsigned = {k: v for k, v in intent.items() if k != 'intent_id'}
    require(intent.get('intent_id') == lab.digest(unsigned), 'Intenção Android foi alterada.')
    mobile.validate_command(intent.get('dry_run'), target, manifest['source_sha'], True)
    mobile.validate_command(generation, target, manifest['source_sha'], False, intent['intent_id'])
    before = mobile.validate_observation(intent.get('patches_before'), target, 'list')
    patches = mobile.validate_observation(after, target, 'list')
    old = {(p['id'], p['number']) for p in before}
    new = [p for p in patches if (p['id'], p['number']) not in old]
    require(len(new) == 1 and old <= {(p['id'], p['number']) for p in patches},
            'Zero/vários patches novos ou histórico removido; resultado permanece desconhecido.')
    patch = new[0]
    observed = mobile.validate_observation(info, target, 'info', patch['number'])
    require(observed == patch and patch['channel'] == 'staging', 'Patch exato não está confirmado em staging.')
    require({a['arch']: a['hash'] for a in patch['artifacts']} ==
            {a['arch']: a['hash'] for a in generation['local_artifacts']},
            'Os três libapp.so do AAB não correspondem ao patch observado.')
    return {'schema': 1, 'kind': 'local_operator_android_staging_receipt',
            'candidate_id': manifest['id'], 'delivery_version': manifest['version'],
            'rc_tag': manifest['rc_tag'], 'github_tag': proof['github_tag'],
            'source_sha': manifest['source_sha'], 'report_digest': lab.digest(manifest),
            'target': mobile.target_identity(target), 'track': 'staging', 'uploaded': True,
            'patch_number': patch['number'], 'provider_patch_id': patch['id'],
            'promoted_to_stable': False, 'provider_git_sha_verified': False,
            'device_validation': {'successful_launch_confirmed': False, 'cold_restart_confirmed': False,
                                  'active_patch': None, 'base_version': target['release_version']},
            'evidence_kind': 'local_operator_cli_aab_and_provider_queries',
            'intent_id': intent['intent_id'], 'operator': OPERATOR,
            'generation': generation, 'patches_after': after, 'staging_info': info,
            'store_delivery_performed': False}


def verify_asset(release_id, receipt):
    release = lab.api(lab.endpoint('releases/' + str(release_id)))
    assets = [a for a in release.get('assets', []) if a.get('name') == ASSET]
    require(len(assets) <= 1, 'Há recibos Android ambíguos na Release.')
    if not assets:
        return False
    asset = assets[0]
    expected = (lab.canonical(receipt) + '\n').encode()
    require(asset.get('digest') == 'sha256:' + hashlib.sha256(expected).hexdigest()
            and asset.get('size') == len(expected),
            'Asset Android existente diverge; não substituir.')
    return True


def attach(proof, receipt, output):
    path = save(output, ASSET, receipt)
    if not verify_asset(proof['release_id'], receipt):
        result = subprocess.run(['gh', 'release', 'upload', proof['github_tag'], str(path),
                                 '--repo', lab.REPOSITORY], text=True, capture_output=True, timeout=120)
        require(result.returncode == 0 and verify_asset(proof['release_id'], receipt),
                'Anexo sem confirmação; preserve o recibo e reconcilie, sem reenviar patch.')


def reconcile(candidate, output):
    manifest, proof, _, _ = readiness(candidate, output)
    intent = json_record(f'candidates/{candidate}/{INTENT}', history_head())
    generation_path = output / 'upload-proof.json'
    require(generation_path.exists(), 'Prova da geração local ausente; não atribuir um patch de outra execução.')
    generation = json.loads(generation_path.read_text())
    target = expected_plan()['target']
    remote_path = f'candidates/{candidate}/{RECEIPT}'
    existing = json_record(remote_path, history_head(), missing=True)
    if existing is not None:
        # A failed asset attachment must remain recoverable after another delivery
        # generated a later patch. Revalidate the sealed original delta and AAB,
        # then query its exact provider identity, never reinterpret the new delta.
        sealed = make_receipt(manifest, proof, intent, generation,
                              existing.get('patches_after'), existing.get('staging_info'))
        require(existing == sealed,
                'Recibo imutável diverge do resultado; não sobrescrever.')
        info = mobile.capture_provider(target, 'info', sealed['patch_number'])
        current = mobile.validate_observation(info, target, 'info', sealed['patch_number'])
        original = mobile.validate_observation(sealed['staging_info'], target, 'info', sealed['patch_number'])
        require(all(current[k] == original[k] for k in ('id', 'number', 'artifacts', 'is_rolled_back')),
                'O patch selado não corresponde mais ao mesmo artefato no provedor.')
        receipt = existing
    else:
        after = mobile.capture_provider(target, 'list')
        before = mobile.validate_observation(intent['patches_before'], target, 'list')
        patches = mobile.validate_observation(after, target, 'list')
        old = {(p['id'], p['number']) for p in before}
        new = [p for p in patches if (p['id'], p['number']) not in old]
        require(len(new) == 1, 'Não foi possível isolar um único patch desta tentativa; não reenviar.')
        info = mobile.capture_provider(target, 'info', new[0]['number'])
        receipt = make_receipt(manifest, proof, intent, generation, after, info)
        create_once(remote_path, receipt)
    attach(proof, receipt, output)
    save(output, 'completed.json', {'uploaded': True, 'patch_number': receipt['patch_number'],
                                  'track': 'staging', 'device_execution_verified': False,
                                  'stable_authorized': False, 'release_asset': ASSET})
    return receipt


def upload(candidate, output):
    manifest, proof, release, operator = readiness(candidate, output)
    other_pending(candidate)
    intent_path = f'candidates/{candidate}/{INTENT}'
    require(json_record(intent_path, history_head(), missing=True) is None,
            'Upload já iniciado ou resposta desconhecida. Use reconcile; não repetir.')
    require(not any(a.get('name') in (ASSET, f'shorebird-staging-receipt-{manifest["version"]}.json')
                    for a in release.get('assets', [])),
            'A Release já contém um recibo Android; reconciliar antes de qualquer upload.')
    dry = json.loads((output / 'dry-run-proof.json').read_text())
    target = expected_plan()['target']
    mobile.validate_command(dry, target, manifest['source_sha'], True)
    # Bind the saved dry-run to its actual files, not user-supplied JSON alone.
    actual = mobile.command_proof(target, manifest['source_sha'], True, 0,
                                 output / 'dry-run.stdout.log', output / 'dry-run.stderr.log',
                                 lab.ROOT / 'build/app/outputs/bundle/release/app-release.aab')
    require(all(actual[k] == dry[k] for k in actual if k != 'captured_at'),
            'Logs/AAB do dry-run mudaram; não executar upload.')
    before = mobile.capture_provider(target, 'list')
    intent = {'schema': 'delivery-android-staging-intent-v1', 'candidate_id': candidate,
              'source_sha': manifest['source_sha'], 'report_digest': lab.digest(manifest),
              'authorization': proof, 'operator': operator, 'mobile_execution_plan': expected_plan(),
              'dry_run': dry, 'patches_before': before, 'attempt': str(uuid.uuid4()),
              'started_at': lab.now(), 'state': 'upload_response_unknown'}
    intent['intent_id'] = lab.digest(intent)
    create_once(intent_path, intent)
    save(output, 'upload-intent.json', intent)
    other_pending(candidate)
    run_patch(target, manifest['source_sha'], output, False, intent['intent_id'])
    return reconcile(candidate, output)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('operation', choices=['readiness', 'dry-run', 'upload', 'reconcile'])
    parser.add_argument('--candidate', required=True)
    parser.add_argument('--output', required=True)
    args = parser.parse_args()
    output = private_output(args.output)
    try:
        if args.operation == 'readiness':
            _, proof, _, _ = readiness(args.candidate, output)
            result = {'ready': True, 'source_sha': proof['source_sha'], 'track': 'staging'}
        elif args.operation == 'dry-run':
            manifest, _, _, _ = readiness(args.candidate, output)
            result = run_patch(expected_plan()['target'], manifest['source_sha'], output, True)
        elif args.operation == 'upload':
            result = upload(args.candidate, output)
        else:
            result = reconcile(args.candidate, output)
        print(lab.canonical({'operation': args.operation, 'success': True,
                             'patch_number': result.get('patch_number'), 'stable_authorized': False}))
        return 0
    except (lab.LabError, OSError, ValueError, KeyError, subprocess.TimeoutExpired) as error:
        message = str(error) if isinstance(error, lab.LabError) else 'Evidência inválida/indisponível; preservar logs e não reenviar patch.'
        save(output, 'blocked.json', {'operation': args.operation, 'reason': message,
                                     'stable_authorized': False, 'retry_upload_authorized': False})
        print(message)
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
