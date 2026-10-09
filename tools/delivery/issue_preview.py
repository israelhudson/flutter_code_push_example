"""Import immutable SHA previews without changing the existing Pages helpers.

The shared Pages lock protects both paths. A previously published snapshot can
be reused only when source fingerprint AND app-byte hash match the new build.
Its wrapper may name an older delivery; the Issue binds the precise code/files.
"""
import argparse
import json
from pathlib import Path
import shutil
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / 'deploy'))
import pages_preview as preview


def merge(incoming, site, sha):
    incoming, site = Path(incoming), Path(site)
    if preview.validate_site(incoming) != [sha]:
        raise ValueError('Artefato não corresponde ao único snapshot preparado.')
    preview.validate_site(site)
    source = incoming / 'snapshots' / sha
    target = site / 'snapshots' / sha
    new = preview.json_file(source / 'metadata.json')
    if target.exists():
        old = preview.json_file(target / 'metadata.json')
        if (old.get('source_sha') != sha or old.get('source_fingerprint') != new.get('source_fingerprint')
                or old.get('web_content_sha256') != new.get('web_content_sha256')):
            raise ValueError('SHA existente possui inputs ou bytes diferentes. Não sobrescrever.')
    else:
        shutil.copytree(source, target)
    # Preserve the root redirect belonging to the existing pipeline.
    if not (site / 'index.html').exists():
        if not (incoming / 'index.html').is_file():
            raise ValueError('Histórico novo precisa de página inicial do build verificado.')
        shutil.copyfile(incoming / 'index.html', site / 'index.html')
    (site / '.nojekyll').touch()
    preview.validate_site(site)
    metadata = preview.json_file(target / 'metadata.json')
    return {**metadata, 'snapshot_manifest_sha256': preview.digest(preview.json_file(target / 'files.json'))}


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--incoming', required=True); p.add_argument('--site', required=True); p.add_argument('--source-sha', required=True)
    args = p.parse_args()
    print(json.dumps(merge(args.incoming, args.site, args.source_sha), ensure_ascii=False))


if __name__ == '__main__':
    main()
