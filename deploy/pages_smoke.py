"""Confirm a deployed, SHA-addressed Pages preview using read-only HTTP GETs.

The expected app and snapshot-manifest digests come from the trusted build job.
This check attests the complete file map and downloads only entry points and JS;
browser interaction and Android/iOS validation remain separate checks.
"""
import argparse
import hashlib
from html.parser import HTMLParser
import json
from pathlib import Path
import re
import sys
import time
from urllib.error import HTTPError, URLError
from urllib.request import HTTPRedirectHandler, Request, build_opener

ORIGIN = 'https://israelhudson.github.io'
PROJECT_BASE = '/flutter_code_push_example/'
MAX_WAIT_SECONDS = 190
RETRY_SECONDS = 10
MAX_RESPONSE_BYTES = 32 * 1024 * 1024
CRITICAL_FILES = ('index.html', 'app/index.html', 'app/flutter_bootstrap.js', 'app/main.dart.js')


class SmokeError(ValueError):
    """Integrity/configuration failure: retrying must not hide it."""


class PropagationPending(Exception):
    """Only an HTTP status compatible with delayed CDN propagation."""


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, request, response, code, message, headers, new_url):
        return None


def digest(value):
    data = json.dumps(value, sort_keys=True, separators=(',', ':'), ensure_ascii=False).encode()
    return hashlib.sha256(data).hexdigest()


def relative_path(value):
    if (not isinstance(value, str) or not value or value.startswith('/')
            or any(char in value for char in '\\%?#:')
            or any(ord(char) < 32 or ord(char) == 127 for char in value)
            or any(part in ('', '.', '..') or part.startswith('.') for part in value.split('/'))):
        raise SmokeError('Caminho público relativo inválido.')
    return value


def fetch(url, timeout):
    # No authentication, redirects, or alternate origin; every URL is assembled
    # from the fixed host/snapshot prefix and validated relative file names.
    request = Request(url, headers={'User-Agent': 'flutter-pages-smoke/1', 'Cache-Control': 'no-cache'})
    try:
        with build_opener(NoRedirect()).open(request, timeout=timeout) as response:
            if response.status != 200:
                raise SmokeError('Resposta HTTP inesperada: ' + str(response.status))
            data = response.read(MAX_RESPONSE_BYTES + 1)
    except HTTPError as error:
        error.close()
        if error.code in (404, 502, 503, 504):
            raise PropagationPending('HTTP ' + str(error.code)) from error
        raise SmokeError('HTTP recusado: ' + str(error.code)) from error
    except (URLError, TimeoutError) as error:
        raise SmokeError('Falha de conexão HTTP; não confirmada como propagação CDN.') from error
    if len(data) > MAX_RESPONSE_BYTES:
        raise SmokeError('Resposta ultrapassa limite de 32 MiB.')
    return data


def json_object(data):
    def unique(pairs):
        result = {}
        for key, value in pairs:
            if key in result:
                raise SmokeError('JSON contém chave duplicada.')
            result[key] = value
        return result
    try:
        result = json.loads(data, object_pairs_hook=unique)
    except (ValueError, UnicodeDecodeError) as error:
        raise SmokeError('JSON público inválido.') from error
    if not isinstance(result, dict):
        raise SmokeError('JSON público precisa ser um objeto.')
    return result


class EntryHTML(HTMLParser):
    def __init__(self, data):
        super().__init__(convert_charrefs=True)
        self.bases, self.scripts, self.frames = [], [], []
        try:
            self.feed(data.decode('utf-8'))
        except UnicodeDecodeError as error:
            raise SmokeError('HTML público não é UTF-8.') from error

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if tag == 'base':
            self.bases.append(attrs.get('href'))
        elif tag == 'script' and 'src' in attrs:
            self.scripts.append(attrs['src'])
        elif tag == 'iframe':
            self.frames.append(attrs.get('src'))


def check_once(source_sha, expected_web_hash, expected_manifest_hash, get):
    manifest = json_object(get('files.json'))
    app_files = {}
    for name, file_hash in manifest.items():
        relative_path(name)
        if not isinstance(file_hash, str) or not re.fullmatch(r'[0-9a-f]{64}', file_hash):
            raise SmokeError('Hash de arquivo público inválido.')
        if name.startswith('app/'):
            app_files[name[4:]] = file_hash
        elif name not in ('index.html', 'metadata.json'):
            raise SmokeError('Arquivo fora do snapshot web permitido.')
    if digest(manifest) != expected_manifest_hash:
        raise SmokeError('Manifesto completo diverge do hash do build confiável.')
    if not app_files or digest(app_files) != expected_web_hash:
        raise SmokeError('Mapa de arquivos Flutter diverge do hash do build confiável.')
    metadata_bytes = get('metadata.json')
    metadata = json_object(metadata_bytes)
    if (metadata.get('schema') != 'pages-preview-v1' or metadata.get('source_sha') != source_sha
            or metadata.get('snapshot_path') != 'snapshots/' + source_sha + '/'
            or metadata.get('web_content_sha256') != expected_web_hash):
        raise SmokeError('Metadata diverge do SHA/hash produzido pelo build confiável.')
    if hashlib.sha256(metadata_bytes).hexdigest() != manifest.get('metadata.json'):
        raise SmokeError('Hash da metadata não confere.')
    downloaded = {}
    for name in CRITICAL_FILES:
        if name not in manifest:
            raise SmokeError('Arquivo principal ausente no manifesto: ' + name)
        data = get(name)
        if hashlib.sha256(data).hexdigest() != manifest[name]:
            raise SmokeError('Bytes publicados divergem do manifesto: ' + name)
        downloaded[name] = data
    base = PROJECT_BASE + 'snapshots/' + source_sha + '/app/'
    app_html = EntryHTML(downloaded['app/index.html'])
    if app_html.bases != [base] or 'flutter_bootstrap.js' not in app_html.scripts:
        raise SmokeError('Base href/bootstrap Flutter incorretos para o snapshot.')
    wrapper = EntryHTML(downloaded['index.html'])
    if wrapper.frames != ['app/'] or source_sha.encode() not in downloaded['index.html']:
        raise SmokeError('Página de entrada não identifica/abre o snapshot esperado.')
    if metadata.get('delivery_tag') is not None:
        tag = metadata['delivery_tag']
        if (not isinstance(tag, str) or not re.fullmatch(r'v\d+\.\d+\.\d+-rc\.[1-9]\d*', tag)
                or tag.encode() not in downloaded['index.html']):
            raise SmokeError('Identidade da entrega não confere com a página do snapshot.')
    return ['files.json', 'metadata.json', *CRITICAL_FILES]


def verify(source_sha, expected_web_hash, expected_manifest_hash, *, request=fetch, now=time.monotonic, sleep=time.sleep):
    if not re.fullmatch(r'[0-9a-f]{40}', source_sha or ''):
        raise SmokeError('Informe SHA40 completo.')
    if not re.fullmatch(r'[0-9a-f]{64}', expected_web_hash or ''):
        raise SmokeError('Informe hash web SHA-256 do build confiável.')
    if not re.fullmatch(r'[0-9a-f]{64}', expected_manifest_hash or ''):
        raise SmokeError('Informe hash SHA-256 do manifesto completo do build confiável.')
    snapshot_url = ORIGIN + PROJECT_BASE + 'snapshots/' + source_sha + '/'
    deadline = now() + MAX_WAIT_SECONDS
    attempts = 0

    def get(name):
        remaining = deadline - now()
        if remaining <= 0:
            raise SmokeError('Verificação HTTP excedeu 190 segundos.')
        data = request(snapshot_url + relative_path(name), min(10, remaining))
        if now() > deadline:
            raise SmokeError('Verificação HTTP excedeu 190 segundos.')
        return data

    while True:
        attempts += 1
        try:
            verified = check_once(source_sha, expected_web_hash, expected_manifest_hash, get)
            return {'success': True, 'source_sha': source_sha,
                    'web_content_sha256': expected_web_hash,
                    'snapshot_manifest_sha256': expected_manifest_hash, 'snapshot_url': snapshot_url,
                    'verified_files': verified, 'attempts': attempts}
        except PropagationPending as error:
            remaining = deadline - now()
            if remaining <= 0:
                raise SmokeError('Snapshot indisponível após 190 segundos: ' + str(error)) from error
            print('Aguardando propagação Pages: ' + str(error), file=sys.stderr)
            sleep(min(RETRY_SECONDS, remaining))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source-sha', required=True)
    parser.add_argument('--expected-web-content-sha256', required=True)
    parser.add_argument('--expected-snapshot-manifest-sha256', required=True)
    parser.add_argument('--output')
    args = parser.parse_args()
    report = verify(args.source_sha, args.expected_web_content_sha256, args.expected_snapshot_manifest_sha256)
    output = json.dumps(report, ensure_ascii=False, indent=2) + '\n'
    if args.output:
        Path(args.output).write_text(output, encoding='utf-8')
    print(output, end='')


if __name__ == '__main__':
    main()
