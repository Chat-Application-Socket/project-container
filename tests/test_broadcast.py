
from chat import create_app, socketio
from chat.connection import connected_users


def setup_clients():
    app = create_app()

    sender = socketio.test_client(app, auth={"username": "Alice"})
    receiver = socketio.test_client(app, auth={"username": "Bob"})
    outsider = socketio.test_client(app, auth={"username": "Charlie"})

    # Get the Socket.IO session IDs recorded by the connection handler.
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

    # Invalid messages must not reach other clients.
    assert not any(
        event["name"] == "new_message"
        for event in receiver.get_received()
    )
    assert not any(
        event["name"] == "new_message"
        for event in outsider.get_received()
    )

    # The sender must receive an error.
    assert any(
        event["name"] == "error"
        for event in sender.get_received()
    )

    sender.disconnect()
    receiver.disconnect()
    outsider.disconnect()