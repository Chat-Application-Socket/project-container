// Client connection handling logic for Chat Application
// Enforces pure WebSocket transport and sanitized DOM rendering (textContent).

/*
 * BEGINNER CONCEPT: Why transports: ["websocket"]?
 * By default, Socket.IO starts with HTTP long-polling (repeated HTTP GET/POST requests)
 * and attempts to upgrade to WebSockets afterward.
 * The SRS (v1.1) strictly forbids HTTP long-polling. Passing `transports: ["websocket"]`
 * tells the Socket.IO client to connect directly and exclusively using the WebSocket protocol (ws:// or wss://).
 */

/*
 * BEGINNER CONCEPT: Handshake & auth
 * When connecting, the client initiates a WebSocket handshake. The `auth` object is passed
 * along in this handshake. The server inspects `auth.username` before accepting the connection.
 * If rejected, the server aborts the handshake and the client fires a `connect_error` event.
 */

let socket = null;

const statusEl = document.getElementById("status");
const usernameInput = document.getElementById("username");
const connectBtn = document.getElementById("connect-btn");
const errorBanner = document.getElementById("error-banner");

// Generate initial guest username: "guest-" + 4 random digits
function generateGuestUsername() {
  const randomDigits = Math.floor(1000 + Math.random() * 9000);
  return `guest-${randomDigits}`;
}

// Display or hide error banner safely using textContent (NFR-SEC-2 XSS protection)
function showError(message) {
  if (!errorBanner) return;
  if (message) {
    errorBanner.textContent = message;
    errorBanner.removeAttribute("hidden");
  } else {
    errorBanner.textContent = "";
    errorBanner.setAttribute("hidden", "true");
  }
}

// Update connection status label and toggle button label
function updateStatus(statusText, isConnected) {
  if (!statusEl) return;
  statusEl.textContent = statusText;
  if (isConnected) {
    statusEl.classList.add("connected");
    if (connectBtn) connectBtn.textContent = "Disconnect";
  } else {
    statusEl.classList.remove("connected");
    if (connectBtn) connectBtn.textContent = "Connect";
  }
}

// Connect to the WebSocket server using the supplied username
function connectToServer(username) {
  // Clear any existing error message
  showError("");

  // Close any existing connection cleanly before establishing a new one
  if (socket) {
    socket.removeAllListeners();
    socket.disconnect();
    socket = null;
  }

  // Auto-reconnect is deferred to Sprint 2 (BL-21). Keep reconnection: false
  // so handshake errors remain visible to the user.
  socket = io({
    transports: ["websocket"],
    auth: { username: username },
    reconnection: false,
  });

  // Fired when the WebSocket handshake completes successfully
  socket.on("connect", () => {
    updateStatus("Connected", true);
    showError("");
  });

  // Fired when server sends acknowledgment payload
  socket.on("ack", (data) => {
    console.log("Server acknowledgment:", data);
  });

  // Fired when the connection is refused or fails (BL-03)
  socket.on("connect_error", (err) => {
    updateStatus("Disconnected", false);

    // If server provided a specific refusal message, extract it;
    // otherwise fallback to a generic friendly error message
    let message = "Unable to connect to server";
    if (err) {
      if (err.data && typeof err.data === "object" && err.data.message) {
        message = err.data.message;
      } else if (err.message && err.message !== "websocket error" && err.message !== "xhr poll error") {
        message = err.message;
      }
    }
    showError(message);
  });

  // Fired when the client disconnects from the server
  socket.on("disconnect", () => {
    updateStatus("Disconnected", false);
  });
}

// Handle Connect / Disconnect button click
if (connectBtn) {
  connectBtn.addEventListener("click", () => {
    if (socket && socket.connected) {
      // Disconnect active socket
      socket.disconnect();
    } else {
      // Clear error and attempt connection with entered username
      showError("");
      const enteredName = usernameInput ? usernameInput.value : "";
      connectToServer(enteredName);
    }
  });
}

// Pre-fill username and initiate connection on initial page load
if (usernameInput) {
  usernameInput.value = generateGuestUsername();
  usernameInput.addEventListener("keydown", (e) => {
    if (e.key === "Enter" && (!socket || !socket.connected)) {
      showError("");
      connectToServer(usernameInput.value);
    }
  });
  connectToServer(usernameInput.value);
}
