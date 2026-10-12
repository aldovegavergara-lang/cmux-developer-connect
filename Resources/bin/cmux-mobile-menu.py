#!/usr/bin/env python3
"""Authenticated, bounded menu over one locally authorized cmux app socket."""
import base64
import hashlib
import hmac
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import os
from pathlib import Path
import secrets
import select
import socket
import stat
import threading
import time
from urllib.parse import parse_qs, urlsplit
import sys
sys.path.insert(0, str(Path(__file__).resolve().parent / 'peer'))
from http_limits import BoundedServerMixin, BoundedRequestMixin, strict_json
import uuid


class MenuError(Exception):
    def __init__(self, code, status=400):
        self.code, self.status = code, status


class NativeSessionMenu:
    def __init__(self, socket_path, readonly=False, expires_at=None, workspace_ids=None):
        self.socket_path = Path(socket_path)
        info = self.socket_path.stat()
        if not stat.S_ISSOCK(info.st_mode) or info.st_uid != os.getuid():
            raise MenuError('app_unavailable', 503)
        self.socket_identity = (info.st_dev, info.st_ino)
        self.readonly = readonly
        self.expires_at = expires_at or time.time() + 3600
        self.csrf = secrets.token_urlsafe(32)
        self.lock = threading.RLock()
        self.cache, self.cache_time = None, 0
        initial = self.rpc('mobile.workspace.list', {})['workspaces']
        # A grant covers this app's existing windows, never another socket/app.
        self.windows = {row['window_id'] for row in initial}
        self.workspace_ids = {str(uuid.UUID(value)).upper() for value in workspace_ids} if workspace_ids else None

    def rpc(self, method, params, admission=None):
        with self.lock, socket.socket(socket.AF_UNIX) as connection:
            if time.time() >= self.expires_at:
                raise MenuError('expired', 410)
            info = self.socket_path.lstat()
            if (info.st_dev, info.st_ino) != self.socket_identity:
                raise MenuError('app_unavailable', 503)
            if admission: admission()
            connection.settimeout(5)
            connection.connect(str(self.socket_path))
            connection.sendall((json.dumps({'id': str(uuid.uuid4()), 'method': method, 'params': params}) + '\n').encode())
            received = bytearray()
            while b'\n' not in received:
                chunk = connection.recv(65536)
                if not chunk or len(received) + len(chunk) > 4 * 1024 * 1024:
                    raise MenuError('app_unavailable', 503)
                received.extend(chunk)
            response = json.loads(received.split(b'\n', 1)[0])
        if not response.get('ok'):
            code = (response.get('error') or {}).get('code', '')
            raise MenuError('session_gone' if code in ('not_found', 'surface_unavailable') else 'app_unavailable', 409)
        return response['result']

    def catalog(self, refresh=False):
        with self.lock:
            if refresh or self.cache is None or time.monotonic() - self.cache_time > 1:
                result = self.rpc('mobile.workspace.list', {})
                rows = []
                for workspace in result['workspaces']:
                    if workspace.get('window_id') not in self.windows:
                        continue
                    if self.workspace_ids is not None and workspace['id'].upper() not in self.workspace_ids:
                        continue
                    terminals = [{key: terminal.get(key) for key in ('id', 'title', 'is_focused', 'is_ready', 'agent_state')}
                                 for terminal in workspace.get('terminals', [])]
                    if not terminals:
                        continue
                    rows.append({'id': workspace['id'], 'title': workspace['title'],
                                 'directory': Path(workspace.get('current_directory') or '').name,
                                 'selected_on_mac': workspace.get('is_selected', False),
                                 'unread': workspace.get('has_unread', False), 'terminals': terminals})
                self.cache, self.cache_time = rows, time.monotonic()
            return {'workspaces': self.cache, 'readonly': self.readonly,
                    'csrf': self.csrf, 'expires_at': self.expires_at}

    def target(self, workspace_id, surface_id):
        try:
            workspace_id, surface_id = str(uuid.UUID(workspace_id)).upper(), str(uuid.UUID(surface_id)).upper()
        except (ValueError, TypeError, AttributeError):
            raise MenuError('session_gone', 404)
        for row in self.catalog(refresh=True)['workspaces']:
            if row['id'].upper() == workspace_id:
                for terminal in row['terminals']:
                    if terminal['id'].upper() == surface_id:
                        return {'workspace_id': workspace_id, 'surface_id': surface_id}
        # Fail closed: never let native routing fall back to a focused terminal.
        raise MenuError('session_gone', 404)

    def replay(self, workspace_id, surface_id):
        params = self.target(workspace_id, surface_id)
        params.update(anchor='screen', max_scrollback_rows=100)
        reply = self.rpc('mobile.terminal.replay', params)
        grid = reply.get('render_grid')
        if not grid or grid.get('format') != 'cmux.render-grid.v1':
            raise MenuError('app_unavailable', 503)
        # Preserve authoritative geometry/colors, but omit host metadata and palette.
        fields = ('format', 'columns', 'rows', 'row_spans', 'styles', 'cursor',
                  'terminal_background', 'terminal_foreground', 'render_revision', 'render_epoch')
        return {'grid': {key: grid.get(key) for key in fields}, 'surface_id': reply['surface_id']}

    def input(self, body):
        if self.readonly:
            raise MenuError('readonly', 403)
        if set(body) - {'workspace_id', 'surface_id', 'text', 'key'}:
            raise MenuError('invalid_request')
        params = self.target(body.get('workspace_id'), body.get('surface_id'))
        keys = {'enter': '\r', 'escape': '\x1b', 'tab': '\t', 'interrupt': '\x03',
                'up': '\x1b[A', 'down': '\x1b[B', 'left': '\x1b[D', 'right': '\x1b[C', 'backspace': '\x7f'}
        if 'key' in body:
            if 'text' in body or not isinstance(body['key'], str) or body['key'] not in keys:
                raise MenuError('invalid_request')
            text = keys[body['key']]
        else:
            text = body.get('text')
            if not isinstance(text, str) or not text or len(text.encode()) > 8192:
                raise MenuError('invalid_request')
        params['text'] = text
        reply = self.rpc('mobile.terminal.input', params)
        return {'queued': bool(reply.get('queued')), 'surface_id': params['surface_id']}


class MenuHTTPServer(BoundedServerMixin, ThreadingHTTPServer):
    daemon_threads = True
    allow_reuse_address = True

    def __init__(self, address, menu, credential, html_path, terminal_port=None, terminal_socket=None, tls_context=None):
        self.menu, self.credential, self.terminal_port = menu, credential, terminal_port
        self.terminal_socket = terminal_socket
        self.html = Path(html_path).read_bytes()
        script = self.html.split(b'<script>', 1)[1].split(b'</script>', 1)[0]
        self.script_hash = base64.b64encode(hashlib.sha256(script).digest()).decode()
        self.configure_connection_limits(total=24, per_address=8, tls_context=tls_context)
        super().__init__(address, MenuHTTPHandler)


class MenuHTTPHandler(BoundedRequestMixin, BaseHTTPRequestHandler):
    protocol_version = 'HTTP/1.1'

    def log_message(self, *args):
        pass  # never log credentials, terminal text, or request/query contents

    def respond(self, status, data, content_type='application/json'):
        data = json.dumps(data).encode() if isinstance(data, dict) else data
        self.send_response(status)
        self.send_header('Content-Type', content_type)
        self.send_header('Content-Length', str(len(data)))
        self.send_header('Cache-Control', 'no-store')
        self.send_header('X-Content-Type-Options', 'nosniff')
        self.send_header('Referrer-Policy', 'no-referrer')
        if content_type.startswith('text/html'):
            self.send_header('Content-Security-Policy', "default-src 'self'; script-src 'sha256-" + self.server.script_hash + "'; style-src 'self' 'unsafe-inline'; frame-ancestors 'self'; object-src 'none'; base-uri 'none'")
        if status == 401:
            self.send_header('WWW-Authenticate', 'Basic realm="cmux Developer Mobile"')
        self.end_headers()
        self.wfile.write(data)

    def authorized(self, mutation=False):
        expected = 'Basic ' + base64.b64encode(self.server.credential.encode()).decode()
        if not hmac.compare_digest(self.headers.get('Authorization', '').encode(), expected.encode()):
            raise MenuError('unauthorized', 401)
        if time.time() >= self.server.menu.expires_at:
            raise MenuError('expired', 410)
        origin = self.headers.get('Origin')
        allowed_origins = {'https://' + self.headers.get('Host', ''), 'http://' + self.headers.get('Host', '')}
        if origin and origin not in allowed_origins:
            raise MenuError('forbidden', 403)
        if mutation and (origin not in allowed_origins or not hmac.compare_digest(
                self.headers.get('X-Cmux-Action', '').encode(), self.server.menu.csrf.encode())):
            raise MenuError('forbidden', 403)

    def do_GET(self):
        try:
            self.authorized()
            parsed = urlsplit(self.path)
            if parsed.path in ('/', '/sessions', '/sessions/'):
                self.respond(200, self.server.html, 'text/html; charset=utf-8')
            elif parsed.path == '/api/sessions':
                self.respond(200, self.server.menu.catalog())
            elif parsed.path == '/api/replay':
                query = parse_qs(parsed.query)
                self.respond(200, self.server.menu.replay(query.get('workspace', [None])[0], query.get('surface', [None])[0]))
            elif parsed.path.startswith('/terminal/') and (self.server.terminal_port or self.server.terminal_socket):
                self.proxy_terminal()
            else:
                raise MenuError('not_found', 404)
        except MenuError as error:
            self.respond(error.status, {'error': error.code})
        except (OSError, ValueError, KeyError, json.JSONDecodeError):
            self.respond(503, {'error': 'app_unavailable'})

    def do_POST(self):
        try:
            self.authorized(mutation=True)
            if urlsplit(self.path).path != '/api/input':
                raise MenuError('not_found', 404)
            length = int(self.headers.get('Content-Length', '0'))
            if not 0 < length <= 32768 or self.headers.get('Content-Type') != 'application/json':
                raise MenuError('invalid_request', 413)
            body = strict_json(self.rfile.read(length))
            if not isinstance(body, dict):
                raise MenuError('invalid_request')
            self.respond(200, self.server.menu.input(body))
        except MenuError as error:
            self.respond(error.status, {'error': error.code})
        except (OSError, ValueError, KeyError, json.JSONDecodeError):
            self.respond(503, {'error': 'app_unavailable'})

    def proxy_terminal(self):
        # Fixed private upstream only. Forward ttyd's original renderer/PTY;
        # this cannot proxy arbitrary hosts, native RPCs or file paths.
        backend = socket.socket(socket.AF_UNIX) if self.server.terminal_socket else socket.socket(socket.AF_INET)
        with backend:
            backend.settimeout(5)
            backend.connect(str(self.server.terminal_socket) if self.server.terminal_socket else ('127.0.0.1', self.server.terminal_port))
            headers = [f'GET {self.path} HTTP/1.1']
            for key, value in self.headers.items():
                if key.lower() not in ('connection', 'authorization', 'x-cmux-authenticated'):
                    headers.append(f'{key}: {value}')
            headers += ['X-Cmux-Authenticated: developer',
                        'Connection: Upgrade' if self.headers.get('Upgrade', '').lower() == 'websocket' else 'Connection: close']
            backend.sendall(('\r\n'.join(headers) + '\r\n\r\n').encode())
            self.wfile.flush()
            # Authentication and Origin checks happen before upgrading; ttyd
            # accepts only the private proxy header. The session deadline is a lease.
            if self.headers.get('Upgrade', '').lower() == 'websocket':
                self.release_request_deadline_for_authenticated_websocket()
                backend.settimeout(30)
                while time.time() < self.server.menu.expires_at:
                    readable, _, _ = select.select([backend, self.connection], [], [], 5)
                    for source in readable:
                        chunk = source.recv(65536)
                        if not chunk:
                            self.close_connection = True
                            return
                        (self.connection if source is backend else backend).sendall(chunk)
            else:
                while True:
                    chunk = backend.recv(65536)
                    if not chunk:
                        break
                    self.connection.sendall(chunk)
            self.close_connection = True
