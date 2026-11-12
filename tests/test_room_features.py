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
