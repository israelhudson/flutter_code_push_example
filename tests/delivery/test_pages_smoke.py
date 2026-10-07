"""HTTP identity, CDN propagation, and asset boundaries of Pages smoke checks."""
import hashlib
import importlib.util
import io
import json
from pathlib import Path
import unittest
from unittest.mock import patch
from urllib.error import HTTPError

ROOT = Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location('pages_smoke', ROOT / 'deploy/pages_smoke.py')
smoke = importlib.util.module_from_spec(spec)
spec.loader.exec_module(smoke)


class PagesSmokeTests(unittest.TestCase):
    def setUp(self):
        self.sha = 'a' * 40
        self.url = smoke.ORIGIN + smoke.PROJECT_BASE + 'snapshots/' + self.sha + '/'
        self.href = smoke.PROJECT_BASE + 'snapshots/' + self.sha + '/app/'
        self.files = {
            'index.html': ('<header>' + self.sha + '</header><iframe src="app/"></iframe>').encode(),
            'app/index.html': ('<base href="' + self.href + '"><script src="flutter_bootstrap.js" async></script>').encode(),
            'app/flutter_bootstrap.js': b'_flutter.loader.load({mainJsPath:"main.dart.js"});',
            'app/main.dart.js': b'compiled app bytes',
            'app/assets/AssetManifest.bin': b'not downloaded by this smoke check',
        }
        self.refresh_manifest()
        self.requests = []
        self.elapsed = 0
        self.sleeps = []

    def refresh_manifest(self):
        app = {name[4:]: hashlib.sha256(data).hexdigest()
               for name, data in self.files.items() if name.startswith('app/')}
        self.expected = smoke.digest(app)
        metadata = {'schema': 'pages-preview-v1', 'source_sha': self.sha,
                    'snapshot_path': 'snapshots/' + self.sha + '/', 'web_content_sha256': self.expected}
        self.files['metadata.json'] = json.dumps(metadata).encode()
        manifest = {name: hashlib.sha256(data).hexdigest() for name, data in self.files.items()
                    if name != 'files.json'}
        self.files['files.json'] = json.dumps(manifest).encode()

    def get(self, url, timeout):
        self.assertTrue(url.startswith(self.url))
        self.assertGreater(timeout, 0)
        self.assertLessEqual(timeout, 10)
        name = url[len(self.url):]
        self.requests.append(name)
        return self.files[name]

    def sleep(self, seconds):
        self.assertLessEqual(seconds, 10)
        self.sleeps.append(seconds)
        self.elapsed += seconds

    def verify(self, request=None):
        return smoke.verify(self.sha, self.expected, request=request or self.get,
                            now=lambda: self.elapsed, sleep=self.sleep)

    def test_confirms_snapshot_and_attests_full_map_without_downloading_engine(self):
        report = self.verify()
        self.assertIs(report['success'], True)
        self.assertEqual(report['snapshot_url'], self.url)
        self.assertEqual(report['web_content_sha256'], self.expected)
        self.assertEqual(self.requests, ['metadata.json', 'files.json', *smoke.CRITICAL_FILES])
        self.assertNotIn('app/assets/AssetManifest.bin', self.requests)

    def test_map_hash_must_match_trusted_build_even_if_metadata_claims_it_does(self):
        manifest = json.loads(self.files['files.json'])
        manifest['app/assets/AssetManifest.bin'] = 'b' * 64
        self.files['files.json'] = json.dumps(manifest).encode()
        with self.assertRaisesRegex(smoke.SmokeError, 'Mapa de arquivos'):
            self.verify()
        self.assertEqual(self.sleeps, [])

    def test_wrong_metadata_or_main_bytes_fail_without_retry(self):
        self.files['app/main.dart.js'] = b'replaced bytes'
        with self.assertRaisesRegex(smoke.SmokeError, 'Bytes publicados'):
            self.verify()
        self.assertEqual(self.sleeps, [])
        metadata = json.loads(self.files['metadata.json'])
        metadata['source_sha'] = 'b' * 40
        self.files['metadata.json'] = json.dumps(metadata).encode()
        with self.assertRaisesRegex(smoke.SmokeError, 'Metadata diverge'):
            self.verify()

    def test_base_href_and_bootstrap_reference_are_checked_beyond_hashes(self):
        self.files['app/index.html'] = b'<base href="/"><script src="flutter_bootstrap.js"></script>'
        self.refresh_manifest()
        with self.assertRaisesRegex(smoke.SmokeError, 'Base href/bootstrap'):
            self.verify()
        self.files['app/index.html'] = ('<base href="' + self.href + '"><script src="wrong.js"></script>').encode()
        self.refresh_manifest()
        with self.assertRaisesRegex(smoke.SmokeError, 'Base href/bootstrap'):
            self.verify()

    def test_unsafe_manifest_paths_fail_before_asset_requests(self):
        for name in ('../private', 'app/../private', '/outside', 'https://outside/a',
                     'app/%2e%2e/private', 'app/main.dart.js?x=1', 'app\\private', 'app/.env'):
            with self.subTest(name=name):
                manifest = json.loads(self.files['files.json'])
                manifest[name] = 'b' * 64
                poisoned = json.dumps(manifest).encode()
                def get(url, timeout):
                    if url.endswith('/files.json'):
                        return poisoned
                    return self.get(url, timeout)
                with self.assertRaisesRegex(smoke.SmokeError, 'Caminho público'):
                    self.verify(request=get)
        self.assertEqual(self.sleeps, [])

    def test_retries_propagation_and_stops_at_190_seconds(self):
        attempts = 0
        def eventually(url, timeout):
            nonlocal attempts
            if url.endswith('/metadata.json'):
                attempts += 1
                if attempts <= 2:
                    raise smoke.PropagationPending('HTTP 404')
            return self.get(url, timeout)
        self.assertEqual(self.verify(request=eventually)['attempts'], 3)
        self.assertEqual(self.sleeps, [10, 10])
        self.elapsed, self.sleeps = 0, []
        def unavailable(url, timeout):
            raise smoke.PropagationPending('HTTP 503')
        with self.assertRaisesRegex(smoke.SmokeError, '190 segundos'):
            self.verify(request=unavailable)
        self.assertEqual(self.elapsed, 190)

    def test_http_only_retries_selected_statuses_and_refuses_redirects(self):
        for status in (404, 502, 503, 504, 301, 302, 403, 429, 500):
            with self.subTest(status=status), patch.object(smoke, 'build_opener') as opener:
                opener.return_value.open.side_effect = HTTPError(self.url, status, 'fixture', {}, io.BytesIO())
                expected = smoke.PropagationPending if status in (404, 502, 503, 504) else smoke.SmokeError
                with self.assertRaises(expected):
                    smoke.fetch(self.url, 1)
        self.assertIsNone(smoke.NoRedirect().redirect_request(None, None, 302, '', {}, 'https://outside/'))


if __name__ == '__main__':
    unittest.main()
