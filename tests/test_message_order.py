"""Tests for live, in-order rendering of received messages (BL-08).

Maps to Test Plan REQ-12 (message order) and BL-08 acceptance criteria:
- New message appears with no refresh (client listens for the pushed "message" event)
- Order matches arrival order (and the server seq number when present)
- View auto-scrolls to the latest message

The ordering logic lives in static/messages.js and is unit tested with Node.js
(tests/js/test_message_store.js). That script is run here so it is part of the
normal `python -m pytest` run; it is skipped if Node.js is not installed.
"""

import os
import shutil
import subprocess

import pytest
from chat import create_app

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
JS_TEST = os.path.join(ROOT, "tests", "js", "test_message_store.js")


@pytest.fixture
def client():
    app = create_app()
    app.config["TESTING"] = True
    return app.test_client()


@pytest.mark.skipif(shutil.which("node") is None, reason="Node.js is not installed")
def test_message_store_orders_and_deduplicates():
    """Run the Node.js unit tests for the message view model."""
    result = subprocess.run(
        ["node", JS_TEST],
        cwd=ROOT,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        universal_newlines=True,
        timeout=60,
    )
    assert result.returncode == 0, result.stdout


def test_message_store_script_is_served(client):
    """static/messages.js is served to the browser."""
    response = client.get("/static/messages.js")
    assert response.status_code == 200
    assert "MessageStore" in response.get_data(as_text=True)


def test_message_store_loaded_before_client_script(client):
    """messages.js must load before client.js, which uses MessageStore."""
    page = client.get("/").get_data(as_text=True)
    store_pos = page.find('src="/static/messages.js"')
    client_pos = page.find('src="/static/client.js"')
    assert store_pos != -1
    assert client_pos != -1
    assert store_pos < client_pos


def test_client_listens_for_pushed_messages(client):
    """client.js renders pushed "message" events live (no polling, no refresh)."""
    script = client.get("/static/client.js").get_data(as_text=True)
    assert 'socket.on("message"' in script
    assert "scrollToLatest" in script
    assert "setInterval" not in script
    assert "location.reload" not in script


def test_messages_rendered_as_text_not_html(client):
    """Received text is written with textContent, never innerHTML (NFR-SEC-2)."""
    for path in ("/static/client.js", "/static/messages.js"):
        script = client.get(path).get_data(as_text=True)
        assert "innerHTML" not in script
        assert "insertAdjacentHTML" not in script
