"""Tests for BL-21: auto-reconnect with a 'Connection lost, reconnecting...' message.

Acceptance criteria (issue #38):
1. Show a notice when the connection drops.
2. Retry the connection with back-off between attempts.
3. Rejoin the previous room after a successful reconnect.
4. Support manual reconnection.
5. An unavailable server must not crash the client.

Maps to Test Plan NFR-REL-1: NT-10 (server restart), NT-11 (network drop),
NT-12 (client starts while the server is down); SAD 4.4.3 / 4.4.4.

Three layers:
- Node.js unit tests for the back-off policy (tests/js/test_reconnect.js).
- Checks that the page loads the policy and wires it into client.js.
- End-to-end browser tests with Playwright + Chromium against a real server
  process that is killed and restarted. These are skipped automatically when
  Playwright or a Chromium build is not available (for example in CI).
"""

import os
import shutil
import socket
import subprocess
import sys
import time

import pytest

from chat import create_app

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
JS_TEST = os.path.join(ROOT, "tests", "js", "test_reconnect.js")
C02 = "Connection lost, reconnecting..."
C01 = "Cannot reach the server. Retrying..."


@pytest.fixture
def client():
    app = create_app()
    app.config["TESTING"] = True
    return app.test_client()


# ---------------------------------------------------------------------------
# Unit tests (Node.js) and page wiring
# ---------------------------------------------------------------------------

@pytest.mark.skipif(shutil.which("node") is None, reason="Node.js is not installed")
def test_reconnect_policy_unit_tests():
    """Back-off formula, attempt limit, reset and manual retry (SAD 4.4.4)."""
    result = subprocess.run(
        ["node", JS_TEST],
        cwd=ROOT,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        universal_newlines=True,
        timeout=60,
    )
    assert result.returncode == 0, result.stdout


def test_reconnect_script_is_served_and_loaded_before_client(client):
    """reconnect.js is served and loads before client.js, which uses it."""
    response = client.get("/static/reconnect.js")
    assert response.status_code == 200
    assert "ReconnectScheduler" in response.get_data(as_text=True)

    page = client.get("/").get_data(as_text=True)
    policy_pos = page.find('src="/static/reconnect.js"')
    client_pos = page.find('src="/static/client.js"')
    assert policy_pos != -1 and client_pos != -1
    assert policy_pos < client_pos


def test_client_uses_websocket_only_and_its_own_reconnect_policy(client):
    """Socket.IO's built-in retry stays off (refusals are never looped) and the
    client rejoins the stored room on connect."""
    script = client.get("/static/client.js").get_data(as_text=True)
    assert 'transports: ["websocket"]' in script
    assert "reconnection: false" in script
    assert "ReconnectScheduler" in script
    assert "desiredRoom" in script
    assert 'socket.emit("join_room", { room: desiredRoom })' in script
    assert "innerHTML" not in script


# ---------------------------------------------------------------------------
# End-to-end browser tests (Playwright)
# ---------------------------------------------------------------------------

def _free_port():
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


class ServerProcess:
    """Runs ``python app.py`` on a fixed port so it can be killed and restarted."""

    def __init__(self, port):
        self.port = port
        self.proc = None

    def start(self):
        env = dict(os.environ, PORT=str(self.port), PYTHONUNBUFFERED="1")
        self.proc = subprocess.Popen(
            [sys.executable, "app.py"],
            cwd=ROOT,
            env=env,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        deadline = time.monotonic() + 15
        while time.monotonic() < deadline:
            try:
                with socket.create_connection(("127.0.0.1", self.port), timeout=0.2):
                    return
            except OSError:
                time.sleep(0.1)
        raise RuntimeError("server did not start")

    def kill(self):
        """Stop abruptly (like a crash): every open connection is dropped."""
        if self.proc and self.proc.poll() is None:
            self.proc.kill()
            self.proc.wait(timeout=10)


@pytest.fixture(scope="module")
def browser():
    sync_api = pytest.importorskip("playwright.sync_api")
    try:
        manager = sync_api.sync_playwright().start()
    except Exception as exc:  # pragma: no cover - environment dependent
        pytest.skip(f"Playwright not usable: {exc}")
    try:
        chromium = manager.chromium.launch()
    except Exception as exc:  # pragma: no cover - no browser installed
        manager.stop()
        pytest.skip(f"Chromium not available: {exc}")
    yield chromium
    chromium.close()
    manager.stop()


@pytest.fixture
def server():
    srv = ServerProcess(_free_port())
    yield srv
    srv.kill()


def _block_cdn(page):
    # The page also references the Socket.IO CDN; the local copy is enough.
    page.route("https://cdn.socket.io/**", lambda route: route.abort())


def _open_chat(browser, server, username, room=None):
    context = browser.new_context()
    page = context.new_page()
    _block_cdn(page)
    page.goto(f"http://127.0.0.1:{server.port}/")
    page.fill("#username", username)
    page.click("#connect-btn")  # disconnect the auto guest session
    page.wait_for_function("document.getElementById('status').textContent === 'Disconnected'")
    page.click("#connect-btn")
    _wait_status(page, "Connected")
    if room:
        page.fill("#room-input", room)
        page.click("#join-room-btn")
        page.wait_for_function(
            f"document.getElementById('current-room-badge').textContent === 'Room: {room}'"
        )
    return context, page


def _wait_status(page, text, timeout=20000):
    page.wait_for_function(
        f"document.getElementById('status').textContent === {text!r}", timeout=timeout
    )


def _banner(page):
    return page.text_content("#error-banner") or ""


def test_nt10_reconnects_and_rejoins_room_after_server_restart(browser, server):
    """NT-10: stop the server, start it again; notice shown, then Connected in room1."""
    server.start()
    context, page = _open_chat(browser, server, "alice", room="room1")
    page.fill("#message-input", "draft kept while offline")

    server.kill()
    page.wait_for_function(
        f"document.getElementById('error-banner').textContent.startsWith({C02!r})",
        timeout=10000,
    )
    assert page.text_content("#status") in ("Reconnecting...",)
    assert page.is_disabled("#send-btn")
    assert page.text_content("#connect-btn") == "Reconnect now"

    # Back-off: at least two failed attempts happen while the server is down
    page.wait_for_function(
        "document.getElementById('error-banner').textContent.includes('attempt 2 of 10')",
        timeout=10000,
    )
    server.start()

    _wait_status(page, "Connected", timeout=20000)
    page.wait_for_function(
        "document.getElementById('current-room-badge').textContent === 'Room: room1'"
    )
    assert page.is_hidden("#error-banner")
    assert page.input_value("#message-input") == "draft kept while offline"
    assert "Reconnected." in page.text_content("#message-list")

    # Chat works again in the rejoined room
    page.click("#send-btn")
    page.wait_for_function(
        "[...document.querySelectorAll('.message-content')]"
        ".some(e => e.textContent === 'draft kept while offline')"
    )
    context.close()


def test_nt11_network_drop_reconnects_and_peer_sees_user_again(browser, server):
    """NT-11: A goes offline then online; A rejoins and B sees A again."""
    server.start()
    ctx_a, page_a = _open_chat(browser, server, "alice", room="room1")
    ctx_b, page_b = _open_chat(browser, server, "bob", room="room1")

    ctx_a.set_offline(True)
    page_a.wait_for_function(
        f"document.getElementById('error-banner').textContent.startsWith({C02!r})",
        timeout=10000,
    )
    page_b.wait_for_function(
        "document.getElementById('message-list').textContent.includes('alice left the room')",
        timeout=10000,
    )

    ctx_a.set_offline(False)  # the 'online' event retries straight away
    _wait_status(page_a, "Connected", timeout=10000)
    page_a.wait_for_function(
        "document.getElementById('current-room-badge').textContent === 'Room: room1'"
    )
    # B sees A again: a join notice for alice after the leave notice
    page_b.wait_for_function(
        "(() => { const t = [...document.querySelectorAll('#message-list .system')]"
        ".map(e => e.textContent);"
        " const left = t.findIndex(x => x.includes('alice left the room'));"
        " return left !== -1 && t.slice(left + 1).some(x => x.includes('alice joined the room'));"
        " })()",
        timeout=10000,
    )
    ctx_a.close()
    ctx_b.close()


def _serve_page_without_chat_server(port):
    """Serve the chat page and static files on ``port`` with a plain HTTP server.

    Used for NT-12: the page has to be open while the chat server is not
    running. The plain server is stopped right after the page loads, so every
    WebSocket attempt then finds nothing listening, exactly as when the chat
    server is down.
    """
    import http.server
    import threading

    index_html = open(os.path.join(ROOT, "templates", "index.html"), "rb").read()
    static_dir = os.path.join(ROOT, "static")

    class Handler(http.server.BaseHTTPRequestHandler):
        def do_GET(self):  # noqa: N802 - name required by BaseHTTPRequestHandler
            path = self.path.split("?", 1)[0]
            if path == "/":
                body, ctype = index_html, "text/html"
            elif path.startswith("/static/"):
                file_path = os.path.join(static_dir, os.path.basename(path))
                if not os.path.isfile(file_path):
                    self.send_error(404)
                    return
                body = open(file_path, "rb").read()
                ctype = "text/css" if path.endswith(".css") else "application/javascript"
            else:
                self.send_error(404)
                return
            self.send_response(200)
            self.send_header("Content-Type", ctype)
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, *args):
            pass

    http.server.ThreadingHTTPServer.allow_reuse_address = True
    httpd = http.server.ThreadingHTTPServer(("127.0.0.1", port), Handler)
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    return httpd


def test_nt12_client_started_while_server_down_keeps_retrying(browser, server):
    """NT-12: the page opens with the server stopped; it connects once it is up."""
    port = server.port
    page_server = _serve_page_without_chat_server(port)

    context = browser.new_context()
    page = context.new_page()
    errors = []
    page.on("pageerror", lambda exc: errors.append(str(exc)))
    _block_cdn(page)
    page.goto(f"http://127.0.0.1:{port}/")
    page_server.shutdown()
    page_server.server_close()  # nothing is listening on the port now

    page.wait_for_function(
        f"document.getElementById('error-banner').textContent.startsWith({C01!r})",
        timeout=10000,
    )
    assert page.text_content("#status") == "Reconnecting..."
    page.wait_for_function(
        "document.getElementById('error-banner').textContent.includes('attempt 3 of 10')",
        timeout=15000,
    )

    server.start()
    _wait_status(page, "Connected", timeout=20000)
    page.wait_for_function(
        "document.getElementById('current-room-badge').textContent === 'Room: global'"
    )
    assert page.is_hidden("#error-banner")
    assert errors == [], errors  # no uncaught exceptions: the client never crashed
    context.close()


def test_manual_disconnect_and_refused_username_are_not_retried(browser, server):
    """Only failures are retried: Disconnect stays disconnected, and a refused
    username shows the server's reason without a retry loop."""
    server.start()
    context, page = _open_chat(browser, server, "alice")

    page.click("#connect-btn")  # Disconnect
    _wait_status(page, "Disconnected")
    page.wait_for_timeout(2500)  # longer than the first back-off step
    assert page.text_content("#status") == "Disconnected"
    assert page.text_content("#connect-btn") == "Connect"

    page.fill("#username", "x" * 51)
    page.click("#connect-btn")
    page.wait_for_function(
        "document.getElementById('error-banner').textContent"
        " === 'Username must not exceed 50 characters'"
    )
    page.wait_for_timeout(2500)
    assert page.text_content("#status") == "Disconnected"
    assert "reconnecting" not in _banner(page).lower()
    context.close()


def test_manual_reconnect_button_after_server_returns(browser, server):
    """'Reconnect now' skips the back-off wait once the server is back."""
    server.start()
    context, page = _open_chat(browser, server, "alice", room="room7")

    server.kill()
    page.wait_for_function(
        "document.getElementById('error-banner').textContent.includes('attempt 3 of 10')",
        timeout=15000,
    )  # next automatic try is about 4 s away
    server.start()
    started = time.monotonic()
    page.click("#connect-btn")  # "Reconnect now"
    _wait_status(page, "Connected", timeout=10000)
    assert time.monotonic() - started < 3.5, "manual reconnect should not wait for the timer"
    page.wait_for_function(
        "document.getElementById('current-room-badge').textContent === 'Room: room7'"
    )
    context.close()
