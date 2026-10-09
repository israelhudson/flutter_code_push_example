"""Frozen presentation for schema 1 records; preserve historical payload hashes.

Copied from trusted main be2bff221bc498b4be66602d912fb2cae1f9ce2a.
Only schema 2 records use the new presentation. No send operation exists here.
"""
import hashlib
import html
import json
import re
from urllib.parse import urlsplit

import release_lab as lab
import slack_notify
import slack_outbox
from changelog_summary import normalized_changes, verify_communication

def required_text(value, field, maximum=200):
    if (not isinstance(value, str) or not value.strip() or len(value) > maximum
            or any(ord(char) < 32 for char in value)):
        raise ValueError(field + ' inválido.')
    return value.strip()


def render_preview(report, policy):
    repo = required_text(policy.get('repository'), 'Repositório')
    if not re.fullmatch(r'[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+', repo):
        raise ValueError('Repositório inválido.')
    tag = required_text(report.get('candidate_tag'), 'Candidata')
    if not re.fullmatch(r'v\d+\.\d+\.\d+-rc\.[1-9]\d*', tag):
        raise ValueError('Tag RC inválida.')
    source = report.get('source_sha', '')
    if not re.fullmatch(r'[0-9a-f]{40}', source):
        raise ValueError('SHA da candidata inválido.')
    run_id = str(report.get('run_id', ''))
    if not re.fullmatch(r'[1-9]\d*', run_id):
        raise ValueError('Execução inválida.')
    title = required_text(report.get('title'), 'Título')
    preview = report.get('preview', {})
    if preview.get('success') is not True or preview.get('source_sha') != source:
        raise ValueError('Preview ainda não confirmado para esta candidata.')
    preview_url = required_text(preview.get('snapshot_url'), 'Preview', 1200)
    parsed = urlsplit(preview_url)
    owner, name = repo.split('/')
    if (parsed.scheme != 'https' or parsed.netloc != owner + '.github.io'
            or parsed.path != '/' + name + '/snapshots/' + source + '/'
            or parsed.query or parsed.fragment):
        raise ValueError('URL do preview não corresponde ao snapshot.')
    people = [required_text(person.get('login'), 'Revisor')
              for person in policy.get('approvers', [])]
    publishers = [required_text(person.get('login'), 'Publicador')
                  for person in policy.get('publishers', [])]
    if len(people) != 2 or len(set(people)) != 2 or set(publishers) != set(people):
        raise ValueError('Aviso exige dois revisores distintos e os mesmos publicadores.')
    if any(not re.fullmatch(r'[A-Za-z0-9-]+', person) for person in people):
        raise ValueError('Conta de revisão inválida.')
    mode = report.get('publication_mode')
    if mode not in ('github_release_only', 'simulation'):
        raise ValueError('Modo de publicação desconhecido.')
    changes = report.get('changes')
    if not isinstance(changes, list):
        raise ValueError('Histórico de commits ausente.')
    original_count = len(changes)
    changes, history_truncated = normalized_changes(changes)
    run_url = 'https://github.com/' + repo + '/actions/runs/' + run_id
    final = ('a tag estável e a Release no GitHub' if mode == 'github_release_only'
             else 'o resultado simulado da entrega')
    selection = None
    if 'communication' in report:
        selection = verify_communication(report)
    summary_source = selection['source'] if selection else 'commits_fallback'
    fallback_reason = selection['fallback_reason'] if selection else 'ai_not_configured'
    labels = {'commits_fallback': 'histórico de commits (fallback)',
              'pr_sections': 'descrição das PRs (texto copiado; sem IA)',
              'ai': 'resumo semitécnico por IA, congelado antes da revisão'}
    lines = ['SIMULAÇÃO DE AVISO SLACK — nenhum envio', '', tag + ' — ' + title,
             'Exemplo do aviso emitido quando a candidata fica pronta para revisão.',
             'Consulte o estado atual das decisões na execução do GitHub.', '',
             'Mudanças — ' + labels[summary_source] + ':']
    if selection:
        lines.append(selection['text'])
    else:
        # Older frozen reports do not include communication. Keep a bounded
        # literal fallback; never attach later source descriptions to them.
        size, included = 0, 0
        for change in changes[:8]:
            if size + len(change) + 3 > 1300:
                break
            lines.append('• ' + change)
            size += len(change) + 3
            included += 1
        if not changes:
            lines.append('• Sem commits adicionais.')
        elif included < original_count or history_truncated:
            lines.append('• Histórico completo no relatório da execução.')
    lines += ['', 'Aprovação da candidata: ' + ' E '.join(people) + '.',
              'Depois dos dois avais, ' + ' OU '.join(publishers)
              + ' pode autorizar ' + final + ' no gate final separado.',
              'Este aviso não aprova nem publica. Não distribui aplicativo mobile.']
    body = '\n'.join(lines)
    # Slack plain_text sections have a 3000-character limit. Full source data
    # stays in the report; the notification links back to that report.
    if len(body) > 2900:
        raise ValueError('Aviso excede o limite de texto; reduzir histórico da entrada.')
    payload = {
        'text': html.escape(body, quote=False),
        'blocks': [
            {'type': 'section', 'text': {'type': 'plain_text', 'text': body, 'emoji': False}},
            {'type': 'section', 'text': {'type': 'mrkdwn', 'verbatim': True,
                                       'text': '<' + preview_url + '|Abrir preview> · <'
                                       + run_url + '|Ler changelog e revisar no GitHub>'}},
        ],
    }
    canonical = json.dumps(report, ensure_ascii=False, sort_keys=True, separators=(',', ':'))
    metadata = {'notification_simulated': True, 'message_sent': False,
                'candidate_tag': tag, 'source_sha': source, 'run_id': run_id,
                'source_report_sha256': hashlib.sha256(canonical.encode()).hexdigest(),
                'summary_source': summary_source, 'fallback_reason': fallback_reason,
                'approval_url': run_url, 'preview_url': preview_url}
    if selection:
        metadata.update(context_sha256=selection['context_sha256'],
                        selected_summary_sha256=selection['selected_sha256'],
                        optional_result_status=selection['optional_result_status'])
    markdown = '# SIMULAÇÃO — aviso Slack, sem envio\n\n' + body + '\n\n'
    markdown += '[Abrir preview](' + preview_url + ') · [Ler changelog e revisar no GitHub](' + run_url + ')\n'
    return payload, markdown, metadata


LABELS = {
    'candidate_available': 'Candidata pronta para revisão',
    'approval_first': 'Aval de Israel registrado',
    'approval_second': 'Aval de Fabrícia registrado',
    'approvals_complete': 'Dois avais registrados',
    'candidate_rejected': 'Candidata rejeitada',
    'candidate_cancelled': 'Avaliação cancelada',
    'candidate_failed': 'Avaliação encerrada com falha',
    'candidate_superseded': 'Candidata substituída',
    'publication_completed': 'Promoção concluída',
    'publication_partial': 'Publicação requer recuperação',
}


DETAILS = {
    'candidate_available': 'Preview e changelog congelados. Israel E Fabrícia precisam aprovar a mesma candidata.',
    'approval_first': 'Este marco registra somente o aval de Israel. Um aval sozinho não habilita PUBLICAR.',
    'approval_second': 'Este marco registra somente o aval de Fabrícia. Um aval sozinho não habilita PUBLICAR.',
    'approvals_complete': 'Marco 2/2: os dois avais foram registrados. Eles apenas habilitam o comando final separado; este aviso não publica.',
    'candidate_rejected': 'Esta avaliação foi recusada. Corrija por PR para a branch de release e prepare outra RC, com novos avais.',
    'candidate_cancelled': 'A avaliação foi cancelada. Nenhum aval desta tentativa autoriza outra RC.',
    'candidate_failed': 'A avaliação foi encerrada sem uma promoção comprovada. Consulte os logs e a causa na execução.',
    'candidate_superseded': 'Outra candidata substituiu esta RC. Seu código, changelog e avais não autorizam a candidata nova.',
    'publication_completed': 'A tag estável e a Release no GitHub foram confirmadas no código aprovado. Nenhum app ou patch mobile foi distribuído.',
    'publication_partial': 'Uma intenção de publicação ficou preservada para recuperação. Não crie outra RC nem repita efeitos sem conferir o recibo.',
}


def render_event(policy, record, item):
    event, report = item['event'], record['report']
    run_url = 'https://github.com/' + lab.REPOSITORY + '/actions/runs/' + str(record['evaluation_run_id'])
    identity = {k: item[k] for k in ('candidate_tag', 'source_sha', 'snapshot_digest', 'run_id')}
    identity['run_url'] = run_url
    key = slack_outbox.logical_event_key(identity, event)
    notice = slack_notify.render_notice('candidate', DETAILS[event], record['candidate_tag'],
                                        record['source_sha'], run_url, simulation=report['result_simulated'],
                                        idempotency_key=key)
    lines = ['LAB · ' + LABELS[event], record['candidate_tag'] + ' — ' + report['title'],
             'Marco histórico desta candidata; consulte o estado atual no GitHub.', DETAILS[event]]
    if event == 'candidate_available':
        selected = verify_communication(report)
        labels = {'pr_sections': 'descrição das PRs, sem IA', 'commits_fallback': 'histórico de commits',
                  'ai': 'resumo por IA congelado'}
        lines += ['', 'O que muda — ' + labels[selected['source']] + ':', selected['text']]
    if event == 'publication_completed' and report['result_simulated']:
        lines[-1] = 'O comando final gerou um resultado simulado. Nenhuma tag estável, Release ou distribuição mobile foi criada.'
    lines += ['', 'Israel E Fabrícia aprovam. Depois, Israel OU Fabrícia dá PUBLICAR no gate separado.',
              'Slack só notifica. Aplicativo e patch mobile não são distribuídos por este fluxo.']
    body = '\n'.join(lines)
    if len(body) > 2900:
        raise lab.LabError('Aviso excede o limite; relatório original preservado.')
    preview_url = report['preview']['snapshot_url']
    notice['payload'].update(text=html.escape(body, quote=False) + '\n' + run_url,
        blocks=[{'type': 'section', 'text': {'type': 'plain_text', 'text': body, 'emoji': False}},
                {'type': 'section', 'text': {'type': 'mrkdwn', 'verbatim': True,
                    'text': '<' + preview_url + '|Abrir preview>'}},
                {'type': 'section', 'text': {'type': 'mrkdwn', 'verbatim': True,
                    'text': '<' + run_url + '|Changelog e decisões no GitHub>'}}])
    notice.update(event=event, identity=identity)
    return notice


