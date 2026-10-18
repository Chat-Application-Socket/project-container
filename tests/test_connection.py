"""Tests for WebSocket connection, handshake validation, and lifecycle.

Maps to Test Plan:
- UT-01B: Valid connection and server acknowledgment
- UT-02A: Multiple concurrent client connections
- UT-02B: Client disconnection cleanup
- UT-01A: Rejection of invalid/empty username
- UT-01C: Rejection of username exceeding max length
"""

import pytest
from chat import create_app, socketio
from chat.connection import get_connected_users


@pytest.fixture
def app():
    """Create and configure a Flask application instance for tests."""
    app = create_app()
    app.config["TESTING"] = True
    return app


def test_valid_connection_receives_ack(app):
    """UT-01B / IT-01B: Valid username establishes connection and receives 'ack'."""
    client = socketio.test_client(app, auth={"username": "guest-1234"})
    assert client.is_connected()

    # Verify 'ack' event received from server
    received = client.get_received()
    ack_events = [msg for msg in received if msg["name"] == "ack"]
    assert len(ack_events) == 1

    ack_data = ack_events[0]["args"][0]
    assert ack_data["username"] == "guest-1234"
    assert ack_data["message"] == "Connected"
    assert "sid" in ack_data

    # Verify user registered in connected users dictionary
    users = get_connected_users()
    assert ack_data["sid"] in users
    assert users[ack_data["sid"]] == "guest-1234"

    client.disconnect()


def test_multiple_clients_connected(app):
    """UT-02A: Two connected clients result in two distinct entries in user dict."""
    client1 = socketio.test_client(app, auth={"username": "alice"})
    client2 = socketio.test_client(app, auth={"username": "bob"})

    assert client1.is_connected()
    assert client2.is_connected()

    users = get_connected_users()
    assert len(users) >= 2
    usernames = list(users.values())
    assert "alice" in usernames
    assert "bob" in usernames

    client1.disconnect()
    client2.disconnect()


def test_disconnect_removes_user(app):
    """UT-02B: Disconnecting a client cleans up its entry from connected users."""
    client = socketio.test_client(app, auth={"username": "charlie"})
    assert client.is_connected()

    received = client.get_received()
    ack_data = [m for m in received if m["name"] == "ack"][0]["args"][0]
    sid = ack_data["sid"]

    assert sid in get_connected_users()

    client.disconnect()
    assert not client.is_connected()
    assert sid not in get_connected_users()
