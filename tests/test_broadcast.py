
from datetime import datetime, timezone
from unittest.mock import patch

from chat import create_app, socketio
from chat.connection import connected_users


def setup_clients():
    app = create_app()

    sender = socketio.test_client(app, auth={"username": "Alice"})
    receiver = socketio.test_client(app, auth={"username": "Bob"})
    outsider = socketio.test_client(app, auth={"username": "Charlie"})

    sid_by_username = {
        username: sid for sid, username in connected_users.items()
    }

    socketio.server.enter_room(
        sid_by_username["Alice"], "room1", namespace="/"
    )
    socketio.server.enter_room(
        sid_by_username["Bob"], "room1", namespace="/"
    )
    socketio.server.enter_room(
        sid_by_username["Charlie"], "room2", namespace="/"
    )

    return sender, receiver, outsider


def test_broadcast_reaches_same_room_only():
    sender, receiver, outsider = setup_clients()

    sender.emit(
        "send_message",
        {"room": "room1", "content": "Hello everyone"},
    )

    received = [
        event for event in receiver.get_received()
        if event["name"] == "new_message"
    ]
    outside_received = [
        event for event in outsider.get_received()
        if event["name"] == "new_message"
    ]

    assert len(received) == 1
    message = received[0]["args"][0]
    assert message["sender"] == "Alice"
    assert message["room"] == "room1"
    assert message["content"] == "Hello everyone"
    assert not outside_received

    sender.disconnect()
    receiver.disconnect()
    outsider.disconnect()


def test_broadcast_ignores_invalid_messages():
    sender, receiver, outsider = setup_clients()

    sender.emit("send_message", {"room": "", "content": "Hello"})
    sender.emit("send_message", {"room": "room1", "content": "x" * 501})

    assert not any(
        event["name"] == "new_message"
        for event in receiver.get_received()
    )

    sender.disconnect()
    receiver.disconnect()
    outsider.disconnect()


def test_timestamp_is_server_generated_utc():
    sender, receiver, outsider = setup_clients()

    with patch("chat.broadcast.datetime") as mock_datetime:
        mock_datetime.now.return_value = datetime(
            2026, 10, 28, 12, 0, 0, tzinfo=timezone.utc
        )

        sender.emit(
            "send_message",
            {
                "room": "room1",
                "content": "Timestamp test",
                "timestamp": "1999-01-01T00:00:00Z",
            },
        )

    received = [
        event for event in receiver.get_received()
        if event["name"] == "new_message"
    ]

    assert len(received) == 1
    message = received[0]["args"][0]
    assert message["timestamp"] == "2026-10-28T12:00:00+00:00"
    assert message["timestamp"] != "1999-01-01T00:00:00Z"

    sender.disconnect()
    receiver.disconnect()
    outsider.disconnect()
