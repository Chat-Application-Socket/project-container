"""Connection lifecycle and handshake validation module.

This module handles:
1. Client WebSocket connection handshakes.
2. Validating authentication credentials passed during connection.
3. Tracking connected clients in an in-memory dictionary.
4. Sending connection acknowledgments (ack).
5. Cleaning up state when clients disconnect (BL-20).

BL-20 - Graceful disconnect handling (SRS 2.2, 5.5 business rule "disconnected
users are not active"; SAD 4.4.4):
- Every way a session can end (client closes the tab, network drop detected by
  the heartbeat, explicit disconnect, transport error) goes through the same
  idempotent ``cleanup_session()`` so no stale session is left in a room.
- A failure while cleaning up, or inside any other event handler, is logged and
  never stops the server.
"""

import logging
import secrets
import threading
from datetime import datetime, timezone

from flask import request
from flask_socketio import ConnectionRefusedError, emit

# Configure module-level logger
logger = logging.getLogger(__name__)
if not logger.handlers:
    logging.basicConfig(level=logging.INFO)

# In-memory mapping of active client connections: {socket_session_id (sid): username}
connected_users = {}
# BL-28: Unique short user IDs for 1-on-1 direct chat lookup
user_ids = {}
id_to_sid = {}

# Event handlers run on several threads (async_mode="threading"), so changes to
# the shared session / room dictionaries are made while holding this lock.
# RLock lets a helper that already holds it call another helper that takes it.
state_lock = threading.RLock()

# E500: unexpected server error (SAD error table). Sent to the client whose
# event failed; the text is fixed so no internal details leak (SAD SC-10).
E500_INTERNAL_ERROR = ("E500", "Something went wrong. Please retry.")


def get_connected_users():
    """Return a shallow copy of the active connected users dictionary.

    Exposed for future backlog items (such as user lists and room logic) and unit tests.
    """
    with state_lock:
        return dict(connected_users)


def is_active(sid):
    """Return True if ``sid`` belongs to a connected, accepted session (BR: only
    active connections may send or receive messages)."""
    return sid in connected_users


def generate_unique_user_id():
    """Generate a unique short user identifier (e.g., USR-A1B2C3)."""
    with state_lock:
        while True:
            candidate = f"USR-{secrets.token_hex(3).upper()}"
            if candidate not in id_to_sid:
                return candidate


def get_user_by_id(user_id):
    """Look up an active user by their unique ID (case-insensitive)."""
    if not isinstance(user_id, str):
        return None
    norm = user_id.strip().upper()
    with state_lock:
        target_sid = id_to_sid.get(norm)
        if not target_sid or target_sid not in connected_users:
            return None
        return target_sid, connected_users[target_sid], norm


def cleanup_session(sid):
    """Remove every trace of a session and return what was removed.

    Safe to call more than once for the same ``sid`` (the second call finds
    nothing and returns ``(None, None)``), so explicit disconnects, transport
    closes and heartbeat timeouts can all use it without double notices.

    Returns a tuple ``(username, room)``: the username the session had (or
    ``None`` if it was never accepted) and the room it was in (or ``None``).
    """
    # Imported here to avoid a circular import (rooms imports this module).
    from chat.rooms import remove_user_from_room

    with state_lock:
        username = connected_users.pop(sid, None)
        uid = user_ids.pop(sid, None)
        if uid:
            id_to_sid.pop(uid, None)
        old_room = remove_user_from_room(sid)
    return username, old_room


def build_leave_notice(username, room):
    """Build the ``system`` leave notice sent to a room (BL-15 format)."""
    return {
        "type": "leave",
        "sender": username,
        "room": room,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "message": f"{username} left the room",
    }


def register(socketio):
    """Register WebSocket connection lifecycle events with SocketIO."""

    # --------------------------------------------------------------------------
    # BEGINNER CONCEPT: What is a Handshake?
    # In WebSocket programming, a "handshake" is the initial HTTP request sent
    # by the client asking the server: "Can we upgrade our connection from regular
    # HTTP to a permanent WebSocket?"
    # During this handshake, the server can inspect the client's information
    # before agreeing to establish the connection.
    # --------------------------------------------------------------------------

    # --------------------------------------------------------------------------
    # BEGINNER CONCEPT: What is the `auth` payload?
    # When using Socket.IO, `auth` is a custom dictionary provided by the client
    # during the handshake (e.g. { username: "Alice" }).
    # This allows the server to authenticate and validate users *before* the
    # connection is formally accepted.
    # --------------------------------------------------------------------------

    @socketio.on("connect")
    def handle_connect(auth):
        """Handle incoming client connection request.

        Reads the username from the `auth` payload, validates it, stores the user,
        and emits an 'ack' confirmation event back to the client.
        """
        # Extract username from auth payload dictionary
        username = ""
        if isinstance(auth, dict):
            raw_username = auth.get("username", "")
            if isinstance(raw_username, str):
                username = raw_username.strip()

        # Validation rules (REQ-2, BL-03):
        # Username must not be empty after trimming and at most 50 characters long.
        if not username:
            # Raising ConnectionRefusedError sends a refusal to the client, aborting handshake
            raise ConnectionRefusedError("Username cannot be empty")

        if len(username) > 50:
            raise ConnectionRefusedError("Username must not exceed 50 characters")

        sid = request.sid
        with state_lock:
            connected_users[sid] = username
            uid = generate_unique_user_id()
            user_ids[sid] = uid
            id_to_sid[uid] = sid
        logger.info("Client connected: sid=%s user=%s id=%s", sid, username, uid)

        # Emit server acknowledgment directly to the newly connected client
        emit("ack", {
            "sid": sid,
            "username": username,
            "user_id": uid,
            "message": "Connected",
        })

    # --------------------------------------------------------------------------
    # BEGINNER CONCEPT: Graceful vs abrupt disconnects (BL-20)
    # A client can leave politely (Disconnect button) or vanish (tab closed,
    # Wi-Fi dropped, laptop lid shut). In the abrupt case the TCP socket closes
    # without warning, or nothing arrives at all; the Socket.IO heartbeat
    # (ping every HEARTBEAT_INTERVAL s, wait HEARTBEAT_TIMEOUT s for the pong)
    # notices the silence and fires the same "disconnect" event below.
    # --------------------------------------------------------------------------

    @socketio.on("disconnect")
    def handle_disconnect(reason=None):
        """Clean up a closed session and tell its room (BL-15, BL-20).

        Runs for every kind of disconnect. It must never raise: an exception
        here would only be logged by Socket.IO, but we also want the room to
        stay consistent, so cleanup happens first and the notice second.
        """
        sid = request.sid
        try:
            username, old_room = cleanup_session(sid)
            logger.info(
                "Client disconnected: sid=%s user=%s room=%s reason=%s",
                sid, username, old_room, reason,
            )
            # Notify the remaining room members (BL-15). The closed socket is
            # skipped: it can no longer receive anything.
            if old_room and username:
                socketio.emit(
                    "system",
                    build_leave_notice(username, old_room),
                    to=old_room,
                    skip_sid=sid,
                )
                # BL-17: send the updated online-users list to the room
                from chat.rooms import emit_room_users
                emit_room_users(old_room)
        except Exception:  # pragma: no cover - defensive, logged for diagnosis
            logger.exception("Disconnect cleanup failed: sid=%s", sid)

    @socketio.on_error_default
    def handle_unexpected_error(exc):
        """Keep the server up when any event handler raises (BL-20, SAD E500).

        The error is logged with its stack trace and the client that sent the
        event gets a short, generic ``error`` event instead of silence.
        """
        sid = getattr(request, "sid", None)
        event = (getattr(request, "event", None) or {}).get("message")
        logger.error(
            "Unhandled error in event handler: sid=%s event=%s",
            sid, event, exc_info=exc,
        )
        if sid and is_active(sid):
            code, message = E500_INTERNAL_ERROR
            emit("error", {"code": code, "message": message, "event": event})
