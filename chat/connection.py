"""Connection lifecycle and handshake validation module.

This module handles:
1. Client WebSocket connection handshakes.
2. Validating authentication credentials passed during connection.
3. Tracking connected clients in an in-memory dictionary.
4. Sending connection acknowledgments (ack).
5. Cleaning up state when clients disconnect.
"""

import logging
from flask import request
from flask_socketio import ConnectionRefusedError, emit

# Configure module-level logger
logger = logging.getLogger(__name__)
if not logger.handlers:
    logging.basicConfig(level=logging.INFO)

# In-memory mapping of active client connections: {socket_session_id (sid): username}
connected_users = {}


def get_connected_users():
    """Return a shallow copy of the active connected users dictionary.

    Exposed for future backlog items (such as user lists and room logic) and unit tests.
    """
    return dict(connected_users)


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
        connected_users[sid] = username
        logger.info("Client connected: sid=%s user=%s", sid, username)

        # Emit server acknowledgment directly to the newly connected client
        emit("ack", {
            "sid": sid,
            "username": username,
            "message": "Connected",
        })

    @socketio.on("disconnect")
    def handle_disconnect():
        """Handle client disconnection and clean up user state (BL-15 notice on disconnect)."""
        sid = request.sid
        username = connected_users.pop(sid, None)
        logger.info("Client disconnected: sid=%s user=%s", sid, username)

        # Notify room members when a user disconnects (BL-15)
        from chat.rooms import remove_user_from_room
        from datetime import datetime, timezone
        old_room = remove_user_from_room(sid)
        if old_room and username:
            emit("system", {
                "type": "leave",
                "sender": username,
                "room": old_room,
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "message": f"{username} left the room",
            }, to=old_room)
