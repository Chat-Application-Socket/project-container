"""Integration checks for BL-10 / NFR-SEC-2 XSS protection."""

from pathlib import Path

import pytest

from chat import create_app, socketio


XSS_PAYLOADS = [
    "<script>alert(1)</script>",
    '<img src=x onerror="alert(1)">',
    "<svg onload=alert(1)>",
    '<iframe src="javascript:alert(1)"></iframe>',
    '<a href="javascript:alert(1)">click</a>',
]


@pytest.mark.parametrize("payload", XSS_PAYLOADS)
def test_xss_payload_is_broadcast_as_plain_text(payload):
    """The server validates message shape and preserves content as plain text."""
    app = create_app()
    app.config["TESTING"] = True
    sender = socketio.test_client(app, auth={"username": "Alice"})
    receiver = socketio.test_client(app, auth={"username": "Bob"})
    try:
        sender.get_received()
        receiver.get_received()

        sender.emit("message", {"content": payload})

        received = [
            event["args"]
            for event in receiver.get_received()
            if event["name"] == "message"
        ]
        assert len(received) == 1
        assert received[0]["content"] == payload
        assert received[0]["sender"] == "Alice"
    finally:
        sender.disconnect()
        receiver.disconnect()


def test_client_renders_message_content_as_text_not_html():
    """The UI must use textContent; message data must never be assigned to innerHTML."""
    client_js = (
        Path(__file__).resolve().parents[1] / "static" / "client.js"
    ).read_text(encoding="utf-8")
    assert "content.textContent = msg.content == null ? \"\" : String(msg.content);" in client_js
    assert "content.innerHTML =" not in client_js
