"""Connection lifecycle and handshake validation module.

Handles client connections, disconnections, and handshake credentials.
"""

# In-memory dictionary tracking connected clients: {session_id: username}
connected_users = {}


def get_connected_users():
    """Return a copy of the currently connected users mapping."""
    return dict(connected_users)


def register(socketio):
    """Register connection event handlers with the SocketIO instance."""
    # Handshake connection and disconnection handlers are implemented in BL-02 and BL-03.
    pass
