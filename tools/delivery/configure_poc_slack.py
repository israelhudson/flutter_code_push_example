"""Read-only plan by default; apply only separate POC namespace protections."""
import argparse
import configure_issue_release as original
import issue_release
import poc_slack
import release_lab as lab


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--output', required=True); p.add_argument('--apply', action='store_true')
    args = p.parse_args()
    prior = issue_release.GUARDS
    try:
        issue_release.GUARDS = poc_slack.GUARDS
        definitions = original.definitions()
    finally:
        issue_release.GUARDS = prior
    for d in definitions:
        for rule in d['rules']:
            if rule['type'] == 'required_status_checks':
                rule['parameters']['required_status_checks'] = [{'context': 'Slack / Verificar contratos'}]
    if args.apply:
        if not lab.api('repos/' + lab.REPOSITORY).get('permissions', {}).get('admin'):
            raise lab.LabError('Administração da POC exigida para aplicar proteções.')
        old = lab.api(lab.endpoint('rulesets'))
        names = {r['name'] for r in old}
        baseline = {r['id']: lab.api(lab.endpoint('rulesets/' + str(r['id']))) for r in old if r['name'] not in poc_slack.GUARDS}
        for definition in definitions:
            if definition['name'] not in names:
                lab.api(lab.endpoint('rulesets'), definition, 'POST')
        poc_slack.protect()
        if any(lab.api(lab.endpoint('rulesets/' + str(i))) != value for i, value in baseline.items()):
            raise lab.LabError('Regra anterior mudou; revisar antes de ativar a POC.')
    lab.output(args.output, 'poc-rulesets.json', {'applied': args.apply, 'rulesets': definitions})


if __name__ == '__main__':
    main()
