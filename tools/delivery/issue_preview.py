"""Import immutable SHA previews without changing the existing Pages helpers.

The shared Pages lock protects both paths. A previously published snapshot can
be reused by default only when source fingerprint AND app-byte hash match.
Slack may explicitly reuse an intact original if only Flutter cache-version
text changed and all build identities and other app bytes match.
Its wrapper may name an older delivery; the Issue binds the precise code/files.
"""
import argparse
import json
import re
from pathlib import Path
import shutil
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / 'deploy'))
import pages_preview as preview


def flutter_bootstrap_equivalent(source, target, new, old):
    """Compare only; never rewrite either snapshot or its approved hashes.

    Flutter regenerates the service-worker cache version even for identical
    inputs. Reuse requires every other app byte (including the worker) to match.
    """
    identity = ('source_sha', 'source_tree', 'source_fingerprint', 'fingerprint',
                'source_build_inputs', 'pages_build_inputs', 'version')
    if any(not new.get(key) or new[key] != old.get(key) for key in identity):
        return False
    before, after = preview.hashes(target / 'app'), preview.hashes(source / 'app')
    if before.keys() != after.keys() or {k for k in before if before[k] != after[k]} != {'flutter_bootstrap.js'}:
        return False
    if 'flutter_service_worker.js' not in before:
        return False
    pattern = rb'(serviceWorkerVersion: ")[0-9]+(")'
    original = (target / 'app/flutter_bootstrap.js').read_bytes()
    rebuilt = (source / 'app/flutter_bootstrap.js').read_bytes()
    if len(re.findall(pattern, original)) != 1 or len(re.findall(pattern, rebuilt)) != 1:
        return False
    return re.sub(pattern, rb'\1VERSION\2', original) == re.sub(pattern, rb'\1VERSION\2', rebuilt)


def merge(incoming, site, sha, allow_flutter_cache_version=False):
    incoming, site = Path(incoming), Path(site)
    if preview.validate_site(incoming) != [sha]:
        raise ValueError('Artefato não corresponde ao único snapshot preparado.')
    preview.validate_site(site)
    source = incoming / 'snapshots' / sha
    target = site / 'snapshots' / sha
    new = preview.json_file(source / 'metadata.json')
    reused_cache_version = False
    if target.exists():
        old = preview.json_file(target / 'metadata.json')
        if (old.get('source_sha') != sha or old.get('source_fingerprint') != new.get('source_fingerprint')
                or old.get('web_content_sha256') != new.get('web_content_sha256')):
            if not allow_flutter_cache_version or not flutter_bootstrap_equivalent(source, target, new, old):
                raise ValueError('SHA existente possui inputs ou bytes diferentes. Não sobrescrever.')
            reused_cache_version = True
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
    result = {**metadata, 'snapshot_manifest_sha256': preview.digest(preview.json_file(target / 'files.json'))}
    if reused_cache_version:
        result['reuse_evidence'] = {
            'reason': 'only_flutter_service_worker_version_differs',
            'incoming_web_content_sha256': new['web_content_sha256'],
            'preserved_web_content_sha256': metadata['web_content_sha256'],
            'changed_app_files': ['flutter_bootstrap.js'],
            'published_snapshot_modified': False,
        }
    return result


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--incoming', required=True); p.add_argument('--site', required=True); p.add_argument('--source-sha', required=True)
    p.add_argument('--allow-flutter-cache-version', action='store_true')
    args = p.parse_args()
    print(json.dumps(merge(args.incoming, args.site, args.source_sha, args.allow_flutter_cache_version), ensure_ascii=False))


if __name__ == '__main__':
    main()
