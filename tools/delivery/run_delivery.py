"""Prepare a delivery through the official workflow; dry-run is entirely offline."""
import argparse
import json
import subprocess
import sys

from delivery_scenarios import SCENARIOS, by_id, validate_inputs
from release_lab import REPOSITORY

WORKFLOW = 'delivery-prepare.yml'
REF = 'main'
DISPATCH_COMMAND = ('gh', 'workflow', 'run', WORKFLOW,
                    '--repo', REPOSITORY, '--ref', REF, '--json')


def plan_request(identifier, version, title):
    scenario = by_id(identifier)
    validate_inputs(version, title)
    return {
        'repository': REPOSITORY,
        'workflow': WORKFLOW,
        'ref': REF,
        'scenario_id': scenario.id,
        'inputs': {'scenario': scenario.label, 'version': version, 'title': title},
        'resolved': scenario.configuration(),
        'effects_if_executed': scenario.effects(),
        'notice': ('A execução prepara uma candidata real. Aceites e controles continuam '
                   'obrigatórios. Android staging exige uma etapa CLI posterior; '
                   'este comando não executa Shorebird.'),
    }


def dispatch(request):
    """One attempt, JSON stdin, no shell and no retry after an uncertain result."""
    try:
        result = subprocess.run(
            list(DISPATCH_COMMAND), input=json.dumps(request['inputs'], ensure_ascii=False),
            text=True, capture_output=True, timeout=45, check=False,
        )
    except FileNotFoundError as error:
        raise RuntimeError('GitHub CLI (gh) ausente. Instale e autentique antes de executar.') from error
    except (subprocess.TimeoutExpired, OSError) as error:
        raise RuntimeError('Disparo sem confirmação. Confira o histórico de Actions antes '
                           'de tentar novamente; não foi feita retentativa automática.') from error
    if result.returncode != 0:
        raise RuntimeError('GitHub CLI não confirmou o disparo. Confira autenticação, '
                           'inputs e histórico de Actions antes de tentar novamente.')


def parser():
    result = argparse.ArgumentParser(description=__doc__)
    commands = result.add_subparsers(dest='operation', required=True)
    prepare = commands.add_parser('prepare', help='Simular ou solicitar o preparo na main.')
    prepare.add_argument('--scenario', required=True, choices=[s.id for s in SCENARIOS])
    prepare.add_argument('--version', required=True, help='Ex.: 1.15.7, sem v e sem RC.')
    prepare.add_argument('--title', required=True, help='Ex.: Corrigir renovação do token no login.')
    mode = prepare.add_mutually_exclusive_group(required=True)
    mode.add_argument('--dry-run', action='store_true', help='Somente mostrar o plano; sem chamadas remotas.')
    mode.add_argument('--execute', action='store_true', help='Solicitar uma execução real pela GitHub CLI.')
    return result


def main(argv=None):
    args = parser().parse_args(argv)
    try:
        request = plan_request(args.scenario, args.version, args.title)
        if args.dry_run:
            response = {'mode': 'dry_run', 'dispatched': False, **request}
        else:
            dispatch(request)
            response = {
                'mode': 'execute', 'dispatch_submitted': True, **request,
                'notice': ('Solicitação enviada; não confirma a conclusão do preparo. '
                           'Acompanhe o run no GitHub Actions.'),
                'actions_url': f'https://github.com/{REPOSITORY}/actions/workflows/{WORKFLOW}',
            }
        print(json.dumps(response, ensure_ascii=False, indent=2))
    except (ValueError, RuntimeError) as error:
        print(str(error), file=sys.stderr)
        return 1
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
