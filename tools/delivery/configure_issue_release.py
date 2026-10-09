"""Create only the separate Issue rulesets. Default is a read-only plan.

Run locally as repository owner after merging the PR. No PAT is stored and no
legacy ruleset/Environment/secret is changed. --apply is an explicit admin write.
"""
import argparse
import json

import issue_release as issue
import release_lab as lab


def definitions():
    result = []
    for name, (target, patterns, required) in issue.GUARDS.items():
        rules = []
        for kind in sorted(required):
            rule = {'type': kind}
            if kind == 'pull_request':
                rule['parameters'] = {'required_approving_review_count': 0, 'dismiss_stale_reviews_on_push': True,
                    'require_code_owner_review': False, 'require_last_push_approval': False,
                    'required_review_thread_resolution': True}
            if kind == 'required_status_checks':
                rule['parameters'] = {'strict_required_status_checks_policy': True,
                    'required_status_checks': [{'context': 'Issue / Verificar contratos'}]}
            rules.append(rule)
        result.append({'name': name, 'target': target, 'enforcement': 'active', 'bypass_actors': [],
                       'conditions': {'ref_name': {'include': patterns, 'exclude': []}}, 'rules': rules})
    return result


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--apply', action='store_true'); p.add_argument('--output', required=True)
    args = p.parse_args()
    requested = definitions()
    if args.apply:
        repo = lab.api('repos/' + lab.REPOSITORY)
        if not repo.get('permissions', {}).get('admin'):
            raise issue.IssueError('Configuração exige conta com administração deste repositório.')
        existing = {r['name']: r for r in issue.pages('rulesets')}
        for value in requested:
            if value['name'] not in existing:
                lab.api(lab.endpoint('rulesets'), value, 'POST')
        issue.protect()  # Never silently replace an existing differently configured ruleset.
    lab.output(args.output, 'issue-rulesets.json', {'applied': args.apply, 'rulesets': requested})
    print(json.dumps({'applied': args.apply, 'existing_pipeline_changed': False}))


if __name__ == '__main__':
    main()
