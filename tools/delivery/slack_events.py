"""Drain frozen candidate notice pointers; Slack never controls release decisions.

Only records enrolled at a new cut are eligible. Events are historical milestones,
not a claim that an older 1/2 observation is still the current approval state.
No app artifact, PR body, user input or later AI response is executed or rendered.
"""
import argparse
import json
import os
from pathlib import Path
import re
import sys
from urllib.parse import quote

import release_lab as lab
import slack_notify
import slack_outbox
import slack_legacy
from release_notes import approver_labels, brief_notes
from slack_preview import readable_payload, render_preview

LABELS = {
    'candidate_available': 'Candidata pronta para revisão',
    'approval_first': 'Aval do Aprovador 1 registrado',
    'approval_second': 'Aval do Aprovador 2 registrado',
    'approvals_complete': 'Dois avais registrados',
    'candidate_rejected': 'Candidata rejeitada',
    'candidate_cancelled': 'Avaliação cancelada',
    'candidate_failed': 'Avaliação encerrada com falha',
    'candidate_superseded': 'Candidata substituída',
    'publication_completed': 'Promoção concluída',
    'publication_partial': 'Publicação requer recuperação',
}
DETAILS = {
    'candidate_available': 'Preview e changelog congelados. Os dois aprovadores revisam a mesma candidata.',
    'approval_first': 'Este marco registra somente o aval do Aprovador 1. Um aval sozinho não habilita o comando final.',
    'approval_second': 'Este marco registra somente o aval do Aprovador 2. Um aval sozinho não habilita o comando final.',
    'approvals_complete': 'Marco 2/2: os dois avais foram registrados. Eles apenas habilitam o comando final separado; este aviso não publica.',
    'candidate_rejected': 'Esta avaliação foi recusada. Corrija por PR para a branch de release e prepare outra RC, com novos avais.',
    'candidate_cancelled': 'A avaliação foi cancelada. Nenhum aval desta tentativa autoriza outra RC.',
    'candidate_failed': 'A avaliação foi encerrada sem uma promoção comprovada. Consulte os logs e a causa na execução.',
    'candidate_superseded': 'Outra candidata substituiu esta RC. Seu código, changelog e avais não autorizam a candidata nova.',
    'publication_completed': 'A tag estável e a Release no GitHub foram confirmadas no código aprovado. Nenhum app ou patch mobile foi distribuído.',
    'publication_partial': 'Uma intenção de publicação ficou preservada para recuperação. Não crie outra RC nem repita efeitos sem conferir o recibo.',
}


def validate_record(policy, record, api=lab.api):
    """Historical notice validation deliberately does not require active branch HEAD.

    Publication commands keep their stronger ensure_current/assert_record checks.
    """
    tag, source, run_id = record.get('candidate_tag'), record.get('source_sha'), str(record.get('evaluation_run_id', ''))
    report = record.get('report')
    if (record.get('notification_schema') != 1 or not lab.TAG.fullmatch(str(tag))
            or not lab.SHA.fullmatch(str(source)) or not re.fullmatch(r'[1-9]\d*', run_id)
            or record.get('policy_digest') != lab.digest(policy)
            or not isinstance(report, dict) or lab.digest(report) != record.get('report_digest')
            or report.get('candidate_tag') != tag or report.get('source_sha') != source
            or str(report.get('run_id')) != run_id or report.get('policy_digest') != lab.digest(policy)
            or report.get('distribution_performed') is not False):
        raise lab.LabError('Identidade ou relatório congelado do aviso diverge.')
    lab.frozen_material(record)
    render_preview(report, policy)  # Validates fixed preview origin and publication roles.
    ref = api(lab.endpoint('git/ref/tags/' + quote(tag, safe='')))
    if ref.get('object', {}).get('type') != 'commit' or ref.get('object', {}).get('sha') != source:
        raise lab.LabError('Tag da RC do aviso não corresponde ao snapshot congelado.')
    run = api(lab.endpoint('actions/runs/' + run_id))
    if (str(run.get('id')) != run_id or run.get('run_attempt') != 1
            or lab.identity(run.get('actor', {})) != lab.identity(record.get('preparer', {}))
            or lab.identity(run.get('actor', {})) not in {lab.identity(p) for p in policy['operators']}
            or str(run.get('path', '')).split('@', 1)[0] not in
            ('.github/workflows/release-lab-prepare.yml', '.github/workflows/release-lab-evaluate.yml')
            or run.get('head_repository', {}).get('full_name', lab.REPOSITORY) != lab.REPOSITORY):
        raise lab.LabError('Run original do aviso não corresponde à avaliação registrada.')
    reviews = api(lab.endpoint('actions/runs/' + run_id + '/approvals'))
    ids = {p['environment']: api(lab.endpoint('environments/' + quote(p['environment'], safe='')))['id']
           for p in [*policy['approvers'], {'environment': policy['final_environment']}]}
    return run, reviews, ids


def validate_event(policy, record, item, evidence, api=lab.api):
    event = item.get('event')
    expected = {'event': event, 'candidate_tag': record['candidate_tag'],
                'source_sha': record['source_sha'], 'snapshot_digest': record['report_digest'],
                'run_id': str(record['evaluation_run_id'])}
    if event not in LABELS or item != expected:
        raise lab.LabError('Ponteiro de aviso desconhecido ou de outra candidata.')
    run, reviews, ids = evidence
    roles = ('first', 'second') if event in ('approvals_complete', 'publication_completed') else (
        (event.removeprefix('approval_'),) if event.startswith('approval_') else ())
    for role in roles:
        person = next(p for p in policy['approvers'] if p['role'] == role)
        observed = lab.review_for(reviews, person['environment'], ids[person['environment']], [person])
        receipt = record.get('approval_receipts', {}).get(role, {})
        if any(receipt.get(k) != value for k, value in
               [('candidate_tag', record['candidate_tag']), ('source_sha', record['source_sha']),
                ('report_digest', record['report_digest']), ('run_attempt', 1), ('review', observed)]
               ) or str(receipt.get('run_id')) != str(record['evaluation_run_id']):
            raise lab.LabError('Aviso de aval sem o recibo e a review originais correspondentes.')
    if event == 'publication_completed':
        receipt = record.get('receipt', {})
        if (record.get('status') != 'completed' or receipt.get('candidate_tag') != record['candidate_tag']
                or receipt.get('source_sha') != record['source_sha']
                or receipt.get('report_digest') != record['report_digest']
                or str(receipt.get('run_id')) != str(record['evaluation_run_id'])
                or receipt.get('distribution_performed') is not False):
            raise lab.LabError('Promoção sem recibo da mesma candidata.')
        observed = lab.validate_reviews(reviews, policy, ids, stage='final')
        if receipt.get('approvers') != observed['approvers'] or receipt.get('publisher') != observed['publisher']:
            raise lab.LabError('Recibo da promoção diverge das decisões originais.')
        if lab.publication_mode(policy) == 'github_release_only':
            intent = record.get('publication', {})
            lab.verify_intent(policy, record, intent)
            stable = api(lab.endpoint('git/ref/tags/' + quote(record['stable_tag'], safe='')))
            if stable.get('object', {}).get('sha') != record['source_sha']:
                raise lab.LabError('Tag estável do aviso diverge do código aprovado.')
            release = api(lab.endpoint('releases/tags/' + quote(record['stable_tag'], safe='')))
            if lab.verify_release(release, intent, record=record, policy=policy) != receipt.get('github_release'):
                raise lab.LabError('Release do aviso diverge do recibo.')
    if event == 'candidate_rejected' and not any(
        r.get('state') == 'rejected' and any(e.get('id') == ids.get(e.get('name')) for e in r.get('environments', []))
        for r in reviews):
        raise lab.LabError('Rejeição não comprovada nas reviews originais.')
    if event in ('candidate_cancelled', 'candidate_failed'):
        observation = record.get('status_observation', {})
        expected_status = 'cancelled' if event == 'candidate_cancelled' else 'evaluation_failed'
        if (observation.get('projected_status') != expected_status
                or str(observation.get('run_id')) != str(record['evaluation_run_id'])):
            raise lab.LabError('Encerramento sem observação da avaliação original.')
    if event == 'candidate_superseded' and record.get('status') != 'superseded':
        raise lab.LabError('Candidata não foi substituída.')
    if event == 'publication_partial' and not record.get('publication', {}).get('last_error'):
        raise lab.LabError('Intenção parcial sem falha registrada.')


def render_event(policy, record, item):
    event, report = item['event'], record['report']
    schema = report.get('presentation_schema', 1)
    record_schema = record.get('presentation_schema', 1)
    if type(schema) is not int or type(record_schema) is not int or schema != record_schema:
        raise lab.LabError('Apresentação do aviso diverge do relatório congelado.')
    if schema == 1:
        return slack_legacy.render_event(policy, record, item)
    if schema != 2:
        raise lab.LabError('Schema de apresentação desconhecido.')
    run_url = 'https://github.com/' + lab.REPOSITORY + '/actions/runs/' + str(record['evaluation_run_id'])
    identity = {k: item[k] for k in ('candidate_tag', 'source_sha', 'snapshot_digest', 'run_id')}
    identity['run_url'] = run_url
    key = slack_outbox.logical_event_key(identity, event)
    notice = slack_notify.render_notice('candidate', DETAILS[event], record['candidate_tag'],
                                        record['source_sha'], run_url, simulation=report['result_simulated'],
                                        idempotency_key=key)
    notes = brief_notes(report)
    description = [DETAILS[event], 'Marco histórico. Consulte o estado atual no GitHub.']
    changes, limitations = [], []
    if event == 'candidate_available':
        description = notes['description']
        changes, limitations = notes['changes'], notes['limitations']
    if event == 'publication_completed' and report['result_simulated']:
        description[0] = 'O comando final gerou um resultado simulado. Nenhuma tag estável ou Release foi criada.'
    aliases = approver_labels(policy)
    footer = ('Decisões no GitHub: ' + ' E '.join(aliases) + ' aprovam a mesma RC.\n'
              'Com 2/2, ' + ' OU '.join(aliases) + ' dá o comando final no gate separado.\n'
              'Slack só informa. Mobile não distribuído. Marco histórico; confira o estado atual no GitHub.')
    preview_url = report['preview']['snapshot_url']
    payload, _ = readable_payload('LAB · ' + LABELS[event] + '\n' + record['candidate_tag'] + ' · ' + report['title'],
        description, changes, footer, preview_url, run_url, source_label=notes['source_label'],
        truncated=notes['truncated'], limitations=limitations)
    notice['payload'].update(payload)
    notice.update(event=event, identity=identity)
    return notice


def drain(policy, tag, output_dir, *, state=None, api=lab.api,
          sender=slack_outbox.send_frozen_notice, render_only=False):
    state = lab.state_read(policy)[0] if state is None else state
    record = state.get('candidates', {}).get(tag)
    if record is None:
        raise lab.LabError('Candidata desconhecida para aviso.')
    output_dir = Path(output_dir); output_dir.mkdir(parents=True, exist_ok=True)
    records = []
    if record.get('supersedes'):
        prior = state.get('candidates', {}).get(record['supersedes'])
        if not prior or prior.get('status') != 'superseded':
            raise lab.LabError('Vínculo de substituição do aviso diverge do journal.')
        records.append(prior)
    records.append(record)
    results = []
    for candidate in records:
        if candidate.get('notification_schema') != 1 or not candidate.get('slack_events'):
            continue  # No retroactive notification of legacy 1.6.0 or unfrozen previews.
        evidence = validate_record(policy, candidate, api)
        for item in candidate['slack_events']:
            validate_event(policy, candidate, item, evidence, api)
            notice = render_event(policy, candidate, item)
            slack_outbox.validate_notice(notice)  # Refuse secrets/unsafe text before writing any artifact.
            destination = output_dir / lab.digest(notice['event_key'])
            destination.mkdir(parents=True, exist_ok=True)
            lab.output(destination, 'notice.json', notice)
            result = ({'state': 'rendered', 'message_sent': False} if render_only
                      else sender(notice, destination))
            results.append({'candidate_tag': candidate['candidate_tag'], 'event': item['event'],
                            'event_key': notice['event_key'], **result})
    value = {'schema': 1, 'candidate_tag': tag, 'render_only': render_only, 'results': results,
             'candidate_state_unchanged': True, 'approval_or_publication_performed': False}
    lab.output(output_dir, 'notification-results.json', value)
    return value


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    target = parser.add_mutually_exclusive_group(required=True)
    target.add_argument('--candidate-tag')
    target.add_argument('--evaluation-run-id')
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--render-only', action='store_true')
    args = parser.parse_args(argv)
    try:
        if os.environ.get('GITHUB_REPOSITORY') != lab.REPOSITORY:
            raise lab.LabError('Aviso limitado ao repositório de laboratório.')
        policy = lab.load_policy()
        state, _ = lab.state_read(policy)
        tag = args.candidate_tag
        if args.evaluation_run_id:
            if not re.fullmatch(r'[1-9]\d*', args.evaluation_run_id):
                raise lab.LabError('Execução de origem inválida.')
            matches = [r['candidate_tag'] for r in state.get('candidates', {}).values()
                       if str(r.get('evaluation_run_id')) == args.evaluation_run_id]
            if not matches:
                lab.output(args.output, 'notification-results.json', {'state': 'skipped', 'reason': 'no_registered_candidate'})
                return 0
            if len(matches) != 1:
                raise lab.LabError('Execução vinculada a mais de uma candidata.')
            tag = matches[0]
        value = drain(policy, tag, args.output, state=state, render_only=args.render_only)
        print(json.dumps({'candidate_tag': tag, 'events': len(value['results']),
                          'states': [r['state'] for r in value['results']]}))
        return 0
    except (ValueError, KeyError, TypeError, OSError):
        # Optional diagnosis: never propagate raw API responses, tokens or input text.
        lab.output(args.output, 'notification-results.json', {'state': 'blocked', 'reason': 'identity_or_evidence_unverified'})
        print('Aviso opcional bloqueado; confira identidade/evidências. Aprovações e publicação seguem independentes.')
        return 0


if __name__ == '__main__':
    raise SystemExit(main())
