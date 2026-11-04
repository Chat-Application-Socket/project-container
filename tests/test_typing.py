"""Tests for room-scoped typing notifications (BL-19)."""

from chat import create_app, socketio


def get_payload(event):
    """Return the first event payload regardless of Socket.IO test format."""
    args = event.get("args")
    if isinstance(args, list) and args:
        return args[0]
    return args


def events_named(client, name):
    """Return received events with the requested name."""
    return [event for event in client.get_received() if event["name"] == name]


def test_typing_is_only_sent_to_other_members_in_same_room():
    """Typing events reach peers in the room, but not the typist or other rooms."""
    app = create_app()
    app.config["TESTING"] = True
    alice = socketio.test_client(app, auth={"username": "Alice"})
    bob = socketio.test_client(app, auth={"username": "Bob"})
    charlie = socketio.test_client(app, auth={"username": "Charlie"})

    alice.emit("join_room", {"room": "team"})
    bob.emit("join_room", {"room": "team"})
    charlie.emit("join_room", {"room": "other"})
    alice.get_received()
    bob.get_received()
    charlie.get_received()

    alice.emit("typing", {})
    bob_typing = events_named(bob, "user_typing")
    assert len(bob_typing) == 1
    assert get_payload(bob_typing[0]) == {
        "username": "Alice",
        "room": "team",
    }
    assert events_named(alice, "user_typing") == []
    assert events_named(charlie, "user_typing") == []

    alice.disconnect()
    bob.disconnect()
    charlie.disconnect()


def test_stop_typing_is_sent_to_room_peers():
    """Stopping typing clears the indicator for peers in the same room."""
    app = create_app()
    app.config["TESTING"] = True
    alice = socketio.test_client(app, auth={"username": "Alice"})
    bob = socketio.test_client(app, auth={"username": "Bob"})

    alice.emit("join_room", {"room": "team"})
    bob.emit("join_room", {"room": "team"})
    alice.get_received()
    bob.get_received()

    alice.emit("stop_typing", {})
    stopped = events_named(bob, "user_stopped_typing")
    assert len(stopped) == 1
    assert get_payload(stopped[0]) == {
        "username": "Alice",
        "room": "team",
    }
    assert events_named(alice, "user_stopped_typing") == []

    alice.disconnect()
    bob.disconnect()


def test_sending_message_clears_typing_indicator_for_room_peers():
    """A sent message also clears the sender's typing indicator."""
    app = create_app()
    app.config["TESTING"] = True
    alice = socketio.test_client(app, auth={"username": "Alice"})
    bob = socketio.test_client(app, auth={"username": "Bob"})

    alice.emit("join_room", {"room": "team"})
    bob.emit("join_room", {"room": "team"})
    alice.get_received()
    bob.get_received()

    alice.emit("message", {"content": "Hello"})
    received = bob.get_received()
    stopped = [
        event for event in received
        if event["name"] == "user_stopped_typing"
    ]
    messages = [event for event in received if event["name"] == "message"]
    assert len(stopped) == 1
    assert get_payload(stopped[0])["username"] == "Alice"
    assert len(messages) == 1

    alice.disconnect()
    bob.disconnect()
