"""Shared bounded HTTP/TLS admission for opt-in private Developer services."""
import json
import socket
import threading


class BoundedServerMixin:
    handshake_timeout = 3
    request_deadline_timeout = 8

    def configure_connection_limits(self, total=12, per_address=4, tls_context=None):
        self.slots = threading.BoundedSemaphore(total)
        self.per_address_limit = per_address
        self.address_counts = {}
        self.address_lock = threading.Lock()
        self.tls_context = tls_context

    def connection_allowed(self, address):
        return True

    def process_request(self, request, address):
        with self.address_lock:
            count = self.address_counts.get(address[0], 0)
            admitted = self.connection_allowed(address) and count < self.per_address_limit and self.slots.acquire(False)
            if admitted: self.address_counts[address[0]] = count+1
        if not admitted:
            request.close(); return
        try: super().process_request(request, address)
        except BaseException:
            self.release_address(address); request.close(); raise

    def release_address(self, address):
        with self.address_lock:
            count = self.address_counts[address[0]]-1
            if count: self.address_counts[address[0]] = count
            else: self.address_counts.pop(address[0], None)
        self.slots.release()

    def process_request_thread(self, request, address):
        try:
            if self.tls_context:
                request.settimeout(self.handshake_timeout)
                request = self.tls_context.wrap_socket(request, server_side=True)
            request.settimeout(self.request_deadline_timeout)
            super().process_request_thread(request, address)
        except (OSError, TimeoutError): pass
        finally:
            request.close(); self.release_address(address)

    def handle_error(self, request, address):
        pass  # Failed adversarial requests must not flood stderr or print content.


class BoundedRequestMixin:
    def handle_one_request(self):
        self.request_expired = False
        def expire():
            self.request_expired = True
            try: self.connection.shutdown(socket.SHUT_RDWR)
            except OSError: pass
        self.request_timer = threading.Timer(self.server.request_deadline_timeout, expire)
        self.request_timer.daemon = True
        self.request_timer.start()
        try: super().handle_one_request()
        finally: self.request_timer.cancel()

    def release_request_deadline_for_authenticated_websocket(self):
        # A separately authenticated WebSocket is bounded by its session lease.
        self.request_timer.cancel()

    def parse_request(self):
        if not super().parse_request(): return False
        singles = ('Host', 'Authorization', 'Content-Length', 'Content-Type', 'Origin', 'Transfer-Encoding')
        if any(len(self.headers.get_all(key, [])) > 1 for key in singles) or self.headers.get('Transfer-Encoding'):
            self.send_error(400, 'Ambiguous request framing'); return False
        length = self.headers.get('Content-Length', '0')
        if not length.isdecimal() or len(length) > 8:
            self.send_error(400, 'Invalid content length'); return False
        if self.command in ('GET', 'HEAD') and int(length) != 0:
            self.send_error(400, 'Unexpected request body'); return False
        return True

    def handle_expect_100(self):
        self.send_error(417, 'Expect is unsupported'); return False


def strict_json(data):
    def object_pairs(pairs):
        result = {}
        for key, value in pairs:
            if key in result: raise ValueError('Duplicate JSON field')
            result[key] = value
        return result
    def constant(_): raise ValueError('Non-finite JSON number')
    return json.loads(data, object_pairs_hook=object_pairs, parse_constant=constant)
