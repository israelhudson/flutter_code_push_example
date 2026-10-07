"""Compile/package a fixed Flutter snapshot; never upload or create a patch.

Android emits an AAB using the project's signing configuration (not certified
for store submission here). iOS emits an unsigned XCArchive: the pinned Flutter
SDK skips IPA export with --no-codesign. No Shorebird CLI or store adapter exists
in this program.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import platform as host_platform
import re
import stat
import subprocess
import sys
import zipfile


KINDS = {'android': 'android-aab-laboratory', 'ios': 'ios-xcarchive-unsigned'}
TOOLING_REPOSITORY = Path(__file__).resolve().parents[1]


def git(repo, *args):
    return subprocess.check_output(['git', '-C', str(repo), *args],
                                   stderr=subprocess.PIPE).decode().strip()


def build_command(platform, defines=None):
    if platform not in KINDS:
        raise ValueError('platform precisa ser android ou ios.')
    args = ['flutter', 'build', 'appbundle' if platform == 'android' else 'ipa', '--release']
    if platform == 'ios':
        args.append('--no-codesign')
    defines = {} if defines is None else defines
    if (not isinstance(defines, dict) or any(
            not isinstance(k, str) or not re.fullmatch(r'[A-Za-z_][A-Za-z0-9_]*', k)
            or not isinstance(v, str) for k, v in defines.items())):
        raise ValueError('dart_defines precisa ser um mapa explícito de strings.')
    return args + [f'--dart-define={key}={defines[key]}' for key in sorted(defines)]


def _snapshot(repo, sha):
    if not re.fullmatch(r'[0-9a-f]{40}', sha or ''):
        raise ValueError('Informe source_sha completo; branches/latest não são permitidos.')
    if git(repo, 'rev-parse', 'HEAD') != sha or git(repo, 'rev-parse', sha + '^{commit}') != sha:
        raise ValueError('Checkout não corresponde ao snapshot solicitado.')
    if git(repo, 'status', '--porcelain', '--untracked-files=no'):
        raise ValueError('Build alterou ou recebeu arquivos rastreados divergentes.')
    return git(repo, 'rev-parse', sha + '^{tree}')


def _product(repo, platform):
    return (repo / 'build/app/outputs/bundle/release/app-release.aab' if platform == 'android'
            else repo / 'build/ios/archive/Runner.xcarchive')


def _validate_product(product, platform):
    if platform == 'android':
        if not product.is_file() or product.is_symlink():
            raise ValueError('AAB esperado não foi produzido.')
        with zipfile.ZipFile(product) as archive:
            if (not {'BundleConfig.pb', 'base/manifest/AndroidManifest.xml'} <= set(archive.namelist())
                    or archive.testzip() is not None):
                raise ValueError('AAB sem a estrutura/integração esperada.')
    elif (not product.is_dir() or product.is_symlink()
          or not (product / 'Info.plist').is_file()
          or not (product / 'Products/Applications/Runner.app/Info.plist').is_file()
          or not (product / 'Products/Applications/Runner.app/Runner').is_file()):
        raise ValueError('XCArchive sem assinatura esperado não foi produzido.')


def _package_product(product, output):
    paths = [product] if product.is_file() else [product, *sorted(product.rglob('*'))]
    with zipfile.ZipFile(output, 'x', compression=zipfile.ZIP_DEFLATED) as archive:
        for path in paths:
            mode = path.lstat().st_mode
            name = path.relative_to(product.parent).as_posix()
            info = zipfile.ZipInfo(name + '/' if stat.S_ISDIR(mode) else name)
            info.create_system = 3
            info.external_attr = mode << 16
            info.compress_type = zipfile.ZIP_DEFLATED
            if stat.S_ISLNK(mode):
                target = os.readlink(path)
                if Path(target).is_absolute() or not path.resolve().is_relative_to(product.resolve()):
                    raise ValueError('Artifact contém symlink fora do próprio bundle.')
                archive.writestr(info, target.encode())
            elif stat.S_ISREG(mode):
                archive.writestr(info, path.read_bytes())
            elif stat.S_ISDIR(mode):
                archive.writestr(info, b'')
            else:
                raise ValueError('Artifact contém tipo de arquivo não suportado.')


def build(repo, source_sha, platform, output, *, tooling_sha=None):
    repo, output = Path(repo).resolve(), Path(output).resolve()
    command = build_command(platform)
    actual_tooling_sha = git(TOOLING_REPOSITORY, 'rev-parse', 'HEAD')
    if (not re.fullmatch(r'[0-9a-f]{40}', actual_tooling_sha)
            or tooling_sha is not None and tooling_sha != actual_tooling_sha):
        raise ValueError('Ferramentas não correspondem ao commit do caller.')
    tree = _snapshot(repo, source_sha)
    if platform == 'ios' and host_platform.system() != 'Darwin':
        raise ValueError('Build iOS exige runner macOS.')
    inputs = json.loads(git(repo, 'show', source_sha + ':delivery/build-inputs.json'))
    if (not re.fullmatch(r'[0-9]+\.[0-9]+\.[0-9]+', inputs.get('flutter_version', ''))
            or not re.fullmatch(r'[0-9a-f]{40}', inputs.get('flutter_revision', ''))):
        raise ValueError('Toolchain Flutter sem versão/revisão fixadas.')
    command = build_command(platform, inputs.get('dart_defines', {}))
    actual = json.loads(subprocess.check_output(['flutter', '--version', '--machine'], cwd=repo))
    if (actual.get('frameworkVersion') != inputs['flutter_version']
            or actual.get('frameworkRevision') != inputs['flutter_revision']):
        raise ValueError('SDK instalado diverge dos inputs aprovados.')
    product = _product(repo, platform)
    if product.exists() or product.is_symlink() or output.exists():
        raise ValueError('Saída existente: use checkout e diretório novos; não reutilize build antigo.')
    subprocess.run(['flutter', 'pub', 'get', '--enforce-lockfile'], cwd=repo, check=True)
    subprocess.run(command, cwd=repo, check=True)
    if _snapshot(repo, source_sha) != tree:
        raise ValueError('Árvore do snapshot mudou durante o build.')
    _validate_product(product, platform)
    output.mkdir(parents=True)
    archive = output / 'mobile.zip'
    _package_product(product, archive)
    metadata = {'schema': 1, 'source_sha': source_sha, 'source_tree': tree,
                'tooling_sha': actual_tooling_sha,
                'platform': platform, 'artifact_kind': KINDS[platform],
                'sha256': hashlib.sha256(archive.read_bytes()).hexdigest(),
                'flutter_version': inputs['flutter_version'],
                'flutter_revision': inputs['flutter_revision'],
                'command': command, 'dart_defines': inputs.get('dart_defines', {}),
                'host_os': host_platform.system(),
                'distribution_performed': False, 'store_upload_performed': False,
                'shorebird_artifact': False, 'patch_compatibility_validated': False,
                'signing': 'unsigned' if platform == 'ios' else 'project-configuration-not-verified'}
    (output / 'metadata.json').write_text(json.dumps(metadata, ensure_ascii=False, indent=2) + '\n')
    if os.environ.get('GITHUB_OUTPUT'):
        with open(os.environ['GITHUB_OUTPUT'], 'a') as f:
            f.write('sha256=' + metadata['sha256'] + '\n')
            f.write('artifact_kind=' + metadata['artifact_kind'] + '\n')
    return metadata


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--repo', type=Path, required=True)
    parser.add_argument('--source-sha', required=True)
    parser.add_argument('--tooling-sha', required=True, help='SHA completo do caller e checkout pipeline')
    parser.add_argument('--platform', choices=tuple(KINDS), required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args(argv)
    try:
        result = build(args.repo, args.source_sha, args.platform, args.output, tooling_sha=args.tooling_sha)
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0
    except (ValueError, OSError, subprocess.CalledProcessError, zipfile.BadZipFile) as error:
        print('Build mobile bloqueado: ' + str(error), file=sys.stderr)
        return 1


if __name__ == '__main__':
    sys.exit(main())
