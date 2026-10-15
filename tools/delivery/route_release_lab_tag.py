"""Read-only ownership check for the LAB's shared v*-rc.* tag trigger.

A version-shaped tag is not an authorization to enter the LAB. Only its active,
prepared journal record may route a push to that flow. Delivery v2 and unregistered
tags are skipped; no journal, reference, review or publication is written here.
"""
import argparse
import os

import release_lab as lab


def classify(tag, source_sha):
    if not lab.TAG.fullmatch(tag or '') or not lab.SHA.fullmatch(source_sha or ''):
        raise lab.LabError('Push sem tag RC ou commit válido; não iniciar o LAB.')
    policy = lab.load_policy()
    state, _ = lab.state_read(policy)
    records = state.get('candidates')
    if not isinstance(records, dict):
        raise lab.LabError('Journal LAB inválido; classificação bloqueada.')
    record = records.get(tag)
    if record is None:
        return {'allow_lab': False, 'reason': 'no_registered_lab_candidate',
                'candidate_tag': tag, 'source_sha': source_sha}
    match = lab.TAG.fullmatch(tag)
    if (not isinstance(record, dict) or state.get('active') != tag
            or record.get('candidate_tag') != tag or record.get('version') != match[1]
            or record.get('source_sha') != source_sha
            or record.get('release_branch') != 'release/' + match[1]
            or record.get('policy_digest') != lab.digest(policy)
            or record.get('status') != 'prepared'
            or record.get('evaluation_run_id') is not None):
        raise lab.LabError('Registro LAB não é uma candidata preparada deste push.')
    if lab.resolve_tag(tag) != source_sha:
        raise lab.LabError('A tag não corresponde ao código registrado no LAB.')
    return {'allow_lab': True, 'reason': 'registered_lab_candidate',
            'candidate_tag': tag, 'source_sha': source_sha}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--tag', required=True)
    parser.add_argument('--source-sha', required=True)
    parser.add_argument('--output', required=True)
    args = parser.parse_args()
    try:
        if (os.environ.get('GITHUB_REPOSITORY') != lab.REPOSITORY
                or os.environ.get('GITHUB_EVENT_NAME') != 'push'
                or os.environ.get('GITHUB_REF') != 'refs/tags/' + args.tag):
            raise lab.LabError('Classificação aceita somente push de tag neste repositório.')
        result = classify(args.tag, args.source_sha)
    except (lab.LabError, ValueError, KeyError) as error:
        result = {'allow_lab': False, 'reason': 'classification_not_confirmed'}
        lab.output(args.output, 'lab-tag-route.json', result)
        lab.outputs({'allow_lab': 'false'})
        print(str(error) if isinstance(error, lab.LabError) else 'Dados inválidos; LAB bloqueado.')
        return 1
    lab.output(args.output, 'lab-tag-route.json', result)
    lab.outputs({'allow_lab': 'true' if result['allow_lab'] else 'false'})
    print(lab.canonical(result))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
