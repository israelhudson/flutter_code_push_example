"""Translate human choices into the existing delivery contract, without effects."""
from dataclasses import dataclass
import os
from pathlib import Path
import sys

from release_lab import VERSION


@dataclass(frozen=True)
class Scenario:
    id: str
    label: str
    scope: str
    validation_mode: str
    patch_mode: str = 'none'

    def configuration(self):
        return {'scope': self.scope, 'validation_mode': self.validation_mode,
                'patch_mode': self.patch_mode}

    def effects(self):
        return {
            'creates_candidate_tag_and_prerelease': True,
            'web_preview': self.validation_mode == 'full',
            'github_release_after_acceptances_and_enabled_controls': self.scope == 'github_test',
            'android_patch': ('assisted_cli_after_github_release'
                              if self.patch_mode == 'android_staging' else 'none'),
            'stable_publication': False,
        }


SCENARIOS = (
    Scenario('candidate_only', 'Só avaliar a candidata', 'none', 'controls_only'),
    Scenario('candidate_preview', 'Avaliar a candidata com preview', 'none', 'full'),
    Scenario('release_only', 'Teste rápido com Release no GitHub', 'github_test', 'controls_only'),
    Scenario('release_preview', 'Teste com preview e Release no GitHub', 'github_test', 'full'),
    Scenario('android_staging', 'Android staging — preview, Release e patch via CLI',
             'github_test', 'full', 'android_staging'),
)
DEFAULT_SCENARIO = SCENARIOS[0]


def by_id(identifier):
    for scenario in SCENARIOS:
        if scenario.id == identifier:
            return scenario
    raise ValueError('Cenário desconhecido. Consulte --help; nenhum cenário padrão foi aplicado.')


def by_label(label):
    for scenario in SCENARIOS:
        if scenario.label == label:
            return scenario
    raise ValueError('Opção do formulário desconhecida; nenhuma configuração foi aplicada.')


def validate_inputs(version, title):
    # Keep the same syntax accepted by the existing preparer. Availability and
    # RC lineage remain checked remotely by that preparer, never guessed here.
    if not VERSION.fullmatch(version or ''):
        raise ValueError('Use uma versão como 1.15.7, sem v, RC ou zeros à esquerda.')
    if not title.strip() or len(title) > 120 or any(ord(c) < 32 for c in title):
        raise ValueError('Informe um título de até 120 caracteres, sem quebras de linha.')


def workflow_outputs(label):
    scenario = by_label(label)
    values = {'scenario_id': scenario.id, **scenario.configuration()}
    # Values come only from the fixed catalog, never from arbitrary input text.
    return ''.join(f'{key}={value}\n' for key, value in values.items())


def main():
    try:
        output = workflow_outputs(os.environ.get('DELIVERY_SCENARIO'))
        target = os.environ.get('GITHUB_OUTPUT')
        if not target:
            raise ValueError('GITHUB_OUTPUT ausente; este comando é usado pelo workflow.')
        with Path(target).open('a', encoding='utf-8') as stream:
            stream.write(output)
    except (ValueError, OSError) as error:
        print(str(error), file=sys.stderr)
        return 1
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
