"""Tests for Room management and notifications (BL-14, BL-15, BL-16).

Maps to:
- REQ-6 / Test Plan REQ-04 (BL-14): Join named room, room scoping, room name validation
- REQ-7 / Test Plan REQ-05, REQ-06 (BL-15): Member join/leave notifications, leave button,
  and disconnect notices
- REQ-10 / SRS 5.5 Business Rules (BL-16): Enforce one room at a time per user
"""

import pytest
from chat import create_app, socketio
from chat.connection import connected_users
from chat.rooms import get_user_room, get_room_members


@pytest.fixture
def app():
    """Create test application."""
    app = create_app()
    app.config["TESTING"] = True
    return app


def get_sid_for_user(username):
    """Find the socket session ID for a username."""
    for sid, user in connected_users.items():
        if user == username:
            return sid
    return None


def get_event_payload(event):
    """Extract event argument dictionary safely whether args is list or dict."""
    args = event.get("args")
    if isinstance(args, list) and args:
        return args[0]
    return args


def test_client_emits_join_room_and_server_adds_client(app):
    """BL-14: Client emits join_room, server adds client and responds with 'joined'."""
    client = socketio.test_client(app, auth={"username": "Alice"})
    assert client.is_connected()
    client.get_received()  # clear ack

    client.emit("join_room", {"room": "engineering"})
    received = client.get_received()

    joined_events = [e for e in received if e["name"] == "joined"]
    assert len(joined_events) == 1
    data = get_event_payload(joined_events[0])
    assert data["room"] == "engineering"
    assert data["username"] == "Alice"
    assert "Alice" in data["members"]

    # Verify server tracking
    sid = get_sid_for_user("Alice")
    assert sid is not None
    assert get_user_room(sid) == "engineering"
    assert "Alice" in get_room_members("engineering")

    client.disconnect()


def test_messages_scoped_to_the_room(app):
    """BL-14: Messages sent in a room only reach clients in that room."""
    c1 = socketio.test_client(app, auth={"username": "Alice"})
    c2 = socketio.test_client(app, auth={"username": "Bob"})
    c3 = socketio.test_client(app, auth={"username": "Charlie"})

    c1.emit("join_room", {"room": "dev-team"})
    c2.emit("join_room", {"room": "dev-team"})
    c3.emit("join_room", {"room": "design-team"})

    c1.get_received()
    c2.get_received()
    c3.get_received()

    # Alice sends a message in dev-team
    c1.emit("message", {"content": "Hello dev team!"})

    c2_msgs = [e for e in c2.get_received() if e["name"] == "message"]
    c3_msgs = [e for e in c3.get_received() if e["name"] == "message"]

    assert len(c2_msgs) == 1
    c2_payload = get_event_payload(c2_msgs[0])
    assert c2_payload["content"] == "Hello dev team!"
    assert c2_payload["room"] == "dev-team"

    # Charlie in design-team must NOT receive this message
    assert len(c3_msgs) == 0

    c1.disconnect()
    c2.disconnect()
    c3.disconnect()


def test_invalid_and_over_30_char_room_rejected(app):
    """BL-14: Blank, whitespace, invalid characters, or >30-char room names rejected."""
    client = socketio.test_client(app, auth={"username": "Alice"})
    client.get_received()

    # Over 30 characters
    long_name = "a" * 31
    client.emit("join_room", {"room": long_name})
    received = client.get_received()
    errors = [e for e in received if e["name"] == "error"]
    assert len(errors) == 1
    assert get_event_payload(errors[0])["code"] == "E303"

    # Empty string
    client.emit("join_room", {"room": ""})
    received = client.get_received()
    errors = [e for e in received if e["name"] == "error"]
    assert len(errors) == 1
    assert get_event_payload(errors[0])["code"] == "E303"

    # Whitespace only
    client.emit("join_room", {"room": "   "})
    received = client.get_received()
    errors = [e for e in received if e["name"] == "error"]
    assert len(errors) == 1
    assert get_event_payload(errors[0])["code"] == "E303"

    # Invalid characters (e.g. symbols not in [A-Za-z0-9_ -])
    client.emit("join_room", {"room": "room$#@!"})
    received = client.get_received()
    errors = [e for e in received if e["name"] == "error"]
    assert len(errors) == 1
    assert get_event_payload(errors[0])["code"] == "E303"

    # Valid boundary: exactly 30 characters should succeed
    boundary_name = "r" * 30
    client.emit("join_room", {"room": boundary_name})
    received = client.get_received()
    joined = [e for e in received if e["name"] == "joined"]
    assert len(joined) == 1

    client.disconnect()


def test_join_and_leave_notices_shown_to_room_members(app):
    """BL-15: Existing room members receive system notifications on join and leave."""
    c1 = socketio.test_client(app, auth={"username": "Alice"})
    c2 = socketio.test_client(app, auth={"username": "Bob"})

    c1.emit("join_room", {"room": "lounge"})
    c1.get_received()  # clear Alice's join events

    # Bob joins lounge
    c2.emit("join_room", {"room": "lounge"})

    # Alice should receive a system join notice
    c1_events = c1.get_received()
    system_join = [
        e for e in c1_events
        if e["name"] == "system" and get_event_payload(e)["type"] == "join"
    ]
    assert len(system_join) == 1
    join_data = get_event_payload(system_join[0])
    assert join_data["sender"] == "Bob"
    assert join_data["room"] == "lounge"
    assert "Bob joined the room" in join_data["message"]

    # Bob leaves lounge
    c2.emit("leave_room", {})

    # Bob receives 'left' ack
    c2_events = c2.get_received()
    left_events = [e for e in c2_events if e["name"] == "left"]
    assert len(left_events) == 1
    assert get_event_payload(left_events[0])["room"] == "lounge"

    # Alice should receive a system leave notice
    c1_events2 = c1.get_received()
    system_leave = [
        e for e in c1_events2
        if e["name"] == "system" and get_event_payload(e)["type"] == "leave"
    ]
    assert len(system_leave) == 1
    leave_data = get_event_payload(system_leave[0])
    assert leave_data["sender"] == "Bob"
    assert leave_data["room"] == "lounge"
    assert "Bob left the room" in leave_data["message"]

    c1.disconnect()
    c2.disconnect()


def test_leave_button_action(app):
    """BL-15: Leave room removes user from room tracking."""
    client = socketio.test_client(app, auth={"username": "Alice"})
    client.emit("join_room", {"room": "roomA"})
    sid = get_sid_for_user("Alice")
    assert get_user_room(sid) == "roomA"

    client.emit("leave_room", {})
    assert get_user_room(sid) is None
    assert "Alice" not in get_room_members("roomA")

    client.disconnect()


def test_disconnect_fires_leave_notice_to_room(app):
    """BL-15: Disconnecting while in a room notifies remaining room members."""
    c1 = socketio.test_client(app, auth={"username": "Alice"})
    c2 = socketio.test_client(app, auth={"username": "Bob"})

    c1.emit("join_room", {"room": "meeting"})
    c2.emit("join_room", {"room": "meeting"})
    c1.get_received()

    # Bob disconnects unexpectedly or closes browser
    c2.disconnect()

    # Alice should receive leave notice for Bob
    c1_events = c1.get_received()
    leave_notices = [
        e for e in c1_events
        if e["name"] == "system" and get_event_payload(e)["type"] == "leave"
    ]
    assert len(leave_notices) == 1
    leave_data = get_event_payload(leave_notices[0])
    assert leave_data["sender"] == "Bob"
    assert leave_data["room"] == "meeting"
    assert "Bob left the room" in leave_data["message"]

    c1.disconnect()


def test_joining_new_room_leaves_old_room(app):
    """BL-14 / BL-15 / BL-16: Joining a new room automatically leaves the old room with notice."""
    c1 = socketio.test_client(app, auth={"username": "Alice"})
    c2 = socketio.test_client(app, auth={"username": "Bob"})

    c1.emit("join_room", {"room": "room1"})
    c2.emit("join_room", {"room": "room1"})
    c2.get_received()

    # Alice switches from room1 to room2
    c1.emit("join_room", {"room": "room2"})

    sid = get_sid_for_user("Alice")
    assert get_user_room(sid) == "room2"
    assert "Alice" not in get_room_members("room1")
    assert "Alice" in get_room_members("room2")

    # Bob in room1 should receive a system leave notice for Alice
    c2_events = c2.get_received()
    leave_notices = [
        e for e in c2_events
        if e["name"] == "system" and get_event_payload(e)["type"] == "leave"
    ]
    assert len(leave_notices) == 1
    assert get_event_payload(leave_notices[0])["sender"] == "Alice"

    c1.disconnect()
    c2.disconnect()


def test_enforce_one_room_at_a_time_messages_not_received_from_old_room(app):
    """BL-16: User who switched rooms only receives messages in their current room."""
    c1 = socketio.test_client(app, auth={"username": "Alice"})
    c2 = socketio.test_client(app, auth={"username": "Bob"})
    c3 = socketio.test_client(app, auth={"username": "Charlie"})

    # Alice and Bob join roomA
    c1.emit("join_room", {"room": "roomA"})
    c2.emit("join_room", {"room": "roomA"})
    # Charlie in roomB
    c3.emit("join_room", {"room": "roomB"})

    c1.get_received()
    c2.get_received()
    c3.get_received()

    # Alice switches from roomA to roomB
    c1.emit("join_room", {"room": "roomB"})
    c1.get_received()

    # Bob sends message to roomA
    c2.emit("message", {"content": "Message in roomA"})

    # Charlie sends message to roomB
    c3.emit("message", {"content": "Message in roomB"})

    alice_messages = [
        get_event_payload(e) for e in c1.get_received()
        if e["name"] == "message"
    ]

    # Alice must only receive message from roomB, never roomA
    assert len(alice_messages) == 1
    assert alice_messages[0]["room"] == "roomB"
    assert alice_messages[0]["content"] == "Message in roomB"

    c1.disconnect()
    c2.disconnect()
    c3.disconnect()
