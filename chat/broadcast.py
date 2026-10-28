"""Message broadcasting module for chat application.

Handles broadcasting real-time chat messages to rooms.
"""

from datetime import datetime, timezone

import uuid

from flask import request
from flask_socketio import emit

from chat.connection import connected_users
from chat.validator import reject_empty_message


def register(socketio):
    """Register message broadcasting handlers with the SocketIO instance."""

    @socketio.on("message")
    @reject_empty_message
    def handle_message(data):
        """Validate and broadcast a plain-text chat message.

        The content remains plain text here. The client must insert it with
        textContent, never innerHTML; HTML-escaping here as well would display
        escaped entities to users rather than the message they typed.
        """
        content = data["content"]
        if len(content) > 500:
            emit("error", {
                "code": "E201",
                "message": "Message must not exceed 500 characters.",
                "event": "message",
            })
            return

        sid = request.sid
        username = connected_users.get(sid)
        if username is None:
            return

        message = {
            "id": uuid.uuid4().hex,
            "sender": username,
            "room": "global",
            "content": content,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "type": "message",
        }
        # SocketIO.emit (rather than context emit) broadcasts to connected clients.
        socketio.emit("message", message)

    # Keep the existing room-specific event for compatibility with the current
    # broadcast tests and callers. Validate its payload on the server too.
    @socketio.on("send_message")
    @reject_empty_message
    def handle_send_message(data):
        """Broadcast a message to all connected users in the selected room."""
        room = data.get("room")
        content = data["content"]

        if not isinstance(room, str) or not room.strip() or len(room) > 30:
            return

        if len(content) > 500:
            return

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
        emit("new_message", message, to=room)
