"""Tests for BL-26 (create room modal, description, visibility, admin)."""

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


def test_create_room_sets_description_visibility_and_admin(app):
    """BL-26: Creator becomes admin and room stores description and visibility."""
    alice = socketio.test_client(app, auth={"username": "Alice"})
    alice.get_received()

    alice.emit("create_room", {
        "room": "design-hub",
        "description": "UI/UX & architecture discussion",
        "visibility": "public",
    })
    received = alice.get_received()
    joined = [e for e in received if e["name"] == "joined"]
    assert len(joined) == 1
    data = _payload(joined[0])
    assert data["room"] == "design-hub"
    assert data["description"] == "UI/UX & architecture discussion"
    assert data["visibility"] == "public"
    assert data["admin"] == "Alice"
    assert data["is_admin"] is True

    alice.disconnect()


def test_create_duplicate_room_returns_error(app):
    """BL-26: Creating an already active room fails with E305."""
    alice = socketio.test_client(app, auth={"username": "Alice"})
    bob = socketio.test_client(app, auth={"username": "Bob"})
    alice.get_received()
    bob.get_received()

    alice.emit("create_room", {"room": "unique-room", "description": "First"})
    alice.get_received()

    bob.emit("create_room", {"room": "unique-room", "description": "Duplicate"})
    errors = [e for e in bob.get_received() if e["name"] == "error"]
    assert len(errors) == 1
    assert _payload(errors[0])["code"] == "E305"

    alice.disconnect()
    bob.disconnect()


def test_public_room_search_excludes_private_rooms(app):
    """BL-27: search_rooms returns public rooms and hides private rooms."""
    alice = socketio.test_client(app, auth={"username": "Alice"})
    bob = socketio.test_client(app, auth={"username": "Bob"})
    alice.get_received()
    bob.get_received()

    alice.emit("create_room", {
        "room": "open-cafe",
        "description": "Public hangout",
        "visibility": "public",
    })
    alice.get_received()

    bob.emit("create_room", {
        "room": "secret-vault",
        "description": "Private team room",
        "visibility": "private",
    })
    bob.get_received()

    alice.emit("search_rooms", {"query": ""})
    room_lists = [e for e in alice.get_received() if e["name"] == "room_list"]
    assert len(room_lists) == 1
    names = [r["room"] for r in _payload(room_lists[0])["rooms"]]
    assert "open-cafe" in names
    assert "secret-vault" not in names

    alice.disconnect()
    bob.disconnect()


def test_private_room_requires_admin_approval(app):
    """BL-27: Joining a private room notifies admin; allow grants access, deny rejects."""
    admin = socketio.test_client(app, auth={"username": "AdminUser"})
    guest = socketio.test_client(app, auth={"username": "GuestUser"})
    admin.get_received()
    guest.get_received()

    admin.emit("create_room", {
        "room": "vip-lounge",
        "description": "Invite only",
        "visibility": "private",
    })
    admin.get_received()

    # Guest requests to join -> receives pending, admin receives join_request
    guest.emit("join_room", {"room": "vip-lounge"})
    guest_events = guest.get_received()
    assert any(e["name"] == "join_request_pending" for e in guest_events)
    assert not any(e["name"] == "joined" for e in guest_events)

    admin_events = admin.get_received()
    reqs = [e for e in admin_events if e["name"] == "join_request"]
    assert len(reqs) == 1
    req_data = _payload(reqs[0])
    assert req_data["requester"] == "GuestUser"

    # Admin approves
    admin.emit("respond_join_request", {
        "room": "vip-lounge",
        "requester_sid": req_data["requester_sid"],
        "allow": True,
    })
    guest_after = guest.get_received()
    joined = [e for e in guest_after if e["name"] == "joined"]
    assert len(joined) == 1
    assert _payload(joined[0])["room"] == "vip-lounge"

    # Second user denied
    intruder = socketio.test_client(app, auth={"username": "Intruder"})
    intruder.get_received()
    intruder.emit("join_room", {"room": "vip-lounge"})
    intruder.get_received()
    reqs2 = [e for e in admin.get_received() if e["name"] == "join_request"]
    assert len(reqs2) == 1
    admin.emit("respond_join_request", {
        "room": "vip-lounge",
        "requester_sid": _payload(reqs2[0])["requester_sid"],
        "allow": False,
    })
    rejected = [e for e in intruder.get_received() if e["name"] == "join_request_rejected"]
    assert len(rejected) == 1

    admin.disconnect()
    guest.disconnect()
    intruder.disconnect()
