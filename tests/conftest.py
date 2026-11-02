"""Shared fixtures for tests that need a real, running server.

Most tests use ``socketio.test_client`` (in-process, no network). A few
behaviours can only be checked over a real socket: an abrupt TCP close
(BL-20), reconnection (BL-21) and latency under load (BL-22). For those the
``live_server`` fixture starts the app on a free localhost port in a background
thread, and ``RawSocketIOClient`` speaks just enough of the Engine.IO v4 /
Socket.IO v5 wire protocol over a plain WebSocket to drive it.
"""

import json
import queue
import threading
import time

import pytest
import simple_websocket
from werkzeug.serving import make_server

from chat import create_app


class RawSocketIOClient:
    """Minimal Socket.IO client over ``simple_websocket.Client``.

    Only what the tests need: connect with ``auth``, emit events, collect
    received events, and either close politely or drop the TCP connection
    without a WebSocket close frame (like a crashed browser or pulled cable).
    """

    def __init__(self, base_url, username, timeout=5.0):
        ws_url = base_url.replace("http://", "ws://") + "/socket.io/?EIO=4&transport=websocket"
        self.events = queue.Queue()
        self.sid = None
        self._ws = simple_websocket.Client(ws_url)
        open_packet = self._ws.receive(timeout=timeout)
        if not open_packet or not open_packet.startswith("0"):
            raise RuntimeError(f"Unexpected Engine.IO open packet: {open_packet!r}")
        self._ws.send("40" + json.dumps({"username": username}))
        # The server's "ack" event can arrive before the CONNECT reply, so read
        # until the CONNECT reply ("40") or a refusal ("44"), keeping events.
        while True:
            reply = self._ws.receive(timeout=timeout)
            if reply is None:
                raise TimeoutError("No Socket.IO CONNECT reply")
            if reply.startswith("40"):
                break
            if reply.startswith("44"):
                raise ConnectionRefusedError(reply[2:])
            if reply.startswith("42"):
                name, *args = json.loads(reply[2:])
                payload = args[0] if args else None
                if name == "ack" and isinstance(payload, dict):
                    self.sid = payload.get("sid")
                self.events.put((name, payload))
        self._running = True
        self._reader = threading.Thread(target=self._read_loop, daemon=True)
        self._reader.start()

    def _read_loop(self):
        while self._running:
            try:
                packet = self._ws.receive(timeout=0.5)
            except Exception:
                break
            if packet is None:
                continue
            if packet == "2":  # Engine.IO ping -> answer with pong
                try:
                    self._ws.send("3")
                except Exception:
                    break
            elif packet.startswith("42"):
                name, *args = json.loads(packet[2:])
                self.events.put((name, args[0] if args else None))

    def emit(self, event, data=None):
        self._ws.send("42" + json.dumps([event, data] if data is not None else [event]))

    def wait_for(self, name, predicate=None, timeout=5.0):
        """Return the payload of the next ``name`` event matching ``predicate``."""
        deadline = time.monotonic() + timeout
        while True:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise TimeoutError(f"No {name!r} event within {timeout}s")
            try:
                got_name, payload = self.events.get(timeout=remaining)
            except queue.Empty:
                continue
            if got_name == name and (predicate is None or predicate(payload)):
                return payload

    def close(self):
        """Polite disconnect: Socket.IO disconnect packet, then WebSocket close."""
        self._running = False
        try:
            self._ws.send("41")
            self._ws.close()
        except Exception:
            pass

    def drop(self):
        """Abrupt disconnect: close the TCP socket with no close frame."""
        self._running = False
        sock = self._ws.sock
        try:
            import socket as _socket

            sock.shutdown(_socket.SHUT_RDWR)
        except OSError:
            pass
        sock.close()


@pytest.fixture
def live_server():
    """Run the chat app on a free localhost port; yield its base URL."""
    app = create_app()
    app.config["TESTING"] = True
    server = make_server("127.0.0.1", 0, app, threaded=True)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield f"http://127.0.0.1:{server.server_port}"
    finally:
        server.shutdown()


def _wait_until(condition, timeout=5.0, interval=0.05):
    """Poll ``condition`` until it is true or ``timeout`` seconds pass."""
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if condition():
            return True
        time.sleep(interval)
    return condition()


@pytest.fixture
def wait_until():
    """Fixture form of :func:`_wait_until` so tests need no helper imports."""
    return _wait_until


@pytest.fixture
def raw_client(live_server):
    """Factory fixture: ``raw_client("alice")`` connects a RawSocketIOClient.

    Every client still open at the end of the test is closed politely.
    """
    clients = []

    def factory(username):
        client = RawSocketIOClient(live_server, username)
        clients.append(client)
        return client

    yield factory
    for client in clients:
        client.close()
