"""Message broadcasting module for chat application.

Handles broadcasting real-time chat messages to rooms.
"""

from flask import request
from flask_socketio import emit

from chat.connection import connected_users


def register(socketio):
    """Register message broadcasting handlers with the SocketIO instance."""

    @socketio.on("send_message")
    def handle_send_message(data):
        """Broadcast a message to all connected users in the selected room."""
        if not isinstance(data, dict):
            return

        room = data.get("room")
        content = data.get("content")

        if not isinstance(room, str) or not room.strip():
            return

        if len(room) > 30:
            return

        if not isinstance(content, str):
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
            "type": "message",
        }

        emit("new_message", message, to=room)
