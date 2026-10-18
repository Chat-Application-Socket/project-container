import os
from chat import create_app, socketio

app = create_app()

if __name__ == "__main__":
    # Read port from PORT environment variable, defaulting to 5000 as required
    port = int(os.environ.get("PORT", 5000))

    # Host 0.0.0.0 binds to all network interfaces, allowing cross-device / container testing.
    # debug=False disables hot-reloading in production/test environments.
    # allow_unsafe_werkzeug=True enables the Werkzeug server to run with WebSocket support.
    socketio.run(
        app,
        host="0.0.0.0",
        port=port,
        debug=False,
        allow_unsafe_werkzeug=True,
    )
