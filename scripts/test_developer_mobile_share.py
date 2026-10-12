#!/usr/bin/env python3
"""Live HTTPS/WebSocket checks against isolated disposable mobile sessions."""
import base64
import importlib.machinery
import importlib.util
import json
import os
from pathlib import Path
import signal
import socket
import ssl
import struct
import subprocess
import tempfile
import time
import unittest
import urllib.error
import urllib.request


HELPER = Path(__file__).resolve().parents[1] / 'Resources/bin/cmux-mobile-share'
MODULE = importlib.machinery.SourceFileLoader('mobile_share', str(HELPER)).load_module()
CLI = os.environ['CMUX_MOBILE_TEST_CLI']
SPEC = importlib.util.spec_from_file_location('mobile_app_fixture', Path(__file__).with_name('test_developer_mobile_menu.py'))
FIXTURE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(FIXTURE)


class WebSocket:
    def __init__(self, details, origin=None, credential=True, path='/terminal/ws'):
        address, port = details['url'].removeprefix('https://').split(':')
        context = ssl.create_default_context(cafile=details['certificate'])
        self.socket = context.wrap_socket(socket.create_connection((address, int(port))), server_hostname=address)
        self.socket.settimeout(3)
        self.token = base64.b64encode(('developer:' + details['password']).encode()).decode()
        headers = [f'GET {path} HTTP/1.1', f'Host: {address}:{port}', 'Upgrade: websocket',
                   'Connection: Upgrade', 'Sec-WebSocket-Version: 13', 'Sec-WebSocket-Protocol: tty',
                   'Sec-WebSocket-Key: ' + base64.b64encode(os.urandom(16)).decode(),
                   'Origin: ' + (origin or details['url'])]
        if credential:
            headers += ['Authorization: Basic ' + self.token]
        self.socket.sendall(('\r\n'.join(headers) + '\r\n\r\n').encode())
        response = bytearray()
        while not response.endswith(b'\r\n\r\n'):
            chunk = self.socket.recv(1)
            if not chunk:
                break
            response.extend(chunk)
        self.accepted = response.startswith(b'HTTP/1.1 101')
        if self.accepted:
            self.send(json.dumps({'AuthToken': self.token, 'columns': 90, 'rows': 25}).encode())

    def send(self, message):
        mask = os.urandom(4)
        length = len(message)
        header = bytes([0x82, 0x80 | length]) if length < 126 else bytes([0x82, 0xfe]) + struct.pack('!H', length)
        self.socket.sendall(header + mask + bytes(value ^ mask[index % 4] for index, value in enumerate(message)))

    def close(self):
        self.socket.close()


class MobileShareTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='cmux-mobile-test-', dir='/tmp')
        self.root = Path(self.temp.name)
        self.process = None
        self.details = None
        self.connections = []
        self.share = MODULE.MobileShare(self.root, CLI)
        self.fixture = FIXTURE.NativeAppFixture(self.root / 'app.sock')

    def tearDown(self):
        for connection in self.connections:
            connection.close()
        if self.process:
            if self.process.poll() is None:
                self.process.send_signal(signal.SIGTERM)
            self.process.wait(timeout=8)
            self.process.stdout.close()
        if self.details:
            self.share.cmux('local-tmux', 'close', '--id', self.details['session_id'])
        self.fixture.close()
        self.temp.cleanup()

    def start(self, readonly=False):
        with socket.socket() as free:
            free.bind(('127.0.0.1', 0))
            port = free.getsockname()[1]
        args = [os.sys.executable, str(HELPER), 'serve', '--cli', CLI, '--state-dir', str(self.root),
                '--session', 'probe', '--cwd', '/tmp', '--port', str(port), '--minutes', '1',
                '--menu', '--app-socket', str(self.fixture.path)]
        if readonly:
            args.append('--readonly')
        self.process = subprocess.Popen(args, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
        line = self.process.stdout.readline().strip()
        self.assertTrue(line.startswith('PAIRING_FILE='), line)
        self.pairing_path = Path(line.split('=', 1)[1])
        self.details = json.loads(self.pairing_path.read_text())
        return self.details

    def connect(self, **kwargs):
        connection = WebSocket(self.details, **kwargs)
        self.connections.append(connection)
        return connection

    def screen(self):
        status = self.share.cmux('local-tmux', 'status', '--id', self.details['session_id'])
        result = subprocess.check_output(['/opt/homebrew/bin/tmux', '-S', status['socket_path'],
                                         'capture-pane', '-p', '-t', status['tmux_session_id']], text=True)
        return result

    def wait_screen(self, text):
        deadline = time.monotonic() + 5
        while time.monotonic() < deadline:
            if text in self.screen():
                return
            time.sleep(0.1)
        self.fail('Shared terminal did not receive the authenticated input')

    def test_tls_auth_and_private_pairing_file(self):
        details = self.start()
        with self.assertRaises(urllib.error.HTTPError) as rejected:
            self.share.request(details['url'], cert=details['certificate'])
        self.assertEqual(rejected.exception.code, 401)
        with self.assertRaises(urllib.error.HTTPError) as wrong:
            self.share.request(details['url'], 'developer:wrong', details['certificate'])
        self.assertEqual(wrong.exception.code, 401)
        with self.share.request(details['url'], 'developer:' + details['password'], details['certificate']) as response:
            self.assertEqual(response.status, 200)
        self.assertEqual(self.pairing_path.stat().st_mode & 0o777, 0o600)
        self.assertGreaterEqual(len(details['password']), 32)
        # System trust alone must reject this ephemeral, self-signed identity.
        with self.assertRaises(urllib.error.URLError):
            self.share.request(details['url'], 'developer:' + details['password'])

    def test_websocket_origin_auth_and_bidirectional_session(self):
        self.start()
        self.assertFalse(self.connect(credential=False).accepted)
        self.assertFalse(self.connect(origin='https://attacker.example').accepted)
        first, second = self.connect(), self.connect()
        self.assertTrue(first.accepted)
        self.assertTrue(second.accepted)
        first.send(b'0printf "PHONE_TO_MAC_OK\\n"\r')
        self.wait_screen('PHONE_TO_MAC_OK')
        second.send(b'0printf "MAC_TO_PHONE_OK\\n"\r')
        self.wait_screen('MAC_TO_PHONE_OK')
        self.process.send_signal(signal.SIGTERM)
        self.process.wait(timeout=8)
        self.assertFalse(self.pairing_path.exists())
        self.assertTrue(self.share.cmux('local-tmux', 'status', '--id', self.details['session_id'])['live'])
        with self.assertRaises(OSError):
            socket.create_connection(('127.0.0.1', int(self.details['url'].rsplit(':', 1)[1])), timeout=1)

    def test_readonly_client_cannot_write(self):
        self.start(readonly=True)
        client = self.connect()
        self.assertTrue(client.accepted)
        deadline = time.monotonic() + 5
        flags = ''
        while time.monotonic() < deadline:
            flags = subprocess.check_output(['/opt/homebrew/bin/tmux', '-S', str(self.root / 'sessions/server.sock'),
                                             'list-clients', '-F', '#{client_flags}'], text=True)
            if 'read-only' in flags:
                break
            time.sleep(0.1)
        self.assertIn('read-only', flags)
        client.send(b'0printf "UNAUTHORIZED_WRITE_MARKER\\n"\r')
        # An authoritative tmux read-only flag plus a rejected HTTP input mode
        # protects against clients bypassing the browser's UI.
        self.assertNotIn('UNAUTHORIZED_WRITE_MARKER', self.screen())

    def test_public_bind_is_rejected(self):
        for address in ('0.0.0.0', '8.8.8.8', '::', '100.64.0.1'):
            with self.assertRaises(ValueError):
                MODULE.MobileShare.validate_bind(address)
        self.assertEqual(MODULE.MobileShare.validate_bind('192.168.1.20'), '192.168.1.20')


if __name__ == '__main__':
    unittest.main(verbosity=2)
