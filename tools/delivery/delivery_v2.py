"""Delivery adapter with automatic database reviewers and an immutable journal.

GitHub is the durable journal. Supabase keeps only frozen authorization, message
identifiers and a transactional outbox. This module never calls Shorebird.
"""
import argparse
import base64
import hashlib
import json
import os
from pathlib import Path
import re
import uuid
from urllib.request import Request, build_opener

import poc_slack as legacy
import release_lab as lab

HISTORY = 'codex/delivery-history'
ID = re.compile(r'delivery-[a-f0-9]{32}')
LEGACY_BODY = legacy.release_body


def require_reviewers(snapshot):
    """Reject missing/spoofed authorization before creating GitHub records.

    SQL rechecks the selected defaults atomically at registration. No fallback to
    configuration-file users or arbitrary accounts is permitted in this lane.
    """
    policy = json.loads(Path('delivery/delivery-policy.json').read_text())
    if (policy.get('reviewer_source') != 'database-v1'
            or type(policy.get('solo')) is not bool
            or not isinstance(snapshot, dict)
            or snapshot.get('schema') != 'delivery-reviewers-v1'
            or snapshot.get('repository') != policy['repository']
            or snapshot.get('team_id') != policy['team_id']
            or type(snapshot.get('solo')) is not bool
            or snapshot['solo'] != policy['solo']):
        raise lab.LabError('Titulares automáticos ausentes ou fora da política confiável.')
    for role in ('technical', 'business'):
        reviewer = snapshot.get(role)
        if (not isinstance(reviewer, dict)
                or not isinstance(reviewer.get('id'), str)
                or not re.fullmatch(r'[a-f0-9]{8}(?:-[a-f0-9]{4}){3}-[a-f0-9]{12}', reviewer['id'])
                or type(reviewer.get('revision')) is not int or reviewer['revision'] < 1
                or not isinstance(reviewer.get('slack_user'), str)
                or not re.fullmatch(r'U[A-Z0-9]+', reviewer['slack_user'])
                or not isinstance(reviewer.get('name'), str)
                or not reviewer['name'].strip() or len(reviewer['name']) > 120
                or any(ord(c) < 32 for c in reviewer['name'])):
            raise lab.LabError('Identidade do titular automático inválida.')
        github_id, login = reviewer.get('github_user_id'), reviewer.get('github_login')
        if (github_id is not None and (type(github_id) is not int or github_id <= 0)
                or login is not None and (not isinstance(login, str)
                    or not re.fullmatch(r'[A-Za-z0-9](?:[A-Za-z0-9-]{0,37}[A-Za-z0-9])?', login))):
            raise lab.LabError('Identidade GitHub do titular inválida.')
    if (not policy['solo'] and (snapshot['technical']['id'] == snapshot['business']['id']
            or snapshot['technical']['slack_user'] == snapshot['business']['slack_user']
            or snapshot['technical'].get('github_user_id') is not None
            and snapshot['technical']['github_user_id'] == snapshot['business'].get('github_user_id'))):
        raise lab.LabError('Dois papéis exigem pessoas distintas fora do ensaio solo.')
    return snapshot


def api_control(operation, **data):
    secret_name = 'POC_PUBLICATION_SECRET' if operation in ('state', 'claim', 'complete', 'presentation') else 'POC_REGISTRATION_SECRET'
    secret = os.environ.get(secret_name)
    if not secret or os.environ.get('DELIVERY_V2_ENABLED') != 'true':
        raise lab.LabError('Delivery v2 disabled or missing credential.')
    request = Request(legacy.backend_origin(os.environ.get('POC_SUPABASE_URL')) + '/functions/v1/delivery-control',
                      data=lab.canonical({'operation': operation, 'run_id': os.environ['GITHUB_RUN_ID'], **data}).encode(),
                      headers={'Authorization': 'Bearer ' + secret, 'Content-Type': 'application/json'}, method='POST')
    try:
        with build_opener(legacy.NoRedirect()).open(request, timeout=30) as response:
            return json.loads(response.read(65537))
    except Exception as error:
        raise lab.LabError('Operação v2 sem confirmação; preserve o recibo e reconcilie antes de repetir.') from error


def write_record(path, value):
    """Append-only by path; never overwrite a different record, even on retry."""
    if not re.fullmatch(r'candidates/delivery-[a-f0-9]{32}/(?:manifest|event-[0-9]+)\.json', path):
        raise lab.LabError('Journal path rejected.')
    content = lab.canonical(value).encode()
    if len(content) > 65536:
        raise lab.LabError('Journal record too large.')
    head = lab.api(lab.endpoint('git/ref/heads/' + HISTORY), missing=True)
    if not head:
        # Never initialize from untrusted application sources.
        lab.create_ref_verified('heads/' + HISTORY, os.environ['GITHUB_SHA'])
    existing = lab.api(lab.endpoint('contents/' + path + '?ref=' + HISTORY), missing=True)
    if existing:
        if base64.b64decode(existing['content']) != content:
            raise lab.LabError('Immutable GitHub record differs; do not overwrite.')
        commit = lab.api(lab.endpoint('git/ref/heads/' + HISTORY))['object']['sha']
    else:
        result = lab.api(lab.endpoint('contents/' + path), {
            'message': 'delivery: record ' + path,
            'content': base64.b64encode(content).decode(), 'branch': HISTORY}, 'PUT')
        commit = result['commit']['sha']
    # Verify using an immutable commit, not the moving branch.
    saved = lab.api(lab.endpoint('contents/' + path + '?ref=' + commit))
    if base64.b64decode(saved['content']) != content:
        raise lab.LabError('GitHub journal verification failed.')
    return {'commit': commit, 'digest': hashlib.sha256(content).hexdigest(), 'path': path}


def drain(output, limit=30):
    receipts = []
    for _ in range(limit):
        lease = str(uuid.uuid4())
        work = api_control('take', lease=lease)
        if not work:
            break
        task, c = work['task'], work['candidate']
        if not ID.fullmatch(c['id']):
            raise lab.LabError('Worker candidate outside v2.')
        if task['kind'] == 'history':
            result = write_record(f"candidates/{c['id']}/event-{task['revision']}.json", task['event'])
            api_control('finish', task_id=task['id'], lease=lease, receipt=result['commit'])
        else:
            result = api_control('send', task_id=task['id'], lease=lease)
        receipts.append({'task_id': task['id'], 'kind': task['kind'], 'receipt': result})
        lab.output(output, 'outbox-receipts.json', receipts)
    return receipts


def changes(report):
    lines=[]
    for commit in report['commits']:
        title=legacy.html.escape(commit['title']).replace('@','&#64;')
        title=re.sub(r'([\\`*_{}\[\]])',r'\\\1',title)
        title=re.sub(r'#([0-9]+)',lambda m:f"[#{m[1]}](https://github.com/{lab.REPOSITORY}/pull/{m[1]})",title)
        lines.append(f"- {title} ([commit](https://github.com/{lab.REPOSITORY}/commit/{commit['sha']}))")
    return '\n'.join(lines) or 'Nenhuma mudança adicional.'


def final_body(c, presentation=None):
    report=json.loads(c['report_text'])
    validated=LEGACY_BODY(c,presentation)
    table='## Versões e publicação'+validated.split('## Versões e publicação',1)[1].split('## O que mudou',1)[0]
    return table.strip()+'\n\n## Mudanças\n\n'+changes(report)+f"\n\n[Publicação](https://github.com/{lab.REPOSITORY}/actions/runs/{os.environ['GITHUB_RUN_ID']}) · [Histórico e evidências](https://github.com/{lab.REPOSITORY}/tree/{HISTORY}/candidates/{c['id']})\n\nCandidata preservada: `{c['rc_tag']}`. Esta Release GitHub não comprova publicação em lojas."


def candidate_release(report):
    """Candidate has the preview; the existing final renderer omits that link."""
    title = f"Release {report['version']}-rc.{report['rc_number']} — {report['title']}"
    preview = f"\n[Ver preview]({report['preview_url']})\n" if report.get('preview_url') else '\nEnsaio sem preview e sem patches.\n'
    body = ('Release Candidate em avaliação.\n' + preview + '\n## Mudanças\n' +
            changes(report) +
            f"\n\n[Preparação]({report['run_url']}) · [Evidências](https://github.com/{lab.REPOSITORY}/tree/{HISTORY}/candidates/{report['id']})")
    expected = {'tag_name': report['rc_tag'], 'target_commitish': report['source_sha'], 'name': title,
                'body': body, 'draft': False, 'prerelease': True, 'make_latest': 'false'}
    existing = lab.api(lab.endpoint('releases/tags/' + report['rc_tag']), missing=True)
    if existing is None:
        existing = lab.api(lab.endpoint('releases'), expected, 'POST')
    if any(existing.get(k) != expected[k] for k in ('tag_name','name','body','draft','prerelease')):
        raise lab.LabError('Candidate Release differs; preserve it and reconcile.')
    return existing


def control(operation, **data):
    output = os.environ.get('DELIVERY_LOG_DIR', 'delivery-logs')
    if operation == 'register':
        report = json.loads(data['report_text'])
        require_reviewers(report.get('reviewers'))
        record = write_record(f"candidates/{report['id']}/manifest.json", report)
        lab.output(output, 'manifest-receipt.json', record)
        release = candidate_release(report)
        lab.output(output, 'candidate-release.json', {'id':release['id'],'url':release['html_url']})
        result = api_control('register', candidate=report['id'], manifest_commit=record['commit'], manifest_digest=record['digest'])
        if (result.get('reviewer_snapshot') != report['reviewers']
                or any(result.get(f'{role}_reviewer_id') != report['reviewers'][role]['id']
                       or result.get(f'{role}_user') != report['reviewers'][role]['slack_user']
                       for role in ('technical', 'business'))):
            raise lab.LabError('Titulares registrados diferem do manifesto; preserve as evidências.')
        drain(output)
        return result
    result = api_control(operation, **data)
    if operation == 'plan':
        require_reviewers(result.get('reviewers'))
    if operation in ('claim', 'complete'):
        drain(output)
    return result


def require_history_protection():
    """Fail closed until the migration's durable-history guard is installed."""
    for summary in lab.api(lab.endpoint('rulesets')):
        if summary.get('name') != 'Entrega - historico preservado':
            continue
        rule = lab.api(lab.endpoint('rulesets/' + str(summary['id'])))
        if (rule.get('enforcement') == 'active' and rule.get('target') == 'branch'
                and not rule.get('bypass_actors')
                and rule.get('conditions', {}).get('ref_name') == {'include':['refs/heads/' + HISTORY], 'exclude':[]}
                and {'non_fast_forward','deletion'} <= {r['type'] for r in rule.get('rules',[])}):
            return
    raise lab.LabError('Proteção do histórico ausente; instalar Entrega - historico preservado antes de ativar v2.')


def main():
    if os.environ.get('GITHUB_REPOSITORY') != lab.REPOSITORY or os.environ.get('DELIVERY_V2_ENABLED') != 'true':
        raise lab.LabError('Exclusive repository and opt-in required.')
    require_history_protection()
    if len(__import__('sys').argv)>1 and __import__('sys').argv[1]=='drain':
        parser=argparse.ArgumentParser();parser.add_argument('command');parser.add_argument('--output',required=True);parser.add_argument('--cancel')
        args=parser.parse_args()
        if args.cancel: api_control('cancel',candidate=args.cancel)
        drain(args.output)
        lab.output(args.output,'compaction-receipt.json',api_control('compact'))
        return 0
    argv=__import__('sys').argv
    if '--output' in argv: os.environ['DELIVERY_LOG_DIR']=argv[argv.index('--output')+1]
    os.environ['DELIVERY_STATE_V2']='true'
    if '--finalize-existing' in argv: raise lab.LabError('Legacy presentation repair is not a v2 operation.')
    legacy.control=control
    legacy.release_body=final_body
    return legacy.main()


if __name__ == '__main__':
    raise SystemExit(main())
