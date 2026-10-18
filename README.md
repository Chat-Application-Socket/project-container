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
| `templates/index.html` | Chat UI template with status badge, controls, and error banner | REQ-1, REQ-2, BL-01, BL-02 |
| `static/client.js` | Client-side Socket.IO client logic (WebSocket-only transport, XSS-safe rendering) | REQ-1, REQ-2, NFR-SEC-2, BL-02, BL-03 |
| `static/style.css` | UI styling for chat container, status indicators, and error banners | BL-01, BL-02 |
| `tests/test_smoke.py` | Basic smoke test verifying application factory creation | BL-01 |
| `tests/test_connection.py` | Pytest test suite testing connection handshakes, refusals, and disconnections | REQ-1, REQ-2, BL-02, BL-03 |

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
