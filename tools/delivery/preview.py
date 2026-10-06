"""Package a real Flutter web build; no hosting, credentials, or Shorebird CLI."""
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import zipfile

from policy import digest


def git(*args):
    return subprocess.check_output(['git', *args]).decode().strip()


def fingerprint(ref='HEAD'):
    # Conservative source identity. Exclude only known non-build documentation
    # and version records; include CI, tooling and build-inputs themselves.
    entries = git('ls-tree', '-r', ref).splitlines()
    entries = [entry for entry in entries if not entry.split('\t', 1)[1].startswith(
        ('docs/', 'referencias/', 'delivery/candidates/'))
        and entry.split('\t', 1)[1] not in ('README.md', 'AGENTS.md')]
    inputs = json.loads(git('show', f'{ref}:delivery/build-inputs.json'))
    return digest({'files': entries, 'inputs': inputs})


def package():
    inputs = json.loads(Path('delivery/build-inputs.json').read_text())
    if subprocess.check_output(['uname', '-s']).decode().strip() != 'Linux':
        raise ValueError('O artefato reutilizável exige o runner Linux declarado.')
    actual = json.loads(subprocess.check_output(['flutter', '--version', '--machine']))
    if (actual['frameworkVersion'] != inputs['flutter_version']
            or actual['frameworkRevision'] != inputs['flutter_revision']):
        raise ValueError('Flutter diferente do build-inputs.json.')
    subprocess.run(['flutter', 'pub', 'get', '--enforce-lockfile'], check=True)
    subprocess.run(inputs['command'], check=True)
    if git('status', '--porcelain', '--untracked-files=no'):
        raise ValueError('O build alterou arquivos rastreados.')
    output = Path('build/delivery-preview')
    output.mkdir(parents=True, exist_ok=True)
    archive = output / 'preview.zip'
    with zipfile.ZipFile(archive, 'w', zipfile.ZIP_DEFLATED) as z:
        for path in sorted(Path('build/web').rglob('*')):
            if path.is_file():
                z.write(path, path.relative_to('build/web'))
    metadata = {'schema': 1, 'source_sha': git('rev-parse', 'HEAD'),
                'source_tree': git('rev-parse', 'HEAD^{tree}'),
                'fingerprint': fingerprint(), 'inputs': inputs,
                'sha256': hashlib.sha256(archive.read_bytes()).hexdigest()}
    (output / 'metadata.json').write_text(json.dumps(metadata, indent=2) + '\n')
    with open(os.environ.get('GITHUB_OUTPUT', os.devnull), 'a') as f:
        f.write(f"fingerprint={metadata['fingerprint']}\n")
    return metadata


if __name__ == '__main__':
    print(fingerprint(sys.argv[2] if len(sys.argv) > 2 else 'HEAD')
          if len(sys.argv) > 1 and sys.argv[1] == 'fingerprint' else json.dumps(package()))
