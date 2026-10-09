"""Isolated Issue ChatOps POC. Comments are data, never shell instructions.

Publication uses live comments and frozen hashes, not checkboxes or issue text.
All mutations share issue-release-mutation and a contents-SHA CAS journal.
Intents precede external writes. An uncertain response is reconciled, not retried
blindly. Existing release-lab state, tags and approval gates are never mutated.
"""
import argparse
import base64
from copy import deepcopy
from datetime import datetime
import json
import os
from pathlib import Path
import re
from urllib.parse import quote

import release_lab as lab
import slack_notify

ROOT = Path(__file__).resolve().parents[2]
POLICY = ROOT / 'delivery/issue-release-policy.json'
STATE_PATH = 'issue-release/state.json'
STATE_BRANCH = 'codex/issue-release-state'
TAG = re.compile(r'test-issue-((?:0|[1-9][0-9]*)\.(?:0|[1-9][0-9]*)\.(?:0|[1-9][0-9]*))-rc\.([1-9][0-9]*)\Z')
COMMAND = re.compile(r'/(aprovar|reprovar|publicar) (test-issue-(?:0|[1-9][0-9]*)\.(?:0|[1-9][0-9]*)\.(?:0|[1-9][0-9]*)-rc\.[1-9][0-9]*)\Z')
TERMINAL = {'rejected', 'superseded', 'published'}
GUARDS = {
    'Issue - tags de teste imutaveis': ('tag', ['refs/tags/test-issue-*'], {'update', 'deletion'}),
    'Issue - correcoes por PR': ('branch', ['refs/heads/test-issue-release/**'],
                                 {'pull_request', 'required_status_checks', 'non_fast_forward', 'deletion'}),
    'Issue - journal append-only': ('branch', ['refs/heads/' + STATE_BRANCH], {'non_fast_forward', 'deletion'}),
}


class IssueError(ValueError):
    pass


def policy_load():
    value = json.loads(POLICY.read_text())
    if (value.get('repository') != lab.REPOSITORY or value.get('state_branch') != STATE_BRANCH
            or value.get('schema') != 1 or value.get('approval_mode') != '1/1'
            or value.get('publication_mode') != 'github_release_only'
            or value.get('distribution_performed') is not False):
        raise IssueError('Política Issue fora da POC 1/1 sem distribuição.')
    owner = [{'login': 'israelhudson', 'id': 18661493}]
    if any(value.get(role) != owner for role in ('operators', 'approvers', 'publishers')):
        raise IssueError('Esta primeira POC exige a identidade explícita de Israel, em 1/1.')
    return value


def context(policy, operation):
    env = os.environ
    if (env.get('ISSUE_RELEASE_ENABLED') != 'true' or env.get('GITHUB_REPOSITORY') != lab.REPOSITORY
            or env.get('GITHUB_REF') != 'refs/heads/main'):
        raise IssueError('Ative ISSUE_RELEASE_ENABLED=true e execute somente na main desta POC.')
    if operation in ('prepare', 'publish-manual'):
        actor = (int(env.get('GITHUB_ACTOR_ID', '0')), env.get('GITHUB_ACTOR', '').lower())
        if (actor not in {lab.identity(p) for p in policy['operators']}
                or env.get('GITHUB_TRIGGERING_ACTOR', '').lower() != actor[1]
                or env.get('GITHUB_EVENT_NAME') != 'workflow_dispatch'):
            raise IssueError('Preparação/recuperação manual exige o operador Israel.')
    elif env.get('GITHUB_EVENT_NAME') not in ('issue_comment', 'issues', 'workflow_dispatch'):
        raise IssueError('Evento não autorizado para a alternativa Issue.')


def pages(path):
    result = []
    for page in range(1, 101):
        batch = lab.api(lab.endpoint(path) + ('&' if '?' in path else '?') + f'per_page=100&page={page}')
        if not isinstance(batch, list):
            raise IssueError('Lista GitHub inválida.')
        result.extend(batch)
        if len(batch) < 100:
            return result
    raise IssueError('Paginação incompleta. Manter publicação bloqueada.')


def protect():
    observed = {r['name']: r for r in pages('rulesets')}
    for name, (kind, patterns, rules) in GUARDS.items():
        if name not in observed:
            raise IssueError('Proteção Issue ausente. Execute configure_issue_release.py após instalar o PR.')
        value = lab.api(lab.endpoint('rulesets/' + str(observed[name]['id'])))
        if (value.get('enforcement') != 'active' or value.get('target') != kind
                or value.get('conditions', {}).get('ref_name') != {'include': patterns, 'exclude': []}
                or value.get('bypass_actors') or not rules <= {r['type'] for r in value.get('rules', [])}):
            raise IssueError('Proteção Issue divergente ou com bypass. Manter bloqueado.')
        if kind == 'branch' and 'required_status_checks' in rules:
            checks = next(r for r in value['rules'] if r['type'] == 'required_status_checks')
            if 'Issue / Verificar contratos' not in {c['context'] for c in checks['parameters']['required_status_checks']}:
                raise IssueError('Check obrigatório de correções Issue ausente.')


class Journal:
    def __init__(self, policy):
        self.policy = policy
        self.sha = None
        self.value = None

    def read(self):
        response = lab.api(lab.endpoint('contents/' + STATE_PATH) + '?ref=' + quote(STATE_BRANCH, safe=''), missing=True)
        if response is None:
            self.sha = None
            self.value = {'schema': 1, 'active': None, 'candidates': {}, 'events': [], 'last_published': None}
        else:
            self.sha = response['sha']
            self.value = json.loads(base64.b64decode(response['content']))
            if self.value.get('schema') != 1:
                raise IssueError('Journal Issue desconhecido.')
        return self.value

    def save(self, action, tag):
        # One CAS attempt. Failure stops the runner; never reapply effects.
        self.value['events'].append({'at': lab.now(), 'action': action, 'tag': tag,
                                    'run_id': os.environ.get('GITHUB_RUN_ID'),
                                    'state_digest': lab.digest(self.value['candidates'])})
        data = {'branch': STATE_BRANCH, 'message': f'issue: {action} {tag}',
                'content': base64.b64encode((lab.canonical(self.value) + '\n').encode()).decode()}
        if self.sha:
            data['sha'] = self.sha
        result = lab.api(lab.endpoint('contents/' + STATE_PATH), data, 'PUT')
        self.sha = result['content']['sha']

    def bootstrap(self):
        lab.create_ref_verified('heads/' + STATE_BRANCH, lab.api(lab.endpoint('commits/main'))['sha'])

    def record(self, tag):
        record = self.read().get('candidates', {}).get(tag)
        if not record:
            raise IssueError('Candidata Issue não registrada.')
        return record

    def by_issue(self, number):
        state = self.read()
        matches = [r for r in state['candidates'].values() if r.get('issue_number') == number]
        if len(matches) != 1:
            return None
        return matches[0]


def tag_sha(tag):
    # Reject annotated/moved references in the experimental namespace.
    ref = lab.api(lab.endpoint('git/ref/tags/' + quote(tag, safe='')), missing=True)
    if ref is None:
        return None
    if ref['object'].get('type') != 'commit':
        raise IssueError('Tag de teste precisa apontar diretamente a um commit.')
    return ref['object']['sha']


def frozen(record, policy):
    if record.get('policy_digest') != lab.digest(policy):
        raise IssueError('Política mudou. Prepare outra candidata.')
    report = record.get('report')
    if not report or record.get('report_digest') != lab.digest(report):
        raise IssueError('Relatório congelado ausente ou alterado.')
    if (report.get('source_sha') != record['source_sha'] or report.get('tag') != record['tag']
            or report.get('title') != record['title'] or report.get('version') != record['version']
            or report.get('stable_tag') != record['stable_tag']
            or tag_sha(record['tag']) != record['source_sha']):
        raise IssueError('Tag/código divergente do relatório congelado.')
    ref = lab.api(lab.endpoint('git/ref/heads/' + quote(record['branch'], safe='')))
    if ref['object'].get('type') != 'commit' or ref['object']['sha'] != record['source_sha']:
        raise IssueError('Branch de correção avançou. Prepare RC2 antes de publicar.')


def enqueue(record, event):
    if record.get('report_digest'):
        key = event + ':' + record['report_digest']
        approval_digest = lab.digest(record.get('approvals', [])) if event == 'approved' else None
        if approval_digest:
            key += ':' + approval_digest
        record.setdefault('notices', {}).setdefault(key, {'event': event, 'state': 'pending', 'approval_digest': approval_digest})


def prepare(policy, version, title, output):
    if not lab.VERSION.fullmatch(version or '') or not title.strip() or len(title) > 120 or any(ord(c) < 32 for c in title):
        raise IssueError('Informe versão major.minor.patch e título em uma linha de até 120 caracteres.')
    protect()
    journal = Journal(policy)
    state = journal.read()
    if journal.sha is None:
        journal.bootstrap()
    pending = state.get('preparation')
    if pending and (pending['version'] != version or pending['title'] != title or pending['policy_digest'] != lab.digest(policy)):
        raise IssueError('Preparação parcial. Repita os mesmos dados para reconciliar.')
    active = state['candidates'].get(state.get('active'))
    if any(r.get('publication') and r['status'] != 'published' for r in state['candidates'].values()):
        raise IssueError('Publicação parcial exige recuperação antes de outra RC.')
    if (active and active['status'] in ('prepared', 'opening') and not pending
            and active['version'] == version and active['title'] == title
            and active['policy_digest'] == lab.digest(policy)):
        ref = lab.api(lab.endpoint('git/ref/heads/' + quote(active['branch'], safe='')))
        if ref['object']['sha'] != active['source_sha'] or tag_sha(active['tag']) != active['source_sha']:
            raise IssueError('Preparação incompleta mudou de código. Inspecionar referências.')
        lab.output(output, 'candidate.json', active)
        lab.outputs({'candidate_tag': active['tag'], 'source_sha': active['source_sha'], 'tooling_sha': active['tooling_sha']})
        return active
    if active and active['status'] not in TERMINAL and not pending:
        raise IssueError('Uma RC Issue por vez. Reprove a atual antes de preparar outra.')
    last = state.get('last_published')
    if last and lab.stable_version(version) <= lab.stable_version(last['version']):
        raise IssueError('Versão experimental já publicada ou anterior à última.')
    branch = 'test-issue-release/' + version
    ref = lab.api(lab.endpoint('git/ref/heads/' + quote(branch, safe='')), missing=True)
    source = ref['object']['sha'] if ref else lab.api(lab.endpoint('commits/main'))['sha']
    lab.trusted_source(source)
    if lab.git('rev-parse', source + ':delivery/issue-release-policy.json') != lab.git('rev-parse', 'HEAD:delivery/issue-release-policy.json'):
        raise IssueError('Política Issue do código difere da main confiável.')
    if pending:
        record = pending
        if source != record['source_sha']:
            raise IssueError('Código mudou durante preparação parcial. Inspecione antes de repetir.')
    else:
        refs = lab.api(lab.endpoint('git/matching-refs/tags/test-issue-' + version + '-rc.'))
        nums = [int(m[2]) for r in refs if (m := TAG.fullmatch(r['ref'][10:])) and m[1] == version]
        tag = f'test-issue-{version}-rc.{max(nums, default=0) + 1}'
        baseline = last['source_sha'] if last else source
        if not last:
            latest = lab.api(lab.endpoint('releases/latest'), missing=True)
            if latest and lab.STABLE_TAG.fullmatch(latest['tag_name']):
                baseline = lab.resolve_tag(latest['tag_name'])
        record = {'tag': tag, 'stable_tag': 'test-issue-' + version, 'version': version, 'title': title,
                  'source_sha': source, 'branch': branch, 'tooling_sha': lab.git('rev-parse', 'HEAD'),
                  'policy_digest': lab.digest(policy), 'created_at': lab.now(), 'base_sha': baseline, 'accepted_comments': {},
                  'base_publication': deepcopy(last), 'status': 'prepared', 'revoked_comment_ids': [],
                  'preparation_run': os.environ['GITHUB_RUN_ID']}
        state['preparation'] = deepcopy(record)
        journal.save('reserve-preparation', tag)
    lab.create_ref_verified('heads/' + branch, source)
    lab.create_ref_verified('tags/' + record['tag'], source)
    # Reload after external effects. Reconcile only the reserved candidate.
    state = journal.read()
    if state.get('preparation', {}).get('tag') != record['tag']:
        raise IssueError('Reserva de corte mudou.')
    if active and active['status'] != 'published':
        old = state['candidates'][active['tag']]
        old['status'] = 'superseded'
        enqueue(old, 'superseded')
    state['candidates'][record['tag']] = record
    state['active'] = record['tag']
    state.pop('preparation', None)
    journal.save('freeze-candidate', record['tag'])
    lab.output(output, 'candidate.json', record)
    lab.outputs({'candidate_tag': record['tag'], 'source_sha': source, 'tooling_sha': record['tooling_sha']})
    return record


def parse(body):
    matched = COMMAND.fullmatch(body.strip()) if isinstance(body, str) else None
    return (matched[1], matched[2]) if matched else None


def permitted(user, people):
    if user.get('type') != 'User' or lab.identity(user) not in {lab.identity(p) for p in people}:
        return False
    permission = lab.api(lab.endpoint('collaborators/' + quote(user['login'], safe='') + '/permission'))
    return permission.get('permission') in ('admin', 'maintain', 'write')


def unchanged_comment(comment, record):
    return (isinstance(comment.get('id'), int) and comment['id'] not in record.get('revoked_comment_ids', [])
            and comment.get('created_at') == comment.get('updated_at')
            and isinstance(comment.get('created_at'), str)
            and comment['created_at'] >= record['opened_at'])


def comment_digest(comment):
    return lab.digest({key: comment.get(key) for key in ('id', 'body', 'created_at', 'updated_at')}
                      | {'author': lab.identity(comment.get('user', {}))})


def decisions(comments, record, policy):
    latest = {}
    for comment in sorted(comments, key=lambda c: c['id']):
        command = parse(comment.get('body'))
        if (not command or command[1] != record['tag'] or command[0] not in ('aprovar', 'reprovar')
                or not unchanged_comment(comment, record) or not permitted(comment.get('user', {}), policy['approvers'])):
            continue
        if (command[0] == 'aprovar' and record.get('accepted_comments', {}).get(str(comment['id'])) != comment_digest(comment)):
            continue  # Only a matching, recorded CREATED event can confer approval.
        latest[comment['user']['id']] = {'command': command[0], 'comment_id': comment['id'],
            'comment_digest': comment_digest(comment), 'author': lab.identity(comment['user'])}
    return latest


def issue_view(record, policy):
    issue = lab.api(lab.endpoint('issues/' + str(record['issue_number'])))
    pending = record.get('view_update', {})
    if (pending.get('pending') and lab.digest(issue.get('body', '')) == pending.get('previous_digest')
            and lab.digest(issue_body(record)) == record.get('issue_body_digest')):
        # Repair ONLY the known old body after a lost PATCH. Unknown human edits
        # remain invalid and never confer approval.
        issue = lab.api(lab.endpoint('issues/' + str(record['issue_number'])), {'body': issue_body(record)}, 'PATCH')
    if (issue.get('pull_request') or issue.get('state') != 'open' or issue.get('locked')
            or issue.get('number') != record['issue_number']
            or lab.digest(issue.get('body', '')) != record.get('issue_body_digest')):
        raise IssueError('Ficha alterada, fechada ou bloqueada. Restaurar a ficha e obter novo aval.')
    return issue, pages(f'issues/{record["issue_number"]}/comments')


def approvals(comments, record, policy):
    latest = decisions(comments, record, policy)
    if any(v['command'] == 'reprovar' for v in latest.values()):
        raise IssueError('Candidata reprovada.')
    expected = {p['id'] for p in policy['approvers']}
    if set(latest) != expected or any(v['command'] != 'aprovar' for v in latest.values()):
        raise IssueError('Falta a aprovação 1/1. Publicação bloqueada.')
    return [latest[p['id']] for p in policy['approvers']]


def issue_body(record):
    report = record['report']
    changelog = '\n'.join('- ' + c['message'].replace('\n', ' ') for c in report['commits']) or '- Nenhum commit novo desde a base registrada.'
    status = {'awaiting_approval': 'Aguardando aprovação (0/1)', 'approved': 'Aprovada (1/1). Falta /publicar',
              'rejected': 'Reprovada. Correção exige nova RC', 'superseded': 'Substituída por outra RC',
              'publishing': 'Publicação em andamento ou parcial', 'published': 'Release de TESTE publicada'}.get(record['status'], record['status'])
    return (f'# TESTE por Issue: {record["version"]} / RC{TAG.fullmatch(record["tag"])[2]}\n\n'
            f'**{record["title"]}**\n\n**Estado:** {status}\n\n'
            f'**Regra:** 1/1, israelhudson. Aprovar apenas habilita o comando final.\n\n'
            f'**Preview:** {report["preview_url"]}\n\n**Tag:** `{record["tag"]}`\n\n'
            f'**Código:** `{record["source_sha"]}`\n\n## Changelog congelado\n\n{changelog}\n\n'
            f'## Comandos\n\n`/aprovar {record["tag"]}`\n\n`/reprovar {record["tag"]}`\n\n'
            f'`/publicar {record["tag"]}`\n\n'
            'Escreva cada comando em um comentário novo. Editar/excluir um aval o invalida. '
            'Checkboxes não autorizam publicação. RC2 começa sem avais antigos.\n\n'
            f'**Relatório SHA-256:** `{record["report_digest"]}`\n\n'
            'Este ensaio cria apenas uma tag test-issue-* e uma prerelease no GitHub, sem alterar Latest ou distribuir o app.\n\n'
            f'<!-- issue-release:{record["tag"]}:{record["report_digest"]} -->')


def refresh(journal, record):
    body = issue_body(record)
    # Journal desired body before updating the Issue. Lost PATCH is repairable.
    record['view_update'] = {'previous_digest': record.get('issue_body_digest'), 'pending': True}
    record['issue_body_digest'] = lab.digest(body)
    journal.save('issue-view-intent', record['tag'])
    response = lab.api(lab.endpoint('issues/' + str(record['issue_number'])), {'body': body}, 'PATCH')
    if lab.digest(response.get('body', '')) != record['issue_body_digest']:
        raise IssueError('Ficha não confirmou atualização. Reconciliar a visão antes de publicar.')
    record['view_update']['pending'] = False
    journal.save('issue-view-confirmed', record['tag'])


def open_issue(policy, tag, metadata, smoke, output):
    journal = Journal(policy)
    record = journal.record(tag)
    if journal.value['active'] != tag or record['status'] not in ('prepared', 'opening'):
        raise IssueError('Candidata não está em preparação.')
    if tag_sha(tag) != record['source_sha'] or record['policy_digest'] != lab.digest(policy):
        raise IssueError('Identidade do corte mudou.')
    required = ('web_content_sha256', 'snapshot_manifest_sha256')
    if (metadata.get('source_sha') != record['source_sha'] or smoke.get('success') is not True
            or smoke.get('source_sha') != record['source_sha']
            or any(metadata.get(k) != smoke.get(k) or not re.fullmatch(r'[a-f0-9]{64}', str(metadata.get(k, ''))) for k in required)):
        raise IssueError('Preview não confirmado pelos bytes do build.')
    preview_url = 'https://israelhudson.github.io/flutter_code_push_example/snapshots/' + record['source_sha'] + '/'
    if smoke.get('snapshot_url') != preview_url:
        raise IssueError('URL de preview fora da identidade permitida.')
    compare = lab.api(lab.endpoint('compare/' + record['base_sha'] + '...' + record['source_sha']))
    if compare.get('total_commits', 0) != len(compare.get('commits', [])) or compare.get('status') not in ('ahead', 'identical'):
        raise IssueError('Changelog truncado ou base não ancestral. Manter bloqueado.')
    report = {'tag': tag, 'source_sha': record['source_sha'], 'preview_url': preview_url,
              'title': record['title'], 'version': record['version'], 'stable_tag': record['stable_tag'],
              'web_content_sha256': metadata['web_content_sha256'], 'snapshot_manifest_sha256': metadata['snapshot_manifest_sha256'],
              'base_sha': record['base_sha'], 'commits': [{'sha': c['sha'], 'message': c['commit']['message'].splitlines()[0]}
                                                       for c in compare.get('commits', [])]}
    if record.get('report_digest') and record['report_digest'] != lab.digest(report):
        raise IssueError('Relatório já congelado diverge. Não reabrir com outro conteúdo.')
    record.update(report=report, report_digest=lab.digest(report), status='opening')
    journal.save('issue-create-intent', tag)
    marker = f'<!-- issue-release:{tag}:{record["report_digest"]} -->'
    matches = [i for i in pages('issues?state=all') if not i.get('pull_request') and marker in i.get('body', '')]
    if len(matches) > 1:
        raise IssueError('Mais de uma ficha. Reconciliar manualmente, sem duplicar.')
    if matches:
        issue = matches[0]
    else:
        record['status'] = 'awaiting_approval'
        issue = lab.api(lab.endpoint('issues'), {'title': f'TESTE Issue: {record["version"]} RC{TAG.fullmatch(tag)[2]} / {record["title"]}',
                    'body': issue_body(record), 'assignees': ['israelhudson']}, 'POST')
    if (issue.get('state') != 'open' or issue.get('user', {}).get('type') != 'Bot'
            or issue.get('user', {}).get('id') != 41898282):
        raise IssueError('Ficha existente não pertence ao bot da automação.')
    record.update(issue_number=issue['number'], issue_url=issue['html_url'], opened_at=issue['created_at'], status='awaiting_approval')
    record['issue_body_digest'] = lab.digest(issue['body'])
    enqueue(record, 'candidate')
    journal.save('issue-opened', tag)
    refresh(journal, record)
    lab.output(output, 'report.json', record)
    lab.outputs({'issue_number': issue['number'], 'candidate_tag': tag, 'issue_url': issue['html_url']})
    return record


def decide(policy, event, output):
    lab.outputs({'publish': 'false', 'issue_number': '0', 'comment_id': '0'})
    if (event.get('repository', {}).get('full_name') != lab.REPOSITORY
            or event.get('issue', {}).get('pull_request')):
        return {'state': 'ignored'}
    number = event.get('issue', {}).get('number')
    if not isinstance(number, int):
        return {'state': 'ignored'}
    journal = Journal(policy)
    record = journal.by_issue(number)
    if not record:
        return {'state': 'ignored-unregistered-issue'}
    tag = record['tag']
    lab.outputs({'candidate_tag': tag})
    if journal.value['active'] != tag or record['status'] in TERMINAL:
        # Completed publication is a read-only receipt, including repeated commands.
        value = {'state': record['status'], 'receipt': record.get('receipt'), 'publish': False}
        lab.output(output, 'decision.json', value)
        return value
    action = event.get('action')
    comment = event.get('comment', {})
    if action in ('edited', 'deleted') and isinstance(comment.get('id'), int):
        record['revoked_comment_ids'] = sorted(set(record['revoked_comment_ids'] + [comment['id']]))
    if not comment and action in ('edited', 'closed', 'reopened'):
        # Human issue-body changes invalidate every recorded approval, even if restored.
        current = pages(f'issues/{number}/comments')
        record['revoked_comment_ids'] = sorted(set(record['revoked_comment_ids'] + [c['id'] for c in current]))
    if record.get('publication'):
        journal.save('comment-observed-during-publication', tag)
        # No edited/deleted event can resume or start publication.
        return {'state': 'publication-intent-pending', 'publish': False}
    try:
        frozen(record, policy)
        _, comments = issue_view(record, policy)
    except (IssueError, lab.LabError) as error:
        record['status'] = 'awaiting_approval'
        record['approvals'] = []
        # A failed identity/view check revokes approvals, not just presentation.
        current = pages(f'issues/{number}/comments')
        record['revoked_comment_ids'] = sorted(set(record['revoked_comment_ids'] + [c['id'] for c in current]))
        journal.save('decision-blocked', tag)
        refresh(journal, record)  # Repair presentation while keeping old votes revoked.
        lab.output(output, 'decision.json', {'state': 'blocked', 'reason': str(error)})
        return {'state': 'blocked', 'publish': False}
    if action == 'created' and parse(comment.get('body')) == ('aprovar', tag):
        live = next((c for c in comments if c['id'] == comment.get('id')), None)
        if (live and unchanged_comment(live, record) and comment_digest(live) == comment_digest(comment)
                and permitted(live.get('user', {}), policy['approvers'])):
            record.setdefault('accepted_comments', {})[str(live['id'])] = comment_digest(live)
    votes = decisions(comments, record, policy)
    # A valid rejection permanently closes this RC, even if another approval follows.
    rejected = any(parse(c.get('body')) == ('reprovar', tag) and unchanged_comment(c, record)
                   and permitted(c.get('user', {}), policy['approvers']) for c in comments)
    if rejected:
        record['status'] = 'rejected'
        record['approvals'] = []
        enqueue(record, 'rejected')
    else:
        record['approvals'] = [v for v in votes.values() if v['command'] == 'aprovar']
        approved = {v['author'][0] for v in record['approvals']} == {p['id'] for p in policy['approvers']}
        record['status'] = 'approved' if approved else 'awaiting_approval'
        if approved:
            enqueue(record, 'approved')
    journal.save('decisions-reconciled', tag)
    refresh(journal, record)
    result = {'state': record['status'], 'publish': False, 'tag': tag}
    if action == 'created' and parse(comment.get('body')) == ('publicar', tag) and record['status'] == 'approved':
        live = next((c for c in comments if c['id'] == comment.get('id')), None)
        if (live and comment_digest(live) == comment_digest(comment) and unchanged_comment(live, record)
                and permitted(live['user'], policy['publishers'])
                and all(v['comment_id'] < live['id'] for v in record['approvals'])):
            result['publish'] = True
            lab.outputs({'publish': 'true', 'issue_number': number, 'comment_id': live['id']})
    lab.output(output, 'decision.json', result)
    return result


def publication_check(journal, policy, tag, comment_id, intent=None):
    record = journal.record(tag)
    if (journal.value['active'] != tag or record['status'] in ('rejected', 'superseded')
            or journal.value.get('last_published') != record['base_publication']):
        raise IssueError('Candidata/base de publicação mudou.')
    frozen(record, policy)
    _, comments = issue_view(record, policy)
    votes = approvals(comments, record, policy)
    command = next((c for c in comments if c['id'] == comment_id), None)
    if (not command or parse(command.get('body')) != ('publicar', tag)
            or not unchanged_comment(command, record) or not permitted(command.get('user', {}), policy['publishers'])
            or any(v['comment_id'] >= comment_id for v in votes)):
        raise IssueError('/publicar precisa ser um comentário novo posterior ao aval, da conta autorizada.')
    proof = {'comment_id': comment_id, 'comment_digest': comment_digest(command),
             'publisher': {'id': command['user']['id'], 'login': command['user']['login']}, 'approvals': votes}
    if intent and (intent['authorization'] != json.loads(lab.canonical(proof))
                   or intent['report_digest'] != record['report_digest']):
        raise IssueError('Aval ou comando final mudou após a intenção. Não continuar os efeitos.')
    return record, proof


def release_payload(record, intent):
    report = record['report']
    return {'tag_name': record['stable_tag'], 'target_commitish': record['source_sha'],
            'name': 'TESTE Issue ' + record['version'] + ' / ' + record['title'],
            'body': f'Ensaio de aprovação por Issue em modo 1/1.\n\nCandidata preservada: `{record["tag"]}`.\n\n'
                    f'Código aprovado: `{record["source_sha"]}`.\n\nFicha: {record["issue_url"]}\n\n'
                    f'Preview: {report["preview_url"]}\n\n'
                    'Publicação somente no GitHub. Nenhum aplicativo ou patch foi distribuído.\n\n'
                    f'<!-- issue-release-intent:{intent["id"]}:{record["report_digest"]} -->',
            'draft': False, 'prerelease': True, 'make_latest': 'false'}


def verify_release(release, record, intent):
    expected = release_payload(record, intent)
    if (not release or any(release.get(k) != expected[k] for k in ('tag_name', 'target_commitish', 'name', 'body', 'draft', 'prerelease'))
            or not release.get('published_at') or not release.get('id')):
        raise IssueError('Release existente diverge da intenção. Não sobrescrever nem publicar outra.')


def verify_http(report):
    import sys
    sys.path.insert(0, str(ROOT / 'deploy'))
    import pages_smoke
    return pages_smoke.verify(report['source_sha'], report['web_content_sha256'], report['snapshot_manifest_sha256'])


def publish(policy, issue_number, comment_id, output):
    protect()
    journal = Journal(policy)
    record = journal.by_issue(issue_number)
    if not record:
        raise IssueError('Issue não registrada.')
    tag = record['tag']
    if record['status'] == 'published':
        # No new authority is inferred from a repeated command. Verify existing effects.
        if tag_sha(record['stable_tag']) != record['source_sha']:
            raise IssueError('Tag publicada diverge do recibo.')
        release = lab.api(lab.endpoint('releases/tags/' + record['stable_tag']))
        verify_release(release, record, record['publication'])
        lab.output(output, 'receipt.json', record['receipt'])
        lab.outputs({'candidate_tag': tag})
        return record['receipt']
    intent = record.get('publication')
    record, proof = publication_check(journal, policy, tag, comment_id, intent)
    # Publish validates the live HTTP files before creating the intent/effects.
    verify_http(record['report'])
    if intent is None:
        intent = {'id': lab.digest({'tag': tag, 'report': record['report_digest'], 'authorization': proof}),
                  'authorization': json.loads(lab.canonical(proof)), 'report_digest': record['report_digest'],
                  'comment_id': comment_id, 'created_at': lab.now()}
        record['publication'] = intent
        record['status'] = 'publishing'
        journal.save('publication-intent', tag)
        refresh(journal, record)
    elif intent['comment_id'] != comment_id:
        raise IssueError('Retome apenas o comando original da publicação parcial.')
    record, _ = publication_check(journal, policy, tag, comment_id, intent)
    lab.create_ref_verified('tags/' + record['stable_tag'], record['source_sha'])
    record, _ = publication_check(journal, policy, tag, comment_id, intent)
    existing = lab.api(lab.endpoint('releases/tags/' + record['stable_tag']), missing=True)
    if existing is None:
        try:
            existing = lab.api(lab.endpoint('releases'), release_payload(record, intent), 'POST')
        except lab.LabError:
            # A lost response may already have published. Only reconcile by exact identity.
            existing = lab.api(lab.endpoint('releases/tags/' + record['stable_tag']), missing=True)
            if existing is None:
                raise
    verify_release(existing, record, intent)
    if tag_sha(record['stable_tag']) != record['source_sha']:
        raise IssueError('Tag final divergente após publicação.')
    # Final observation does not create another effect; keep the actual receipt.
    record = journal.record(tag)
    receipt = {'tag': tag, 'stable_tag': record['stable_tag'], 'source_sha': record['source_sha'],
               'report_digest': record['report_digest'], 'authorization': intent['authorization'],
               'release_id': existing['id'], 'release_url': existing['html_url'],
               'published_at': existing['published_at'], 'github_release_published': True,
               'approval_mode': '1/1', 'distribution_performed': False}
    record['receipt'] = receipt
    record['status'] = 'published'
    journal.value['last_published'] = {'version': record['version'], 'source_sha': record['source_sha'], 'tag': record['stable_tag']}
    enqueue(record, 'published')
    journal.save('published', tag)
    refresh(journal, record)
    lab.output(output, 'receipt.json', receipt)
    lab.outputs({'candidate_tag': tag})
    return receipt


def notify(policy, tag, output):
    journal = Journal(policy)
    record = journal.record(tag)
    results = []
    token = os.environ.get('SLACK_BOT_TOKEN')
    for key, notice in list(record.get('notices', {}).items()):
        if notice['state'] != 'pending':
            continue  # sent/unknown are never blindly repeated on an ephemeral runner.
        if notice['event'] == 'approved' and (record['status'] != 'approved'
                or notice.get('approval_digest') != lab.digest(record.get('approvals', []))):
            notice['state'] = 'superseded'
            journal.save('slack-obsolete-event', tag)
            continue
        if not token:
            results.append({'key': key, 'state': 'pending', 'reason': 'secret-absent'})
            continue
        slack_notify.verify_destination(token)
        labels = {'candidate': 'Candidata pronta para avaliar', 'approved': 'Aval registrado. Falta /publicar',
                  'rejected': 'RC reprovada', 'superseded': 'RC substituída', 'published': 'Release de teste publicada'}
        text = (f'TESTE de aprovação por Issue (1/1): {tag}\n{record["title"]}\n'
                f'Evento: {labels[notice["event"]]}\nEstado atual: {record["status"]}\nPreview: {record["report"]["preview_url"]}\n'
                f'Aprovação e /publicar separado: {record["issue_url"]}\n'
                'Este ensaio publica somente no GitHub. Slack não aprova nem publica.')
        notice['state'] = 'unknown'
        journal.save('slack-intent', tag)  # Remote checkpoint precedes POST.
        response = slack_notify.slack_api('chat.postMessage', {
            'channel': slack_notify.CHANNEL_ID, 'text': text, 'mrkdwn': False,
            'unfurl_links': False, 'unfurl_media': False}, token)
        if response.get('channel') != slack_notify.CHANNEL_ID or not re.fullmatch(r'\d+\.\d+', str(response.get('ts', ''))):
            raise IssueError('Slack sem recibo exato. Unknown bloqueia reenvio automático.')
        notice.update(state='sent', ts=response['ts'])
        journal.save('slack-sent', tag)
        results.append({'key': key, 'state': 'sent', 'channel': response['channel'], 'ts': response['ts']})
    lab.output(output, 'notifications.json', results)
    return results


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest='operation', required=True)
    p = commands.add_parser('prepare'); p.add_argument('--version', required=True); p.add_argument('--title', required=True)
    p = commands.add_parser('open'); p.add_argument('--tag', required=True); p.add_argument('--metadata', required=True); p.add_argument('--smoke', required=True)
    p = commands.add_parser('decide'); p.add_argument('--event', required=True)
    p = commands.add_parser('publish'); p.add_argument('--issue', type=int, required=True); p.add_argument('--comment', type=int, required=True)
    p = commands.add_parser('notify'); p.add_argument('--tag', required=True)
    for p in commands.choices.values():
        p.add_argument('--output', required=True)
    args = parser.parse_args(argv)
    try:
        policy = policy_load()
        context(policy, 'publish-manual' if args.operation == 'publish' and os.environ.get('GITHUB_EVENT_NAME') == 'workflow_dispatch' else args.operation)
        if args.operation == 'prepare':
            value = prepare(policy, args.version, args.title, args.output)
        elif args.operation == 'open':
            value = open_issue(policy, args.tag, json.loads(Path(args.metadata).read_text()), json.loads(Path(args.smoke).read_text()), args.output)
        elif args.operation == 'decide':
            value = decide(policy, json.loads(Path(args.event).read_text()), args.output)
        elif args.operation == 'publish':
            value = publish(policy, args.issue, args.comment, args.output)
        else:
            value = notify(policy, args.tag, args.output)
        print(lab.canonical(value))
        return 0
    except (IssueError, lab.LabError, slack_notify.NoticeError, ValueError, OSError, KeyError) as error:
        message = str(error) if isinstance(error, (IssueError, lab.LabError, slack_notify.NoticeError)) else 'Dados inválidos ou indisponíveis. Manter bloqueado.'
        lab.output(args.output, 'blocked.json', {'state': 'blocked', 'reason': message, 'distribution_performed': False})
        print(message)
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
