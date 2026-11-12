
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

    @socketio.on("typing")
    def handle_typing(data=None):
        """Notify other members of the sender's current room that they are typing (BL-19)."""
        sid = request.sid
        username = connected_users.get(sid)
        if not username:
            return

        from chat.rooms import get_user_room
        room = get_user_room(sid)
        if room:
            emit("user_typing", {"username": username, "room": room}, to=room, skip_sid=sid)

    @socketio.on("stop_typing")
    def handle_stop_typing(data=None):
        """Clear the sender's typing indicator for other members of their room (BL-19)."""
        sid = request.sid
        username = connected_users.get(sid)
        if not username:
            return

        from chat.rooms import get_user_room
        room = get_user_room(sid)
        if room:
            emit("user_stopped_typing", {"username": username, "room": room}, to=room, skip_sid=sid)

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

        if data.get("encrypted") is True and isinstance(data.get("ciphertext"), str):
            message["encrypted"] = True
            message["ciphertext"] = data["ciphertext"]
            message["iv"] = data.get("iv", "") if isinstance(data.get("iv"), str) else ""
            message["enc_mode"] = (
                data.get("enc_mode", "aes-gcm")
                if isinstance(data.get("enc_mode"), str) else "aes-gcm"
            )
            message["content"] = "[Encrypted message]"

        try:
            validate_message_object(message)
        except MessageValidationError as exc:
            emit("error", exc.to_payload("message"))
            return

        if user_room:
            emit(
                "user_stopped_typing",
                {"username": username, "room": user_room},
                to=user_room,
                skip_sid=sid,
            )
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

        emit(
            "user_stopped_typing",
            {"username": username, "room": room},
            to=room,
            skip_sid=sid,
        )
        emit("new_message", message, to=room)
