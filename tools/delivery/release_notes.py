"""Small presentation copies of already frozen candidate communication.

The original report, source selection and identity are never rewritten. Text
reduction is literal and deterministic; no inference, late source or AI call is
introduced. Both Slack and GitHub can use the same bounded notes.
"""
import re
import unicodedata

from changelog_summary import normalized_changes, verify_communication

SOURCE_LABELS = {'commits_fallback': 'histórico de commits',
                 'pr_sections': 'descrição das PRs (texto copiado; sem IA)',
                 'ai': 'resumo por IA congelado'}
_KNOWN_ROLES = {'israelhudson': 'Aprovador 1', 'fahnassau30': 'Aprovador 2'}
_PREFIX = re.compile(r'^(?:feat|fix|docs|refactor|test|chore|ci|build|perf|style|revert)(?:\([^)]*\))?!?:\s*', re.I)


def approver_labels(policy):
    """Aliases only: raw GitHub identity remains in policy/review receipts."""
    labels = []
    for position, person in enumerate(policy.get('approvers', []), 1):
        role = person.get('role')
        label = {'first': 'Aprovador 1', 'second': 'Aprovador 2'}.get(role)
        labels.append(label or _KNOWN_ROLES.get(person.get('login'), 'Aprovador ' + str(position)))
    return labels


def _plain(value):
    if not isinstance(value, str):
        raise ValueError('Texto das notas inválido.')
    value = ''.join(c if unicodedata.category(c) not in ('Cc', 'Cf') else ' ' for c in value)
    return re.sub(r'\s+', ' ', value).strip()


def _short(value, maximum):
    value = _plain(value)
    return value if len(value) <= maximum else value[:maximum - 1].rstrip() + '…'


def brief_notes(report):
    """Return <=4 description lines, <=4 changes and bounded literal caveats."""
    changes, history_truncated = normalized_changes(report.get('changes'))
    selected = verify_communication(report) if 'communication' in report else None
    source = selected['source'] if selected else 'commits_fallback'
    rows = selected['text'].splitlines() if selected else []
    descriptive, validation, limitations = [], [], []
    for row in rows:
        row = re.sub(r'^\s*(?:[•*-]|\d+[.)])\s*', '', row).strip()
        if not row:
            continue
        if row.startswith('Como validar:'):
            validation.append(row.removeprefix('Como validar:').strip())
        elif row.startswith('Limitações:'):
            limitations.append(row.removeprefix('Limitações:').strip())
        elif source != 'commits_fallback':
            descriptive.append(re.sub(r'^PR [^—]+— O que muda:\s*', '', row))
    title = _short(report.get('title', 'Candidata para revisão'), 160)
    if descriptive:
        description = [title, *[_short(row, 180) for row in descriptive[:3]]]
    else:
        count = len(report['changes'])
        description = [title, 'Este corte reúne ' + str(count) + (' mudança registrada.' if count == 1 else ' mudanças registradas.'),
                       'Confira o preview e os detalhes no changelog desta candidata.']
    if len(description) < 3:
        description.append('Confira o preview antes de registrar a decisão no GitHub.')
    subjects = []
    for change in changes:
        subject = _PREFIX.sub('', change)
        short = _short(subject, 150)
        if short and short not in subjects:
            subjects.append(short)
        if len(subjects) == 4:
            break
    truncated = (history_truncated or len(changes) > len(subjects) or len(descriptive) > 3
                 or any(len(_plain(row)) > 180 for row in [*descriptive, *validation, *limitations])
                 or any(len(_plain(_PREFIX.sub('', row))) > 150 for row in changes[:4])
                 or len(validation) > 2 or len(limitations) > 2)
    return {'description': description[:4], 'changes': subjects or ['Sem commits adicionais desde a base registrada.'],
            'validation': [_short(row, 180) for row in validation[:2]],
            'limitations': [_short(row, 180) for row in limitations[:2]],
            'source': source, 'source_label': SOURCE_LABELS[source],
            'fallback_reason': selected['fallback_reason'] if selected else 'ai_not_configured',
            'truncated': truncated}
