
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
        """Validate and broadcast a chat message scoped to the client room (BL-14)."""
        sid = request.sid
        username = connected_users.get(sid)

        if username is None:
            return

        from chat.rooms import get_user_room
        user_room = get_user_room(sid)

        message = {
            "id": uuid.uuid4().hex,
            "sender": username,
            "room": user_room or "global",
            "content": data["content"],
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "type": "message",
        }

        try:
            validate_message_object(message)
        except MessageValidationError as exc:
            emit("error", exc.to_payload("message"))
            return

        if user_room:
            socketio.emit("message", message, to=user_room)
        else:
            socketio.emit("message", message)

    @socketio.on("send_message")
    @reject_empty_message
    def handle_send_message(data):
        """Validate and broadcast a room-specific message (BL-14)."""
        sid = request.sid
        username = connected_users.get(sid)

        if username is None:
            return

        from chat.rooms import get_user_room
        room = data.get("room") or get_user_room(sid) or "global"
        content = data["content"]

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
