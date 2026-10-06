"""Create only isolated lab refs and their protections; never changes main/access."""
import argparse
from github_delivery import BASE, api, git
from policy import CONTEXT, LEDGER

TAG_RULE_NAME = 'Laboratorio - RC imutavel'


def configure(seed):
    sha = git('rev-parse', seed)
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
    existing = [r for r in api(f'{BASE}/rulesets') if r['name'] == TAG_RULE_NAME]
    expected = {'name': TAG_RULE_NAME, 'target': 'tag', 'enforcement': 'active', 'bypass_actors': [],
                'conditions': {'ref_name': {'include': ['refs/tags/lab/delivery/**'], 'exclude': []}},
                'rules': [{'type': 'update'}, {'type': 'deletion'}]}
    if not existing:
        api(f'{BASE}/rulesets', expected)
    else:
        current = api(f'{BASE}/rulesets/{existing[0]["id"]}')
        if any(current.get(k) != v for k, v in expected.items()):
            raise ValueError('Ruleset existente diferente do esperado; revisar sem sobrescrever.')
    print('Laboratório protegido: 2 reviews, status obrigatório, admins incluídos; RC sem update/delete.')
    print('main e permissões de pessoas/Actions não foram alteradas.')


if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--seed', required=True, help='Commit já enviado da implementação revisável')
    configure(p.parse_args().seed)
