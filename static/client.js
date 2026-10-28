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
const messageList = document.getElementById("message-list");

// BL-04: Chat area elements
const messageList = document.getElementById("message-list");
const emptyState = document.getElementById("empty-state");
const messageForm = document.getElementById("message-form");
const messageInput = document.getElementById("message-input");
const sendBtn = document.getElementById("send-btn");
const charCounter = document.getElementById("char-counter");

// Limits and client-local messages (SAD 4.4.2, Table 15)
const MAX_MESSAGE_LENGTH = 500;
const MSG_NOT_CONNECTED = "You are not connected."; // C05
const MSG_EMPTY_INPUT = "Type a message first."; // C04 (BL-07)

// BL-07: Characters that render as nothing. String.prototype.trim() already
// removes normal whitespace; these zero-width characters are removed as well so
// the client applies the same rule as the server validator (chat/validator.py).
const INVISIBLE_CHARS = /[​‌‍⁠﻿]/g;

// BL-07: True when the text is empty or contains only whitespace / invisible characters
function isBlankMessage(text) {
  if (typeof text !== "string") return true;
  return text.replace(INVISIBLE_CHARS, "").trim().length === 0;
}

// Username confirmed by the server in the "ack" event (used to highlight own messages)
let currentUsername = null;

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
  setComposerEnabled(isConnected);
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

/* ===========================================================================
 * BL-04: Chat page UI helpers
 * ======================================================================== */

// Enable the message box and Send button only while connected (BR-1)
function setComposerEnabled(enabled) {
  if (messageInput) messageInput.disabled = !enabled;
  if (sendBtn) sendBtn.disabled = !enabled;
}

// Format a server timestamp (RFC 3339 UTC string) as local HH:MM:SS.
// Falls back to the raw value, or an empty string, if it cannot be parsed.
function formatTimestamp(timestamp) {
  if (!timestamp) return "";
  const date = new Date(timestamp);
  if (isNaN(date.getTime())) return String(timestamp);
  return date.toLocaleTimeString([], { hour: "2-digit", minute: "2-digit", second: "2-digit" });
}

// Build one message row: sender + timestamp on top, message text below.
// Every value is written with textContent so HTML in a message is shown as text (NFR-SEC-2).
function createMessageElement(msg) {
  const item = document.createElement("li");
  item.className = "message";
  if (currentUsername && msg.sender === currentUsername) {
    item.classList.add("own");
  }

  const meta = document.createElement("div");
  meta.className = "message-meta";

  const sender = document.createElement("span");
  sender.className = "message-sender";
  sender.textContent = msg.sender ? String(msg.sender) : "unknown";

  const time = document.createElement("time");
  time.className = "message-time";
  if (msg.timestamp) {
    time.setAttribute("datetime", String(msg.timestamp));
    time.title = String(msg.timestamp);
  }
  time.textContent = formatTimestamp(msg.timestamp);

  const content = document.createElement("p");
  content.className = "message-content";
  content.textContent = msg.content == null ? "" : String(msg.content);

  meta.appendChild(sender);
  meta.appendChild(time);
  item.appendChild(meta);
  item.appendChild(content);
  return item;
}

// Append a message to the end of the message list
function renderMessage(msg) {
  if (!messageList || !msg || typeof msg !== "object") return null;
  if (emptyState && emptyState.parentNode) {
    emptyState.parentNode.removeChild(emptyState);
  }
  const item = createMessageElement(msg);
  messageList.appendChild(item);
  return item;
}

/* ===========================================================================
 * BL-08: Render received messages live, in order, without page refresh
 * ======================================================================== */

// Ordered, de-duplicated list of received messages (static/messages.js)
const messageStore = typeof MessageStore === "function" ? new MessageStore() : null;

// How close (in px) to the bottom counts as "reading the latest messages"
const AUTO_SCROLL_THRESHOLD_PX = 80;

function isNearBottom() {
  if (!messageList) return true;
  const distance = messageList.scrollHeight - messageList.scrollTop - messageList.clientHeight;
  return distance <= AUTO_SCROLL_THRESHOLD_PX;
}

function scrollToLatest() {
  if (!messageList) return;
  messageList.scrollTop = messageList.scrollHeight;
}

// Insert a message at a given position of the list (index from MessageStore)
function renderMessageAt(msg, index) {
  if (!messageList) return null;
  if (emptyState && emptyState.parentNode) {
    emptyState.parentNode.removeChild(emptyState);
  }
  const item = createMessageElement(msg);
  const nextItem = messageList.children[index] || null;
  messageList.insertBefore(item, nextItem);
  return item;
}

// Called for every "message" event pushed by the server (no polling, no refresh).
// The view follows new messages if the user is already at the bottom or the
// message is their own; if they scrolled up to read older ones, it stays put.
function handleIncomingMessage(msg) {
  if (!msg || typeof msg !== "object") return;

  const followLatest = isNearBottom() || (currentUsername && msg.sender === currentUsername);

  let item;
  if (messageStore) {
    const index = messageStore.add(msg);
    if (index === -1) return; // duplicate or invalid: never shown twice
    item = renderMessageAt(msg, index);
  } else {
    item = renderMessage(msg);
  }

  if (item && followLatest) {
    scrollToLatest();
  }
}

// Empty the message area (used when the user starts a new connection)
function clearMessages() {
  if (messageStore) messageStore.clear();
  if (!messageList) return;
  while (messageList.firstChild) {
    messageList.removeChild(messageList.firstChild);
  }
  if (emptyState) messageList.appendChild(emptyState);
}

// Keep the "n / 500" counter in sync with the input box
function updateCharCounter() {
  if (!charCounter || !messageInput) return;
  const length = messageInput.value.length;
  charCounter.textContent = `${length} / ${MAX_MESSAGE_LENGTH}`;
  charCounter.classList.toggle("near-limit", length >= MAX_MESSAGE_LENGTH - 50);
}

// Send the text in the input box to the server.
// The server derives sender, room and timestamp; the client sends only content (SAD ADR-2).
function sendMessage() {
  if (!messageInput) return;

  // BL-07: Block empty / whitespace-only input before anything is sent (C04).
  // Nothing is emitted, the box keeps focus, and the user sees a short hint.
  if (isBlankMessage(messageInput.value)) {
    messageInput.value = "";
    updateCharCounter();
    showError(MSG_EMPTY_INPUT);
    messageInput.focus();
    return;
  }

  if (!socket || !socket.connected) {
    showError(MSG_NOT_CONNECTED);
    return;
  }

  const content = messageInput.value.trim();
  socket.emit("message", { content: content });
  showError("");

  messageInput.value = "";
  updateCharCounter();
  messageInput.focus();
}

// Send button (form submit) and Enter key handling
if (messageForm) {
  messageForm.addEventListener("submit", (e) => {
    e.preventDefault();
    sendMessage();
  });
}

if (messageInput) {
  messageInput.addEventListener("keydown", (e) => {
    // Enter sends; Shift+Enter inserts a new line; ignore Enter while an IME is composing
    if (e.key === "Enter" && !e.shiftKey && !e.isComposing) {
      e.preventDefault();
      sendMessage();
    }
  });
  messageInput.addEventListener("input", () => {
    updateCharCounter();
    // BL-07: Hide the "Type a message first." hint once the user starts typing
    if (errorBanner && errorBanner.textContent === MSG_EMPTY_INPUT && !isBlankMessage(messageInput.value)) {
      showError("");
    }
  });
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

  // BL-08: A new connection starts with an empty message area
  clearMessages();

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
    if (data && typeof data.username === "string") {
      currentUsername = data.username;
    }
  });

  // BL-08: Server pushes each chat message as a "message" event:
  // {id, type, sender, room, content, timestamp, seq}. Render it straight away.
  socket.on("message", (data) => {
    try {
      handleIncomingMessage(data);
    } catch (err) {
      // A bad event must never break the page (SAD 4.4)
      console.error("Could not display message:", err);
    }
  });

  // BL-07: Server rejected one of our requests, e.g. an empty message sent outside the UI.
  // Payload is {code, message, event}; only the fixed, readable message is shown.
  socket.on("error", (data) => {
    let message = "Something went wrong. Please retry.";
    if (data && typeof data === "object" && typeof data.message === "string" && data.message) {
      message = data.message;
    }
    showError(message);
  });

// Display incoming messages with the server-generated timestamp.
  socket.on("new_message", (message) => {
    if (!messageList || !message || typeof message !== "object") {
      return;
    }

    const item = document.createElement("li");
    const timestamp = document.createElement("time");
    const text = document.createElement("span");

    const sender =
      typeof message.sender === "string" ? message.sender : "Unknown";

    const content =
      typeof message.content === "string" ? message.content : "";

    if (typeof message.timestamp === "string") {
      timestamp.dateTime = message.timestamp;

      const date = new Date(message.timestamp);
      timestamp.textContent = Number.isNaN(date.getTime())
        ? message.timestamp
        : date.toLocaleString();
    } else {
      timestamp.textContent = "Time unavailable";
    }

    text.textContent = ` ${sender}: ${content}`;

    item.appendChild(timestamp);
    item.appendChild(text);
    messageList.appendChild(item);
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
