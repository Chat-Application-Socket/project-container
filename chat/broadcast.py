
"""Message broadcasting module for chat application."""

from datetime import datetime, timezone

import uuid

from flask import request
from flask_socketio import emit

from chat.connection import connected_users
from chat.validator import (
    reject_empty_message,
    validate_message_object,
    MessageValidationError,
)


def register(socketio):
    """Register message broadcasting handlers."""

    @socketio.on("message")
    @reject_empty_message
    def handle_message(data):
        """Validate and broadcast a chat message."""
        sid = request.sid
        username = connected_users.get(sid)

        if username is None:
            return

        message = {
            "id": uuid.uuid4().hex,
            "sender": username,
            "room": "global",
            "content": data["content"],
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "type": "message",
        }

        try:
            validate_message_object(message)
        except MessageValidationError as exc:
            emit("error", exc.to_payload("message"))
            return

        socketio.emit("message", message)

    @socketio.on("send_message")
    @reject_empty_message
    def handle_send_message(data):
        """Validate and broadcast a room-specific message."""
        room = data.get("room")
        content = data["content"]

        sid = request.sid
        username = connected_users.get(sid)

        if username is None:
            return

        message = {
            "sender": username,
            "room": room,
            "content": content,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "type": "message",
        }

        try:
            validate_message_object(message)
        except MessageValidationError as exc:
            emit("error", exc.to_payload("send_message"))
            return

        emit("new_message", message, to=room)
