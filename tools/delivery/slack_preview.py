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

from changelog_summary import verify_communication
from release_notes import approver_labels, brief_notes
import slack_legacy


def readable_payload(heading, description, changes, footer, preview_url, run_url,
                     *, source_label=None, truncated=False, limitations=None):
    """URL buttons navigate only; fallback includes every readable section/link.

    Official Block Kit docs checked 2026-10-09:
    https://docs.slack.dev/reference/block-kit/block-elements/button-element/
    https://docs.slack.dev/reference/block-kit/blocks/divider-block/
    https://docs.slack.dev/reference/methods/chat.postMessage/
    """
    texts = [heading, '\n'.join(description)]
    if changes:
        change_text = 'Mudanças' + (' · ' + source_label if source_label else '') + '\n'
        change_text += '\n'.join('• ' + value for value in changes)
        if truncated:
            change_text += '\nHistórico completo no changelog.'
        texts.append(change_text)
    if limitations:
        texts.append('Limitações\n' + '\n'.join('• ' + value for value in limitations))
    texts.append(footer)
    buttons = [
        {'type': 'button', 'text': {'type': 'plain_text', 'text': 'Preview', 'emoji': False},
         'url': preview_url, 'accessibility_label': 'Abrir o preview congelado desta candidata'},
        {'type': 'button', 'text': {'type': 'plain_text', 'text': 'Changelog', 'emoji': False},
         'url': run_url, 'accessibility_label': 'Ler o changelog da mesma candidata no GitHub'},
        {'type': 'button', 'text': {'type': 'plain_text', 'text': 'Revisar GitHub', 'emoji': False},
         'url': run_url, 'accessibility_label': 'Abrir a execução e suas decisões no GitHub'},
    ]
    blocks = []
    for position, text in enumerate(texts):
        if len(text) > 2900:
            raise ValueError('Seção do aviso excede o limite de texto.')
        if position in (2, len(texts) - 1):
            blocks.append({'type': 'divider'})
        blocks.append({'type': 'section', 'text': {'type': 'plain_text', 'text': text, 'emoji': False}})
    blocks += [{'type': 'divider'}, {'type': 'actions', 'elements': buttons}]
    fallback = '\n\n'.join(texts) + '\n\n' + '\n'.join(button['text']['text'] + ': ' + button['url'] for button in buttons)
    escaped = html.escape(fallback, quote=False)
    if len(escaped) > 4000:
        raise ValueError('Fallback do aviso excede o limite de texto.')
    return {'text': escaped, 'blocks': blocks}, fallback


def required_text(value, field, maximum=200):
    if (not isinstance(value, str) or not value.strip() or len(value) > maximum
            or any(ord(char) < 32 for char in value)):
        raise ValueError(field + ' inválido.')
    return value.strip()


def render_preview(report, policy):
    schema = report.get('presentation_schema', 1)
    if type(schema) is not int:
        raise ValueError('Schema de apresentação desconhecido.')
    if schema == 1:
        return slack_legacy.render_preview(report, policy)
    if schema != 2:
        raise ValueError('Schema de apresentação desconhecido.')
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
    notes = brief_notes(report)
    run_url = 'https://github.com/' + repo + '/actions/runs/' + run_id
    final = ('a tag estável e a Release no GitHub' if mode == 'github_release_only'
             else 'o resultado simulado da entrega')
    selection = None
    if 'communication' in report:
        selection = verify_communication(report)
    summary_source = selection['source'] if selection else 'commits_fallback'
    fallback_reason = selection['fallback_reason'] if selection else 'ai_not_configured'
    aliases = approver_labels(policy)
    footer = ('Próximo passo: ' + ' E '.join(aliases) + ' revisam esta candidata.\n'
              'Com 2/2, ' + ' OU '.join(aliases) + ' autoriza ' + final + ' no gate final separado.\n'
              'Este aviso não aprova nem publica. Mobile não distribuído.')
    payload, body = readable_payload('SIMULAÇÃO DE AVISO SLACK — nenhum envio\n' + tag + ' · ' + title,
        notes['description'], notes['changes'], footer, preview_url, run_url,
        source_label=notes['source_label'], truncated=notes['truncated'], limitations=notes['limitations'])
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
    markdown += '[Preview](' + preview_url + ') · [Changelog](' + run_url + ') · [Revisar GitHub](' + run_url + ')\n'
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
