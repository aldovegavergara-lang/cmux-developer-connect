#!/usr/bin/env python3
"""Behavioral HTTP admission/routing tests over a disposable local app fixture."""
import base64
import importlib.util
import json
import os
from pathlib import Path
import socket
import tempfile
import threading
import time
import unittest
import urllib.error
import urllib.request
import uuid

RESOURCE = Path(__file__).resolve().parents[1] / 'Resources/bin'
SPEC = importlib.util.spec_from_file_location('mobile_menu', RESOURCE / 'cmux-mobile-menu.py')
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


class NativeAppFixture:
    def __init__(self, socket_path):
        self.path = socket_path
        self.calls = []
        self.workspaces = []
        for name in ('Coordinador', '<script>foreign</script>', 'Otra ventana'):
            self.workspaces.append({'id': str(uuid.uuid4()).upper(), 'window_id': 'window-fixture',
                'title': name, 'current_directory': '/tmp/project', 'terminals': [
                    {'id': str(uuid.uuid4()).upper(), 'title': name, 'is_ready': True, 'is_focused': True}]})
        self.listener = socket.socket(socket.AF_UNIX)
        self.listener.bind(str(socket_path))
        self.listener.listen(5)
        self.listener.settimeout(0.1)
        self.running = True
        self.thread = threading.Thread(target=self.run)
        self.thread.start()

    def run(self):
        while self.running:
            try:
                conn, _ = self.listener.accept()
            except socket.timeout:
                continue
            with conn:
                raw = bytearray()
                while b'\n' not in raw:
                    raw.extend(conn.recv(65536))
                request = json.loads(raw)
                self.calls.append((request['method'], request['params']))
                if request['method'] == 'mobile.workspace.list':
                    result = {'workspaces': self.workspaces}
                elif request['method'] == 'mobile.terminal.replay':
                    result = {'surface_id': request['params']['surface_id'], 'render_grid': {
                        'format': 'cmux.render-grid.v1', 'columns': 80, 'rows': 20,
                        'row_spans': [{'row': 0, 'column': 0, 'text': '<img src=x onerror=alert(1)>', 'cell_width': 30, 'style_id': 0}],
                        'styles': [{'id': 0, 'foreground': '#ff00ff', 'background': '#141824'}],
                        'cursor': {'visible': True, 'row': 1, 'column': 0}}}
                else:
                    result = {'queued': False}
                conn.sendall((json.dumps({'id': request['id'], 'ok': True, 'result': result}) + '\n').encode())

    def close(self):
        self.running = False
        self.thread.join(timeout=2)
        self.listener.close()


class MenuTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='cmux-menu-test-', dir='/tmp')
        self.fixture = NativeAppFixture(Path(self.temp.name) / 'app.sock')
        self.allowed = self.fixture.workspaces[:2]
        self.menu = MODULE.NativeSessionMenu(self.fixture.path, workspace_ids=[w['id'] for w in self.allowed])
        self.server = MODULE.MenuHTTPServer(('127.0.0.1', 0), self.menu, 'developer:TEST_CREDENTIAL_ONLY', RESOURCE / 'cmux-mobile-menu.html')
        self.thread = threading.Thread(target=self.server.serve_forever)
        self.thread.start()
        self.url = f'http://127.0.0.1:{self.server.server_port}'

    def tearDown(self):
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(timeout=2)
        self.fixture.close()
        self.temp.cleanup()

    def request(self, path, body=None, auth=True, csrf=True, origin=None):
        headers = {}
        if auth:
            headers['Authorization'] = 'Basic ' + base64.b64encode(b'developer:TEST_CREDENTIAL_ONLY').decode()
        if body is not None:
            headers.update({'Content-Type': 'application/json', 'Origin': origin or self.url})
            if csrf:
                headers['X-Cmux-Action'] = self.menu.csrf
        data = json.dumps(body).encode() if body is not None else None
        response = urllib.request.urlopen(urllib.request.Request(self.url + path, data=data, headers=headers), timeout=5)
        return response.status, response.read(), response.headers

    def body(self, index=0):
        workspace = self.allowed[index]
        return {'workspace_id': workspace['id'], 'surface_id': workspace['terminals'][0]['id'], 'text': 'HELLO\r'}

    def assert_rejected(self, status, path, **kwargs):
        with self.assertRaises(urllib.error.HTTPError) as error:
            self.request(path, **kwargs)
        self.assertEqual(error.exception.code, status)

    def test_authenticated_catalog_and_menu_headers(self):
        self.assert_rejected(401, '/', auth=False)
        status, data, headers = self.request('/')
        self.assertEqual(status, 200)
        self.assertIn(b'sessionsButton', data)
        self.assertIn('frame-ancestors', headers['Content-Security-Policy'])
        _, rows, _ = self.request('/api/sessions')
        self.assertEqual([row['id'] for row in json.loads(rows)['workspaces']], [w['id'] for w in self.allowed])

    def test_selection_reads_distinct_real_surface_identity_and_colors(self):
        for row in self.allowed:
            surface = row['terminals'][0]['id']
            _, data, _ = self.request('/api/replay?workspace=' + row['id'] + '&surface=' + surface)
            reply = json.loads(data)
            self.assertEqual(reply['surface_id'], surface)
            self.assertEqual(reply['grid']['styles'][0]['foreground'], '#ff00ff')
        methods = [method for method, _ in self.fixture.calls]
        self.assertNotIn('workspace.select', methods)
        self.assertNotIn('surface.focus', methods)

    def test_unknown_and_cross_workspace_targets_never_reach_input(self):
        bad = self.body()
        bad['surface_id'] = self.allowed[1]['terminals'][0]['id']
        self.assert_rejected(404, '/api/input', body=bad)
        foreign = self.fixture.workspaces[2]
        self.assert_rejected(404, '/api/input', body={'workspace_id': foreign['id'], 'surface_id': foreign['terminals'][0]['id'], 'text': 'x'})
        self.assertFalse(any(method == 'mobile.terminal.input' for method, _ in self.fixture.calls))

    def test_csrf_origin_readonly_and_arbitrary_method_denied(self):
        self.assert_rejected(403, '/api/input', body=self.body(), csrf=False)
        self.assert_rejected(403, '/api/input', body=self.body(), origin='https://attacker.example')
        self.assert_rejected(400, '/api/input', body={**self.body(), 'command': 'run-me'})
        malformed = self.body()
        malformed.pop('text')
        malformed['key'] = ['enter']
        self.assert_rejected(400, '/api/input', body=malformed)
        self.assert_rejected(404, '/api/rpc', body={'method': 'workspace.close'})
        self.menu.readonly = True
        self.assert_rejected(403, '/api/input', body=self.body())
        self.assertFalse(any(method == 'mobile.terminal.input' for method, _ in self.fixture.calls))

    def test_input_routed_to_selected_target_and_gone_session_rejected(self):
        for index in range(2):
            self.request('/api/input', body=self.body(index))
        inputs = [params for method, params in self.fixture.calls if method == 'mobile.terminal.input']
        self.assertEqual([params['surface_id'] for params in inputs], [w['terminals'][0]['id'] for w in self.allowed])
        self.fixture.workspaces.remove(self.allowed[0])
        self.assert_rejected(404, '/api/input', body=self.body())
        self.menu.expires_at = time.time() - 1
        self.assert_rejected(410, '/api/sessions')


if __name__ == '__main__':
    unittest.main(verbosity=2)
