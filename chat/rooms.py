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
# room_metadata: { room_name: {description, visibility, admin_sid, admin} }
# pending_requests: { room_name: { requester_sid: requester_username } }
user_rooms = {}
room_members = {}
room_metadata = {}
pending_requests = {}


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
        for req_map in pending_requests.values():
            req_map.pop(sid, None)
        old_room = user_rooms.pop(sid, None)
        if old_room and old_room in room_members:
            room_members[old_room].discard(sid)
            if not room_members[old_room]:
                room_members.pop(old_room, None)
                room_metadata.pop(old_room, None)
                pending_requests.pop(old_room, None)
    return old_room


def emit_room_users(room, socketio_inst=None):
    """Broadcast the active usernames in a room to its remaining members."""
    info = get_room_info(room)
    payload = {
        "room": room,
        "members": get_room_members(room),
        "admin": info["admin"],
    }
    if socketio_inst is not None:
        socketio_inst.emit("user_list", payload, to=room)
    else:
        emit("user_list", payload, to=room)


def _complete_room_join(sid, username, room, socketio_inst=None):
    """Move a connected user from any previous room into ``room`` and notify."""
    send = socketio_inst.emit if socketio_inst is not None else emit
    old_room = user_rooms.get(sid)
    if old_room == room:
        info = get_room_info(room)
        send("joined", {
            "room": room,
            "username": username,
            "members": get_room_members(room),
            "description": info["description"],
            "visibility": info["visibility"],
            "admin": info["admin"],
            "is_admin": info["admin_sid"] == sid,
        }, to=sid)
        return

    if old_room:
        socketio_leave_room(old_room, sid=sid)
        remove_user_from_room(sid)
        send("system", {
            "type": "leave",
            "sender": username,
            "room": old_room,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "message": f"{username} left the room",
        }, to=old_room)
        emit_room_users(old_room, socketio_inst=socketio_inst)

    with state_lock:
        if sid not in connected_users:
            return
        socketio_join_room(room, sid=sid)
        user_rooms[sid] = room
        room_members.setdefault(room, set()).add(sid)

    info = get_room_info(room)
    emit_room_users(room, socketio_inst=socketio_inst)

    send("joined", {
        "room": room,
        "username": username,
        "members": get_room_members(room),
        "description": info["description"],
        "visibility": info["visibility"],
        "admin": info["admin"],
        "is_admin": info["admin_sid"] == sid,
    }, to=sid)

    send("system", {
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

        _complete_room_join(sid, username, room, socketio_inst=socketio)

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

        # BL-27: Private room join requests require admin approval
        info = get_room_info(room)
        if info["visibility"] == "private" and info["admin_sid"] != sid:
            with state_lock:
                already_member = sid in room_members.get(room, set())
                if not already_member:
                    pending_requests.setdefault(room, {})[sid] = username
            if not already_member:
                emit("join_request_pending", {
                    "room": room,
                    "admin": info["admin"],
                    "message": f"Join request sent to {info['admin']} for '{room}'.",
                })
                if info["admin_sid"] and info["admin_sid"] in connected_users:
                    socketio.emit("join_request", {
                        "room": room,
                        "requester_sid": sid,
                        "requester": username,
                    }, to=info["admin_sid"])
                return

        _complete_room_join(sid, username, room, socketio_inst=socketio)

    @socketio.on("respond_join_request")
    def handle_respond_join_request(data):
        """Admin approves or rejects a pending join request for a private room (BL-27)."""
        sid = request.sid
        if sid not in connected_users or not isinstance(data, dict):
            return

        room = data.get("room")
        req_sid = data.get("requester_sid")
        allow = bool(data.get("allow"))
        if not isinstance(room, str) or not isinstance(req_sid, str):
            return

        info = get_room_info(room)
        if info["admin_sid"] != sid:
            emit("error", {
                "code": "E403",
                "message": "Only the room admin can approve or deny requests.",
                "event": "respond_join_request",
            })
            return

        with state_lock:
            req_username = pending_requests.get(room, {}).pop(req_sid, None)
            still_connected = req_sid in connected_users

        if not req_username or not still_connected:
            return

        if allow:
            _complete_room_join(req_sid, req_username, room, socketio_inst=socketio)
        else:
            socketio.emit("join_request_rejected", {
                "room": room,
                "message": f"Your request to join '{room}' was declined by the admin.",
            }, to=req_sid)

    @socketio.on("search_rooms")
    def handle_search_rooms(data=None):
        """Return active public rooms matching an optional search query (BL-27)."""
        sid = request.sid
        if sid not in connected_users:
            return

        query = ""
        if isinstance(data, dict) and isinstance(data.get("query"), str):
            query = data["query"].strip().lower()

        results = []
        with state_lock:
            all_rooms = set(room_members.keys()) | set(room_metadata.keys())
            for r in sorted(all_rooms):
                meta = room_metadata.get(r, {})
                if meta.get("visibility") == "private":
                    continue
                desc = meta.get("description", "")
                if query and query not in r.lower() and query not in desc.lower():
                    continue
                results.append({
                    "room": r,
                    "description": desc,
                    "admin": meta.get("admin"),
                    "member_count": len(room_members.get(r, set())),
                })

        emit("room_list", {"rooms": results, "query": query})

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
