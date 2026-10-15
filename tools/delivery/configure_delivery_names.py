"""Plan additive official-name guards; --apply never changes an existing rule."""
import argparse

import delivery_names as names
import release_lab as lab


def definitions():
    result = []
    for name, (target, patterns, kinds) in names.GUARDS.items():
        rules = []
        for kind in sorted(kinds):
            rule = {'type': kind}
            if kind == 'pull_request':
                rule['parameters'] = {'required_approving_review_count': 0,
                    'dismiss_stale_reviews_on_push': True, 'require_code_owner_review': False,
                    'require_last_push_approval': False, 'required_review_thread_resolution': True}
            if kind == 'required_status_checks':
                rule['parameters'] = {'strict_required_status_checks_policy': True,
                    'do_not_enforce_on_create': True,
                    'required_status_checks': [{'context': c} for c in sorted(names.CHECKS)]}
            rules.append(rule)
        result.append({'name': name, 'target': target, 'enforcement': 'active', 'bypass_actors': [],
                       'conditions': {'ref_name': {'include': patterns, 'exclude': []}}, 'rules': rules})
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', required=True)
    parser.add_argument('--apply', action='store_true')
    args = parser.parse_args()
    requested = definitions()
    if args.apply:
        if not lab.api('repos/' + lab.REPOSITORY).get('permissions', {}).get('admin'):
            raise lab.LabError('Configuração exige administração deste repositório.')
        old = lab.api(lab.endpoint('rulesets'))
        baseline = {r['id']: lab.api(lab.endpoint('rulesets/' + str(r['id']))) for r in old}
        present = {r['name'] for r in old}
        for definition in requested:
            if definition['name'] not in present:
                lab.api(lab.endpoint('rulesets'), definition, 'POST')
        names.protect()
        if any(lab.api(lab.endpoint('rulesets/' + str(i))) != value for i, value in baseline.items()):
            raise lab.LabError('Regra preexistente mudou; conferir antes de habilitar.')
    lab.output(args.output, 'official-name-rulesets.json', {'applied': args.apply, 'rulesets': requested})


if __name__ == '__main__':
    main()
