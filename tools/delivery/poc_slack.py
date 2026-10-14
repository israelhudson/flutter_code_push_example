"""Isolated Slack/Supabase POC. No Shorebird calls or legacy journal writes."""
import argparse
import html
import json
import os
from pathlib import Path
import re
import time
from urllib.parse import urlparse
from urllib.request import HTTPRedirectHandler, Request, build_opener

import release_lab as lab

PROJECT_FORBIDDEN = 'uvfwvplcziehxrkidrxh'
GUARDS = {
    'Slack - tags imutaveis': ('tag', ['refs/tags/poc-*'], {'update', 'deletion'}),
    'Slack - PRs solo': ('branch', ['refs/heads/slack-main', 'refs/heads/poc-release/**'], {'pull_request', 'required_status_checks', 'non_fast_forward', 'deletion'}),
}


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, request, response, code, message, headers, newurl):
        return None


def backend_origin(value):
    p = urlparse(value or '')
    if (p.scheme != 'https' or not re.fullmatch(r'[a-z]{20}\.supabase\.co', p.hostname or '')
            or p.hostname.startswith(PROJECT_FORBIDDEN + '.') or p.username or p.password
            or p.port or p.query or p.fragment or p.path not in ('', '/')):
        raise lab.LabError('Informe projeto Supabase exclusivo; o projeto compartilhado está bloqueado.')
    return 'https://' + p.hostname


def control(operation, **data):
    base = backend_origin(os.environ.get('POC_SUPABASE_URL'))
    secret_name = 'POC_PUBLICATION_SECRET' if operation in ('state', 'claim', 'complete') else 'POC_REGISTRATION_SECRET'
    secret = os.environ.get(secret_name)
    if not secret:
        raise lab.LabError('Credencial exclusiva da POC ausente: ' + secret_name)
    body = {'operation': operation, 'run_id': os.environ['GITHUB_RUN_ID'], **data}
    request = Request(base + '/functions/v1/poc-control', method='POST',
                      data=lab.canonical(body).encode(),
                      headers={'Content-Type': 'application/json', 'Authorization': 'Bearer ' + secret})
    try:
        with build_opener(NoRedirect()).open(request, timeout=40) as r:
            content = r.read(65537)
            if len(content) > 65536:
                raise ValueError('Response too large')
            return json.loads(content)
    except Exception as error:
        raise lab.LabError('Backend não confirmou a operação. Confira destino, habilitação e recibos; não repetir envio incerto.') from error


def protect():
    rules = {r['name']: r for r in lab.api(lab.endpoint('rulesets'))}
    for name, (target, patterns, required) in GUARDS.items():
        if name not in rules:
            raise lab.LabError('Proteção POC ausente. Aplicar configure_poc_slack.py antes do corte.')
        r = lab.api(lab.endpoint('rulesets/' + str(rules[name]['id'])))
        if (r.get('enforcement') != 'active' or r.get('target') != target or r.get('bypass_actors')
                or r.get('conditions', {}).get('ref_name') != {'include': patterns, 'exclude': []}
                or not required <= {rule['type'] for rule in r.get('rules', [])}):
            raise lab.LabError('Proteção POC divergente; manter bloqueado.')
        if 'required_status_checks' in required:
            c = next(rule for rule in r['rules'] if rule['type'] == 'required_status_checks')
            if not c['parameters'].get('strict_required_status_checks_policy') or 'Slack / Verificar contratos' not in {x['context'] for x in c['parameters']['required_status_checks']}:
                raise lab.LabError('Check de correções POC ausente.')
            pr = next(rule for rule in r['rules'] if rule['type'] == 'pull_request')
            if pr['parameters'].get('required_approving_review_count') != 0:
                raise lab.LabError('A integração solo exige zero reviews humanos apenas nas branches Slack.')


def checked_source(source_sha, output, release_branch):
    """Require real post-merge CI on the exact integration commit before refs."""
    runs = lab.api(lab.endpoint('actions/workflows/poc-slack-tests.yml/runs?'
                               'head_sha=' + source_sha + '&event=push&status=success&per_page=100'))
    for run in runs.get('workflow_runs', []):
        if (run.get('head_sha') != source_sha or run.get('head_branch') not in ('slack-main', release_branch)
                or run.get('event') != 'push' or run.get('status') != 'completed'
                or run.get('conclusion') != 'success'):
            continue
        jobs = lab.api(lab.endpoint('actions/runs/' + str(run['id']) + '/jobs?per_page=100'))
        if any(j.get('name') == 'Slack / Verificar contratos' and j.get('status') == 'completed'
               and j.get('conclusion') == 'success' for j in jobs.get('jobs', [])):
            lab.output(output, 'source-check.json', {'source_sha': source_sha, 'run_id': run['id'],
                                                    'success': True})
            return
    lab.output(output, 'source-check.json', {'source_sha': source_sha, 'success': False})
    raise lab.LabError('Aguarde Slack - Verificar contratos concluir com sucesso após o merge '
                       'na slack-main ou na branch de correção da RC. O check do PR não substitui o check do commit integrado; '
                       'nenhuma branch ou tag foi criada nesta tentativa.')


RECOVERY_PATHS = ('.github', 'deploy', 'tools/delivery', 'delivery/release-lab-policy.json', 'supabase')


def trusted_poc_source(plan, output):
    try:
        return lab.trusted_source(plan['source_sha'])
    except lab.LabError:
        # Explicit reviewed compatibility record; no generic divergence fallback.
        try:
            recovery = json.loads(lab.git('show', 'HEAD:delivery/poc-preview-recovery.json'))
            if (recovery['source_sha'] != plan['source_sha'] or recovery['rc_tag'] != plan['rc_tag']
                    or recovery['publication_scope'] != plan['publication_scope']
                    or recovery['schema'] != 'poc-preview-recovery-v1'):
                raise ValueError('Recovery identity differs')
            for ref, key in ((plan['source_sha'], 'source_objects'), ('HEAD', 'tooling_objects')):
                if set(recovery[key]) != set(RECOVERY_PATHS):
                    raise ValueError('Incomplete recovery binding')
                for path in RECOVERY_PATHS:
                    if lab.git('rev-parse', ref + ':' + path) != recovery[key][path]:
                        raise ValueError('Recovery tooling/source differs')
            # Even a recovery cannot alter the app backend contract.
            if recovery['source_objects']['supabase'] != recovery['tooling_objects']['supabase']:
                raise ValueError('Backend recovery is not authorized')
        except (lab.LabError, ValueError, KeyError, TypeError):
            raise lab.LabError('Recuperação exige RC, fonte e ferramentas exatamente revisadas.') from None
        lab.output(output, 'tooling-recovery.json', recovery)
        return lab.git('rev-parse', 'HEAD')


def prepare(version, title, scope, output, validation_mode='full'):
    if not lab.VERSION.fullmatch(version or '') or not title.strip() or len(title) > 120 or any(ord(c) < 32 for c in title):
        raise lab.LabError('Informe versão major.minor.patch e título curto em uma linha.')
    if validation_mode not in ('full', 'controls_only'):
        raise lab.LabError('Modo de validação desconhecido.')
    protect()
    p = control('plan', version=version, title=title, publication_scope=scope, validation_mode=validation_mode)
    if (p.get('version') != version or p.get('rc_tag') != f'poc-v{version}-rc.{p.get("rc_number")}'
            or type(p.get('rc_number')) is not int or p['rc_number'] < 1
            or not re.fullmatch(r'poc-[a-f0-9]{32}', p.get('id', ''))
            or not lab.SHA.fullmatch(p.get('source_sha', '')) or p.get('branch') != 'poc-release/' + version
            or p.get('creator') != 'israelhudson' or p.get('publication_scope') != scope
            or p.get('validation_mode', 'full') != validation_mode):
        raise lab.LabError('Plano remoto fora da identidade da POC.')
    trusted_poc_source(p, output)
    checked_source(p['source_sha'], output, p['branch'])
    if lab.git('rev-parse', p['source_sha'] + ':supabase') != lab.git('rev-parse', 'HEAD:supabase'):
        raise lab.LabError('Código do backend difere das ferramentas confiáveis.')
    latest = lab.api(lab.endpoint('releases/latest'))
    base_tag = latest['tag_name']
    if not re.fullmatch(r'v\d+\.\d+\.\d+', base_tag):
        raise lab.LabError('Base de changelog nativa não identificada.')
    base_ref = lab.api(lab.endpoint('git/ref/tags/' + base_tag))
    if base_ref['object']['type'] != 'commit':
        raise lab.LabError('Base anotada precisa de resolução explícita; não usar ponta de branch.')
    p['changelog_base_sha'] = base_ref['object']['sha']
    p['changelog_base_tag'] = base_tag
    p['title'] = title
    p['tooling_sha'] = lab.git('rev-parse', 'HEAD')
    p['run_url'] = f'https://github.com/{lab.REPOSITORY}/actions/runs/{os.environ["GITHUB_RUN_ID"]}'
    lab.output(output, 'candidate-plan.json', p)  # Intent recorded before GitHub effects.
    lab.create_ref_verified('heads/' + p['branch'], p['source_sha'])
    lab.create_ref_verified('tags/' + p['rc_tag'], p['source_sha'])
    lab.outputs({'candidate_tag': p['rc_tag'], 'source_sha': p['source_sha'], 'tooling_sha': p['tooling_sha']})
    return p


def register(plan, metadata, smoke, output):
    mode = plan.get('validation_mode', 'full')
    if mode not in ('full', 'controls_only'):
        raise lab.LabError('Modo de validação desconhecido.')
    if mode == 'controls_only':
        if metadata is not None or smoke is not None:
            raise lab.LabError('Ensaio somente de controles não aceita prova de preview.')
        preview = {'preview_url': None, 'preview_sha': None, 'web_content_sha256': None,
                   'snapshot_manifest_sha256': None, 'preview_performed': False}
    else:
        if not isinstance(metadata, dict) or not isinstance(smoke, dict):
            raise lab.LabError('Modo completo exige as provas do preview.')
        if (metadata.get('source_sha') != plan['source_sha'] or smoke.get('success') is not True
            or smoke.get('source_sha') != plan['source_sha']
            or any(metadata.get(k) != smoke.get(k) for k in ('web_content_sha256', 'snapshot_manifest_sha256'))):
            raise lab.LabError('Preview sem prova de SHA e bytes do build.')
        if smoke.get('snapshot_url') != f'https://israelhudson.github.io/flutter_code_push_example/snapshots/{plan["source_sha"]}/':
            raise lab.LabError('Preview fora da identidade da candidata.')
        preview = {'preview_url': smoke['snapshot_url'], 'preview_sha': plan['source_sha'],
                   'web_content_sha256': metadata['web_content_sha256'],
                   'snapshot_manifest_sha256': metadata['snapshot_manifest_sha256'], 'preview_performed': True}
    source = plan['source_sha']
    base = plan['changelog_base_sha']
    compare = lab.api(lab.endpoint('compare/' + base + '...' + source))
    if compare.get('status') not in ('ahead', 'identical') or compare.get('total_commits') != len(compare.get('commits', [])):
        raise lab.LabError('Histórico não ancestral ou truncado.')
    commits = [{'sha': c['sha'], 'title': c['commit']['message'].splitlines()[0]} for c in compare['commits']]
    r = {**plan, 'repository': lab.REPOSITORY, **preview, 'validation_mode': mode, 'distribution_performed': False,
         'changelog_base_sha': base, 'commits': commits, 'changelog': '\n'.join('- ' + c['title'] for c in commits),
         'platforms': {'android': {'base_release_version': None, 'effective_patch': None},
                       'ios': {'base_release_version': None, 'effective_patch': None}}}
    lab.output(output, 'frozen-report.json', r)
    result = control('register', report_text=lab.canonical(r), report_digest=lab.digest(r))
    if result.get('id') != plan['id']:
        raise lab.LabError('Registro remoto divergente.')
    lab.output(output, 'registration.json', result)
    for _ in range(12):
        status = control('delivery', candidate=plan['id'])
        lab.output(output, 'card-receipt.json', status)
        if status.get('delivery') == 'sent' and status.get('message_ts'):
            return status
        if status.get('delivery') in ('uncertain', 'skipped'):
            raise lab.LabError('Envio de cartão incerto; reconciliar sem reenviar.')
        time.sleep(2)
    raise lab.LabError('Registro preservado, mas cartão ainda sem recibo; inspecionar o backend.')


def legacy_release_body(c):
    report = json.loads(c['report_text'])
    limit = '\n\nEnsaio somente de controles: sem preview, build web ou patches. Não comprova distribuição do aplicativo.' if report.get('validation_mode') == 'controls_only' else ''
    return 'Release de TESTE da POC Slack.' + limit + '\n\nCódigo aprovado: ' + c['source_sha'] + '\n\nRelatório: ' + c['report_digest'] + '\n\n' + c['report_text']


def release_body(c):
    report = json.loads(c['report_text'])
    # Plain text from the frozen report must not become links, mentions or HTML.
    def plain(value):
        value = html.escape(str(value)).replace('@', '&#64;')
        return re.sub(r'([\\`*_{}\[\]()#+.!|~-])', r'\\\1', value)
    title = plain(report.get('title', 'Entrega aprovada'))
    rc = plain(report.get('rc_tag', c.get('rc_tag', 'Candidata aprovada')))
    body = ['## Release final no GitHub', title,
            '**Ambiente de testes da POC.** A classificação final desta Release não promove patches Shorebird nem publica em lojas.',
            'Candidata de origem: ' + rc + '. A tag candidata permanece no histórico.',
            'Código aprovado: `' + c['source_sha'] + '`.', '## O que mudou']
    body.append('\n'.join('- ' + plain(line.removeprefix('- ')) for line in report.get('changelog', '').splitlines())
                or 'Consulte o relatório aprovado abaixo.')
    if report.get('validation_mode') == 'controls_only':
        body.append('Ensaio somente de controles: sem preview, build web ou patches.')
    elif report.get('preview_url') == f'https://israelhudson.github.io/flutter_code_push_example/snapshots/{c["source_sha"]}/':
        body.append('[Abrir preview aprovado](' + report['preview_url'] + ')')
    body.append('## Distribuição do aplicativo\nEsta automação publica somente no GitHub. Evidências de Android/iOS executadas separadamente ficam nos anexos, quando disponíveis.')
    # A fenced JSON block preserves the exact original text without broken autolinks.
    fence = '`' * max(3, max((len(m[0]) + 1 for m in re.finditer(r'`+', c['report_text'])), default=3))
    body.append('<details>\n<summary>Relatório técnico aprovado</summary>\n\n'
                + 'Digest: `' + c['report_digest'] + '`\n\n'
                + fence + 'json\n' + c['report_text'] + '\n' + fence + '\n\n</details>')
    return '\n\n'.join(body)


def finalize_existing(c, authorization, output):
    """Explicit metadata repair. Never republishes, moves tags or replaces evidence."""
    receipt = authorization.get('receipt', {})
    tag = 'poc-v' + c['version']
    expected_receipt = {'tag': tag, 'source_sha': c['source_sha'], 'report_digest': c['report_digest'],
                        'release_url': f'https://github.com/{lab.REPOSITORY}/releases/tag/{tag}'}
    if (c.get('status') != 'published' or authorization.get('already_published') is not True
            or not re.fullmatch(r'poc-v\d+\.\d+\.\d+', tag)
            or c.get('rc_tag') != f'poc-v{c["version"]}-rc.{c.get("rc_number")}'
            or any(receipt.get(k) != v for k, v in expected_receipt.items())):
        raise lab.LabError('Correção exige publicação concluída e recibo da mesma candidata.')
    def verify_refs():
        for ref in (c['rc_tag'], tag):
            value = lab.api(lab.endpoint('git/ref/tags/' + ref))
            if value.get('object', {}).get('type') != 'commit' or value.get('object', {}).get('sha') != c['source_sha']:
                raise lab.LabError('Tag divergente; correção de apresentação bloqueada.')
    verify_refs()
    existing = lab.api(lab.endpoint('releases/tags/' + tag))
    body = release_body(c)
    expected = {'id': receipt.get('release_id'), 'tag_name': tag, 'name': 'POC Slack — ' + c['version'],
                'html_url': expected_receipt['release_url'], 'draft': False}
    if (type(expected['id']) is not int or expected['id'] <= 0
            or any(existing.get(k) != v for k, v in expected.items())
            or type(existing.get('prerelease')) is not bool
            or existing.get('body') not in (legacy_release_body(c), body)):
        raise lab.LabError('Release alterada ou fora do recibo; não sobrescrever.')
    lab.output(output, 'release-before.json', existing)
    assets = lambda r: sorted((a['id'], a['name'], a.get('digest'), a['size']) for a in r.get('assets', []))
    changed = existing['prerelease'] or existing['body'] != body
    if changed:
        control('claim', candidate=c['id'])
        # Do not overwrite a concurrent edit made during validation.
        current = lab.api(lab.endpoint('releases/' + str(existing['id'])))
        if (any(current.get(k) != existing.get(k) for k in (*expected, 'body', 'prerelease', 'updated_at'))
                or assets(current) != assets(existing)):
            raise lab.LabError('Release mudou durante a conferência; reconciliar antes de corrigir.')
        update = {'prerelease': False, 'body': body, 'make_latest': 'false'}
        lab.output(output, 'release-correction-intent.json', {'release_id': existing['id'], 'update': update})
        lab.api(lab.endpoint('releases/' + str(existing['id'])), update, 'PATCH')
    actual = lab.api(lab.endpoint('releases/' + str(existing['id'])))
    lab.output(output, 'release-after.json', actual)
    verify_refs()
    if (any(actual.get(k) != v for k, v in expected.items()) or actual.get('prerelease') is not False
            or actual.get('body') != body or assets(existing) != assets(actual)):
        raise lab.LabError('Correção sem confirmação completa; não repetir sem reconciliar.')
    result = {'release_id': actual['id'], 'release_url': actual['html_url'], 'tag': tag,
              'source_sha': c['source_sha'], 'prerelease': False, 'changed': changed,
              'assets_preserved': True, 'publication_receipt_unchanged': True,
              'distribution_performed': False}
    lab.output(output, 'release-correction-receipt.json', result)
    return result


def publish(candidate, output, finalize=False):
    if not re.fullmatch(r'poc-[a-f0-9]{32}', candidate or ''):
        raise lab.LabError('ID de candidata inválido.')
    protect()
    c = control('state', candidate=candidate)
    if not lab.SHA.fullmatch(c.get('source_sha', '')) or c.get('publication_scope') != 'github_test':
        raise lab.LabError('Candidata sem escopo GitHub TESTE.')
    if finalize and c.get('status') != 'published':
        raise lab.LabError('Correção de apresentação aceita apenas candidata já publicada.')
    authorization = control('claim', candidate=candidate)
    lab.output(output, 'publication-intent.json', authorization)
    if finalize:
        return finalize_existing(c, authorization, output)
    if authorization.get('already_published'):
        lab.output(output, 'receipt.json', authorization['receipt'])
        return authorization['receipt']
    tag = 'poc-v' + c['version']
    if not re.fullmatch(r'poc-v\d+\.\d+\.\d+', tag):
        raise lab.LabError('Tag final fora do namespace POC.')
    control('claim', candidate=candidate)  # Live recheck immediately before each external effect.
    lab.create_ref_verified('tags/' + tag, c['source_sha'])
    control('claim', candidate=candidate)
    existing = lab.api(lab.endpoint('releases/tags/' + tag), missing=True)
    expected = {'tag_name': tag, 'target_commitish': c['source_sha'], 'name': 'POC Slack — ' + c['version'],
                'body': release_body(c), 'draft': False, 'prerelease': False, 'make_latest': 'false'}
    if existing is None:
        existing = lab.api(lab.endpoint('releases'), expected, 'POST')
    if any(existing.get(k) != expected[k] for k in ('tag_name', 'body', 'name', 'draft', 'prerelease')):
        raise lab.LabError('Release existente diverge; não sobrescrever.')
    receipt = {'tag': tag, 'source_sha': c['source_sha'], 'report_digest': c['report_digest'],
               'release_id': existing['id'], 'release_url': existing['html_url'],
               'published_at': existing['published_at'], 'prerelease': False, 'distribution_performed': False,
               'platforms': json.loads(c['report_text'])['platforms']}
    lab.output(output, 'receipt.json', receipt)  # Preserve actual effect even if completion API response is lost.
    control('complete', candidate=candidate, receipt=receipt)
    return receipt


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest='operation', required=True)
    p = commands.add_parser('prepare'); p.add_argument('--version', required=True); p.add_argument('--title', required=True); p.add_argument('--scope', choices=['none','github_test'], default='none')
    p.add_argument('--validation-mode', choices=['full', 'controls_only'], default='full')
    p = commands.add_parser('register'); p.add_argument('--plan', required=True); p.add_argument('--metadata'); p.add_argument('--smoke')
    p = commands.add_parser('publish'); p.add_argument('--candidate', required=True)
    p.add_argument('--finalize-existing', action='store_true', help='Corrigir apenas apresentação de Release já publicada; não republicar.')
    for p in commands.choices.values():
        p.add_argument('--output', required=True)
    a = parser.parse_args()
    try:
        if (os.environ.get('POC_SLACK_ENABLED') != 'true' or os.environ.get('GITHUB_REPOSITORY') != lab.REPOSITORY
                or os.environ.get('POC_SOURCE_BRANCH', 'slack-main') not in ('main', 'slack-main') or os.environ.get('GITHUB_REF') != 'refs/heads/' + os.environ.get('POC_SOURCE_BRANCH', 'slack-main') or os.environ.get('GITHUB_EVENT_NAME') != 'workflow_dispatch'
                or not re.fullmatch(r'\d+', os.environ.get('GITHUB_RUN_ID', ''))):
            raise lab.LabError('Execute somente o workflow manual habilitado na branch de integração configurada da POC.')
        if a.operation == 'prepare':
            result = prepare(a.version, a.title, a.scope, a.output, a.validation_mode)
        elif a.operation == 'register':
            result = register(*(json.loads(Path(p).read_text()) if p else None for p in (a.plan, a.metadata, a.smoke)), a.output)
        else:
            if os.environ.get('POC_SLACK_PUBLISH_ENABLED') != 'true':
                raise lab.LabError('Publicação GitHub de teste ainda desativada.')
            result = publish(a.candidate, a.output, a.finalize_existing)
        print(lab.canonical(result))
        return 0
    except (lab.LabError, ValueError, OSError, KeyError) as error:
        reason = str(error) if isinstance(error, lab.LabError) else 'Dados inválidos; manter bloqueado.'
        lab.output(a.output, 'blocked.json', {'reason': reason, 'distribution_performed': False})
        print(reason)
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
