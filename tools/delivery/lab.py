"""Operar o laboratório local de entregas com Israel representando os papéis.

Identidade real: Israel. Samuel, Vinícius e Ian/Yan são papéis simulados.
O único publicador desta CLI grava recibos fictícios em uma pasta local.
"""
import argparse
import json
from pathlib import Path
import sys

from lab_engine import FakePublisher, LabStore, make_manifest, run_demo
from policy import digest


OPERATOR = 'local:israel'
BANNER = 'LABORATÓRIO — papéis simulados por Israel; sem distribuição real.'


def read_json(path):
    return json.loads(Path(path).read_text(encoding='utf-8'))


def build_parser():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--db', default='build/delivery-lab/state.sqlite',
                        help='Banco local persistente deste ensaio.')
    parser.add_argument('--provider-dir', default='build/delivery-lab/provider',
                        help='Pasta dos recibos do provedor falso local.')
    commands = parser.add_subparsers(dest='command', required=True)
    demo = commands.add_parser('demo', help='Executar cenário isolado e gerar evidências locais.')
    demo.add_argument('--folder', default='build/delivery-lab/demo')
    init = commands.add_parser('init', help='Registrar produção e bases fictícias do ensaio.')
    init.add_argument('--production-sha', required=True)
    init.add_argument('--targets', required=True, help='Arquivo JSON com os alvos do laboratório.')
    review = commands.add_parser('technical-review', help='Representar a revisão técnica de Ian.')
    review.add_argument('--sha', required=True)
    review.add_argument('--role', choices=['ian', 'yan'], default='ian')
    manifest = commands.add_parser('manifest', help='Criar o manifesto fixado antes de preparar a RC.')
    manifest.add_argument('--repo', required=True)
    manifest.add_argument('--ref', required=True, help='Commit/ref resolvido uma vez durante a preparação.')
    manifest.add_argument('--targets', required=True)
    manifest.add_argument('--preview', required=True, help='JSON com identidade e caminho do preview.')
    manifest.add_argument('--inputs', required=True)
    manifest.add_argument('--delivery-id', required=True)
    manifest.add_argument('--rc', type=int, default=1)
    manifest.add_argument('--output', required=True, help='Novo arquivo; não sobrescreve manifesto anterior.')
    prepare = commands.add_parser('prepare', help='Fixar candidata/manifesto e iniciar em 0/2.')
    prepare.add_argument('--manifest', required=True, help='Manifesto JSON completo da candidata.')
    prepare.add_argument('--request-id', required=True)
    prepare.add_argument('--urgent', action='store_true', help='Priorizar a correção a partir da produção.')
    for name in ('approve', 'revoke'):
        command = commands.add_parser(name, help='Representar uma ação de aprovação da versão.')
        command.add_argument('--candidate', required=True)
        command.add_argument('--role', choices=['samuel', 'vinicius'], required=True)
        command.add_argument('--hash', dest='manifest_hash', required=True)
        command.add_argument('--request-id')
    for name in ('status', 'events'):
        command = commands.add_parser(name, help='Consultar estado ou histórico persistido.')
        command.add_argument('--candidate')
    commands.add_parser('next', help='Ativar a próxima candidata válida da fila.')
    publish = commands.add_parser('publish', help='Comando final: publicar somente no provedor falso.')
    publish.add_argument('--candidate', required=True)
    publish.add_argument('--hash', dest='manifest_hash', required=True)
    publish.add_argument('--command-id', required=True)
    publish.add_argument('--repo', required=True, help='Repositório local com o snapshot aprovado.')
    publish.add_argument('--fail-destination', choices=['android', 'ios', 'web'], action='append', default=[],
                         help='Injetar falha somente no provedor falso para ensaiar recuperação.')
    publish.add_argument('--failure-mode', choices=['before', 'after', 'warning'], default='before')
    reconcile = commands.add_parser('reconcile', help='Consultar efeitos pendentes no provedor falso.')
    reconcile.add_argument('--candidate', required=True)
    reconcile.add_argument('--repo', required=True)
    return parser


def execute(args):
    if args.command == 'demo':
        return run_demo(Path(args.folder))
    store = LabStore(Path(args.db))
    if args.command == 'init':
        return store.initialize(args.production_sha, read_json(args.targets), operator=OPERATOR)
    if args.command == 'technical-review':
        return store.technical_review(args.sha, role=args.role, actor=OPERATOR)
    if args.command == 'manifest':
        manifest = make_manifest(Path(args.repo), args.ref, store.production(),
                                 read_json(args.targets), read_json(args.preview),
                                 read_json(args.inputs), args.delivery_id, rc=args.rc)
        output = Path(args.output)
        output.parent.mkdir(parents=True, exist_ok=True)
        with output.open('x', encoding='utf-8') as file:
            json.dump(manifest, file, ensure_ascii=False, indent=2)
            file.write('\n')
        return {'mode': 'laboratory', 'simulation': True,
                'manifest_path': str(output.resolve()), 'source_sha': manifest['source_sha'],
                'candidate_id': manifest['candidate_id'], 'manifest_hash': digest(manifest),
                'pre_analysis': manifest['pre_analysis']}
    if args.command == 'prepare':
        return store.prepare(read_json(args.manifest), args.request_id,
                             actor=OPERATOR, urgent=args.urgent)
    if args.command in ('approve', 'revoke'):
        operation = getattr(store, args.command)
        return operation(args.candidate, args.role, args.manifest_hash,
                         actor=OPERATOR, request_id=args.request_id)
    if args.command == 'status':
        return store.status(args.candidate)
    if args.command == 'events':
        return store.events(args.candidate)
    if args.command == 'next':
        return store.activate_next(OPERATOR)
    failures = ({dest: args.failure_mode for dest in args.fail_destination}
                if args.command == 'publish' else {})
    adapter = FakePublisher(Path(args.provider_dir), failures=failures)
    if args.command == 'publish':
        return store.publish(args.candidate, args.manifest_hash, args.command_id,
                             Path(args.repo), adapter, actor=OPERATOR)
    return store.reconcile(args.candidate, Path(args.repo), adapter, actor=OPERATOR)


def main(argv=None):
    args = build_parser().parse_args(argv)
    print(BANNER, file=sys.stderr)
    try:
        result = execute(args)
    except (ValueError, RuntimeError, OSError) as error:
        print(json.dumps({'mode': 'laboratory', 'simulation': True, 'error': str(error)},
                         ensure_ascii=False, indent=2), file=sys.stderr)
        return 1
    print(json.dumps(result, ensure_ascii=False, indent=2, default=str))
    return 0


if __name__ == '__main__':
    sys.exit(main())
