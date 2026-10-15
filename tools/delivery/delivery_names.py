"""Frozen release identities for the official lane and its historical records.

The RC chooses its namespace once. A later code/config change cannot rename a
published release, move a tag, or convert an old RC2 into a different lineage.
"""
import re

import release_lab as lab

GUARDS = {
    'Entrega - tags imutaveis': ('tag', ['refs/tags/v*'], {'update', 'deletion'}),
    'Entrega - correcoes por PR': (
        'branch', ['refs/heads/release/**'],
        {'pull_request', 'required_status_checks', 'non_fast_forward', 'deletion'}),
}
CHECKS = {'Flutter analyze e test', 'Slack / Verificar contratos'}


def frozen_names(candidate):
    version = candidate.get('version')
    match = re.fullmatch(r'(poc-)?v(\d+\.\d+\.\d+)-rc\.([1-9][0-9]*)',
                         str(candidate.get('rc_tag', '')))
    if not match or match[2] != version:
        raise lab.LabError('Tag RC não corresponde à versão congelada.')
    if 'rc_number' in candidate and (type(candidate['rc_number']) is not int
                                      or candidate['rc_number'] != int(match[3])):
        raise lab.LabError('Número da RC difere da tag congelada.')
    prefix = match[1] or ''
    branch = ('poc-release/' if prefix else 'release/') + version
    if 'branch' in candidate and candidate['branch'] != branch:
        raise lab.LabError('Branch e tag pertencem a namespaces diferentes.')
    return {'rc_tag': match[0], 'final_tag': prefix + 'v' + version, 'branch': branch}


def final_tag(candidate):
    return frozen_names(candidate)['final_tag']


def protect():
    """Only additive, no-bypass guards; never silently relax an existing rule."""
    summaries = {r['name']: r for r in lab.api(lab.endpoint('rulesets'))}
    for name, (target, patterns, required) in GUARDS.items():
        if name not in summaries:
            raise lab.LabError('Proteção dos nomes oficiais ausente; aplicar configure_delivery_names.py.')
        rule = lab.api(lab.endpoint('rulesets/' + str(summaries[name]['id'])))
        if (rule.get('target') != target or rule.get('enforcement') != 'active'
                or rule.get('bypass_actors')
                or rule.get('conditions', {}).get('ref_name') != {'include': patterns, 'exclude': []}
                or not required <= {r['type'] for r in rule.get('rules', [])}):
            raise lab.LabError('Proteção dos nomes oficiais divergente; manter bloqueado.')
        if target == 'branch':
            checks = next(r for r in rule['rules'] if r['type'] == 'required_status_checks')['parameters']
            pr = next(r for r in rule['rules'] if r['type'] == 'pull_request')['parameters']
            if (checks.get('strict_required_status_checks_policy') is not True
                    or not CHECKS <= {r['context'] for r in checks.get('required_status_checks', [])}
                    or pr.get('required_approving_review_count') != 0):
                raise lab.LabError('Correções oficiais exigem PR e checks; ensaio solo sem revisão humana.')
