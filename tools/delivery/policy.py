"""Pure delivery policy. GitHub reviews are data, never an approval boolean input."""
import hashlib
import json
from datetime import datetime, timezone

REQUIRED = ('samuelcamilo', 'friasvinicius')
REPO = 'israelhudson/flutter_code_push_example'
LEDGER = 'codex/lab-versions'
CONTEXT = 'delivery / Samuel + Vinicius'


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(',', ':'), ensure_ascii=False)


def digest(value):
    return hashlib.sha256(canonical(value).encode()).hexdigest()


def decide(reviews, head_sha, author):
    """Latest decisive review per identity; comments do not revoke an approval.

    A dismissed review supersedes an earlier approval. Reviews of an older head
    do not authorize the current record. The candidate manifest is in that head.
    """
    latest = {}
    for review in sorted(reviews, key=lambda r: (r.get('submitted_at') or '', r['id'])):
        # A lab role event must never become a live GitHub identity approval,
        # even if its payload contains one of the required usernames.
        if (review.get('simulation') or review.get('simulated')
                or review.get('is_simulated') or review.get('simulated_role')
                or review.get('mode') in ('lab', 'laboratory', 'simulation', 'simulated')):
            continue
        login = review['user']['login'].lower()
        if login not in REQUIRED or review['state'] not in (
                'APPROVED', 'CHANGES_REQUESTED', 'DISMISSED'):
            continue
        latest[login] = review
    approved = [login for login in REQUIRED if login != author.lower()
                and latest.get(login, {}).get('state') == 'APPROVED'
                and latest[login].get('commit_id') == head_sha]
    return {'allowed': len(approved) == len(REQUIRED), 'approved': approved,
            'missing': [login for login in REQUIRED if login not in approved],
            'count': len(approved), 'required': len(REQUIRED)}


def preview_usable(metadata, expected_fingerprint, artifact, now=None):
    now = now or datetime.now(timezone.utc)
    return (metadata.get('fingerprint') == expected_fingerprint
            and not artifact.get('expired', True)
            and datetime.fromisoformat(artifact['expires_at'].replace('Z', '+00:00')) > now)


def assert_record_change(files, path):
    if len(files) != 1 or files[0]['filename'] != path or files[0]['status'] != 'added':
        raise ValueError('O PR de versão deve adicionar somente um manifesto novo.')
