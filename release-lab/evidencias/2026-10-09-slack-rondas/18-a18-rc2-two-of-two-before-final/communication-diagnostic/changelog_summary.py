"""Freeze review communication without contacting an AI or waiting for one.

Descriptions are source material, never instructions. The optional auxiliary
collector can save PR/task text before review. Delivery may use that snapshot,
or its own commit history immediately. No function here changes an approval,
version, destination, report on disk, or publication state.
"""
import argparse
from copy import deepcopy
from datetime import datetime, timezone
import hashlib
import io
import json
from pathlib import Path, PurePosixPath
import re
import subprocess
import sys
import time
import unicodedata
from urllib.parse import urlsplit
import zipfile


TAG = re.compile(r'v\d+\.\d+\.\d+-rc\.[1-9]\d*')
SHA = re.compile(r'[0-9a-f]{40}')
SUMMARY_LIMIT = 1400
REPOSITORY = 'israelhudson/flutter_code_push_example'


def digest(value):
    canonical = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(',', ':'))
    return hashlib.sha256(canonical.encode()).hexdigest()


def timestamp(value=None):
    value = value or datetime.now(timezone.utc).isoformat(timespec='microseconds')
    if not isinstance(value, str):
        raise ValueError('Instante inválido.')
    try:
        parsed = datetime.fromisoformat(value.replace('Z', '+00:00'))
    except ValueError as error:
        raise ValueError('Instante inválido.') from error
    if parsed.tzinfo is None:
        raise ValueError('Instante deve incluir o fuso.')
    return parsed.astimezone(timezone.utc).isoformat(timespec='microseconds')


def text(value, maximum, multiline=False):
    if not isinstance(value, str) or len(value) > maximum:
        raise ValueError('Texto ausente ou muito grande.')
    allowed = '\n\t' if multiline else ''
    if any(unicodedata.category(char) == 'Cc' and char not in allowed for char in value):
        raise ValueError('Texto contém controle inválido.')
    return value.strip()


def normalized_changes(changes):
    """Bound notification copies; full original history remains in the report."""
    if not isinstance(changes, list) or any(not isinstance(item, str) for item in changes):
        raise ValueError('Histórico de commits inválido.')
    bounded, truncated = [], len(changes) > 1000
    for item in changes[:1000]:
        clean = ''.join(char if unicodedata.category(char) != 'Cc' else ' ' for char in item).strip()
        if len(clean) > 500:
            clean = clean[:497] + '…'
            truncated = True
        bounded.append(clean or '(mensagem de commit vazia)')
    return bounded, truncated


def identity(report):
    tag, sha, base = (report.get(key, '') for key in ('candidate_tag', 'source_sha', 'changelog_base_sha'))
    if (any(not isinstance(item, str) for item in (tag, sha, base))
            or not TAG.fullmatch(tag) or not SHA.fullmatch(sha) or not SHA.fullmatch(base)):
        raise ValueError('Identidade da candidata ou base inválida.')
    return tag, sha, base


def freeze_context(report, sources=None, collected_at=None):
    """Copy bounded source descriptions; later edits do not change this input."""
    tag, sha, base = identity(report)
    original_changes = report.get('changes')
    changes, truncated = normalized_changes(original_changes)
    items = []
    for source in sources or []:
        if len(items) >= 30 or not isinstance(source, dict):
            raise ValueError('Fontes inválidas ou excessivas.')
        kind = source.get('kind')
        if kind not in ('pr', 'task'):
            raise ValueError('Tipo de fonte inválido.')
        source_id = text(source.get('id'), 100)
        url = text(source.get('url'), 1200)
        parsed = urlsplit(url)
        if (not source_id or parsed.scheme != 'https' or not parsed.hostname
                or parsed.username or parsed.password or parsed.query or parsed.fragment):
            raise ValueError('Identificador/URL da fonte inválido.')
        items.append({'kind': kind, 'id': source_id, 'url': url,
                      'title': text(source.get('title', ''), 300),
                      'body': text(source.get('body', ''), 12000, multiline=True)})
    if len({item['id'] for item in items}) != len(items):
        raise ValueError('Fonte duplicada.')
    value = {'schema': 1, 'candidate_tag': tag, 'source_sha': sha,
             'changelog_base_sha': base, 'changes': changes,
             'source_history_sha256': digest(original_changes),
             'commit_count': len(original_changes), 'history_truncated': truncated,
             'sources': items, 'collected_at': timestamp(collected_at)}
    return {**value, 'context_sha256': digest(value)}


def verified_context(report, context):
    tag, sha, base = identity(report)
    if not isinstance(context, dict):
        raise ValueError('Formato do contexto inválido.')
    payload = {key: value for key, value in context.items() if key != 'context_sha256'}
    if context.get('context_sha256') != digest(payload):
        raise ValueError('Hash do contexto divergente.')
    if (context.get('candidate_tag') != tag or context.get('source_sha') != sha
            or context.get('changelog_base_sha') != base
            or context.get('source_history_sha256') != digest(report.get('changes'))):
        raise ValueError('Contexto pertence a outra candidata/intervalo.')
    # Reapply limits/schema checks to an independently supplied snapshot.
    expected = freeze_context(report, context.get('sources'), context.get('collected_at'))
    if expected != context:
        raise ValueError('Formato do contexto inválido.')
    return deepcopy(context)


def normalize_heading(value):
    value = unicodedata.normalize('NFKD', value.lower())
    return ''.join(char for char in value if not unicodedata.combining(char)).strip(' :')


def explicit_sections(context):
    """Use literal PR sections, without deriving claims from technical titles."""
    names = {'o que muda para o usuario': 'O que muda',
             'o que muda para quem usa': 'O que muda',
             'como validar': 'Como validar', 'limitacoes': 'Limitações'}
    sections = []
    for source in context['sources']:
        if source['kind'] != 'pr':
            continue
        found, active = {}, None
        for line in source['body'].splitlines():
            heading = re.match(r'^\s{0,3}#{1,6}\s+(.+?)\s*#*\s*$', line)
            if heading:
                active = names.get(normalize_heading(heading.group(1)))
                if active:
                    found.setdefault(active, [])
            elif active and line.strip():
                found[active].append(line.strip())
        change = ' '.join(found.get('O que muda', []))
        if not change or len(change) > 600 or re.search(r'(?i)\b(TODO|TBD)\b|<!--|-->', change):
            continue
        sections.append('PR ' + source['id'] + ' — O que muda: ' + change)
        for label in ('Como validar', 'Limitações'):
            content = ' '.join(found.get(label, []))
            if content and len(content) <= 350:
                sections.append(label + ': ' + content)
    result = '\n'.join(sections)
    # A partial concatenation must not drop a limitation of the selected PR.
    return result if len(result) <= SUMMARY_LIMIT else ''


def commits_fallback(context):
    rows = context['changes']
    lines, size = [], 0
    for row in rows[:8]:
        if size + len(row) + 3 > SUMMARY_LIMIT - 70:
            break
        lines.append('• ' + row)
        size += len(row) + 3
    if len(lines) < context['commit_count'] or context['history_truncated']:
        lines.append('• Histórico completo no relatório da execução.')
    return '\n'.join(lines) or '• Sem commits adicionais desde a base registrada.'


def select_summary(context, optional_result=None, selected_at=None):
    """Select once, immediately. A late/invalid result remains only evidence."""
    selected_at = timestamp(selected_at)
    if selected_at < context['collected_at']:
        raise ValueError('A seleção não pode anteceder a coleta das fontes.')
    result_status, fallback_reason = 'not_configured', 'ai_not_configured'
    chosen, source = '', 'commits_fallback'
    result_hash = None
    if optional_result is None:
        chosen = explicit_sections(context)
        if chosen:
            source, fallback_reason = 'pr_sections', None
    else:
        result_hash = digest(optional_result)
        try:
            state = optional_result.get('status')
            if state != 'completed':
                result_status = state if state in ('disabled', 'failed', 'timeout', 'no_access', 'no_credits', 'running') else 'invalid_result'
                fallback_reason = 'ai_' + result_status
            elif any(optional_result.get(key) != context.get(key)
                     for key in ('candidate_tag', 'source_sha', 'context_sha256')):
                result_status, fallback_reason = 'identity_mismatch', 'ai_identity_mismatch'
            elif not optional_result.get('finished_at'):
                result_status, fallback_reason = 'invalid_result', 'ai_invalid_result'
            elif timestamp(optional_result.get('finished_at')) > selected_at:
                result_status, fallback_reason = 'late_result', 'ai_late_result'
            elif timestamp(optional_result.get('finished_at')) < context['collected_at']:
                result_status, fallback_reason = 'invalid_result', 'ai_invalid_result'
            else:
                content = text(optional_result.get('text'), SUMMARY_LIMIT, multiline=True)
                ids = optional_result.get('source_ids')
                valid_ids = {'commits', *(item['id'] for item in context['sources'])}
                if (not content or not isinstance(ids, list) or not ids
                        or not all(isinstance(item, str) and item in valid_ids for item in ids)
                        or any(not text(optional_result.get(key), 100)
                               for key in ('provider', 'model', 'prompt_revision'))):
                    raise ValueError('Resultado IA incompleto.')
                chosen, source = content, 'ai'
                result_status, fallback_reason = 'selected', None
        except (AttributeError, ValueError, TypeError):
            result_status, fallback_reason = 'invalid_result', 'ai_invalid_result'
    if not chosen:
        chosen = commits_fallback(context)
    value = {'schema': 1, 'candidate_tag': context['candidate_tag'],
             'source_sha': context['source_sha'], 'context_sha256': context['context_sha256'],
             'source': source, 'text': chosen, 'fallback_reason': fallback_reason,
             'selected_at': selected_at, 'optional_result_status': result_status,
             'optional_result_sha256': result_hash}
    if source == 'ai':
        value['ai'] = {key: optional_result[key]
                       for key in ('provider', 'model', 'prompt_revision', 'source_ids', 'finished_at')}
    return {**value, 'selected_sha256': digest(value)}


def frozen_communication(report, *, context=None, optional_result=None, selected_at=None):
    context = (verified_context(report, context) if context is not None
               else freeze_context(report, collected_at=selected_at))
    selection = select_summary(context, optional_result, selected_at)
    return {'schema': 1, 'context': context, 'selection': selection}


def verify_communication(report):
    """Verify already frozen content. Never regenerate it with newer sources."""
    communication = report.get('communication')
    if not isinstance(communication, dict) or communication.get('schema') != 1:
        raise ValueError('Comunicação congelada ausente.')
    context = verified_context(report, communication.get('context', {}))
    selection = communication.get('selection', {})
    payload = {key: value for key, value in selection.items() if key != 'selected_sha256'}
    if (selection.get('selected_sha256') != digest(payload)
            or any(selection.get(key) != context.get(key)
                   for key in ('candidate_tag', 'source_sha', 'context_sha256'))
            or selection.get('source') not in ('ai', 'pr_sections', 'commits_fallback')
            or not text(selection.get('text'), SUMMARY_LIMIT, multiline=True)):
        raise ValueError('Material selecionado divergente.')
    timestamp(selection.get('selected_at'))
    return deepcopy(selection)


def collect_pr_context(candidate, repo, *, api_budget_seconds=20, maximum_commits=12):
    """Optional reader: no candidate code execution and no publication API.

    Run only in the auxiliary workflow. Missing/slow PR APIs preserve the exact
    local commit fallback. The candidate source and base must already exist in
    the trusted collector's Git database; this function never fetches or writes.
    """
    tag, sha, base = identity(candidate)
    repo = Path(repo).resolve()
    changes = subprocess.check_output(['git', '-C', str(repo), 'log', '--format=%s',
                                       base + '..' + sha], text=True, timeout=5).splitlines()
    report = {'candidate_tag': tag, 'source_sha': sha, 'changelog_base_sha': base, 'changes': changes}
    commits = subprocess.check_output(['git', '-C', str(repo), 'log', '--format=%H',
                                       base + '..' + sha], text=True, timeout=5).splitlines()
    sources, seen, errors = [], set(), []
    deadline = time.monotonic() + api_budget_seconds
    for commit in commits[:maximum_commits]:
        if not SHA.fullmatch(commit):
            raise ValueError('Git devolveu identidade de commit inválida.')
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            errors.append('pr_collection_budget_exceeded')
            break
        try:
            completed = subprocess.run(['gh', 'api', 'repos/' + REPOSITORY + '/commits/' + commit + '/pulls'],
                capture_output=True, text=True, check=True, timeout=min(3, remaining))
            pulls = json.loads(completed.stdout)
            if not isinstance(pulls, list):
                raise ValueError('Resposta de PR inválida.')
            for pull in pulls:
                # Associations can include an unmerged PR or another repo.
                # Only merged PRs with their merge commit in this exact range
                # can contribute literal product sections.
                number = pull.get('number')
                if (not pull.get('merged_at') or pull.get('merge_commit_sha') not in commits
                        or type(number) is not int or number < 1 or number in seen
                        or pull.get('base', {}).get('repo', {}).get('full_name') != REPOSITORY):
                    continue
                url = 'https://github.com/' + REPOSITORY + '/pull/' + str(number)
                item = {'kind': 'pr', 'id': str(number), 'url': url,
                        'title': pull.get('title') or '', 'body': pull.get('body') or ''}
                if len(item['body']) > 12000 or len(item['title']) > 300:
                    errors.append('pr_' + str(number) + '_oversized')
                    continue
                sources.append(item)
                seen.add(number)
        except (subprocess.SubprocessError, OSError, ValueError, TypeError, AttributeError):
            # Do not retain stderr: it could contain authentication details.
            errors.append('pr_context_unavailable_for_' + commit)
    if len(commits) > maximum_commits:
        errors.append('pr_commit_lookup_limit_reached')
    return report, freeze_context(report, sources), {'schema': 1, 'errors': errors,
        'provider_active': False, 'ai_requests': 0, 'tasks_collected': False,
        'collection_kind': 'merged_pr_descriptions', 'candidate_tag': tag, 'source_sha': sha}


def read_available_context(run_id, artifact_name='release-lab-context', budget_seconds=3):
    """One opportunistic read, with a shared short timeout; never poll or wait.

    An absent, malformed or slow artifact is a communication fallback. The
    caller still verifies the returned context against its own frozen RC/code.
    """
    observation = {'schema': 1, 'run_id': str(run_id), 'artifact_name': artifact_name,
                   'status': 'unavailable', 'provider_active': False}
    if (not re.fullmatch(r'[1-9]\d*', str(run_id)) or artifact_name != 'release-lab-context'
            or not 0 < budget_seconds <= 3):
        return None, {**observation, 'status': 'invalid_request'}
    deadline = time.monotonic() + budget_seconds
    maximum = 512 * 1024

    def fetch(path):
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            raise subprocess.TimeoutExpired(['gh', 'api'], budget_seconds)
        response = subprocess.run(['gh', 'api', 'repos/' + REPOSITORY + '/' + path],
                                  capture_output=True, check=True, timeout=remaining)
        if len(response.stdout) > maximum:
            raise ValueError('Resposta excessiva.')
        return response.stdout

    try:
        listing = json.loads(fetch('actions/runs/' + str(run_id) + '/artifacts?per_page=100'))
        if not isinstance(listing, dict) or not isinstance(listing.get('artifacts'), list):
            raise ValueError('Listagem inválida.')
        matches = [item for item in listing['artifacts'] if item.get('name') == artifact_name]
        if not matches:
            return None, {**observation, 'status': 'not_ready'}
        if len(matches) != 1:
            raise ValueError('Artefato ambíguo.')
        artifact = matches[0]
        artifact_id, size = artifact.get('id'), artifact.get('size_in_bytes')
        if (artifact.get('expired') is not False or type(artifact_id) is not int or artifact_id < 1
                or type(size) is not int or not 0 < size <= maximum
                or str(artifact.get('workflow_run', {}).get('id', run_id)) != str(run_id)):
            raise ValueError('Identidade/tamanho do artefato inválido.')
        raw = fetch('actions/artifacts/' + str(artifact_id) + '/zip')
        with zipfile.ZipFile(io.BytesIO(raw)) as archive:
            members = archive.infolist()
            if not members or len(members) > 10 or sum(item.file_size for item in members) > maximum:
                raise ValueError('Conteúdo do artefato excessivo.')
            targets = []
            for item in members:
                path = PurePosixPath(item.filename)
                if (path.is_absolute() or '..' in path.parts or '\\' in item.filename
                        or (item.external_attr >> 16) & 0o170000 == 0o120000
                        or (not item.is_dir() and path.name not in
                            ('context.json', 'communication.json', 'collection.json', 'communication.md'))):
                    raise ValueError('Caminho/symlink fora do contrato.')
                if path.name == 'context.json' and not item.is_dir():
                    targets.append(item)
            if len(targets) != 1:
                raise ValueError('Contexto ausente ou duplicado.')
            context = json.loads(archive.read(targets[0]))
            if not isinstance(context, dict):
                raise ValueError('Contexto inválido.')
        return context, {**observation, 'status': 'available', 'artifact_id': artifact_id,
                         'archive_sha256': hashlib.sha256(raw).hexdigest()}
    except subprocess.TimeoutExpired:
        return None, {**observation, 'status': 'timeout'}
    except (OSError, ValueError, TypeError, AttributeError, KeyError,
            subprocess.SubprocessError, zipfile.BadZipFile, RuntimeError):
        return None, {**observation, 'status': 'invalid_or_unavailable'}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    inputs = parser.add_mutually_exclusive_group(required=True)
    inputs.add_argument('--report', type=Path)
    inputs.add_argument('--collect-candidate', type=Path)
    parser.add_argument('--repo', type=Path, default=Path('.'))
    parser.add_argument('--sources', type=Path)
    parser.add_argument('--context', type=Path)
    parser.add_argument('--optional-result', type=Path)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args(argv)
    try:
        collection = None
        if args.collect_candidate:
            if args.sources or args.context or args.optional_result:
                raise ValueError('Coleta não combina fontes/resultados externos.')
            candidate = json.loads(args.collect_candidate.read_text())
            report, context, collection = collect_pr_context(candidate, args.repo)
        else:
            report = json.loads(args.report.read_text())
            context = json.loads(args.context.read_text()) if args.context else None
        if args.sources:
            if context:
                raise ValueError('Escolha fontes ou contexto previamente congelado.')
            context = freeze_context(report, json.loads(args.sources.read_text()))
        result = json.loads(args.optional_result.read_text()) if args.optional_result else None
        communication = frozen_communication(report, context=context, optional_result=result)
        args.output.mkdir(parents=True, exist_ok=True)
        (args.output / 'context.json').write_text(json.dumps(communication['context'], ensure_ascii=False, indent=2) + '\n')
        (args.output / 'communication.json').write_text(json.dumps(communication, ensure_ascii=False, indent=2) + '\n')
        (args.output / 'communication.md').write_text('Fonte: ' + communication['selection']['source'] + '\n\n' + communication['selection']['text'] + '\n')
        if collection is not None:
            (args.output / 'collection.json').write_text(json.dumps(collection, indent=2) + '\n')
        print('Material copiado e selecionado; nenhuma IA consultada e nenhum aviso enviado.')
        return 0
    except (ValueError, OSError, TypeError, KeyError, subprocess.SubprocessError):
        print('Comunicação não gerada: entrada inválida. Use commits da candidata; nenhum envio/IA.', file=sys.stderr)
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
