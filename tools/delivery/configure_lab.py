"""Create only isolated lab refs and their protections; never changes main/access."""
import argparse
from github_delivery import BASE, TAG_RULE_PATTERNS, api, git
from policy import CONTEXT, LEDGER

TAG_RULE_NAME = 'Laboratorio - RC imutavel'
NEUTRAL_TAG_RULE_NAME = 'Laboratorio - entrega RC imutavel'


def tag_rule(name, pattern):
    return {'name': name, 'target': 'tag', 'enforcement': 'active', 'bypass_actors': [],
            'conditions': {'ref_name': {'include': [pattern], 'exclude': []}},
            'rules': [{'type': 'update'}, {'type': 'deletion'}]}


def configure(seed):
    sha = git('rev-parse', seed)
    # Add the neutral namespace separately. Never broaden, replace or weaken an
    # existing rule, including the legacy RC rule. Inspect every rule before any
    # mutation so a conflicting setup leaves the remote unchanged.
    expected_rules = [tag_rule(TAG_RULE_NAME, TAG_RULE_PATTERNS['legacy']),
                      tag_rule(NEUTRAL_TAG_RULE_NAME, TAG_RULE_PATTERNS['neutral'])]
    existing = api(f'{BASE}/rulesets')
    missing = []
    for expected in expected_rules:
        matching = [r for r in existing if r['name'] == expected['name']]
        if len(matching) > 1:
            raise ValueError('Rulesets duplicados; revisar sem sobrescrever.')
        if not matching:
            missing.append(expected)
            continue
        current = api(f'{BASE}/rulesets/{matching[0]["id"]}')
        if any(current.get(k) != v for k, v in expected.items()):
            raise ValueError('Ruleset existente diferente do esperado; revisar sem sobrescrever.')
    for expected in missing:
        api(f'{BASE}/rulesets', expected)
    refs = api(f'{BASE}/git/matching-refs/heads/{LEDGER}')
    if not any(r['ref'] == 'refs/heads/' + LEDGER for r in refs):
        api(f'{BASE}/git/refs', {'ref': 'refs/heads/' + LEDGER, 'sha': sha})
    api(f'{BASE}/branches/{LEDGER}/protection', {
        'required_status_checks': {'strict': False, 'contexts': [CONTEXT]},
        'enforce_admins': True,
        'required_pull_request_reviews': {'dismiss_stale_reviews': True,
            'require_code_owner_reviews': False, 'required_approving_review_count': 2},
        'restrictions': None, 'allow_force_pushes': False, 'allow_deletions': False,
        'required_conversation_resolution': True}, 'PUT')
    print('Laboratório protegido: 2 reviews, status obrigatório, admins incluídos; RC legado e neutro sem update/delete.')
    print('main e permissões de pessoas/Actions não foram alteradas.')


if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--seed', required=True, help='Commit já enviado da implementação revisável')
    configure(p.parse_args().seed)
