"""Promote the same GitHub LAB prerelease after Israel's issue review.

The review is an authenticated owner issue comment, not a pull-request review.
No source ref, laboratory database, build or release asset is ever written.
Reviews consume currently visible comments; deleted decisions have no immutable
history in this API. Revoke through a new explicit command, never by deletion.
"""
import argparse
from datetime import datetime
import json
import os
from pathlib import Path
import re
import sys
import tempfile

import github_lab_release as release
from policy import canonical, digest
from remote_state import GitDataAPIError, RemoteState, gh_api

REPO, BASE, URL = release.REPO, release.BASE, release.URL
WORKFLOW = REPO + '/.github/workflows/github-lab-promote.yaml@refs/heads/main'
SCHEMA = 'github-lab-promotion-v1'
REVIEW_SCHEMA = 'github-lab-promotion-review-v1'
TARGET = 'github_release_only'
ReleaseError = release.ReleaseError


class Audit(release.Audit):
    FIELDS = release.Audit.FIELDS | {'review_issue', 'comment_id', 'reviewer_id',
                                    'promotion_identity', 'promoted', 'approval_status'}

    def checkpoint(self, **fields):
        if set(fields) - self.FIELDS:
            raise ReleaseError('Campo fora da lista permitida no checkpoint.')
        release.atomic_json(self.folder / 'checkpoint.json', {'schema': SCHEMA, **fields})


def authenticate(environment, api):
    if environment.get('GITHUB_WORKFLOW_REF') != WORKFLOW:
        raise ReleaseError('Use somente a promoção GitHub LAB manualmente na main pessoal.')
    # The shared verifier still checks actual repository owner/actor numeric IDs,
    # event, ref and rerun actor; only the expected workflow is adapted here.
    return release.authenticate({**environment, 'GITHUB_WORKFLOW_REF': release.WORKFLOW}, api)


def commands(plan):
    suffix = plan['candidate_id'] + ' ' + plan['manifest_hash']
    return 'APROVAR PRODUCAO ' + suffix, 'REVOGAR PRODUCAO ' + suffix


def issue_title(plan):
    return '[LAB] Revisar promoção de ' + plan['candidate_id']


def issue_body(plan):
    approve, revoke = commands(plan)
    marker = ('<!-- ' + REVIEW_SCHEMA + ' candidate:' + plan['candidate_id']
              + ' manifest:' + plan['manifest_hash'] + ' release:' + plan['release_identity']
              + ' source:' + plan['source_sha'] + ' target:' + TARGET + ' -->')
    return (marker + '\n'
            + 'Revisão real de Israel para promover esta candidata à versão estável do **GitHub LAB**.\n\n'
            + '- Candidata: `' + plan['candidate_id'] + '`\n'
            + '- Versão: `' + plan['version'] + '`\n'
            + '- Fonte congelada: `' + plan['source_sha'] + '`\n'
            + '- Manifesto SHA-256: `' + plan['manifest_hash'] + '`\n'
            + '- Identidade da release: `' + plan['release_identity'] + '`\n'
            + '- Destino de produção do laboratório: `' + TARGET + '`\n\n'
            + '[Conferir candidata no GitHub](' + URL + '/releases/tag/' + plan['tag'] + ')\n'
            + '[Experimentar o preview da mesma fonte](' + plan['preview']['pages_url'] + ')\n\n'
            + 'Israel (`israelhudson`) revisa a candidata e publica um comentário novo contendo somente um dos comandos:\n\n'
            + '```text\n' + approve + '\n```\n\n'
            + 'Para revogar, publique outro comentário novo:\n\n'
            + '```text\n' + revoke + '\n```\n\n'
            + 'O último comando válido de Israel decide. Comentários editados não autorizam a promoção. '
              'Depois da aprovação, Israel executa manualmente a Action de promoção. '
              'Este controle consulta comentários atualmente visíveis; não recupera decisões apagadas. '
              'Para revogar, use um novo comentário e preserve o histórico.\n\n'
            + 'A promoção preserva a tag, o SHA, o registro GitHub e os quatro arquivos publicados; '
              'não recompila nem distribui o app. As duas aprovações antigas de Samuel/Vinícius '
              'continuam simuladas, com 0 reviews reais de PR. '
              'Esta revisão por comentário é real e independente dessas simulações. '
              'Distribuição mobile: **false**; sem Shorebird, loja ou TestFlight.\n')


def real_user(value, owner):
    return (isinstance(value, dict) and value.get('type') == 'User'
            and value.get('login') == owner['login'] and type(value.get('id')) is int
            and value['id'] == owner['id'])


def timestamp(value):
    if not isinstance(value, str):
        raise ReleaseError('Data da revisão GitHub inválida.')
    try:
        parsed = datetime.fromisoformat(value.replace('Z', '+00:00'))
        if parsed.tzinfo is None:
            raise ValueError()
        return parsed
    except ValueError:
        raise ReleaseError('Data da revisão GitHub inválida.') from None


def read_review(api, number, plan, owner):
    if type(number) is not int or number <= 0:
        raise ReleaseError('Informe o número inteiro positivo da issue de revisão.')
    issue = api('GET', BASE + '/issues/' + str(number))
    expected_url = URL + '/issues/' + str(number)
    if (issue.get('number') != number or type(issue.get('id')) is not int or issue['id'] <= 0
            or issue.get('html_url') != expected_url or issue.get('state') != 'open'
            or 'pull_request' in issue or not real_user(issue.get('user'), owner)
            or not any(real_user(user, owner) for user in issue.get('assignees', []))
            or issue.get('title') != issue_title(plan) or issue.get('body') != issue_body(plan)):
        raise ReleaseError('Issue de revisão não corresponde ao proprietário/candidata/hash/destino exatos.')
    issue_updated = timestamp(issue.get('updated_at'))
    timestamp(issue.get('created_at'))
    approve, revoke = commands(plan)
    seen, decisive = set(), []
    for page in range(1, 11):
        comments = api('GET', BASE + '/issues/' + str(number) + '/comments?per_page=100&page=' + str(page))
        if not isinstance(comments, list):
            raise ReleaseError('Lista de comentários GitHub inválida.')
        for comment in comments:
            comment_id = comment.get('id')
            if type(comment_id) is not int or comment_id <= 0 or comment_id in seen:
                raise ReleaseError('Comentários com IDs inválidos/duplicados; não presumir aprovação.')
            seen.add(comment_id)
            # Simulation annotations and bot/user identity mismatches never count.
            if (not real_user(comment.get('user'), owner)
                    or any(comment.get(key) for key in ('simulation', 'simulated', 'is_simulated', 'simulated_role'))
                    or comment.get('mode') in ('lab', 'laboratory', 'simulation', 'simulated')):
                continue
            body = comment.get('body')
            created = timestamp(comment.get('created_at'))
            updated = timestamp(comment.get('updated_at'))
            if (comment.get('html_url') != expected_url + '#issuecomment-' + str(comment_id)
                    or created > updated or updated > issue_updated):
                raise ReleaseError('Comentário não corresponde à identidade/data da issue de revisão.')
            edited = comment['created_at'] != comment['updated_at']
            if not edited and (not isinstance(body, str) or body.strip() not in (approve, revoke)):
                continue
            # An edited decisive command invalidates earlier approvals, rather
            # than silently falling back to an old approval or counting edits.
            # The current API cannot show the original text. Treat every newer
            # edited owner comment as invalidation until a fresh approval exists.
            status = ('edited' if edited
                      else 'approved' if body.strip() == approve else 'revoked')
            decisive.append({'status': status, 'comment_id': comment_id,
                             'comment_url': comment['html_url'], 'created_at': comment['created_at'],
                             'updated_at': comment['updated_at']})
        if len(comments) < 100:
            break
    else:
        raise ReleaseError('Paginação de comentários excede limite; revisão bloqueada.')
    chosen = (max(decisive, key=lambda c: (timestamp(c['updated_at']), c['comment_id']))
              if decisive else {'status': 'awaiting_review'})
    snapshot = {'issue_id': issue['id'], 'issue_number': number, 'issue_url': expected_url,
                'issue_updated_at': issue['updated_at'], 'issue_body_sha256': release.sha256(issue['body'].encode()),
                'reviewer': {'login': owner['login'], 'id': owner['id'], 'identity_source': 'github_issue_comment'},
                **chosen}
    return snapshot


def approval_receipt(review):
    if review['status'] != 'approved':
        raise ReleaseError('Promoção exige novo comentário de aprovação real e não editado de Israel.')
    return {key: review[key] for key in ('issue_id', 'issue_number', 'issue_url', 'reviewer',
                                        'comment_id', 'comment_url', 'created_at', 'updated_at')}


def promotion_receipt(plan, review, original, tag_sha, assets):
    record = {'schema': SCHEMA, 'mode': 'laboratory', 'production_target': TARGET,
              'distribution_performed': False, 'candidate_id': plan['candidate_id'],
              'tag': plan['tag'], 'source_sha': plan['source_sha'], 'version': plan['version'],
              'manifest_hash': plan['manifest_hash'], 'release_identity': plan['release_identity'],
              'release_id': original['id'], 'tag_sha': tag_sha,
              'approval': approval_receipt(review), 'real_issue_review_count': 1,
              'real_pr_review_count': 0, 'historical_simulated_approval_count': 2,
              'assets': [{'name': name, 'id': asset['id'], 'size': asset['size'], 'digest': asset['digest']}
                         for name, asset in sorted(assets.items())]}
    return {**record, 'promotion_identity': digest(record)}


def promoted_body(plan, receipt):
    return (release.release_body(plan)
            + '\n---\n\nO registro acima preserva o histórico da candidata. '
              'Esta mesma release foi **promovida à versão estável do GitHub LAB**, '
              'após revisão real de Israel, mantendo fonte, tag e arquivos.\n\n'
            + '[Revisão real da promoção](' + receipt['approval']['comment_url'] + ')\n\n'
            + 'Destino: `' + TARGET + '`. Distribuição mobile: **false**. '
              'Esta revisão é um comentário autenticado; **0 reviews reais de PR**.\n\n'
            + '<!-- ' + SCHEMA + ' ' + canonical(receipt) + ' -->\n')


def validate_promoted(value, plan, receipt):
    if (value.get('id') != receipt['release_id'] or value.get('tag_name') != plan['tag']
            or value.get('draft') is not False or value.get('prerelease') is not False
            or value.get('name') != '[LAB · ESTÁVEL] ' + plan['version'] + ' · ' + plan['tag']
            or value.get('body') != promoted_body(plan, receipt)
            or value.get('html_url') != URL + '/releases/tag/' + plan['tag']):
        raise ReleaseError('Release promovida tem outra identidade/conteúdo; nenhuma alteração permitida.')


def frozen_release(api, plan, spec, assets):
    release.tag_protection(api)
    tag_sha = release.verify_tag(api, spec, required=True)
    original = release.find_release(api, plan['tag'])
    if original is None or original.get('draft') is not False:
        raise ReleaseError('Promoção exige a candidata já publicada; não cria nem publica drafts.')
    found = release.assets_on_release(api, original, assets)
    if set(found) != set(assets):
        raise ReleaseError('Candidata publicada incompleta; promoção bloqueada.')
    if original.get('prerelease') is True:
        release.validate_release(original, plan)
        if original.get('html_url') != URL + '/releases/tag/' + plan['tag']:
            raise ReleaseError('URL da candidata diverge da identidade congelada.')
    elif original.get('prerelease') is not False:
        raise ReleaseError('Estado da candidata GitHub inválido.')
    return original, tag_sha, found


def asset_snapshot(found):
    return {name: {key: asset.get(key) for key in ('id', 'name', 'size', 'digest', 'state')}
            for name, asset in found.items()}


def release_snapshot(value):
    return {key: value.get(key) for key in ('id', 'tag_name', 'name', 'body', 'draft', 'prerelease', 'html_url')}


def confirm_assets(api, original, expected, assets):
    found = release.assets_on_release(api, original, assets)
    if asset_snapshot(found) != asset_snapshot(expected):
        raise ReleaseError('IDs/conteúdo dos arquivos publicados mudaram; promoção bloqueada.')


def existing_receipt(value, plan, review, tag_sha, found, owner):
    marker = '<!-- ' + SCHEMA + ' '
    body = value.get('body', '')
    if not isinstance(body, str) or body.count(marker) != 1 or not body.endswith(' -->\n'):
        raise ReleaseError('Recibo da promoção existente ausente/inválido.')
    try:
        receipt = json.loads(body.rsplit(marker, 1)[1][:-5])
        approval = receipt['approval']
        if (set(approval) != {'issue_id', 'issue_number', 'issue_url', 'reviewer', 'comment_id', 'comment_url',
                             'created_at', 'updated_at'}
                or approval['issue_id'] != review['issue_id'] or approval['issue_number'] != review['issue_number']
                or approval['issue_url'] != review['issue_url']
                or approval['reviewer'] != {'login': owner['login'], 'id': owner['id'], 'identity_source': 'github_issue_comment'}
                or type(approval['comment_id']) is not int or approval['comment_id'] <= 0
                or approval['comment_url'] != review['issue_url'] + '#issuecomment-' + str(approval['comment_id'])
                or approval['created_at'] != approval['updated_at']):
            raise ValueError()
        timestamp(approval['created_at'])
        historical = {**review, 'status': 'approved', **approval}
        expected = promotion_receipt(plan, historical, value, tag_sha, found)
        if receipt != expected:
            raise ValueError()
    except (TypeError, KeyError, ValueError):
        raise ReleaseError('Recibo da promoção existente diverge da fonte/revisão/arquivos.') from None
    validate_promoted(value, plan, receipt)
    return receipt


def run(action, candidate, manifest_hash, review_issue, output, environment=None, *, api=gh_api, remote=None):
    audit = Audit(output)
    try:
        if action not in ('plan', 'promote') or not re.fullmatch(r'entrega-\d{4,}-rc\.[1-9]\d*', candidate or ''):
            raise ReleaseError('Ação/candidata inválida para promoção GitHub LAB.')
        if not re.fullmatch(r'[0-9a-f]{64}', manifest_hash or ''):
            raise ReleaseError('Informe SHA-256 completo do manifesto congelado.')
        owner = authenticate(environment or os.environ, api)
        audit.event('owner_authenticated', actor_id=owner['id'], login=owner['login'], run_id=owner['run_id'])

        def readonly(method, path, data=None):
            if method != 'GET' or data is not None:
                raise ReleaseError('Estado remoto é somente leitura na promoção.')
            return api(method, path)

        remote = remote or RemoteState(api=readonly)
        with tempfile.TemporaryDirectory(prefix='github-lab-promote-state-') as folder:
            loaded = remote.load(Path(folder) / 'state')
            manifest, preview = release.read_candidate(loaded, candidate, manifest_hash)
            plan, spec, assets = release.prepare_plan(manifest, preview, owner, loaded.head_sha, api, output)
            audit.event('candidate_verified', candidate_id=candidate, manifest_hash=manifest_hash,
                        source_sha=plan['source_sha'], state_head=loaded.head_sha, simulated_count=2)
        original, tag_sha, found = frozen_release(api, plan, spec, assets)
        review = read_review(api, review_issue, plan, owner)
        audit.event('review_verified', review_issue=review_issue, approval_status=review['status'],
                    reviewer_id=owner['id'], comment_id=review.get('comment_id'))
        approved = review['status'] == 'approved'
        receipt = promotion_receipt(plan, review, original, tag_sha, found) if approved else None
        if original['prerelease'] is False:
            historical = existing_receipt(original, plan, review, tag_sha, found, owner)
            if action == 'promote' and (not approved or receipt != historical):
                raise ReleaseError('Promoção existente não corresponde à aprovação atual; histórico preservado.')
            receipt = historical
        plan.update(promotion_schema=SCHEMA, production_target=TARGET,
                    review=review, release_id=original['id'], tag_sha=tag_sha,
                    already_promoted=original['prerelease'] is False,
                    promotion_identity=receipt['promotion_identity'] if receipt else None,
                    real_issue_review_count=1 if approved else 0, real_pr_review_count=0,
                    historical_promotion_approval=receipt['approval'] if original['prerelease'] is False else None)
        release.atomic_json(Path(output) / 'plan.json', plan)
        result = {'schema': SCHEMA, 'action': action, 'candidate_id': candidate, 'tag': candidate,
                  'version': plan['version'], 'source_sha': plan['source_sha'], 'manifest_hash': manifest_hash,
                  'release_identity': plan['release_identity'], 'release_id': original['id'],
                  'review_issue': review_issue, 'review_issue_url': review['issue_url'],
                  'approval_status': review['status'], 'approval_comment_id': review.get('comment_id'),
                  'real_issue_review_count': 1 if approved else 0, 'real_pr_review_count': 0,
                  'historical_simulated_approval_count': 2, 'production_target': TARGET,
                  'distribution_performed': False, 'promoted': False,
                  'release_url': URL + '/releases/tag/' + candidate,
                  'already_promoted': original['prerelease'] is False,
                  'status': 'ready' if approved else 'awaiting_review'}
        audit.checkpoint(release_identity=plan['release_identity'], release_id=original['id'],
                         status=result['status'], promoted=False, review_issue=review_issue)
        audit.event('promotion_plan_ready', release_id=original['id'], status=result['status'])
        if action == 'promote':
            if not approved or receipt is None:
                raise ReleaseError('Promoção exige aprovação real atual de Israel; consulte a issue.')
            # Every gate is read again immediately before the only remote write.
            with tempfile.TemporaryDirectory(prefix='github-lab-promote-recheck-') as folder:
                current = remote.load(Path(folder) / 'state')
                release.read_candidate(current, candidate, manifest_hash)
            fresh, fresh_tag, fresh_assets = frozen_release(api, plan, spec, assets)
            if (fresh_tag != tag_sha or asset_snapshot(fresh_assets) != asset_snapshot(found)
                    or release_snapshot(fresh) != release_snapshot(original)):
                raise ReleaseError('Tag/release/arquivos mudaram antes da promoção; efeito bloqueado.')
            fresh_review = read_review(api, review_issue, plan, owner)
            if fresh_review != review:
                raise ReleaseError('Revisão/issue mudou antes da promoção; execute um novo plano.')
            audit.event('promotion_gates_rechecked', release_id=original['id'], review_issue=review_issue,
                        comment_id=review['comment_id'], reviewer_id=owner['id'], tag_sha=tag_sha,
                        state_head=current.head_sha)
            if original['prerelease']:
                release.mutation(audit, plan['release_identity'], 'promote_release',
                    lambda: api('PATCH', BASE + '/releases/' + str(original['id']), {
                        'prerelease': False, 'name': '[LAB · ESTÁVEL] ' + plan['version'] + ' · ' + plan['tag'],
                        'body': promoted_body(plan, receipt), 'make_latest': 'false'}),
                    release_id=original['id'], review_issue=review_issue, comment_id=review['comment_id'],
                    promotion_identity=receipt['promotion_identity'])
            final = api('GET', BASE + '/releases/' + str(original['id']))
            validate_promoted(final, plan, receipt)
            confirm_assets(api, final, found, assets)
            if release.verify_tag(api, spec, required=True) != tag_sha:
                raise ReleaseError('Tag mudou após o efeito; confirmação bloqueada.')
            release.atomic_json(Path(output) / 'promotion-receipt.json', receipt)
            result.update(status='promoted', promoted=True, promotion_identity=receipt['promotion_identity'])
            audit.checkpoint(release_identity=plan['release_identity'], release_id=original['id'], status='promoted',
                             promoted=True, promotion_identity=receipt['promotion_identity'], review_issue=review_issue,
                             comment_id=review['comment_id'], reviewer_id=owner['id'])
            audit.event('promotion_confirmed', release_id=original['id'], promoted=True,
                        promotion_identity=receipt['promotion_identity'], review_issue=review_issue,
                        comment_id=review['comment_id'], reviewer_id=owner['id'])
        release.atomic_json(Path(output) / 'result.json', result)
        return result
    except Exception as error:
        reason = str(error) if isinstance(error, ReleaseError) else 'Falha de verificação/API; conteúdo omitido.'
        audit.event('failed', status='failed', error_type=type(error).__name__, reason=reason,
                    http_status=error.status if isinstance(error, GitDataAPIError) else None)
        release.atomic_json(Path(output) / 'result.json', {'schema': SCHEMA, 'status': 'failed',
                            'promoted': False, 'distribution_performed': False, 'error_type': type(error).__name__})
        if isinstance(error, ReleaseError):
            raise
        raise ReleaseError('Verificação da promoção falhou; consulte os logs permitidos.') from None


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--action', choices=('plan', 'promote'), default='plan')
    parser.add_argument('--candidate', required=True)
    parser.add_argument('--manifest-hash', required=True)
    parser.add_argument('--review-issue', type=int, required=True)
    parser.add_argument('--output', required=True)
    args = parser.parse_args()
    try:
        result = run(args.action, args.candidate, args.manifest_hash, args.review_issue, args.output)
    except ReleaseError as error:
        print(str(error), file=sys.stderr); return 1
    print(json.dumps(result, ensure_ascii=False, indent=2)); return 0


if __name__ == '__main__':
    raise SystemExit(main())
