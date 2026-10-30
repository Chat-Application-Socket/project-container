"""Room management module for chat application.

Handles room membership, joining, leaving, and single room enforcement (BL-14, BL-15, BL-16).
"""

from datetime import datetime, timezone
import re
from flask import request
from flask_socketio import emit, join_room as socketio_join_room, leave_room as socketio_leave_room
from chat.connection import connected_users

DEFAULT_ROOM = "global"
MAX_ROOM_NAME_LENGTH = 30
ROOM_NAME_REGEX = re.compile(r"^[A-Za-z0-9_ -]{1,30}$")

# In-memory mapping of active rooms:
# user_rooms: { sid: room_name }
# room_members: { room_name: set(sid) }
user_rooms = {}
room_members = {}


def is_valid_room_name(room):
    """Validate room name according to SAD 4.3.5.

    Must be non-empty after trimming, at most 30 characters, and match the allowed pattern.
    """
    if not isinstance(room, str):
        return False
    trimmed = room.strip()
    if not trimmed or len(trimmed) > MAX_ROOM_NAME_LENGTH:
        return False
    return bool(ROOM_NAME_REGEX.match(trimmed))


def get_user_room(sid):
    """Return the current room name for a client session, or None."""
    return user_rooms.get(sid)


def get_room_members(room):
    """Return the list of usernames currently in a room."""
    sids = room_members.get(room, set())
    return [connected_users[s] for s in sids if s in connected_users]


def remove_user_from_room(sid):
    """Remove user from their active room and clean up empty rooms.

    Returns the previous room name, or None.
    """
    old_room = user_rooms.pop(sid, None)
    if old_room and old_room in room_members:
        room_members[old_room].discard(sid)
        if not room_members[old_room]:
            room_members.pop(old_room, None)
    return old_room


def register(socketio):
    """Register room event handlers with the SocketIO instance."""

    @socketio.on("join_room")
    def handle_join_room(data):
        """Handle client request to join a named room (REQ-6, REQ-10 / BL-14, BL-16)."""
        sid = request.sid
        username = connected_users.get(sid)
        if not username:
            return

        raw_room = None
        if isinstance(data, dict):
            raw_room = data.get("room")
        elif isinstance(data, str):
            raw_room = data

        # Default to 'global' if room is completely omitted
        if raw_room is None:
            room = DEFAULT_ROOM
        else:
            if not is_valid_room_name(raw_room):
                emit("error", {
                    "code": "E303",
                    "message": "Invalid room name. Must be 1-30 valid characters.",
                    "event": "join_room",
                })
                return
            room = raw_room.strip()

        old_room = user_rooms.get(sid)
        if old_room == room:
            # Already in this room, acknowledge and return
            emit("joined", {
                "room": room,
                "username": username,
                "members": get_room_members(room),
            })
            return

        # Leaving previous room if present (REQ-10: one room at a time)
        if old_room:
            socketio_leave_room(old_room)
            remove_user_from_room(sid)
            # Notify members of the old room that user left (BL-15)
            emit("system", {
                "type": "leave",
                "sender": username,
                "room": old_room,
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "message": f"{username} left the room",
            }, to=old_room)

        # Join the new room
        socketio_join_room(room)
        user_rooms[sid] = room
        if room not in room_members:
            room_members[room] = set()
        room_members[room].add(sid)

        # Acknowledge join to sender
        emit("joined", {
            "room": room,
            "username": username,
            "members": get_room_members(room),
        })

        # Notify existing and new members in room (REQ-7 / BL-15)
        emit("system", {
            "type": "join",
            "sender": username,
            "room": room,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "message": f"{username} joined the room",
        }, to=room)

    @socketio.on("leave_room")
    def handle_leave_room(data=None):
        """Handle client request to leave their current room (REQ-7 / BL-15)."""
        sid = request.sid
        username = connected_users.get(sid)
        if not username:
            return

        old_room = user_rooms.get(sid)
        if not old_room:
            return

        socketio_leave_room(old_room)
        remove_user_from_room(sid)

        # Acknowledge leave to sender
        emit("left", {"room": old_room})

        # Notify remaining members in the room (REQ-7 / BL-15)
        emit("system", {
            "type": "leave",
            "sender": username,
            "room": old_room,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "message": f"{username} left the room",
        }, to=old_room)
