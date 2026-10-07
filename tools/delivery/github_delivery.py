"""GitHub-only delivery laboratory. This program cannot distribute mobile apps.

Uses gh's existing auth; never creates credentials or invites reviewers.
The production publication path consumes live GitHub reviews, never fixtures.
"""
import argparse
import base64
from datetime import datetime
import hashlib
import io
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import tempfile
from urllib.parse import quote
import zipfile
from zoneinfo import ZoneInfo

from policy import (CONTEXT, LEDGER, REPO, REQUIRED, assert_record_change,
                    canonical, decide, digest, preview_usable)
from preview import fingerprint, git

BASE = f'repos/{REPO}'
URL = f'https://github.com/{REPO}'
LEGACY_TAG_PATTERN = r'lab/delivery/\d{4}-\d{2}-\d{2}-rc\.[1-9]\d*'
DELIVERY_PATTERN = r'entrega-\d{4,}'
NEUTRAL_TAG_PATTERN = DELIVERY_PATTERN + r'-rc\.[1-9]\d*'
TAG_PATTERN = f'(?:{LEGACY_TAG_PATTERN}|{NEUTRAL_TAG_PATTERN})'
TAG_RULE_PATTERNS = {'legacy': 'refs/tags/lab/delivery/**',
                     'neutral': 'refs/tags/entrega-*-rc.*'}


def assert_exact_sha(sha):
    if not re.fullmatch(r'[0-9a-f]{40}', sha or '') or git('rev-parse', sha) != sha:
        raise ValueError('Informe o SHA completo exato.')


def is_ancestor(previous, sha):
    return subprocess.run(['git', 'merge-base', '--is-ancestor', previous, sha],
                          capture_output=True).returncode == 0


def assert_tag_protection(neutral=False):
    """Fail closed before mutations; an existing legacy rule does not cover RCs
    in the neutral namespace. Never add bypasses or edit rules here.
    """
    pattern = TAG_RULE_PATTERNS['neutral' if neutral else 'legacy']
    rules = [api(f'{BASE}/rulesets/{r["id"]}') for r in api(f'{BASE}/rulesets')]
    if not any(r.get('target') == 'tag' and r.get('enforcement') == 'active'
               and not r.get('bypass_actors')
               and pattern in r.get('conditions', {}).get('ref_name', {}).get('include', [])
               and not r.get('conditions', {}).get('ref_name', {}).get('exclude', [])
               and {'update', 'deletion'} <= {rule['type'] for rule in r.get('rules', [])}
               for r in rules):
        raise ValueError('Proteção das tags RC ausente; configure o namespace do laboratório primeiro.')


def record_path(tag):
    return 'delivery/candidates/' + tag.replace('/', '-') + '.json'


def api(path, data=None, method=None):
    args = ['gh', 'api', path, '-H', 'Accept: application/vnd.github+json']
    if method or data is not None:
        args += ['--method', method or 'POST']
    if data is not None:
        args += ['--input', '-']
    result = subprocess.run(args, input=None if data is None else canonical(data).encode(),
                            stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    if result.returncode:
        raise RuntimeError(result.stderr.decode().strip() + ' ' + result.stdout.decode().strip())
    return json.loads(result.stdout) if result.stdout else None


def pages(path, key=None):
    values = []
    for page in range(1, 1001):
        data = api(path + ('&' if '?' in path else '?') + f'per_page=100&page={page}')
        batch = data[key] if key else data
        values.extend(batch)
        if len(batch) < 100:
            return values
    raise ValueError('Paginação excedeu limite; falha fechada.')


def content(path, ref):
    data = api(f'{BASE}/contents/{quote(path, safe="/")}?ref={quote(ref, safe="")}')
    return base64.b64decode(data['content']).decode()


def artifact_data(artifact_id):
    artifact = api(f'{BASE}/actions/artifacts/{int(artifact_id)}')
    if artifact['expired']:
        raise ValueError('Preview expirado. Crie nova candidata; não substitua a aprovada.')
    archive = subprocess.check_output(['gh', 'api', f'{BASE}/actions/artifacts/{int(artifact_id)}/zip'])
    with zipfile.ZipFile(io.BytesIO(archive)) as z:
        if sorted(z.namelist()) != ['metadata.json', 'preview.zip']:
            raise ValueError('Conteúdo inesperado no artefato.')
        metadata = json.loads(z.read('metadata.json'))
        web_zip = z.read('preview.zip')
    if hashlib.sha256(web_zip).hexdigest() != metadata['sha256']:
        raise ValueError('Hash do preview não confere.')
    run = api(f'{BASE}/actions/runs/{artifact["workflow_run"]["id"]}')
    if run['conclusion'] != 'success' or run['repository']['full_name'] != REPO:
        raise ValueError('Preview sem execução bem-sucedida deste repositório.')
    if run['path'] not in ('.github/workflows/delivery-preview.yml',
                           '.github/workflows/delivery-candidate.yml'):
        raise ValueError('Workflow de preview não autorizado.')
    return artifact, metadata, web_zip, run


def find_preview(sha):
    expected = fingerprint(sha)
    pulls = pages(f'{BASE}/commits/{sha}/pulls')
    heads = {p['head']['sha'] for p in pulls if p['merged_at']
             and p['merge_commit_sha'] == sha and p['base']['ref'] == 'main'
             and p['head']['repo'] and p['head']['repo']['full_name'] == REPO}
    for run in pages(f'{BASE}/actions/workflows/delivery-preview.yml/runs?event=pull_request&status=success', 'workflow_runs'):
        if run['head_sha'] not in heads:
            continue
        for a in pages(f'{BASE}/actions/runs/{run["id"]}/artifacts', 'artifacts'):
            if not a['name'].startswith('web-preview-') or a['expired']:
                continue
            _, metadata, _, _ = artifact_data(a['id'])
            if preview_usable(metadata, expected, a):
                return a['id']
    return None


def record_body(record, decision=None):
    decision = decision or {'count': 0, 'approved': []}
    status = 'COMANDO FINAL LIBERADO NO LABORATÓRIO' if decision['count'] == 2 else 'PUBLICAÇÃO BLOQUEADA'
    rows = '\n'.join(f'| {name} (`{login}`) | {"Aprovou" if login in decision["approved"] else "Aguardando"} |'
                     for name, login in [('Samuel', REQUIRED[0]), ('Vinicius', REQUIRED[1])])
    changes = '\n'.join(f'- `{c["sha"][:12]}` {c["subject"].replace("@", "＠")}' for c in record['changes'])
    return f'''# {status} — {decision['count']}/2

## Versão {record['tag']}

**LABORATÓRIO · SEM DISTRIBUIÇÃO DO APP**

Este PR aprova a **versão**, depois da revisão do código. Não substitui o PR de código por Ian.

| Responsável | Aprovação desta versão |
|---|---|
{rows}

## O que será validado

{changes or '- Sem alteração de código desde a baseline declarada.'}

[Comparar todo o conteúdo]({record['compare_url']}) · [SHA exato]({URL}/commit/{record['source_sha']})

## Experimentar o preview web

[Baixar preview fixo desta candidata]({record['preview']['url']})

O GitHub entrega um ZIP privado, não uma página hospedada. Extraia o download e depois `preview.zip`;
nessa pasta execute `python3 -m http.server 8080` e abra http://localhost:8080.
O artefato vence em **{record['preview']['expires_at']}**. Preview expirado bloqueia a publicação;
uma nova candidata precisa ser criada e aprovada. Nenhum deploy do app é feito.

## Identidade da versão

- Tag RC: `{record['tag']}` (protegida contra alteração e exclusão).
- Código exato: `{record['source_sha']}`.
- Snapshot: todos os arquivos versionados desse commit; a tag permanece fixa.
- Baseline do changelog: `{record['previous_sha']}`. Não é calculada pela RC anterior.
- Base mobile declarada no projeto: **{record['mobile_base']}** (sem consulta de disponibilidade no Shorebird).
- Patch iOS: **a gerar**. Patch Android: **a gerar**. Os números podem ser diferentes.
- Preview: **{record['preview']['origin']}**; SHA-256 `{record['preview']['sha256']}`.
- Modo: **{record['mode']}**.

## Como aprovar e publicar

1. Leia as mudanças e experimente o preview.
2. Samuel e Vinicius usam **Files changed → Review changes → Approve** neste PR.
3. Com as duas aprovações válidas, o responsável pode usar **Merge pull request**.
4. As duas aprovações apenas liberam o comando final. O responsável executa manualmente
   **Actions → Publicar agora → Run workflow**, com `action=publish` e o número deste PR.
5. Esse comando revalida as aprovações e cria somente uma **GitHub pre-release de laboratório**.

O botão tem o nome nativo do GitHub; não é um botão customizado “Publicar”.
As revisões são vinculadas ao commit do registro. Alterações exigem novas aprovações.
Não foram enviados pedidos de review, menções notificáveis, convites ou avisos no Slack.
'''


def create_candidate(sha, artifact_id, demo=False, delivery_id=None, previous_sha=None):
    """Prepare an immutable source/preview record; never publish on approval.

    Neutral deliveries require an explicit baseline from the last completed
    delivery. The caller must supply its source SHA, never the last RC's SHA.
    Existing release branches only advance to descendants, without force push.
    """
    assert_exact_sha(sha)
    neutral = delivery_id is not None
    if neutral and not re.fullmatch(DELIVERY_PATTERN, delivery_id):
        raise ValueError('delivery_id deve ter o formato entrega-0042.')
    if neutral and not previous_sha:
        raise ValueError('Declare --previous-sha da última entrega concluída; não use a RC anterior.')
    if previous_sha:
        assert_exact_sha(previous_sha)
        if not is_ancestor(previous_sha, sha):
            raise ValueError('Baseline precisa ser ancestral do snapshot candidato.')
    release_branch = f'release/{delivery_id}' if neutral else None
    release_ref = None
    if release_branch:
        release_ref = next((r for r in pages(f'{BASE}/git/matching-refs/heads/{release_branch}')
                            if r['ref'] == 'refs/heads/' + release_branch), None)
        if release_ref and not is_ancestor(release_ref['object']['sha'], sha):
            raise ValueError('Nova RC precisa descender da branch release; não reescreva seu histórico.')
    if not demo and not release_ref:
        main_sha = api(f'{BASE}/git/ref/heads/main')['object']['sha']
        comparison = api(f'{BASE}/compare/{sha}...{main_sha}')
        if comparison['status'] not in ('ahead', 'identical'):
            raise ValueError('A primeira RC precisa pertencer ao histórico integrado da main.')
    artifact, metadata, _, _ = artifact_data(artifact_id)
    if not preview_usable(metadata, fingerprint(sha), artifact):
        raise ValueError('Preview divergente ou expirado.')
    # The branch endpoint is readable by GITHUB_TOKEN. The /protection endpoint
    # needs administration permission, which the workflow deliberately lacks.
    if not api(f'{BASE}/branches/{LEDGER}')['protected']:
        raise ValueError('Branch de versões sem proteção; configure o laboratório.')
    assert_tag_protection(neutral)
    ledger = api(f'{BASE}/git/ref/heads/{LEDGER}')['object']['sha']
    tags = pages(f'{BASE}/git/matching-refs/tags/{delivery_id if neutral else "lab/delivery/"}')
    # A retry of the same source is a no-op only while its record/PR already exists.
    open_candidates = []
    for p in pages(f'{BASE}/pulls?state=all&base={quote(LEDGER, safe="")}'):
        if p['head']['ref'].startswith('codex/candidate-'):
            files = pages(f'{BASE}/pulls/{p["number"]}/files')
            if len(files) == 1 and files[0]['filename'].startswith('delivery/candidates/'):
                old = json.loads(content(files[0]['filename'], p['head']['sha']))
                if (old['source_sha'] == sha and old['preview']['artifact_id'] == int(artifact_id)
                        and (not neutral or old.get('delivery_id') == delivery_id)
                        and (previous_sha is None or old.get('previous_sha') == previous_sha)):
                    print(p['html_url'])
                    return p
                if p.get('state') == 'open':
                    open_candidates.append(p['html_url'])
    if neutral and open_candidates:
        raise ValueError('Outra RC está aberta. Encerre a candidata antiga antes de preparar uma nova: '
                         + ', '.join(open_candidates))
    date = datetime.now(ZoneInfo('America/Fortaleza')).date().isoformat()
    prefix = f'{delivery_id}-rc.' if neutral else f'lab/delivery/{date}-rc.'
    sequence = 1 + max([int(t['ref'].rsplit('.', 1)[1]) for t in tags
                         if re.fullmatch('refs/tags/' + re.escape(prefix) + r'[1-9]\d*', t['ref'])] or [0])
    tag = prefix + str(sequence)
    previous = previous_sha or git('rev-list', '--max-parents=0', sha).splitlines()[0]
    raw = git('log', '--reverse', '--format=%H%x09%s', f'{previous}..{sha}')
    record = {'schema': 1, 'repository': REPO, 'tag': tag, 'source_sha': sha,
              'source_tree': git('rev-parse', f'{sha}^{{tree}}'),
              'mobile_base': re.search(r'^version:\s*(\S+)', git('show', f'{sha}:pubspec.yaml'), re.M)[1],
              'patches': {'ios': None, 'android': None}, 'approvers': list(REQUIRED),
              'mode': ('demo-before-main-merge' if demo else
                       'release-snapshot-dry-run' if neutral else 'post-main-merge-dry-run'),
              'previous_sha': previous, 'compare_url': f'{URL}/compare/{previous}...{sha}',
              'baseline': {'source_sha': previous,
                           'mode': 'explicit' if previous_sha else 'repository-root'},
              'changes': [dict(zip(('sha', 'subject'), line.split('\t', 1))) for line in raw.splitlines()],
              'preview': {'artifact_id': int(artifact_id), 'fingerprint': metadata['fingerprint'],
                          'sha256': metadata['sha256'], 'expires_at': artifact['expires_at'],
                          'url': f'{URL}/actions/runs/{artifact["workflow_run"]["id"]}/artifacts/{artifact_id}',
                          'origin': 'build do PR reutilizado' if metadata['source_sha'] != sha else 'build do SHA candidato'}}
    if neutral:
        record.update({'delivery_id': delivery_id, 'release_branch': release_branch})
    # All protection, snapshot, baseline and preview checks precede mutations.
    # A branch is a mutable workspace. Only the annotated tag/record authorizes
    # publication; later main/release heads are never substituted for this SHA.
    if release_branch and not release_ref:
        api(f'{BASE}/git/refs', {'ref': 'refs/heads/' + release_branch, 'sha': sha})
    elif release_ref and release_ref['object']['sha'] != sha:
        api(f'{BASE}/git/refs/heads/{release_branch}', {'sha': sha, 'force': False}, 'PATCH')
    # Immutable annotated tag binds the source AND the complete review record.
    tag_object = api(f'{BASE}/git/tags', {'tag': tag, 'message': 'LAB ONLY manifest-sha256:' + digest(record),
                                        'object': sha, 'type': 'commit'})
    api(f'{BASE}/git/refs', {'ref': 'refs/tags/' + tag, 'sha': tag_object['sha']})
    path = record_path(tag)
    blob = api(f'{BASE}/git/blobs', {'content': json.dumps(record, ensure_ascii=False, indent=2) + '\n', 'encoding': 'utf-8'})
    tree = api(f'{BASE}/git/trees', {'base_tree': api(f'{BASE}/git/commits/{ledger}')['tree']['sha'],
                                   'tree': [{'path': path, 'mode': '100644', 'type': 'blob', 'sha': blob['sha']}]})
    commit = api(f'{BASE}/git/commits', {'message': f'lab: review {tag}', 'tree': tree['sha'], 'parents': [ledger]})
    branch = 'codex/candidate-' + tag.replace('/', '-')
    api(f'{BASE}/git/refs', {'ref': 'refs/heads/' + branch, 'sha': commit['sha']})
    pr = api(f'{BASE}/pulls', {'title': f'[LAB] Aprovar versão {tag}', 'head': branch,
                              'base': LEDGER, 'body': record_body(record)})
    print(pr['html_url'])
    return pr


def inspect(number):
    pr = api(f'{BASE}/pulls/{int(number)}')
    if pr['base']['ref'] != LEDGER or not pr['head']['ref'].startswith('codex/candidate-'):
        raise ValueError('Este não é um PR de versão do laboratório.')
    if pr['head']['repo']['full_name'] != REPO:
        raise ValueError('Registro de fork não permitido.')
    files = pages(f'{BASE}/pulls/{number}/files')
    path_pattern = (r'delivery/candidates/(?:lab-delivery-\d{4}-\d{2}-\d{2}'
                    r'|entrega-\d{4,})-rc\.[1-9]\d*\.json')
    if len(files) != 1 or not re.fullmatch(path_pattern, files[0]['filename']):
        raise ValueError('Caminho de manifesto inválido.')
    assert_record_change(files, files[0]['filename'])
    record = json.loads(content(files[0]['filename'], pr['head']['sha']))
    if (not re.fullmatch(TAG_PATTERN, record['tag']) or record['repository'] != REPO
            or record['approvers'] != list(REQUIRED) or record['patches'] != {'ios': None, 'android': None}):
        raise ValueError('Identidade ou política do manifesto inválida.')
    if files[0]['filename'] != record_path(record['tag']):
        raise ValueError('Caminho e tag não correspondem.')
    neutral = bool(re.fullmatch(NEUTRAL_TAG_PATTERN, record['tag']))
    if neutral and (record.get('delivery_id') != record['tag'].rsplit('-rc.', 1)[0]
                    or record.get('release_branch') != 'release/' + record['delivery_id']
                    or record.get('baseline') != {'source_sha': record['previous_sha'], 'mode': 'explicit'}):
        raise ValueError('Identidade da entrega ou baseline explícita inválida.')
    assert_tag_protection(neutral)
    tag_ref = api(f'{BASE}/git/ref/tags/{record["tag"]}')['object']
    if tag_ref['type'] != 'tag':
        raise ValueError('Tag anotada obrigatória.')
    tag = api(f'{BASE}/git/tags/{tag_ref["sha"]}')
    if tag['object']['sha'] != record['source_sha'] or tag['message'].strip() != 'LAB ONLY manifest-sha256:' + digest(record):
        raise ValueError('SHA/tag/manifesto foi alterado; aprovação inválida.')
    artifact, metadata, _, _ = artifact_data(record['preview']['artifact_id'])
    if (not preview_usable(metadata, record['preview']['fingerprint'], artifact)
            or metadata['sha256'] != record['preview']['sha256']):
        raise ValueError('Preview divergente ou expirado; nova candidata necessária.')
    reviews = pages(f'{BASE}/pulls/{number}/reviews')
    result = decide(reviews, pr['head']['sha'], pr['user']['login'])
    return pr, record, result


def gate(number):
    pr = api(f'{BASE}/pulls/{int(number)}')
    try:
        pr, record, result = inspect(number)
        description = f'{result["count"]}/2 aprovações válidas; ' + ('liberado' if result['allowed'] else 'bloqueado')
        state = 'success' if result['allowed'] else 'failure'
        summary = record_body(record, result)
    except (ValueError, RuntimeError, KeyError, TypeError) as error:
        state, description, summary = 'failure', 'Registro inválido ou preview indisponível', str(error)
    # A pending/failed check prevents merging; the publisher independently checks again.
    api(f'{BASE}/statuses/{pr["head"]["sha"]}', {'state': state, 'context': CONTEXT,
        'description': description, 'target_url': pr['html_url']})
    print(summary)
    if os.environ.get('GITHUB_STEP_SUMMARY'):
        with open(os.environ['GITHUB_STEP_SUMMARY'], 'a') as f:
            f.write(summary)
    return state == 'success'


def assert_current_rc(record):
    if not re.fullmatch(NEUTRAL_TAG_PATTERN, record['tag']):
        return
    prefix, sequence = record['tag'].rsplit('-rc.', 1)
    tags = pages(f'{BASE}/git/matching-refs/tags/{prefix}-rc.')
    if any(re.fullmatch('refs/tags/' + re.escape(prefix) + r'-rc\.[1-9]\d*', t['ref'])
           and int(t['ref'].rsplit('.', 1)[1]) > int(sequence) for t in tags):
        raise ValueError('RC obsoleta: outra candidata da entrega existe; novas aprovações são necessárias.')


def publish(number):
    pr, record, result = inspect(number)
    if not pr['merged'] or not result['allowed']:
        raise ValueError(f'PUBLICAÇÃO BLOQUEADA: {result["count"]}/2; PR precisa estar aprovado e integrado ao registro.')
    assert_current_rc(record)
    # One last fresh review/head read immediately before any release mutation.
    current = api(f'{BASE}/pulls/{number}')
    if current['head']['sha'] != pr['head']['sha'] or not decide(
            pages(f'{BASE}/pulls/{number}/reviews'), current['head']['sha'], current['user']['login'])['allowed']:
        raise ValueError('As aprovações mudaram; publicação cancelada.')
    existing = [r for r in pages(f'{BASE}/releases') if r['tag_name'] == record['tag']]
    if existing:
        raise ValueError('Release já existe; não alterar nem publicar novamente automaticamente.')
    artifact, metadata, web_zip, _ = artifact_data(record['preview']['artifact_id'])
    # These are the only publication operations: a GitHub LAB pre-release and assets.
    release = api(f'{BASE}/releases', {'tag_name': record['tag'], 'name': '[LAB · DRY-RUN] ' + record['tag'],
        'body': record_body(record, result) + '\n\nAprovação registrada em ' + pr['html_url'],
        'draft': True, 'prerelease': True, 'make_latest': 'false'})
    with tempfile.TemporaryDirectory() as folder:
        p = Path(folder)
        (p / 'preview.zip').write_bytes(web_zip)
        (p / 'candidate.json').write_text(json.dumps(record, indent=2))
        (p / 'receipt.json').write_text(json.dumps({'dry_run': True, 'distribution_performed': False,
            'source_sha': record['source_sha'], 'record_sha': pr['head']['sha'],
            'approved_by': result['approved'], 'patches': record['patches'], 'version_pr': pr['html_url']}, indent=2))
        subprocess.run(['gh', 'release', 'upload', record['tag'], *map(str, p.iterdir()), '--repo', REPO], check=True)
    # No Shorebird, store, Pages, cloud host or deployment endpoint exists here.
    final_pr, final_record, final_result = inspect(number)
    if (not final_pr['merged'] or not final_result['allowed']
            or final_pr['head']['sha'] != pr['head']['sha'] or final_record != record):
        raise ValueError('Estado mudou durante upload. Draft não publicado; revisar recuperação manual.')
    assert_current_rc(record)
    release = api(f'{BASE}/releases/{release["id"]}', {'draft': False, 'make_latest': 'false'}, 'PATCH')
    print(release['html_url'])


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest='command', required=True)
    find = sub.add_parser('find-preview'); find.add_argument('--sha', required=True)
    create = sub.add_parser('candidate')
    create.add_argument('--sha', required=True); create.add_argument('--artifact', required=True, type=int)
    create.add_argument('--demo-before-merge', action='store_true')
    create.add_argument('--delivery-id', help='Identidade neutra da entrega, por exemplo entrega-0042')
    create.add_argument('--previous-sha', help='SHA completo da última entrega concluída; primeira execução declara a baseline')
    for name in ('gate', 'publish'):
        p = sub.add_parser(name); p.add_argument('--pr', type=int, required=True)
    args = parser.parse_args()
    if args.command == 'find-preview':
        found = find_preview(args.sha)
        with open(os.environ.get('GITHUB_OUTPUT', os.devnull), 'a') as f:
            f.write('artifact=' + (str(found) if found else '') + '\n')
        print(found or 'Preview não reutilizável; build necessário.')
    elif args.command == 'candidate':
        create_candidate(args.sha, args.artifact, args.demo_before_merge,
                         delivery_id=args.delivery_id, previous_sha=args.previous_sha)
    elif args.command == 'gate':
        sys.exit(0 if gate(args.pr) else 1)
    else:
        publish(args.pr)


if __name__ == '__main__':
    main()
