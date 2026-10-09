"""Derive current read-only audit facts from immutable laboratory captures."""
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import re

ROOT = Path(__file__).resolve().parent / 'live-evidence'


def raw_lines(data):
    return len(data.splitlines())


def load(path):
    return json.loads(path.read_bytes())


def normalize_slack(text):
    text = text.replace('\\/', '/')
    return re.sub(r'\\u([0-9a-fA-F]{4})', lambda match: chr(int(match.group(1), 16)), text)


def summarize():
    report = {'schema': 1, 'generated_at': datetime.now(timezone.utc).isoformat(),
              'scope': 'current_capture_audit_only', 'read_only_sources': True,
              'line_count_method': 'len(raw_bytes.splitlines())', 'runs': [],
              'candidate_observations': {}, 'slack_notifications': [], 'gaps': []}
    for summary_path in sorted(ROOT.rglob('collection-summary.json')):
        summary = load(summary_path)
        folder = summary_path.parent
        logs = []
        failures = []
        for request in summary['requests']:
            extension = '.log' if request['name'].startswith('job-') else '.json'
            stdout = (folder / (request['name'] + extension)).read_bytes()
            stderr = (folder / (request['name'] + '.stderr')).read_bytes()
            assert len(stdout) == request['stdout_bytes']
            assert len(stderr) == request['stderr_bytes']
            assert hashlib.sha256(stdout).hexdigest() == request['stdout_sha256']
            if request['status'] != 'collected':
                failures.append({'name': request['name'], 'exit_code': request['exit_code'],
                                 'stdout_bytes': len(stdout), 'stderr_bytes': len(stderr),
                                 'source': str((folder / (request['name'] + extension)).relative_to(ROOT))})
            elif request['name'].startswith('job-'):
                logs.append({'job_id': request['name'][4:], 'bytes': len(stdout),
                             'lines': raw_lines(stdout), 'sha256': request['stdout_sha256']})
        report['runs'].append({'run_id': summary['run_id'], 'status': summary['run_status'],
                               'conclusion': summary['run_conclusion'],
                               'collection_status': summary['collection_status'],
                               'jobs': len(summary['jobs']), 'logs_collected': len(logs),
                               'log_bytes': sum(x['bytes'] for x in logs),
                               'log_lines': sum(x['lines'] for x in logs),
                               'skipped_jobs': sum(x['log_status'] == 'not_applicable_skipped' for x in summary['jobs']),
                               'failed_log_responses': failures, 'logs': logs,
                               'summary_source': str(summary_path.relative_to(ROOT))})
        if failures:
            report['gaps'].append({'kind': 'raw_log_collection_partial', 'run_id': summary['run_id'],
                                   'failed_requests': len(failures), 'source': str(summary_path.relative_to(ROOT)),
                                   'scenario_result_not_reclassified': True})
    for path in sorted(ROOT.rglob('state.snapshot.json')):
        state = load(path)
        for tag, candidate in state['candidates'].items():
            if tag not in ['v1.7.0-rc.1', 'v1.8.0-rc.1', 'v1.8.0-rc.2']:
                continue
            observed = {'status': candidate['status'], 'source_sha': candidate['source_sha'],
                        'run_id': candidate['evaluation_run_id'], 'report_digest': candidate.get('report_digest'),
                        'approval_progress': candidate.get('approval_progress'),
                        'source': str(path.relative_to(ROOT))}
            report['candidate_observations'].setdefault(tag, []).append(observed)
    for tag, observations in report['candidate_observations'].items():
        assert len({x['source_sha'] for x in observations}) == 1, f'Candidate source changed: {tag}'
        digests = {x['report_digest'] for x in observations if x['report_digest'] is not None}
        assert len(digests) <= 1, f'Frozen candidate report changed: {tag}'
    slack_messages = {}
    for path in sorted(ROOT.rglob('slack*.json')):
        payload = load(path)
        tool_result = payload.get('tool_result', {})
        for content in tool_result.get('content', []):
            if content.get('type') != 'text':
                continue
            parsed = json.loads(content['text'])
            text = normalize_slack(parsed.get('messages', ''))
            for section in text.split('=== Message from ')[1:]:
                match = re.search(r'Message TS: (\d+\.\d+)', section)
                if not match:
                    continue
                ts = match.group(1)
                if 'U0C750FTCS3' not in section.split('Message TS:')[0]:
                    continue
                slack_messages.setdefault(ts, {'text': section, 'sources': []})['sources'].append(str(path.relative_to(ROOT)))
    sent = {}
    for path in sorted(ROOT.rglob('outbox.snapshot.json')):
        for event in load(path).get('events', []):
            if event['state'] != 'sent' or event['identity']['candidate_tag'] not in ['v1.7.0-rc.1', 'v1.8.0-rc.1', 'v1.8.0-rc.2']:
                continue
            receipt = event['receipt']
            key = event['event_key']
            if key in sent:
                assert sent[key]['receipt']['ts'] == receipt['ts']
                assert sent[key]['receipt']['channel'] == receipt['channel']
                continue
            sent[key] = event
    for key, event in sorted(sent.items(), key=lambda item: float(item[1]['receipt']['ts'])):
        receipt = event['receipt']
        identity = event['identity']
        match = slack_messages.get(receipt['ts'])
        confirmed = bool(match and identity['candidate_tag'] in match['text'] and
                         identity['run_id'] in match['text'] and identity['source_sha'] in match['text'])
        report['slack_notifications'].append({'event': key.split(':')[0],
                                               'candidate_tag': identity['candidate_tag'],
                                               'run_id': identity['run_id'], 'source_sha': identity['source_sha'],
                                               'snapshot_digest': identity['snapshot_digest'],
                                               'channel': receipt['channel'], 'ts': receipt['ts'],
                                               'at': event['at'], 'receipt_state': 'sent',
                                               'independent_channel_read_confirmed': confirmed,
                                               'channel_read_sources': match['sources'] if match else [],
                                               'url': 'https://app.slack.com/archives/' + receipt['channel'] + '/p' + receipt['ts'].replace('.', '')})
        if not confirmed:
            report['gaps'].append({'kind': 'sent_receipt_without_matching_independent_read',
                                   'event_key': key, 'ts': receipt['ts']})
    for path in sorted(ROOT.rglob('capture-summary.json')):
        summary = load(path)
        if summary.get('status') == 'collection_timeout':
            report['gaps'].append({'kind': 'additional_local_http_collection_timeout',
                                   'source': str(path.relative_to(ROOT)),
                                   'timeout_seconds': summary['timeout_seconds'],
                                   'workflow_preview_result_preserved_separately': True})
    report['totals'] = {'runs_collected': len(report['runs']),
                         'real_job_logs': sum(x['logs_collected'] for x in report['runs']),
                         'real_job_log_bytes': sum(x['log_bytes'] for x in report['runs']),
                         'real_job_log_lines': sum(x['log_lines'] for x in report['runs']),
                         'sent_events_in_outbox': len(report['slack_notifications']),
                         'independent_notifications_confirmed': sum(x['independent_channel_read_confirmed'] for x in report['slack_notifications'])}
    (ROOT / 'audit-current.json').write_text(json.dumps(report, ensure_ascii=False, indent=2) + '\n')
    print(json.dumps(report['totals'], ensure_ascii=False, indent=2))
    print(json.dumps(report['gaps'], ensure_ascii=False, indent=2))


if __name__ == '__main__':
    summarize()
