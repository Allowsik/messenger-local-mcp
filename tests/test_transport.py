import json
import tempfile
import threading
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from messenger_mcp.core import App, Matrix, MatrixError
from messenger_mcp.sending import send_text


class TransportTests(unittest.TestCase):
    def setUp(self):
        self.requests = []
        requests = self.requests

        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *args):
                pass

            def do_GET(self):
                requests.append(self.path)
                if self.path.endswith('/redirect'):
                    self.send_response(302)
                    self.send_header('Location', '/credential-sink')
                    self.end_headers()
                    return
                self.send_response(200 if self.path.endswith('/invalid') else 403)
                self.end_headers()
                self.wfile.write(b'not-json' if self.path.endswith('/invalid') else b'{"error":"sensitive upstream content"}')

            def do_PUT(self):
                body = json.loads(self.rfile.read(int(self.headers['Content-Length'])))
                requests.append((self.path, body))
                self.send_response(200)
                self.end_headers()
                self.wfile.write(b'{"event_id":"$synthetic:test"}')

        self.http = ThreadingHTTPServer(('127.0.0.1', 0), Handler)
        self.thread = threading.Thread(target=self.http.serve_forever, daemon=True)
        self.thread.start()
        self.url = f'http://127.0.0.1:{self.http.server_port}'

    def tearDown(self):
        self.http.shutdown()
        self.http.server_close()
        self.thread.join()

    def test_redirect_is_not_followed(self):
        with self.assertRaises(MatrixError) as caught:
            Matrix(self.url, 'synthetic-token').request('GET', '/redirect')
        self.assertEqual(caught.exception.status, 302)
        self.assertEqual(self.requests, ['/_matrix/client/v3/redirect'])

    def test_error_body_is_not_exposed(self):
        with self.assertRaises(MatrixError) as caught:
            Matrix(self.url).request('GET', '/forbidden')
        self.assertEqual(caught.exception.status, 403)
        self.assertNotIn('sensitive', str(caught.exception))

    def test_invalid_json_is_a_transport_error(self):
        with self.assertRaises(MatrixError):
            Matrix(self.url).request('GET', '/invalid')

    def test_real_http_send_is_deduplicated_across_app_instances(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            (root / 'runtime').mkdir()
            config = root / 'config.json'
            config.write_text(json.dumps({'homeserver': self.url, 'user_id': '@owner:test',
                                          'allowed_rooms': {'!allowed:test': 'Synthetic'}, 'send_mode': 'direct'}))
            (root / 'runtime/session.json').write_text(json.dumps({'homeserver': self.url,
                'user_id': '@owner:test', 'access_token': 'synthetic-token'}))
            first = send_text(App(config), '!allowed:test', 'Synthetic transport test', 'transport-test-001')
            second = send_text(App(config), '!allowed:test', 'Synthetic transport test', 'transport-test-001')
            self.assertEqual(first['status'], 'accepted')
            self.assertEqual(second['event_id'], first['event_id'])
            self.assertEqual(len(self.requests), 1)
            self.assertIn('/rooms/%21allowed%3Atest/send/m.room.message/mcp-', self.requests[0][0])
            self.assertEqual(self.requests[0][1]['body'], 'Synthetic transport test')
