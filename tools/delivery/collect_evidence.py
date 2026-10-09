"""Collect read-only GitHub run evidence without overwriting previous captures."""
import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import re
import subprocess
import sys

REPOSITORY = 'israelhudson/flutter_code_push_example'


def request(path, raw=False):
    command = ['gh', 'api', '--method', 'GET', path]
    if raw:
        command.append('--allow-escape-sequences')
    return subprocess.run(command, capture_output=True, timeout=60)


def collect(run_id, output, repository=REPOSITORY, requester=request):
    run_id = str(run_id)
    if not re.fullmatch(r'[1-9]\d*', run_id) or repository != REPOSITORY:
        raise ValueError('Execução ou repositório inválido para este laboratório.')
    output = Path(output)
    # A capture is one immutable observation, even when some requests fail.
    output.mkdir(parents=True, exist_ok=False)
    captures = []

    def save(name, endpoint, raw=False):
        try:
            response = requester(endpoint, raw)
            stdout, stderr, code = response.stdout, response.stderr, response.returncode
        except (OSError, subprocess.TimeoutExpired) as error:
            stdout, stderr, code = b'', (type(error).__name__ + '\n').encode(), 124
        (output / (name + ('.log' if raw else '.json'))).write_bytes(stdout)
        (output / (name + '.stderr')).write_bytes(stderr)
        item = {'name': name, 'endpoint': endpoint, 'exit_code': code,
                'stdout_bytes': len(stdout), 'stderr_bytes': len(stderr),
                'stdout_sha256': hashlib.sha256(stdout).hexdigest(),
                'status': 'collected' if code == 0 else 'collection_failed'}
        captures.append(item)
        if raw or code:
            return None
        try:
            return json.loads(stdout)
        except (ValueError, UnicodeError):
            item['status'] = 'invalid_json'
            return None

    base = 'repos/' + repository + '/actions/runs/' + run_id
    run = save('run', base)
    if isinstance(run, dict) and str(run.get('id')) != run_id:
        raise ValueError('Resposta não corresponde à execução solicitada; coleta preservada.')
    save('reviews', base + '/approvals')
    jobs = []
    page = 1
    while True:
        result = save('jobs-page-' + str(page), base + '/jobs?filter=all&per_page=100&page=' + str(page))
        if not isinstance(result, dict) or not isinstance(result.get('jobs'), list):
            break
        entries = result['jobs']
        jobs.extend(entries)
        if len(entries) < 100:
            break
        page += 1
        if page > 100:
            raise ValueError('Paginação excede o limite do coletor; coleta preservada.')
    logs = []
    seen = set()
    for job in jobs:
        job_id = str(job.get('id', ''))
        if not re.fullmatch(r'[1-9]\d*', job_id) or job_id in seen:
            raise ValueError('Identidade de job inválida ou duplicada; coleta preservada.')
        seen.add(job_id)
        item = {'job_id': job_id, 'name': job.get('name'),
                'run_attempt': job.get('run_attempt'), 'conclusion': job.get('conclusion')}
        if job.get('conclusion') == 'skipped':
            item['log_status'] = 'not_applicable_skipped'
        elif job.get('status') != 'completed':
            item['log_status'] = 'pending_job'
        else:
            save('job-' + job_id, 'repos/' + repository + '/actions/jobs/' + job_id + '/logs', raw=True)
            item['log_status'] = captures[-1]['status']
            # Some rejected gates never start a runner and have no logs.
            # An unavailable log remains an explicit gap, even if rejection
            # itself was expected. Do not reinterpret the collection as PASS.
        logs.append(item)
    partial = any(c['status'] != 'collected' for c in captures)
    pending = any(j['log_status'] == 'pending_job' for j in logs)
    summary = {'schema': 1, 'collected_at': datetime.now(timezone.utc).isoformat(),
               'repository': repository, 'run_id': run_id,
               'run_status': run.get('status') if isinstance(run, dict) else None,
               'run_conclusion': run.get('conclusion') if isinstance(run, dict) else None,
               'run_attempt': run.get('run_attempt') if isinstance(run, dict) else None,
               'collection_status': 'partial' if partial else 'pending' if pending else 'complete',
               'requests': captures, 'jobs': logs,
               'read_only': True, 'scenario_result': 'not_evaluated',
               'note': 'Coleta não transforma falha do workflow em teste aprovado; comparar efeitos e objetivo separadamente.'}
    (output / 'collection-summary.json').write_text(json.dumps(summary, ensure_ascii=False, indent=2) + '\n')
    return summary


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--run-id', required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args(argv)
    try:
        summary = collect(args.run_id, args.output)
    except (ValueError, OSError) as error:
        print(str(error), file=sys.stderr)
        return 1
    print(json.dumps({k: summary[k] for k in ('run_id', 'run_conclusion', 'collection_status')}, ensure_ascii=False))
    return 2 if summary['collection_status'] == 'partial' else 0


if __name__ == '__main__':
    raise SystemExit(main())
