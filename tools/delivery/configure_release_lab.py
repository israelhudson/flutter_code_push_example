"""Apply the reviewed public LAB policy; preserve old refs, Pages and history."""
import argparse
import json
from pathlib import Path
from release_lab import api, endpoint, environments, git, load_policy, now, output


def ruleset_matches(current, spec):
    """Accept only known safe server defaults; never rewrite a divergent rule."""
    normalized = json.loads(json.dumps(current))
    for rule in normalized.get('rules', []):
        if rule.get('type') == 'pull_request':
            parameters = rule.get('parameters', {})
            if parameters.get('required_reviewers') == []:
                parameters.pop('required_reviewers')
            if parameters.get('require_extra_approval_for_unattributed_changes') is True:
                parameters.pop('require_extra_approval_for_unattributed_changes')
    return all(normalized.get(key) == value for key, value in spec.items())


def configure(folder, protect_branches=False):
    policy = load_policy()
    audit = {'at': now(), 'repository': policy['repository'], 'changes': []}
    people = {p['environment']: [p] for p in policy['approvers']}
    people[policy['final_environment']] = policy['publishers']
    for name, reviewers in people.items():
        current = api(endpoint('environments/' + name))
        output(folder, name + '-before.json', current)
        data = {'wait_timer': 0, 'prevent_self_review': False,
                'reviewers': [{'type': 'User', 'id': p['id']} for p in reviewers],
                'can_admins_bypass': False,
                'deployment_branch_policy': {'protected_branches': False, 'custom_branch_policies': True}}
        api(endpoint('environments/' + name), data, 'PUT')
        existing = api(endpoint('environments/' + name + '/deployment-branch-policies'))['branch_policies']
        wanted = {('main', 'branch'), ('v*-rc.*', 'tag')}
        if any((r['name'], r['type']) not in wanted for r in existing):
            raise ValueError('Ref extra no ambiente; não apagar proteção sem revisão.')
        for pattern, kind in wanted - {(r['name'], r['type']) for r in existing}:
            api(endpoint('environments/' + name + '/deployment-branch-policies'), {'name': pattern, 'type': kind}, 'POST')
        audit['changes'].append({'environment': name, 'reviewer_ids': [p['id'] for p in reviewers]})
    # Add only the exact RC namespace to Pages, preserving every existing policy.
    page_rules = api(endpoint('environments/github-pages/deployment-branch-policies'))['branch_policies']
    if not any(r['name'] == 'v*-rc.*' and r['type'] == 'tag' for r in page_rules):
        api(endpoint('environments/github-pages/deployment-branch-policies'), {'name': 'v*-rc.*', 'type': 'tag'}, 'POST')
        audit['changes'].append({'environment': 'github-pages', 'added_ref': 'v*-rc.*'})
    expected = [
        {'name': 'LAB - novas RCs imutaveis', 'target': 'tag', 'enforcement': 'active', 'bypass_actors': [],
         'conditions': {'ref_name': {'include': ['refs/tags/v*-rc.*'], 'exclude': []}},
         'rules': [{'type': 'update'}, {'type': 'deletion'}]},
        {'name': 'LAB - journal append-only', 'target': 'branch', 'enforcement': 'active', 'bypass_actors': [],
         'conditions': {'ref_name': {'include': ['refs/heads/' + policy['state_branch']], 'exclude': []}},
         'rules': [{'type': 'deletion'}, {'type': 'non_fast_forward'}]}
    ]
    if policy.get('publication_mode') == 'github_release_only':
        expected.append({
            'name': 'LAB - tags estaveis imutaveis', 'target': 'tag',
            'enforcement': 'active', 'bypass_actors': [],
            'conditions': {'ref_name': {'include': ['refs/tags/v*'],
                                        'exclude': ['refs/tags/v*-rc.*']}},
            'rules': [{'type': 'update'}, {'type': 'deletion'}]
        })
    if protect_branches:
        expected.append({'name': 'LAB - main e release revisadas', 'target': 'branch', 'enforcement': 'active', 'bypass_actors': [],
                         'conditions': {'ref_name': {'include': ['refs/heads/main', 'refs/heads/release/**'], 'exclude': []}},
                         'rules': [{'type': 'deletion'}, {'type': 'non_fast_forward'},
                                   {'type': 'pull_request', 'parameters': {'dismiss_stale_reviews_on_push': True,
                                    'require_code_owner_review': False, 'require_last_push_approval': False,
                                    'required_approving_review_count': 1, 'required_review_thread_resolution': True,
                                    'allowed_merge_methods': ['merge', 'squash', 'rebase']}},
                                   {'type': 'required_status_checks', 'parameters': {'strict_required_status_checks_policy': True,
                                    'do_not_enforce_on_create': True, 'required_status_checks': [{'context': 'Flutter analyze e test'}]}}]})
    rules = api(endpoint('rulesets'))
    for spec in expected:
        matching = [r for r in rules if r['name'] == spec['name']]
        if len(matching) > 1:
            raise ValueError('Ruleset duplicado; não sobrescrever.')
        if matching:
            current = api(endpoint('rulesets/' + str(matching[0]['id'])))
            if not ruleset_matches(current, spec):
                raise ValueError('Ruleset diverge; revisar antes de alterar.')
        else:
            created = api(endpoint('rulesets'), spec, 'POST')
            audit['changes'].append({'ruleset': spec['name'], 'id': created['id']})
    if api(endpoint('git/ref/heads/' + policy['state_branch']), missing=True) is None:
        sha = api(endpoint('commits/main'))['sha']
        api(endpoint('git/refs'), {'ref': 'refs/heads/' + policy['state_branch'], 'sha': sha}, 'POST')
        audit['changes'].append({'state_branch_created': policy['state_branch'], 'seed': sha})
    audit['environment_ids'] = environments(policy)
    output(folder, 'configuration.json', audit)
    print(json.dumps(audit, ensure_ascii=False))


if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--output', required=True)
    p.add_argument('--protect-branches', action='store_true', help='Após merge da implementação, exigir checks e 1 review elegível em main/release.')
    args = p.parse_args()
    configure(args.output, args.protect_branches)
