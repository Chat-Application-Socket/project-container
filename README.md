# Chat Application (Socket Programming)

A real-time multi-user chat web application engineered using modern socket programming principles.
The application enables responsive, bi-directional communication between clients and a central server
over dedicated WebSocket connections without long-polling fallbacks.

## Decision Record: Backend Stack
- **Decision**: Flask + Flask-SocketIO with `simple-websocket` in `async_mode="threading"`
- **Date**: 2026-10-18
- **Rationale**:
  - The SRS (v1.1) permits either Flask + Flask-SocketIO or Node.js (not both).
  - Aligns with the core Python skill set of the team of 4.
  - `simple-websocket` provides pure, standard-compliant WebSocket protocol transport (satisfying the constraint strictly forbidding HTTP long-polling).
  - Running Flask-SocketIO in `async_mode="threading"` eliminates eventlet/gevent monkey-patching and native C-extension compilation problems on Windows, ensuring seamless cross-platform operation across Windows, macOS, and Linux.
- **Alternatives Considered**: Node.js + ws (rejected to leverage team Python experience and simpler integration with existing Python CI workflows).

## Project Structure

| Folder / File | Purpose | SRS Requirement / Backlog Item |
| :--- | :--- | :--- |
| `app.py` | Application entry point; initializes and runs Socket.IO server on configurable `PORT` (default 5000) | BL-01 |
| `requirements.txt` | Pinned production dependencies (Flask, Flask-SocketIO, simple-websocket) | BL-01 |
| `pytest.ini` | Pytest configuration specifying test paths and pythonpath | BL-01 |
| `.flake8` | Flake8 linter configuration enforcing PEP 8 standards (max-line-length 100) | BL-01 |
| `.gitignore` | Ignores virtual environments, caches, bytecode, and environment files | BL-01 |
| `chat/__init__.py` | Application factory `create_app()` and global `socketio` instance registration | BL-01, NFR-MNT-1 |
| `chat/connection.py` | Connection lifecycle management, handshake auth validation, and connected user registry | REQ-1, REQ-2, BL-02, BL-03 |
| `chat/rooms.py` | Room management module stub (default global room, join/leave handlers) | BL-14 (Sprint 2) |
| `chat/broadcast.py` | Message broadcasting module stub (delivering messages to rooms) | BL-05 |
| `chat/validator.py` | Server-side message validation: rejects empty / whitespace-only messages with error `E304` and provides the `@reject_empty_message` decorator for the `message` handler | REQ-5, BL-07 |
| `templates/index.html` | Chat UI template with status badge, controls, error banner, message list and message input with Send button | REQ-1, REQ-2, BL-01, BL-02, BL-04 |
| `static/client.js` | Client-side Socket.IO client logic (WebSocket-only transport, XSS-safe rendering, Send button / Enter key, message rendering) | REQ-1, REQ-2, NFR-SEC-2, BL-02, BL-03, BL-04 |
| `static/style.css` | UI styling for chat container, status indicators, error banners, message list and responsive (phone width) layout | BL-01, BL-02, BL-04 |
| `tests/test_smoke.py` | Basic smoke test verifying application factory creation | BL-01 |
| `tests/test_connection.py` | Pytest test suite testing connection handshakes, refusals, and disconnections | REQ-1, REQ-2, BL-02, BL-03 |
| `tests/test_chat_ui.py` | Checks the chat page contains the message list, input, Send button, error banner and mobile viewport | BL-04 |
| `tests/test_message_validation.py` | Unit and integration tests for empty / whitespace-only message rejection (UT-05A to UT-05C, IT-05B) | REQ-5, BL-07 |

## Setup Steps

### Windows (PowerShell)
```powershell
# 1. Create a virtual environment
py -m venv .venv

# 2. Activate the virtual environment
.venv\Scripts\Activate.ps1

# 3. Install dependencies
pip install -r requirements.txt
```

### macOS / Linux (bash / zsh)
```bash
# 1. Create a virtual environment
python3 -m venv .venv

# 2. Activate the virtual environment
source .venv/bin/activate

# 3. Install dependencies
pip install -r requirements.txt
```

## Running the Application
Start the server with a single command:
```bash
python app.py
```
Then open your web browser at:
[http://localhost:5000](http://localhost:5000)

### Using the chat page
- The page connects automatically with a `guest-XXXX` username (change it and click **Connect** to use another name).
- Type in the message box at the bottom and press **Enter** or click **Send**. Use **Shift+Enter** for a new line.
- Messages appear in the message area with the sender, the text and the time. The message box and Send button are disabled while disconnected.
- Problems (server unreachable, rejected username, rejected message) are shown in the red banner at the top.
- Empty or whitespace-only messages are blocked: the page shows *Type a message first.* and sends nothing. The server checks again and answers a blank message with an `error` event (`E304`, *Message cannot be empty.*) without broadcasting it.

### Message validation contract (for the `message` handler)
The `message` event handler must be wrapped with `@reject_empty_message` from `chat/validator.py`, so blank messages are rejected on the server even when the UI is bypassed:
```python
from chat.validator import reject_empty_message

@socketio.on("message")
@reject_empty_message
def handle_message(data):
    content = data["content"]  # already trimmed and never empty
```

To override the default port, set the `PORT` environment variable:
```bash
PORT=8080 python app.py
```

## Running Tests and Linting
Run the test suite using pytest:
```bash
pytest
```

Run code style checks with flake8:
```bash
flake8 . --max-line-length 100
```

## Team Workflow
- **Branching Strategy**: Create an isolated Git branch per backlog item following the naming pattern: `bl-<item-number>-<short-description>` (e.g., `bl-01-repo-skeleton`, `bl-02-websocket-connect`, `bl-03-reject-handshake`).
- **Commit Messages**: Prefix commit messages with the backlog item ID (e.g., `BL-01: Setup repository skeleton and modular structure`).
- **Pull Requests**: Pull request descriptions must include `Closes #<issue-number>` (e.g., `Closes #8`).
- **Review & Quality Gate**:
  - Pull requests require approval from at least one teammate before merging.
  - GitHub Actions CI workflow must pass all checks (`pytest`, `flake8`, port check) on Python 3.9 and 3.12.
- **No Direct Commits to Main**: Work is merged strictly via pull requests into the base branch.

## Definition of Done (DoD)
A backlog item is completed only when:
1. All acceptance criteria for the backlog item are met and verified.
2. Code is cleanly modularized, PEP 8 compliant (`flake8 . --max-line-length 100`), and free of regressions.
3. Automated unit and integration tests are written and passing locally and in CI (`pytest`).
4. Documentation and README instructions are updated to reflect any new behavior or configuration.
5. Branch is pushed, a Pull Request is opened with `Closes #<issue>`, peer reviewed, and merged.

## Production HTTPS / WSS (BL-23)

In production, serve the chat application over HTTPS and use TLS to encrypt WebSocket traffic in transit. A recommended setup is Nginx as a reverse proxy with a valid TLS certificate, forwarding WebSocket connections to the Flask-SocketIO application.

### Client connection behavior

The client uses a relative Socket.IO URL:

```javascript
socket = io({
  transports: ["websocket"],
  auth: { username: username },
  reconnection: false,
});
```

Because the URL is relative to the current page, the browser uses the page's origin and scheme. When the page is served over HTTPS, the WebSocket connection uses `wss://`. When running locally over HTTP, it uses `ws://`. WebSocket-only transport remains enforced; HTTP long-polling is not enabled.

### Production setup with Nginx

1. Deploy the application on a Linux server with a domain name pointing to that server.
2. Install Nginx and obtain a valid TLS certificate for the domain, for example using Certbot.
3. Configure Nginx to terminate TLS and proxy WebSocket requests to the Flask-SocketIO application.
4. Keep the application's backend port private. Configure the server firewall to prevent public access to port 5000; expose HTTPS through Nginx instead.

Example Nginx server configuration (replace `chat.example.com` and certificate paths with your actual values):

```nginx
server {
    listen 80;
    server_name chat.example.com;
    return 301 https://$host$request_uri;
}

server {
    listen 443 ssl;
    server_name chat.example.com;

    ssl_certificate /etc/letsencrypt/live/chat.example.com/fullchain.pem;
    ssl_certificate_key /etc/letsencrypt/live/chat.example.com/privkey.pem;

    location / {
        proxy_pass http://127.0.0.1:5000;
        proxy_http_version 1.1;

        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;

        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection "upgrade";

        proxy_read_timeout 3600s;
        proxy_send_timeout 3600s;
    }
}
```

### Start and verify

1. Start the Flask-SocketIO application using the project's normal startup command.
2. Configure Nginx with the server block above, validate the configuration with `sudo nginx -t`, and reload Nginx.
3. Open `https://chat.example.com` in a browser and connect to the chat.
4. In the browser's Developer Tools, open the Network tab and filter for WS (WebSocket). Confirm that the connection uses `wss://` and completes successfully.
5. Send a message and confirm that it reaches the other connected client.
6. Confirm that the application backend port is not publicly accessible and that HTTP requests to the domain redirect to HTTPS.

A successful local test does not prove production TLS is configured. Verify the deployed domain, certificate, WebSocket connection, and firewall separately.