"""Tests for BL-20: graceful disconnect handling and cleanup.

Acceptance criteria (issue #37):
1. A closed socket is removed from its room and from the user list.
2. Only active connections can send and receive messages.
3. The server stays up after an abrupt client disconnect.

Maps to Test Plan: UT-08B (user list excludes disconnected users),
IT-07C (abrupt disconnect is announced), ST-03B (recipient disconnects
mid-chat; others still receive; server reports no error).
"""

import pytest

from chat import create_app, socketio
from chat import rooms
from chat.connection import cleanup_session, connected_users, get_connected_users


@pytest.fixture
def app():
    app = create_app()
    app.config["TESTING"] = True
    return app


def _sid(client):
    """Return the server-side sid of a test client from its ``ack`` event."""
    for event in client.get_received():
        if event["name"] == "ack":
            return event["args"][0]["sid"]
    raise AssertionError("no ack received")


def _payload(event):
    args = event.get("args")
    return args[0] if isinstance(args, list) and args else args


def _join(client, room):
    client.emit("join_room", {"room": room})
    client.get_received()


def _participants(room):
    """Socket.IO's own registry of sids in ``room`` (yields (sid, eio_sid))."""
    return {sid for sid, _eio_sid in socketio.server.manager.get_participants("/", room)}


def _events(client, name):
    return [_payload(e) for e in client.get_received() if e["name"] == name]


# ---------------------------------------------------------------------------
# AC1: closed socket removed from room and user list
# ---------------------------------------------------------------------------

def test_disconnect_removes_session_from_room_and_user_list(app):
    """UT-08B: after B disconnects, only A is listed in room1."""
    a = socketio.test_client(app, auth={"username": "alice"})
    b = socketio.test_client(app, auth={"username": "bob"})
    a_sid, b_sid = _sid(a), _sid(b)
    _join(a, "room1")
    _join(b, "room1")
    assert sorted(rooms.get_room_members("room1")) == ["alice", "bob"]

    b.disconnect()

    assert b_sid not in get_connected_users()
    assert rooms.get_user_room(b_sid) is None
    assert b_sid not in rooms.room_members.get("room1", set())
    assert rooms.get_room_members("room1") == ["alice"]
    # Socket.IO's own room registry no longer lists B either
    participants = _participants("room1")
    assert b_sid not in participants
    assert a_sid in participants

    a.disconnect()


def test_last_member_disconnect_deletes_empty_room(app):
    """A room with no active members is removed, not kept as an empty shell."""
    a = socketio.test_client(app, auth={"username": "alice"})
    _join(a, "lonely-room")
    assert "lonely-room" in rooms.room_members

    a.disconnect()

    assert "lonely-room" not in rooms.room_members


def test_cleanup_session_is_idempotent(app):
    """The same cleanup path can run twice (e.g. leave + close) without errors."""
    a = socketio.test_client(app, auth={"username": "alice"})
    sid = _sid(a)
    _join(a, "room1")

    first = cleanup_session(sid)
    second = cleanup_session(sid)

    assert first == ("alice", "room1")
    assert second == (None, None)
    assert sid not in connected_users
    assert rooms.get_user_room(sid) is None

    a.disconnect()  # the real disconnect afterwards must not fail either
    assert sid not in connected_users


def test_cleanup_of_unknown_session_returns_nothing():
    """Refused handshakes never registered; cleaning them up is a no-op."""
    assert cleanup_session("never-connected-sid") == (None, None)


def test_disconnect_announces_leave_to_others_only(app):
    """IT-07C: others in the room see 'bob left the room' exactly once."""
    a = socketio.test_client(app, auth={"username": "alice"})
    b = socketio.test_client(app, auth={"username": "bob"})
    _join(a, "room1")
    _join(b, "room1")
    a.get_received()

    b.disconnect()

    notices = [n for n in _events(a, "system") if n["type"] == "leave"]
    assert len(notices) == 1
    assert notices[0]["sender"] == "bob"
    assert notices[0]["room"] == "room1"
    assert notices[0]["message"] == "bob left the room"

    a.disconnect()


# ---------------------------------------------------------------------------
# AC2: only active connections send and receive
# ---------------------------------------------------------------------------

def test_remaining_members_still_receive_after_a_peer_disconnects(app):
    """ST-03B: C leaves mid-chat; A's message still reaches B; no error."""
    a = socketio.test_client(app, auth={"username": "alice"})
    b = socketio.test_client(app, auth={"username": "bob"})
    c = socketio.test_client(app, auth={"username": "carol"})
    c_sid = _sid(c)
    for client in (a, b, c):
        _join(client, "room1")
    a.get_received()
    b.get_received()

    c.disconnect()
    a.emit("message", {"content": "still here?"})

    b_messages = _events(b, "message")
    assert [m["content"] for m in b_messages] == ["still here?"]
    assert not _events(a, "error")
    # The message was never queued for the closed session
    assert c_sid not in _participants("room1")

    a.disconnect()
    b.disconnect()


def test_events_from_a_cleaned_up_session_are_ignored(app):
    """A session that is no longer active cannot broadcast or join rooms.

    This covers the race where an event from a socket is processed just after
    its session was cleaned up (for example by a heartbeat timeout).
    """
    a = socketio.test_client(app, auth={"username": "alice"})
    b = socketio.test_client(app, auth={"username": "bob"})
    a_sid = _sid(a)
    _join(a, "room1")
    _join(b, "room1")
    b.get_received()

    cleanup_session(a_sid)  # A is no longer an active session
    a.emit("message", {"content": "ghost message"})
    a.emit("join_room", {"room": "room2"})

    assert _events(b, "message") == []
    assert rooms.get_user_room(a_sid) is None
    assert "room2" not in rooms.room_members

    a.disconnect()
    b.disconnect()


# ---------------------------------------------------------------------------
# AC3: server stays up after abrupt disconnects and handler errors
# ---------------------------------------------------------------------------

def test_handler_exception_is_reported_and_server_keeps_working(app, monkeypatch):
    """An unexpected error inside a handler returns E500; the next event works."""
    a = socketio.test_client(app, auth={"username": "alice"})
    _join(a, "room1")

    def boom(_room):
        raise RuntimeError("simulated failure")

    monkeypatch.setattr(rooms, "is_valid_room_name", boom)
    a.emit("join_room", {"room": "room2"})
    errors = _events(a, "error")
    assert errors and errors[-1]["code"] == "E500"
    assert "simulated" not in errors[-1]["message"]  # no internals leaked

    monkeypatch.undo()
    a.emit("message", {"content": "after the error"})
    assert [m["content"] for m in _events(a, "message")] == ["after the error"]
    a.disconnect()


def test_abrupt_tcp_drop_is_cleaned_up_and_announced(raw_client, wait_until):
    """IT-07C over a real socket: B's TCP connection dies with no close frame.

    The server must remove B, tell A that B left, and keep serving: A can still
    chat and a brand-new client can connect afterwards.
    """
    a = raw_client("alice-live")
    b = raw_client("bob-live")
    a.emit("join_room", {"room": "live-room"})
    a.wait_for("joined")
    b.emit("join_room", {"room": "live-room"})
    b.wait_for("joined")
    a.wait_for("system", lambda p: p["type"] == "join" and p["sender"] == "bob-live")

    b.drop()

    notice = a.wait_for(
        "system", lambda p: p["type"] == "leave" and p["sender"] == "bob-live", timeout=5
    )
    assert notice["room"] == "live-room"
    assert wait_until(lambda: b.sid not in get_connected_users())
    assert rooms.get_room_members("live-room") == ["alice-live"]

    # Server still up: existing client chats, a new client can connect.
    a.emit("message", {"content": "server survived"})
    assert a.wait_for("message")["content"] == "server survived"
    c = raw_client("carol-live")
    c.emit("join_room", {"room": "live-room"})
    assert sorted(c.wait_for("joined")["members"]) == ["alice-live", "carol-live"]
