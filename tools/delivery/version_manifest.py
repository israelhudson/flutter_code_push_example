"""Frozen delivery identity and per-platform version plan; never a publisher.

The LAB adapter attests a web preview only. A pubspec version is build metadata,
not evidence of an installed Android/iOS version or a generated Shorebird patch.
Actual mobile outcomes must later be recorded in a separate provider receipt.
"""
import argparse
import copy
import html
import json
from pathlib import Path
import re

from policy import digest

SCHEMA = 'delivery-platform-versions-v1'
SHA = re.compile(r'[0-9a-f]{40}')
HASH = re.compile(r'[0-9a-f]{64}')
TAG = re.compile(r'v(\d+\.\d+\.\d+)-rc\.([1-9]\d*)')
APP_VERSION = re.compile(r'(\d+\.\d+\.\d+(?:-[0-9A-Za-z]+(?:[.-][0-9A-Za-z]+)*)?)\+([0-9]+)')
APP_ID = re.compile(r'[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}')
PREVIEW_ORIGIN = 'https://israelhudson.github.io/flutter_code_push_example/snapshots/'


def split_app_version(value):
    match = APP_VERSION.fullmatch(value or '') if isinstance(value, str) else None
    if not match:
        raise ValueError('Versão do app exige versão+build explícitos; latest não é uma base.')
    return {'version': match[1], 'build_number': match[2], 'release_version': value}


def patch_identity(app_id, platform, release_version, patch_number):
    """An unambiguous identifier; this does not prove generation/distribution."""
    if not isinstance(app_id, str) or not APP_ID.fullmatch(app_id):
        raise ValueError('Patch exige app_id Shorebird explícito.')
    if platform not in ('android', 'ios'):
        raise ValueError('Patch deve identificar Android ou iOS; web não usa Shorebird.')
    split_app_version(release_version)
    if type(patch_number) is not int or patch_number < 1:
        raise ValueError('Número do patch exige inteiro positivo confirmado pelo provedor.')
    return {'app_id': app_id, 'platform': platform, 'release_version': release_version,
            'patch_number': patch_number}


def build_manifest(*, candidate_tag, stable_tag, source_sha, pubspec_version, platforms, preview):
    app_metadata = split_app_version(pubspec_version)
    if not isinstance(platforms, dict) or set(platforms) - {'android', 'ios'}:
        raise ValueError('Plano mobile admite somente Android e iOS.')
    mobile = {}
    for platform in ('android', 'ios'):
        platform_data = platforms.get(platform, {})
        if not isinstance(platform_data, dict):
            raise ValueError('Identidade mobile deve ser um objeto por plataforma.')
        base = platform_data.get('base')
        if base is not None:
            if not isinstance(base, dict) or not SHA.fullmatch(str(base.get('source_sha', ''))):
                raise ValueError('Base mobile exige SHA40 completo.')
            base = copy.deepcopy(base)
            version = split_app_version(base.get('release_version'))
            base_identity = {'source_sha': base['source_sha'], 'release_version': version['release_version'],
                             'app_id': base.get('app_id'), 'flavor': base.get('flavor'),
                             'verification': 'configured_unverified'}
        else:
            version, base_identity = None, None
        mobile[platform] = {
            'platform': platform, 'planned_app_version': version,
            'observed_app_version': None, 'shorebird_base': base_identity,
            'patch_number': None, 'patch_status': 'not_generated',
            'distribution_status': 'not_performed', 'provider_receipt': None,
            'evidence': 'Base configurada é intenção; nenhum build mobile, patch ou distribuição foi executado.'}
    value = {
        'schema': SCHEMA,
        'delivery': {'candidate_tag': candidate_tag, 'stable_tag': stable_tag, 'source_sha': source_sha},
        'pubspec_metadata': app_metadata,
        'platforms': {**mobile, 'web': {
            'platform': 'web', 'app_version': app_metadata, 'build_id': source_sha,
            'web_content_sha256': preview.get('web_content_sha256'),
            'snapshot_manifest_sha256': preview.get('snapshot_manifest_sha256'),
            'preview_url': preview.get('snapshot_url'),
            'preview_verified': preview.get('success') is True and preview.get('source_sha') == source_sha,
            'shorebird_status': 'not_applicable', 'patch_number': None,
            'distribution_status': 'preview_only'}},
        'distribution_performed': False,
        'note': 'A tag identifica a entrega. Versões e resultados de cada plataforma têm identidade própria.'}
    validate_manifest(value)
    return value


def validate_manifest(value):
    if not isinstance(value, dict) or value.get('schema') != SCHEMA:
        raise ValueError('Manifesto de versões desconhecido.')
    delivery = value.get('delivery', {})
    tag = TAG.fullmatch(str(delivery.get('candidate_tag', '')))
    if (not tag or delivery.get('stable_tag') != 'v' + tag[1]
            or not SHA.fullmatch(str(delivery.get('source_sha', '')))):
        raise ValueError('Entrega exige RC, tag estável correspondente e SHA40 congelado.')
    app_metadata = value.get('pubspec_metadata', {})
    if not isinstance(app_metadata, dict) or app_metadata != split_app_version(app_metadata.get('release_version')):
        raise ValueError('Versão e build do pubspec divergentes.')
    if value.get('distribution_performed') is not False:
        raise ValueError('Este manifesto é plano LAB; resultado mobile exige recibo do provedor separado.')
    platforms = value.get('platforms', {})
    if not isinstance(platforms, dict) or set(platforms) != {'android', 'ios', 'web'}:
        raise ValueError('Manifesto exige identidade Android, iOS e web separada.')
    for platform in ('android', 'ios'):
        item = platforms[platform]
        if not isinstance(item, dict):
            raise ValueError('Identidade mobile deve ser um objeto por plataforma.')
        if (item.get('platform') != platform or item.get('patch_number') is not None
                or item.get('patch_status') != 'not_generated'
                or item.get('distribution_status') != 'not_performed'
                or item.get('observed_app_version') is not None
                or item.get('provider_receipt') is not None):
            raise ValueError('Plano mobile não pode inventar patch, instalação ou distribuição.')
        base = item.get('shorebird_base')
        planned = item.get('planned_app_version')
        if base is None:
            if planned is not None:
                raise ValueError('Versão mobile planejada exige base explícita.')
        else:
            if not isinstance(base, dict):
                raise ValueError('Base mobile deve ser um objeto.')
            version = split_app_version(base.get('release_version'))
            if (not SHA.fullmatch(str(base.get('source_sha', '')))
                    or planned != version or base.get('verification') != 'configured_unverified'):
                raise ValueError('Versão/base mobile planejada divergente ou alegação de verificação indevida.')
            if base.get('app_id') is not None and not APP_ID.fullmatch(str(base['app_id'])):
                raise ValueError('app_id Shorebird inválido.')
            flavor = base.get('flavor')
            if flavor is not None and not re.fullmatch(r'[A-Za-z0-9_-]{1,80}', str(flavor)):
                raise ValueError('Flavor mobile inválido.')
    web = platforms['web']
    if not isinstance(web, dict):
        raise ValueError('Identidade web deve ser um objeto.')
    source = delivery['source_sha']
    if (web.get('platform') != 'web' or web.get('build_id') != source
            or web.get('app_version') != value['pubspec_metadata']
            or web.get('preview_verified') is not True
            or web.get('shorebird_status') != 'not_applicable'
            or web.get('patch_number') is not None or web.get('distribution_status') != 'preview_only'
            or web.get('preview_url') != PREVIEW_ORIGIN + source + '/'
            or any(not HASH.fullmatch(str(web.get(k, ''))) for k in ('web_content_sha256', 'snapshot_manifest_sha256'))):
        raise ValueError('Identidade web exige preview verificado, hashes e ausência de patch Shorebird.')
    return value


def render_markdown(value):
    validate_manifest(value)
    delivery = value['delivery']
    lines = ['## Entrega e versões por plataforma', '',
             '**Entrega:** ' + delivery['candidate_tag'] + ' → ' + delivery['stable_tag'] + '.',
             '**Código congelado:** `' + delivery['source_sha'] + '`.',
             '**Metadado pubspec do build web:** ' + html.escape(value['pubspec_metadata']['release_version']) + '.', '',
             '| Plataforma | Versão do app / build | Base Shorebird | Patch | Resultado |',
             '|---|---|---|---|---|']
    for platform in ('android', 'ios'):
        item = value['platforms'][platform]
        planned = item['planned_app_version']
        app = planned['version'] + ' / ' + planned['build_number'] + ' (alvo configurado, não verificado)' if planned else 'Não verificada'
        base = html.escape(item['shorebird_base']['release_version']) if item['shorebird_base'] else 'Não configurada'
        lines += ['| ' + platform + ' | ' + app + ' | ' + base + ' | Não gerado | Não distribuído |']
    web = value['platforms']['web']
    lines += ['| web | ' + html.escape(web['app_version']['version']) + ' / ' + web['app_version']['build_number']
              + ' (metadado compilado) | Não se aplica | Não se aplica | Preview publicado e verificado; produção web não comprovada |', '',
              '**Identidade web:** build `' + web['build_id'] + '`; bytes SHA-256 `' + web['web_content_sha256'] + '`.',
              '**Manifesto de versões SHA-256:** `' + digest(value) + '`.', '',
              'A tag da entrega não altera automaticamente a versão instalada. Um patch futuro será identificado por app_id, plataforma, release-base exata e número retornado pelo Shorebird.']
    return '\n'.join(lines) + '\n'


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--report', required=True)
    parser.add_argument('--output', required=True)
    args = parser.parse_args()
    report = json.loads(Path(args.report).read_text(encoding='utf-8'))
    value = build_manifest(candidate_tag=report['candidate_tag'], stable_tag=report['stable_tag'],
                           source_sha=report['source_sha'], pubspec_version=report['pubspec_version'],
                           platforms=report.get('platforms', {}), preview=report['preview'])
    folder = Path(args.output)
    folder.mkdir(parents=True, exist_ok=True)
    (folder / 'version-manifest.json').write_text(json.dumps(value, ensure_ascii=False, indent=2) + '\n')
    (folder / 'version-manifest.md').write_text(render_markdown(value), encoding='utf-8')
    print(json.dumps({'version_manifest_digest': digest(value), 'distribution_performed': False}))


if __name__ == '__main__':
    main()
