import os
from flask import Flask, render_template
from flask_socketio import SocketIO

# SocketIO instance configured with async_mode="threading" to ensure cross-platform
# compatibility (avoiding eventlet/gevent issues on Windows).
# transports are restricted to "websocket" on the client side per SRS.
#
# BL-20: Heartbeat (SAD configuration table). The server pings each client every
# HEARTBEAT_INTERVAL seconds and drops it if no pong arrives within
# HEARTBEAT_TIMEOUT seconds, so a silent connection loss (cable pulled, laptop
# asleep) is detected within about 45 s and the session is cleaned up.
HEARTBEAT_INTERVAL = 25
HEARTBEAT_TIMEOUT = 20

socketio = SocketIO(
    async_mode="threading",
    ping_interval=HEARTBEAT_INTERVAL,
    ping_timeout=HEARTBEAT_TIMEOUT,
)


def create_app():
    """Application factory for the real-time chat application."""
    base_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
    app = Flask(
        __name__,
        template_folder=os.path.join(base_dir, "templates"),
        static_folder=os.path.join(base_dir, "static"),
    )

    @app.route("/")
    def index():
        return render_template("index.html")

    # Bind the socketio extension to the Flask application
    socketio.init_app(app)

    # Register modular socket event handlers
    from chat import connection, rooms, broadcast

    connection.register(socketio)
    rooms.register(socketio)
    broadcast.register(socketio)

    return app
