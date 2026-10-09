"""Immutable GET-only snapshots for the authorized Slack laboratory rounds."""
import argparse
import base64
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import re
import subprocess

REPO = 'israelhudson/flutter_code_push_example'
ROOT = Path(__file__).resolve().parent / 'live-evidence'


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--stage', required=True)
    parser.add_argument('--run-id', action='append', default=[])
    parser.add_argument('--tag', action='append', default=[])
    parser.add_argument('--pull', action='append', default=[])
    args = parser.parse_args()
    assert re.fullmatch(r'[a-z0-9-]+', args.stage)
    assert all(re.fullmatch(r'[1-9]\d*', value) for value in args.run_id + args.pull)
    assert all(re.fullmatch(r'v\d+\.\d+\.\d+(?:-rc\.\d+)?', value) for value in args.tag)
    folder = ROOT / args.stage
    folder.mkdir(parents=True, exist_ok=False)
    requests = []

    def get(name, endpoint):
        result = subprocess.run(['gh', 'api', '--method', 'GET', f'repos/{REPO}/{endpoint}'],
                                capture_output=True, timeout=60)
        (folder / (name + '.json')).write_bytes(result.stdout)
        (folder / (name + '.stderr')).write_bytes(result.stderr)
        requests.append({'name': name, 'method': 'GET', 'endpoint': endpoint,
                         'exit_code': result.returncode, 'stdout_bytes': len(result.stdout),
                         'stderr_bytes': len(result.stderr),
                         'stdout_sha256': hashlib.sha256(result.stdout).hexdigest(),
                         'stderr_sha256': hashlib.sha256(result.stderr).hexdigest()})
        if result.returncode:
            return None
        return json.loads(result.stdout)

    for number in args.pull:
        get('pr-' + number, 'pulls/' + number)
        get('pr-' + number + '-reviews', 'pulls/' + number + '/reviews')
    for run_id in args.run_id:
        get('run-' + run_id, 'actions/runs/' + run_id)
        get('run-' + run_id + '-jobs', 'actions/runs/' + run_id + '/jobs?filter=all&per_page=100')
        get('run-' + run_id + '-approvals', 'actions/runs/' + run_id + '/approvals')
        get('run-' + run_id + '-artifacts', 'actions/runs/' + run_id + '/artifacts?per_page=100')
    ref = get('state-branch-ref', 'git/ref/heads/codex/release-lab-state')
    assert ref, 'Cannot establish state snapshot identity'
    commit = get('state-branch-commit', 'git/commits/' + ref['object']['sha'])
    tree = get('state-branch-tree', 'git/trees/' + commit['tree']['sha'] + '?recursive=1')
    assert tree and not tree['truncated'], 'Cannot establish complete state tree'
    snapshots = []
    for entry in tree['tree']:
        if entry['type'] == 'blob' and entry['path'] in ['release-lab/state.json', 'release-lab/slack-outbox.json']:
            name = 'state' if entry['path'] == 'release-lab/state.json' else 'outbox'
            blob = get(name + '-blob', 'git/blobs/' + entry['sha'])
            assert blob and blob['encoding'] == 'base64'
            data = base64.b64decode(blob['content'])
            (folder / (name + '.snapshot.json')).write_bytes(data)
            json.loads(data)
            snapshots.append({'path': entry['path'], 'snapshot_file': name + '.snapshot.json',
                              'commit': ref['object']['sha'], 'git_blob_sha': entry['sha'],
                              'bytes': len(data), 'sha256': hashlib.sha256(data).hexdigest()})
    for tag in args.tag:
        get('tag-' + tag, 'git/ref/tags/' + tag)
        get('release-' + tag, 'releases/tags/' + tag)
    summary = {'schema': 1, 'stage': args.stage, 'captured_at': datetime.now(timezone.utc).isoformat(),
               'repository': REPO, 'read_only': True, 'state_observed_at_commit': ref['object']['sha'],
               'requests': requests, 'snapshots': snapshots,
               'note': 'A 404/missing release or raw failed run is an observation; determine scenario result separately.'}
    (folder / 'capture-summary.json').write_text(json.dumps(summary, ensure_ascii=False, indent=2) + '\n')
    print(json.dumps({'stage': args.stage, 'requests': len(requests), 'state_commit': ref['object']['sha']}, ensure_ascii=False), flush=True)


if __name__ == '__main__':
    main()
