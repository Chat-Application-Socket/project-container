"""Room management module for chat application.

Handles room membership, joining, leaving, and single room enforcement (BL-14, BL-15, BL-16).
"""

from datetime import datetime, timezone
import re
from flask import request
from flask_socketio import emit, join_room as socketio_join_room, leave_room as socketio_leave_room
from chat.connection import connected_users, state_lock

DEFAULT_ROOM = "global"
MAX_ROOM_NAME_LENGTH = 30
MAX_DESCRIPTION_LENGTH = 120
ROOM_NAME_REGEX = re.compile(r"^[A-Za-z0-9_ -]{1,30}$")

# In-memory mapping of active rooms:
# user_rooms: { sid: room_name }
# room_members: { room_name: set(sid) }
# room_metadata: { room_name: {description, visibility, admin_sid, admin_username} }
user_rooms = {}
room_members = {}
room_metadata = {}


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
    with state_lock:
        sids = set(room_members.get(room, set()))
        # Only sessions that are still connected count (BL-20).
        return [connected_users[s] for s in sids if s in connected_users]


def get_room_info(room):
    """Return metadata (description, visibility, admin) for a room."""
    with state_lock:
        meta = room_metadata.get(room)
        if not meta:
            return {
                "description": "",
                "visibility": "public",
                "admin_sid": None,
                "admin": None,
            }
        return dict(meta)


def remove_user_from_room(sid):
    """Remove user from their active room and clean up empty rooms.

    Returns the previous room name, or None.
    """
    with state_lock:
        old_room = user_rooms.pop(sid, None)
        if old_room and old_room in room_members:
            room_members[old_room].discard(sid)
            if not room_members[old_room]:
                room_members.pop(old_room, None)
                room_metadata.pop(old_room, None)
    return old_room


def emit_room_users(room):
    """Broadcast the active usernames in a room to its remaining members."""
    info = get_room_info(room)
    emit("user_list", {
        "room": room,
        "members": get_room_members(room),
        "admin": info["admin"],
    }, to=room)


def _complete_room_join(sid, username, room):
    """Move a connected user from any previous room into ``room`` and notify."""
    old_room = user_rooms.get(sid)
    if old_room == room:
        info = get_room_info(room)
        emit("joined", {
            "room": room,
            "username": username,
            "members": get_room_members(room),
            "description": info["description"],
            "visibility": info["visibility"],
            "admin": info["admin"],
            "is_admin": info["admin_sid"] == sid,
        })
        return

    if old_room:
        socketio_leave_room(old_room)
        remove_user_from_room(sid)
        emit("system", {
            "type": "leave",
            "sender": username,
            "room": old_room,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "message": f"{username} left the room",
        }, to=old_room)
        emit_room_users(old_room)

    with state_lock:
        if sid not in connected_users:
            return
        socketio_join_room(room)
        user_rooms[sid] = room
        room_members.setdefault(room, set()).add(sid)

    info = get_room_info(room)
    emit_room_users(room)

    emit("joined", {
        "room": room,
        "username": username,
        "members": get_room_members(room),
        "description": info["description"],
        "visibility": info["visibility"],
        "admin": info["admin"],
        "is_admin": info["admin_sid"] == sid,
    })

    emit("system", {
        "type": "join",
        "sender": username,
        "room": room,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "message": f"{username} joined the room",
    }, to=room)


def register(socketio):
    """Register room event handlers with the SocketIO instance."""

    @socketio.on("create_room")
    def handle_create_room(data):
        """Create a new public or private room with description and admin (BL-26)."""
        sid = request.sid
        username = connected_users.get(sid)
        if not username:
            return

        if not isinstance(data, dict):
            data = {}

        raw_room = data.get("room")
        if not is_valid_room_name(raw_room):
            emit("error", {
                "code": "E303",
                "message": "Invalid room name. Must be 1-30 valid characters.",
                "event": "create_room",
            })
            return

        room = raw_room.strip()
        raw_desc = data.get("description", "")
        description = (
            raw_desc.strip()[:MAX_DESCRIPTION_LENGTH]
            if isinstance(raw_desc, str) else ""
        )
        raw_vis = data.get("visibility", "public")
        visibility = "private" if raw_vis == "private" else "public"

        with state_lock:
            if room in room_metadata or room in room_members:
                emit("error", {
                    "code": "E305",
                    "message": "Room already exists. Choose another name or join it.",
                    "event": "create_room",
                })
                return
            room_metadata[room] = {
                "description": description,
                "visibility": visibility,
                "admin_sid": sid,
                "admin": username,
            }

        _complete_room_join(sid, username, room)

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

        _complete_room_join(sid, username, room)

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
        emit_room_users(old_room)
