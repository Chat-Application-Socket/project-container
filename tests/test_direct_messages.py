"""Tests for BL-28 (Unique User ID assignment and 1-on-1 direct messaging)."""

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


def test_ack_assigns_unique_user_id(app):
    """BL-28: Each connected client receives a unique USR-XXXXXX identifier."""
    c1 = socketio.test_client(app, auth={"username": "Alice"})
    c2 = socketio.test_client(app, auth={"username": "Bob"})

    ack1 = _payload([e for e in c1.get_received() if e["name"] == "ack"][0])
    ack2 = _payload([e for e in c2.get_received() if e["name"] == "ack"][0])

    assert ack1["user_id"].startswith("USR-")
    assert ack2["user_id"].startswith("USR-")
    assert ack1["user_id"] != ack2["user_id"]

    c1.disconnect()
    c2.disconnect()


def test_lookup_and_start_dm_isolates_two_users(app):
    """BL-28: Users can find each other by ID and start a private 1-on-1 DM room."""
    alice = socketio.test_client(app, auth={"username": "Alice"})
    bob = socketio.test_client(app, auth={"username": "Bob"})
    eve = socketio.test_client(app, auth={"username": "Eve"})
    try:
        bob_id = _payload([e for e in bob.get_received() if e["name"] == "ack"][0])["user_id"]
        alice.get_received()
        eve.get_received()

        # Lookup Bob by ID (case-insensitive)
        alice.emit("lookup_user", {"user_id": bob_id.lower()})
        res = _payload([e for e in alice.get_received() if e["name"] == "user_lookup_result"][0])
        assert res["found"] is True
        assert res["username"] == "Bob"
        assert res["user_id"] == bob_id

        # Alice starts DM with Bob
        alice.emit("start_dm", {"user_id": bob_id})
        joined = _payload([e for e in alice.get_received() if e["name"] == "joined"][0])
        dm_room = joined["room"]
        assert dm_room.startswith("dm:")
        assert joined["visibility"] == "private"

        # Bob receives dm_invite and automatically joins the private 1-on-1 DM room
        bob_events = bob.get_received()
        invites = [e for e in bob_events if e["name"] == "dm_invite"]
        assert len(invites) == 1
        assert _payload(invites[0])["from_username"] == "Alice"
        bob_joined = [e for e in bob_events if e["name"] == "joined"]
        assert len(bob_joined) == 1
        assert _payload(bob_joined[0])["room"] == dm_room

        # Eve cannot join the DM room directly or find it in search_rooms
        eve.emit("join_room", {"room": dm_room})
        errs = [e for e in eve.get_received() if e["name"] == "error"]
        assert len(errs) == 1
        assert _payload(errs[0])["code"] == "E403"

        eve.emit("search_rooms", {"query": ""})
        room_list = _payload([e for e in eve.get_received() if e["name"] == "room_list"][0])
        assert all(not r["room"].startswith("dm:") for r in room_list["rooms"])
    finally:
        alice.disconnect()
        bob.disconnect()
        eve.disconnect()
