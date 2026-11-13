"""Tests for BL-29 (End-to-End Encrypted private room and DM message relay)."""

import pytest
from chat import create_app, socketio


@pytest.fixture
def app():
    """Create test application."""
    app = create_app()
    app.config["TESTING"] = True
    return app


def _payload(event):
    args = event.get("args")
    return args[0] if isinstance(args, list) and args else args


def test_encrypted_message_relayed_without_exposing_plaintext(app):
    """BL-29: Server relays ciphertext and iv in private/DM rooms without plaintext."""
    alice = socketio.test_client(app, auth={"username": "Alice"})
    bob = socketio.test_client(app, auth={"username": "Bob"})
    try:
        bob_id = _payload([e for e in bob.get_received() if e["name"] == "ack"][0])["user_id"]
        alice.get_received()

        alice.emit("start_dm", {"user_id": bob_id})
        alice.get_received()

        bob_invites = [e for e in bob.get_received() if e["name"] == "dm_invite"]
        assert len(bob_invites) == 1
        bob.emit("start_dm", {"user_id": _payload(bob_invites[0])["from_user_id"]})
        bob.get_received()
        alice.get_received()

        alice.emit("message", {
            "content": "[Encrypted message]",
            "encrypted": True,
            "ciphertext": "U2VjcmV0Q2lwaGVydGV4dA==",
            "iv": "MTIzNDU2Nzg5MDEy",
            "enc_mode": "aes-gcm",
        })

        msgs = [e for e in bob.get_received() if e["name"] == "message"]
        assert len(msgs) == 1
        msg = _payload(msgs[0])
        assert msg["encrypted"] is True
        assert msg["ciphertext"] == "U2VjcmV0Q2lwaGVydGV4dA=="
        assert msg["iv"] == "MTIzNDU2Nzg5MDEy"
        assert msg["enc_mode"] == "aes-gcm"
        assert msg["content"] == "[Encrypted message]"
    finally:
        alice.disconnect()
        bob.disconnect()
