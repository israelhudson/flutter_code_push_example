"""Archive old untagged PR snapshots; release bytes remain live and immutable."""
import argparse
from datetime import datetime
from pathlib import Path
import re
import shutil

import issue_preview
import release_lab as lab

pages = issue_preview.preview
KEEP_PRS = 2


def tagged_commits():
    """Resolve every namespace and annotated tag; fail closed on incomplete reads."""
    pinned = set()
    for page in range(1, 101):
        refs = lab.api(lab.endpoint(f'git/refs/tags?per_page=100&page={page}'))
        if not isinstance(refs, list):
            raise ValueError('Lista de tags incompleta; não arquivar.')
        for ref in refs:
            obj, seen = ref['object'], set()
            while obj['type'] == 'tag':
                if obj['sha'] in seen or len(seen) >= 10:
                    raise ValueError('Tag anotada não resolvida; não arquivar.')
                seen.add(obj['sha'])
                obj = lab.api(lab.endpoint('git/tags/' + obj['sha']))['object']
            if obj['type'] != 'commit' or not lab.SHA.fullmatch(obj['sha']):
                raise ValueError('Tag sem commit verificável; não arquivar.')
            pinned.add(obj['sha'])
        if len(refs) < 100:
            return pinned
    raise ValueError('Paginação de tags excedida; não arquivar.')


def plan(site, incoming=None):
    site = Path(site)
    ids = set(pages.validate_site(site))
    pinned = tagged_commits()
    # Metadata is a conservative extra pin, even if an old tag is unavailable.
    pinned.update(sha for sha in ids if pages.json_file(site / 'snapshots' / sha / 'metadata.json').get('delivery_tag'))
    root = (site / 'index.html').read_text() if (site / 'index.html').exists() else ''
    root_ids = set(re.findall(r'snapshots/([a-f0-9]{40})/', root))
    if not root_ids <= ids:
        raise ValueError('Página inicial aponta para snapshot ausente; não arquivar.')
    pinned |= root_ids
    incoming_ids = set(pages.validate_site(incoming)) if incoming else set()
    if incoming and len(incoming_ids) != 1:
        raise ValueError('Artefato de entrada precisa de um único snapshot.')
    pinned |= incoming_ids
    dates = {}
    for sha in ids - pinned:
        c = lab.api(lab.endpoint('commits/' + sha))
        if c.get('sha') != sha:
            raise ValueError('Data de commit sem identidade confirmada.')
        dates[sha] = datetime.fromisoformat(c['commit']['committer']['date'].replace('Z', '+00:00')).timestamp()
    recent = sorted(dates, key=lambda s: (dates[s], s), reverse=True)[:KEEP_PRS]
    keep = (ids & pinned) | set(recent)
    remove = ids - keep
    sizes = {sha: sum(p.stat().st_size for p in (site / 'snapshots' / sha).rglob('*') if p.is_file()) for sha in ids}
    root_bytes = sum(p.stat().st_size for p in site.iterdir() if p.is_file())
    incoming_bytes = sum(p.stat().st_size for p in Path(incoming).rglob('*') if p.is_file()) if incoming else 0
    projected = root_bytes + sum(sizes[s] for s in keep) + (incoming_bytes if incoming_ids - ids else 0)
    if projected > pages.MAX_SITE_BYTES:
        raise ValueError('Candidatas/releases preservadas excedem a capacidade; migrar armazenamento, não apagar entregas.')
    return {'history_commit': pages.git(site, 'rev-parse', 'HEAD'), 'keep_prs': KEEP_PRS,
            'preserved': sorted(keep), 'archived': sorted(remove), 'pinned': sorted(ids & pinned),
            'archived_bytes': sum(sizes[s] for s in remove), 'projected_bytes': projected}


def apply(site, report):
    site = Path(site)
    if (pages.git(site, 'rev-parse', 'HEAD') != report['history_commit']
            or pages.git(site, 'status', '--porcelain', '--untracked-files=all')):
        raise ValueError('Histórico mudou ou contém alterações; recalcular plano.')
    if tagged_commits() & set(report['archived']):
        raise ValueError('Nova tag protege snapshot planejado para arquivo; recalcular plano.')
    pages.validate_site(site)
    for sha in report['archived']:
        if not lab.SHA.fullmatch(sha):
            raise ValueError('Snapshot fora da identidade permitida.')
    for sha in report['archived']:
        shutil.rmtree(site / 'snapshots' / sha)
    pages.validate_site(site)
    # The caller persists an ordinary commit under pages-preview concurrency.
    # report.history_commit remains the recovery point for every removed file.


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--site', required=True)
    parser.add_argument('--incoming')
    parser.add_argument('--output', required=True)
    parser.add_argument('--apply', action='store_true')
    args = parser.parse_args()
    report = plan(args.site, args.incoming)
    lab.output(args.output, 'preview-retention.json', report)
    if args.apply:
        apply(args.site, report)
    print(lab.canonical({**report, 'applied_to_working_copy': args.apply}))


if __name__ == '__main__':
    main()
