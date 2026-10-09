"""Render a candidate Slack notice offline. This module has no send operation.

The payload is an illustration of the candidate-ready event, not live approval
state. It never reads credentials or contacts Slack, GitHub, Plane or an AI.
"""
import argparse
import hashlib
import html
import json
from pathlib import Path
import re
import sys
from urllib.parse import urlsplit


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
    changes = [required_text(change, 'Commit', 500) for change in changes]
    run_url = 'https://github.com/' + repo + '/actions/runs/' + run_id
    final = ('a tag estável e a Release no GitHub' if mode == 'github_release_only'
             else 'o resultado simulado da entrega')
    lines = ['SIMULAÇÃO DE AVISO SLACK — nenhum envio', '', tag + ' — ' + title,
             'Exemplo do aviso emitido quando a candidata fica pronta para revisão.',
             'Consulte o estado atual das decisões na execução do GitHub.', '',
             'Mudanças — histórico de commits (fallback; resumo IA não configurado):']
    lines += ['• ' + change for change in changes[:8]] or ['• Sem commits adicionais.']
    if len(changes) > 8:
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
                'summary_source': 'commits_fallback', 'fallback_reason': 'ai_not_configured',
                'approval_url': run_url, 'preview_url': preview_url}
    markdown = '# SIMULAÇÃO — aviso Slack, sem envio\n\n' + body + '\n\n'
    markdown += '[Abrir preview](' + preview_url + ') · [Ler changelog e revisar no GitHub](' + run_url + ')\n'
    return payload, markdown, metadata


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--report', type=Path, required=True)
    parser.add_argument('--policy', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args(argv)
    try:
        report = json.loads(args.report.read_text())
        policy = json.loads(args.policy.read_text())
        payload, markdown, metadata = render_preview(report, policy)
        args.output.mkdir(parents=True, exist_ok=True)
        (args.output / 'slack-message.json').write_text(json.dumps(payload, ensure_ascii=False, indent=2) + '\n')
        (args.output / 'slack-preview.md').write_text(markdown)
        (args.output / 'slack-preview-metadata.json').write_text(json.dumps(metadata, indent=2) + '\n')
        print('SIMULAÇÃO: aviso gerado localmente; nenhuma mensagem enviada ao Slack.')
        return 0
    except (ValueError, OSError, KeyError, TypeError):
        print('Não foi possível gerar a ilustração; confira relatório, política e pasta de saída. Nenhum envio realizado.', file=sys.stderr)
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
