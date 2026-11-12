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

// BL-14 & BL-15: Room elements
const roomInput = document.getElementById("room-input");
const joinRoomBtn = document.getElementById("join-room-btn");
const leaveRoomBtn = document.getElementById("leave-room-btn");
const currentRoomBadge = document.getElementById("current-room-badge");
const roomAdminBadge = document.getElementById("room-admin-badge");
const roomVisibilityBadge = document.getElementById("room-visibility-badge");
const roomDescriptionBadge = document.getElementById("room-description-badge");
const e2eeBadge = document.getElementById("e2ee-badge");
let currentRoom = null;
let currentRoomAdmin = null;
let currentRoomVisibility = "public";
const Crypto = typeof ChatCrypto === "object" && ChatCrypto ? ChatCrypto : null;
const roomKeys = {};
let typingTimeout = null;
const typingUsers = {};
let isTyping = false;

// BL-26: Create Room modal elements
const openCreateRoomBtn = document.getElementById("open-create-room-btn");
const createRoomModal = document.getElementById("create-room-modal");
const createRoomForm = document.getElementById("create-room-form");
const closeCreateRoomBtn = document.getElementById("close-create-room-btn");
const createRoomCancelBtn = document.getElementById("create-room-cancel-btn");
const newRoomNameInput = document.getElementById("new-room-name");
const newRoomDescInput = document.getElementById("new-room-description");
const newRoomVisibilitySelect = document.getElementById("new-room-visibility");

// BL-27: Room discovery & Admin join request elements
const roomSearchInput = document.getElementById("room-search-input");
const roomSearchBtn = document.getElementById("room-search-btn");
const roomSearchResults = document.getElementById("room-search-results");
const joinRequestsPanel = document.getElementById("join-requests-panel");
const joinRequestsList = document.getElementById("join-requests-list");
const pendingJoinRequests = [];

// BL-28: Unique User ID & 1-on-1 Direct Message elements
const myUserIdEl = document.getElementById("my-user-id");
const copyUserIdBtn = document.getElementById("copy-user-id-btn");
const dmIdSearchInput = document.getElementById("dm-id-search-input");
const dmSearchBtn = document.getElementById("dm-search-btn");
const dmSearchResult = document.getElementById("dm-search-result");
let myUserId = null;

// BL-18: Current room presence elements
const onlineUsersList = document.getElementById("online-users-list");
const onlineUsersCount = document.getElementById("online-users-count");

// BL-04: Chat area elements
const emptyState = document.getElementById("empty-state");
const messageForm = document.getElementById("message-form");
const messageInput = document.getElementById("message-input");
const sendBtn = document.getElementById("send-btn");
const charCounter = document.getElementById("char-counter");
const typingIndicator = document.getElementById("typing-indicator");

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

/* ===========================================================================
 * BL-21: Connection state and automatic reconnection (SAD 4.4.3, 4.4.4)
 * ======================================================================== */

// Pure policy helpers from static/reconnect.js (back-off, reasons, messages)
const Reconnect = typeof ChatReconnect === "object" && ChatReconnect ? ChatReconnect : null;
const RECONNECT_MESSAGES = Reconnect ? Reconnect.MESSAGES : {
  C01_UNREACHABLE: "Cannot reach the server. Retrying...",
  C02_CONNECTION_LOST: "Connection lost, reconnecting...",
  C03_GAVE_UP: "Could not reconnect. Click Reconnect to try again.",
  SERVER_CLOSED: "The server closed the connection. Click Reconnect to try again.",
  RECONNECTED: "Reconnected.",
};
const MAX_RECONNECT_ATTEMPTS = Reconnect ? Reconnect.DEFAULTS.maxAttempts : 0;
const DEFAULT_ROOM = "global";

// Status chip states (SAD 4.5): Disconnected, Connecting, Connected, Reconnecting, Error
const STATE_LABELS = {
  disconnected: "Disconnected",
  connecting: "Connecting...",
  connected: "Connected",
  reconnecting: "Reconnecting...",
  error: "Error",
};
let connectionState = "disconnected";

// True once this session has been connected at least once; decides whether a
// failure is "cannot reach the server" (C01) or "connection lost" (C02).
let hadSession = false;

// Room to (re)join after every successful connect. Updated when the server
// confirms a join, cleared when the user leaves on purpose (REQ-15: rejoin the
// previous room after a reconnect).
let desiredRoom = DEFAULT_ROOM;

// Back-off scheduler; null only if reconnect.js failed to load.
const reconnectScheduler = Reconnect ? new Reconnect.ReconnectScheduler({
  onAttempt: attemptReconnect,
  onGiveUp: handleReconnectGiveUp,
}) : null;

// Generate initial guest username: "guest-" + 4 random digits
function generateGuestUsername() {
  const randomDigits = Math.floor(1000 + Math.random() * 9000);
  return `guest-${randomDigits}`;
}

// Display or hide the banner safely using textContent (NFR-SEC-2 XSS protection).
// level "warning" (amber) is used while reconnecting; everything else is an error (red).
function showError(message, level) {
  if (!errorBanner) return;
  errorBanner.classList.toggle("warning", Boolean(message) && level === "warning");
  if (message) {
    errorBanner.textContent = message;
    errorBanner.removeAttribute("hidden");
  } else {
    errorBanner.textContent = "";
    errorBanner.setAttribute("hidden", "true");
  }
}

// BL-14 & BL-15 & BL-26 & BL-27 & BL-28: Room & DM control enabling
function setRoomControlsEnabled(enabled, inRoom = false) {
  if (joinRoomBtn) joinRoomBtn.disabled = !enabled;
  if (leaveRoomBtn) leaveRoomBtn.disabled = !enabled || !inRoom;
  if (roomInput) roomInput.disabled = !enabled;
  if (openCreateRoomBtn) openCreateRoomBtn.disabled = !enabled;
  if (roomSearchInput) roomSearchInput.disabled = !enabled;
  if (roomSearchBtn) roomSearchBtn.disabled = !enabled;
  if (dmIdSearchInput) dmIdSearchInput.disabled = !enabled;
  if (dmSearchBtn) dmSearchBtn.disabled = !enabled;
  if (copyUserIdBtn) copyUserIdBtn.disabled = !enabled || !myUserId;
}

function renderDmLookupResult(data) {
  if (!dmSearchResult) return;
  dmSearchResult.textContent = "";
  if (!data) return;

  if (!data.found) {
    const empty = document.createElement("li");
    empty.className = "directory-meta";
    empty.textContent = data.message || "User not found.";
    dmSearchResult.appendChild(empty);
    return;
  }

  const li = document.createElement("li");
  li.className = "directory-item";
  const box = document.createElement("div");
  box.className = "directory-info";
  const title = document.createElement("div");
  title.className = "directory-name";
  title.textContent = data.username;
  const meta = document.createElement("div");
  meta.className = "directory-meta";
  meta.textContent = data.user_id;
  box.appendChild(title);
  box.appendChild(meta);

  const btn = document.createElement("button");
  btn.type = "button";
  btn.className = "btn-accent btn-sm";
  btn.textContent = data.is_self ? "You" : "Chat";
  btn.disabled = Boolean(data.is_self);
  btn.addEventListener("click", () => {
    if (socket && socket.connected) {
      showError("");
      socket.emit("start_dm", { user_id: data.user_id });
    }
  });

  li.appendChild(box);
  li.appendChild(btn);
  dmSearchResult.appendChild(li);
}

function renderRoomSearchResults(rooms) {
  if (!roomSearchResults) return;
  roomSearchResults.textContent = "";
  const list = Array.isArray(rooms) ? rooms : [];
  if (list.length === 0) {
    const empty = document.createElement("li");
    empty.className = "directory-meta";
    empty.textContent = "No matching public rooms.";
    roomSearchResults.appendChild(empty);
    return;
  }
  list.forEach((info) => {
    const li = document.createElement("li");
    li.className = "directory-item";

    const box = document.createElement("div");
    box.className = "directory-info";
    const title = document.createElement("div");
    title.className = "directory-name";
    title.textContent = `${info.room} (${info.member_count || 0})`;
    const meta = document.createElement("div");
    meta.className = "directory-meta";
    const adminText = info.admin ? `Admin: ${info.admin}` : "Public";
    meta.textContent = info.description ? `${info.description} — ${adminText}` : adminText;
    box.appendChild(title);
    box.appendChild(meta);

    const btn = document.createElement("button");
    btn.type = "button";
    btn.className = "btn-sm";
    btn.textContent = info.room === currentRoom ? "Joined" : "Join";
    btn.disabled = info.room === currentRoom;
    btn.addEventListener("click", () => {
      if (socket && socket.connected) {
        showError("");
        socket.emit("join_room", { room: info.room });
      }
    });

    li.appendChild(box);
    li.appendChild(btn);
    roomSearchResults.appendChild(li);
  });
}

function renderJoinRequests() {
  if (!joinRequestsPanel || !joinRequestsList) return;
  joinRequestsList.textContent = "";
  if (pendingJoinRequests.length === 0) {
    joinRequestsPanel.setAttribute("hidden", "true");
    return;
  }
  joinRequestsPanel.removeAttribute("hidden");
  pendingJoinRequests.forEach((req, index) => {
    const li = document.createElement("li");
    li.className = "directory-item";

    const box = document.createElement("div");
    box.className = "directory-info";
    const title = document.createElement("div");
    title.className = "directory-name";
    title.textContent = req.requester;
    const meta = document.createElement("div");
    meta.className = "directory-meta";
    meta.textContent = `Wants to join ${req.room}`;
    box.appendChild(title);
    box.appendChild(meta);

    const actions = document.createElement("div");
    actions.className = "input-group";

    const allowBtn = document.createElement("button");
    allowBtn.type = "button";
    allowBtn.className = "btn-success btn-sm";
    allowBtn.textContent = "Allow";
    allowBtn.addEventListener("click", () => {
      if (socket && socket.connected) {
        socket.emit("respond_join_request", {
          room: req.room,
          requester_sid: req.requester_sid,
          allow: true,
        });
      }
      pendingJoinRequests.splice(index, 1);
      renderJoinRequests();
    });

    const denyBtn = document.createElement("button");
    denyBtn.type = "button";
    denyBtn.className = "btn-danger btn-sm";
    denyBtn.textContent = "Deny";
    denyBtn.addEventListener("click", () => {
      if (socket && socket.connected) {
        socket.emit("respond_join_request", {
          room: req.room,
          requester_sid: req.requester_sid,
          allow: false,
        });
      }
      pendingJoinRequests.splice(index, 1);
      renderJoinRequests();
    });

    actions.appendChild(allowBtn);
    actions.appendChild(denyBtn);
    li.appendChild(box);
    li.appendChild(actions);
    joinRequestsList.appendChild(li);
  });
}

function updateRoomMetaBadges(data) {
  if (!data || !data.room) {
    currentRoomAdmin = null;
    currentRoomVisibility = "public";
    if (roomAdminBadge) {
      roomAdminBadge.textContent = "";
      roomAdminBadge.setAttribute("hidden", "true");
    }
    if (roomVisibilityBadge) {
      roomVisibilityBadge.textContent = "";
      roomVisibilityBadge.classList.remove("private");
      roomVisibilityBadge.setAttribute("hidden", "true");
    }
    if (roomDescriptionBadge) {
      roomDescriptionBadge.textContent = "";
      roomDescriptionBadge.setAttribute("hidden", "true");
    }
    if (e2eeBadge) e2eeBadge.setAttribute("hidden", "true");
    return;
  }

  currentRoomAdmin = typeof data.admin === "string" && data.admin ? data.admin : null;
  currentRoomVisibility = data.visibility === "private" ? "private" : "public";
  if (roomAdminBadge) {
    if (currentRoomAdmin) {
      roomAdminBadge.textContent = `Admin: ${currentRoomAdmin}`;
      roomAdminBadge.removeAttribute("hidden");
    } else {
      roomAdminBadge.textContent = "";
      roomAdminBadge.setAttribute("hidden", "true");
    }
  }
  if (roomVisibilityBadge) {
    const vis = currentRoomVisibility;
    roomVisibilityBadge.textContent = vis === "private" ? "Private" : "Public";
    roomVisibilityBadge.classList.toggle("private", vis === "private");
    roomVisibilityBadge.removeAttribute("hidden");
  }
  if (e2eeBadge) {
    if (currentRoomVisibility === "private") {
      e2eeBadge.removeAttribute("hidden");
    } else {
      e2eeBadge.setAttribute("hidden", "true");
    }
  }
  if (roomDescriptionBadge) {
    const desc = typeof data.description === "string" ? data.description.trim() : "";
    if (desc) {
      roomDescriptionBadge.textContent = desc;
      roomDescriptionBadge.removeAttribute("hidden");
    } else {
      roomDescriptionBadge.textContent = "";
      roomDescriptionBadge.setAttribute("hidden", "true");
    }
  }
}

// BL-21: Label of the Connect button for each state.
// - connected: "Disconnect" (manual disconnect, no automatic reconnect)
// - connecting / reconnecting: "Reconnect now" (skip the back-off wait)
// - error, or closed by the server: "Reconnect" (manual reconnection, C03)
// - disconnected: "Connect" (new session with the name in the box)
function connectButtonLabel(state) {
  if (state === "connected") return "Disconnect";
  if (state === "reconnecting") return "Reconnect now";
  if (state === "connecting") return hadSession ? "Reconnect now" : "Connecting...";
  if (state === "error") return "Reconnect";
  return "Connect";
}

// Update the status chip, button label and enabled controls for a state
function setConnectionState(state) {
  connectionState = state;
  const isConnected = state === "connected";
  if (!isConnected) {
    currentRoom = null;
    if (currentRoomBadge) currentRoomBadge.textContent = "Room: none";
    updateRoomMetaBadges(null);
    renderOnlineUsers([]);
  }
  // The composer is disabled while disconnected; typed text stays in the box
  // so it can be sent after reconnecting (SAD 4.4.3: not queued in v1.0).
  setComposerEnabled(isConnected);
  setRoomControlsEnabled(isConnected, Boolean(currentRoom));
  if (connectBtn) {
    connectBtn.textContent = connectButtonLabel(state);
    connectBtn.disabled = state === "connecting" && !hadSession;
  }
  if (!statusEl) return;
  statusEl.textContent = STATE_LABELS[state] || STATE_LABELS.disconnected;
  statusEl.classList.toggle("connected", isConnected);
  statusEl.classList.toggle("reconnecting", state === "reconnecting" || state === "connecting");
}

// Text shown while waiting for the next attempt, e.g.
// "Connection lost, reconnecting... (attempt 2 of 10 in 3 s)"
function reconnectNotice(attempt, delayMs) {
  const base = hadSession ? RECONNECT_MESSAGES.C02_CONNECTION_LOST : RECONNECT_MESSAGES.C01_UNREACHABLE;
  if (!attempt) return base;
  const seconds = Math.max(1, Math.round(delayMs / 1000));
  return `${base} (attempt ${attempt} of ${MAX_RECONNECT_ATTEMPTS} in ${seconds} s)`;
}

// Connection failed or dropped: wait (back-off) and try again
function scheduleReconnect() {
  if (!reconnectScheduler) {
    // reconnect.js missing: fall back to the old behaviour (manual reconnect)
    setConnectionState("error");
    showError(RECONNECT_MESSAGES.C03_GAVE_UP);
    return;
  }
  const delay = reconnectScheduler.scheduleNext();
  if (delay < 0) return; // gave up; handleReconnectGiveUp() updated the UI
  setConnectionState("reconnecting");
  showError(reconnectNotice(reconnectScheduler.attempts, delay), "warning");
}

// Called by the scheduler when it is time for the next attempt
function attemptReconnect(attempt) {
  if (!socket) return;
  setConnectionState("reconnecting");
  const base = hadSession ? RECONNECT_MESSAGES.C02_CONNECTION_LOST : RECONNECT_MESSAGES.C01_UNREACHABLE;
  showError(`${base} (attempt ${attempt} of ${MAX_RECONNECT_ATTEMPTS})`, "warning");
  try {
    // Re-opens the same socket: listeners, message list and username are kept.
    socket.connect();
  } catch (err) {
    // An unavailable server must never break the page (REQ-13)
    console.error("Reconnect attempt failed:", err);
    scheduleReconnect();
  }
}

// All automatic attempts failed (C03): stop and offer the Reconnect button
function handleReconnectGiveUp() {
  setConnectionState("error");
  showError(RECONNECT_MESSAGES.C03_GAVE_UP);
}

// Manual reconnection (Reconnect / Reconnect now button, browser back online)
function reconnectNow() {
  if (!socket) return;
  showError(hadSession ? RECONNECT_MESSAGES.C02_CONNECTION_LOST : RECONNECT_MESSAGES.C01_UNREACHABLE,
    "warning");
  if (reconnectScheduler) {
    reconnectScheduler.retryNow();
  } else {
    setConnectionState("reconnecting");
    socket.connect();
  }
}

function renderOnlineUsers(members, adminName) {
  if (!onlineUsersList || !onlineUsersCount) return;
  const admin = typeof adminName === "string" ? adminName : currentRoomAdmin;
  const users = Array.isArray(members) ? members.filter((name) => typeof name === "string") : [];
  onlineUsersList.textContent = "";
  onlineUsersCount.textContent = String(users.length);
  if (users.length === 0) {
    const empty = document.createElement("li");
    empty.className = "online-users-empty";
    empty.textContent = "No room members yet.";
    onlineUsersList.appendChild(empty);
    return;
  }
  users.forEach((username) => {
    const item = document.createElement("li");
    item.className = "online-user";
    const nameSpan = document.createElement("span");
    nameSpan.textContent = username;
    item.appendChild(nameSpan);
    if (admin && username === admin) {
      const pill = document.createElement("span");
      pill.className = "admin-pill";
      pill.textContent = "Admin";
      item.appendChild(pill);
    }
    if (username === currentUsername) item.classList.add("online-user-self");
    onlineUsersList.appendChild(item);
  });
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

// BL-15: Render system join/leave notices safely using textContent (NFR-SEC-2)
function renderSystemNotice(text, timestamp) {
  if (!messageList || !text) return;
  if (emptyState && emptyState.parentNode) {
    emptyState.parentNode.removeChild(emptyState);
  }
  const item = document.createElement("li");
  item.className = "message system";
  const content = document.createElement("span");
  content.textContent = text;
  item.appendChild(content);

  if (timestamp) {
    const time = document.createElement("time");
    time.className = "message-time";
    time.setAttribute("datetime", String(timestamp));
    time.textContent = ` (${formatTimestamp(timestamp)})`;
    item.appendChild(time);
  }

  messageList.appendChild(item);
  scrollToLatest();
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
async function handleIncomingMessage(msg) {
  if (!msg || typeof msg !== "object") return;

  let displayMsg = msg;
  const msgRoom = msg.room || currentRoom;
  if (msg.encrypted && Crypto && msgRoom && roomKeys[msgRoom]) {
    const plaintext = await Crypto.decryptMessage(msg, roomKeys[msgRoom].keyHex);
    displayMsg = Object.assign({}, msg, { content: plaintext });
  }

  const followLatest = isNearBottom() || (currentUsername && displayMsg.sender === currentUsername);

  let item;
  if (messageStore) {
    const index = messageStore.add(displayMsg);
    if (index === -1) return; // duplicate or invalid: never shown twice
    item = renderMessageAt(displayMsg, index);
  } else {
    item = renderMessage(displayMsg);
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

function clearTypingIndicator(username) {
  if (typingUsers[username]) {
    clearTimeout(typingUsers[username]);
    delete typingUsers[username];
  }
  renderTypingIndicator();
}

function renderTypingIndicator() {
  if (!typingIndicator) return;
  const names = Object.keys(typingUsers);
  typingIndicator.textContent = names.length === 0
    ? ""
    : names.length === 1
      ? names[0] + " is typing..."
      : names.join(", ") + " are typing...";
}

function stopTyping() {
  if (typingTimeout) {
    clearTimeout(typingTimeout);
    typingTimeout = null;
  }
  if (isTyping && socket && socket.connected) {
    socket.emit("stop_typing", {});
  }
  isTyping = false;
}

function sendTyping() {
  if (!socket || !socket.connected || !currentRoom || !messageInput) return;
  if (isBlankMessage(messageInput.value)) {
    stopTyping();
    return;
  }
  socket.emit("typing", {});
  isTyping = true;
  if (typingTimeout) clearTimeout(typingTimeout);
  typingTimeout = setTimeout(stopTyping, 2000);
}

// Send the text in the input box to the server.
// The server derives sender, room and timestamp; the client sends only content (SAD ADR-2).
async function sendMessage() {
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
  stopTyping();
  if (currentRoomVisibility === "private" && Crypto && currentRoom) {
    if (!roomKeys[currentRoom]) {
      roomKeys[currentRoom] = {
        keyHex: Crypto.generateKeyHex(),
        useFallback: !Crypto.hasSubtle(),
      };
      socket.emit("share_room_key", {
        room: currentRoom,
        key_hex: roomKeys[currentRoom].keyHex,
        use_fallback: roomKeys[currentRoom].useFallback,
      });
    }
    const enc = await Crypto.encryptMessage(
      content,
      roomKeys[currentRoom].keyHex,
      roomKeys[currentRoom].useFallback || !Crypto.hasSubtle()
    );
    socket.emit("message", Object.assign({ content: "[Encrypted message]" }, enc));
  } else {
    socket.emit("message", { content: content });
  }
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
    sendTyping();
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

  // BL-21: A new session starts fresh: default room, no failed attempts.
  hadSession = false;
  desiredRoom = DEFAULT_ROOM;
  if (reconnectScheduler) reconnectScheduler.reset();
  setConnectionState("connecting");

  // BL-21: Socket.IO's built-in reconnection stays off. Reconnecting is done by
  // reconnectScheduler (static/reconnect.js) so the timing follows SAD 4.4.4
  // exactly, the user sees each attempt, and a refused handshake (bad
  // username) is never retried in a loop. `timeout` bounds one attempt so an
  // unreachable host fails within 5 s (Test Plan IT-02C).
  socket = io({
    transports: ["websocket"],
    auth: { username: username },
    reconnection: false,
    timeout: 5000,
  });

  // Fired when the WebSocket handshake completes successfully (first connect
  // and every successful reconnect)
  socket.on("connect", () => {
    const isReconnect = hadSession;
    hadSession = true;
    if (reconnectScheduler) reconnectScheduler.reset();
    setConnectionState("connected");
    showError("");
    // Join the default room on first connect (BL-14) and the previous room
    // after a reconnect (BL-21). Nothing is joined if the user had left.
    if (desiredRoom) {
      socket.emit("join_room", { room: desiredRoom });
    }
    socket.emit("search_rooms", { query: roomSearchInput ? roomSearchInput.value.trim() : "" });
    if (isReconnect) {
      renderSystemNotice(RECONNECT_MESSAGES.RECONNECTED, new Date().toISOString());
    }
  });

  // BL-14 & BL-26: Acknowledged room join
  socket.on("joined", (data) => {
    stopTyping();
    Object.keys(typingUsers).forEach(clearTypingIndicator);
    if (data && typeof data.room === "string") {
      currentRoom = data.room;
      desiredRoom = data.room; // BL-21: rejoin this room after a reconnect
      if (currentRoomBadge) currentRoomBadge.textContent = `Room: ${data.room}`;
      if (roomInput) roomInput.value = data.room;
      updateRoomMetaBadges(data);
      setRoomControlsEnabled(true, true);
      renderOnlineUsers(data.members, data.admin);
      socket.emit("search_rooms", { query: roomSearchInput ? roomSearchInput.value.trim() : "" });

      // BL-29: Ensure private rooms & 1-on-1 DMs have an active E2EE room key
      if (data.visibility === "private" && Crypto) {
        if ((data.is_admin || data.room.startsWith("dm:")) && !roomKeys[data.room]) {
          roomKeys[data.room] = {
            keyHex: Crypto.generateKeyHex(),
            useFallback: !Crypto.hasSubtle(),
          };
          socket.emit("share_room_key", {
            room: data.room,
            key_hex: roomKeys[data.room].keyHex,
            use_fallback: roomKeys[data.room].useFallback,
          });
        } else if (!roomKeys[data.room]) {
          socket.emit("request_room_key", { use_fallback: !Crypto.hasSubtle() });
        }
      }
    }
  });

  // BL-29: Receive or share room encryption keys for private rooms & 1-on-1 DMs
  socket.on("room_key_shared", (data) => {
    if (!data || !data.room || !data.key_hex) return;
    const prev = roomKeys[data.room];
    roomKeys[data.room] = {
      keyHex: data.key_hex,
      useFallback: Boolean(data.use_fallback) || (prev ? prev.useFallback : false),
    };
  });

  socket.on("room_key_requested", (data) => {
    if (!data || !data.room || !roomKeys[data.room]) return;
    if (data.use_fallback) {
      roomKeys[data.room].useFallback = true;
    }
    socket.emit("share_room_key", {
      room: data.room,
      key_hex: roomKeys[data.room].keyHex,
      use_fallback: roomKeys[data.room].useFallback,
    });
  });

  // BL-15: Acknowledged room leave
  socket.on("left", (data) => {
    stopTyping();
    Object.keys(typingUsers).forEach(clearTypingIndicator);
    currentRoom = null;
    desiredRoom = null; // BL-21: user left on purpose; do not rejoin it
    if (currentRoomBadge) currentRoomBadge.textContent = "Room: none";
    updateRoomMetaBadges(null);
    renderOnlineUsers([]);
    setRoomControlsEnabled(true, false);
    socket.emit("search_rooms", { query: roomSearchInput ? roomSearchInput.value.trim() : "" });
  });

  // BL-27: Public room search results & Private room join requests
  socket.on("room_list", (data) => {
    renderRoomSearchResults(data && data.rooms ? data.rooms : []);
  });

  socket.on("join_request", (data) => {
    if (!data || !data.room || !data.requester_sid || !data.requester) return;
    const exists = pendingJoinRequests.some(
      (r) => r.room === data.room && r.requester_sid === data.requester_sid
    );
    if (!exists) {
      pendingJoinRequests.push(data);
      renderJoinRequests();
      renderSystemNotice(`${data.requester} requested to join ${data.room}.`, new Date().toISOString());
    }
  });

  socket.on("join_request_pending", (data) => {
    if (data && data.message) {
      showError(data.message, "warning");
    }
  });

  socket.on("join_request_rejected", (data) => {
    if (data && data.message) {
      showError(data.message);
    }
  });

  // BL-28: Direct Message user lookup & incoming 1-on-1 DM invite
  socket.on("user_lookup_result", (data) => {
    renderDmLookupResult(data);
  });

  socket.on("dm_invite", (data) => {
    if (!data || !data.from_user_id || !data.from_username) return;
    renderSystemNotice(
      `${data.from_username} (${data.from_user_id}) started a private 1-on-1 chat with you.`,
      new Date().toISOString()
    );
    if (dmSearchResult) {
      dmSearchResult.textContent = "";
      renderDmLookupResult({
        found: true,
        user_id: data.from_user_id,
        username: `${data.from_username} (Incoming DM)`,
        is_self: false,
      });
    }
  });

  // BL-17/BL-18: Live online-user list for the active room
  socket.on("user_list", (data) => {
    if (!data || data.room !== currentRoom || !Array.isArray(data.members)) return;
    renderOnlineUsers(data.members, data.admin);
  });

  // BL-19: Show typing activity from other members of the current room.
  socket.on("user_typing", (data) => {
    if (!data || data.room !== currentRoom || typeof data.username !== "string" ||
        data.username === currentUsername) return;
    if (typingUsers[data.username]) clearTimeout(typingUsers[data.username]);
    typingUsers[data.username] = setTimeout(() => clearTypingIndicator(data.username), 2000);
    renderTypingIndicator();
  });

  socket.on("user_stopped_typing", (data) => {
    if (!data || data.room !== currentRoom || typeof data.username !== "string") return;
    clearTypingIndicator(data.username);
  });

  // BL-15: System notification for user join / leave
  socket.on("system", (data) => {
    if (data && typeof data.message === "string") {
      renderSystemNotice(data.message, data.timestamp);
    }
  });

  // Fired when server sends acknowledgment payload
  socket.on("ack", (data) => {
    console.log("Server acknowledgment:", data);
    if (data && typeof data.username === "string") {
      currentUsername = data.username;
    }
    if (data && typeof data.user_id === "string") {
      myUserId = data.user_id;
      if (myUserIdEl) myUserIdEl.textContent = myUserId;
      if (copyUserIdBtn) copyUserIdBtn.disabled = false;
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
  // Fired when the connection is refused (BL-03) or the server cannot be
  // reached (BL-21). Only the second case is retried.
  socket.on("connect_error", (err) => {
    const refused = Reconnect
      ? Reconnect.isHandshakeRefusal(err, socket ? socket.active : undefined)
      : true;

    if (!refused) {
      // Server down or network unavailable: keep the page usable and retry
      // with back-off (REQ-13, NT-12).
      scheduleReconnect();
      return;
    }

    if (reconnectScheduler) reconnectScheduler.reset();
    setConnectionState("disconnected");

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

  // Fired when an established connection ends (BL-21)
  socket.on("disconnect", (reason) => {
    // BL-19: Clear typing state when disconnected
    stopTyping();
    Object.keys(typingUsers).forEach(clearTypingIndicator);

    if (reason === "io client disconnect") {
      // The user clicked Disconnect: no automatic reconnect
      if (reconnectScheduler) reconnectScheduler.reset();
      setConnectionState("disconnected");
      return;
    }

    const autoRetry = Reconnect ? Reconnect.shouldAutoReconnect(reason) : false;
    if (autoRetry) {
      // Server stopped, network dropped or heartbeat missed (C02)
      scheduleReconnect();
      return;
    }

    // The server closed the session on purpose: offer a manual Reconnect
    if (reconnectScheduler) reconnectScheduler.reset();
    setConnectionState("error");
    showError(RECONNECT_MESSAGES.SERVER_CLOSED);
  });
}


// Handle Connect / Disconnect / Reconnect button click
if (connectBtn) {
  connectBtn.addEventListener("click", () => {
    if (socket && socket.connected) {
      // Disconnect active socket (manual: no automatic reconnect)
      socket.disconnect();
    } else if (socket && hadSession &&
               (connectionState === "reconnecting" || connectionState === "connecting" ||
                connectionState === "error")) {
      // BL-21: manual reconnection keeps the session's name, room and messages
      reconnectNow();
    } else {
      // Clear error and attempt connection with entered username
      showError("");
      const enteredName = usernameInput ? usernameInput.value : "";
      connectToServer(enteredName);
    }
  });
}

// BL-21: React to the browser's own network status.
// Going offline closes the dead connection at once instead of waiting up to
// 45 s for the heartbeat; coming back online retries without waiting for the
// back-off timer (Test Plan NT-11).
window.addEventListener("offline", () => {
  if (socket && socket.connected && socket.io && socket.io.engine) {
    socket.io.engine.close(); // reason "forced close" -> scheduleReconnect()
  }
});

window.addEventListener("online", () => {
  if (socket && !socket.connected &&
      (connectionState === "reconnecting" || connectionState === "error")) {
    reconnectNow();
  }
});

// BL-14 & BL-15: Join and Leave Room button handlers
if (joinRoomBtn) {
  joinRoomBtn.addEventListener("click", () => {
    if (!socket || !socket.connected) {
      showError(MSG_NOT_CONNECTED);
      return;
    }
    const enteredRoom = roomInput ? roomInput.value.trim() : "";
    if (!enteredRoom) {
      showError("Room name cannot be empty.");
      return;
    }
    if (enteredRoom.length > 30) {
      showError("Room name must not exceed 30 characters.");
      return;
    }
    showError("");
    socket.emit("join_room", { room: enteredRoom });
  });
}

if (leaveRoomBtn) {
  leaveRoomBtn.addEventListener("click", () => {
    if (!socket || !socket.connected) {
      showError(MSG_NOT_CONNECTED);
      return;
    }
    showError("");
    socket.emit("leave_room", {});
  });
}

// BL-26: Create Room modal handlers
function closeCreateRoomModal() {
  if (createRoomModal) createRoomModal.setAttribute("hidden", "true");
}

if (openCreateRoomBtn && createRoomModal) {
  openCreateRoomBtn.addEventListener("click", () => {
    if (!socket || !socket.connected) {
      showError(MSG_NOT_CONNECTED);
      return;
    }
    if (newRoomNameInput) newRoomNameInput.value = "";
    if (newRoomDescInput) newRoomDescInput.value = "";
    if (newRoomVisibilitySelect) newRoomVisibilitySelect.value = "public";
    createRoomModal.removeAttribute("hidden");
    if (newRoomNameInput) newRoomNameInput.focus();
  });
}

if (closeCreateRoomBtn) {
  closeCreateRoomBtn.addEventListener("click", closeCreateRoomModal);
}
if (createRoomCancelBtn) {
  createRoomCancelBtn.addEventListener("click", closeCreateRoomModal);
}
if (createRoomModal) {
  createRoomModal.addEventListener("click", (e) => {
    if (e.target === createRoomModal) closeCreateRoomModal();
  });
}

if (createRoomForm) {
  createRoomForm.addEventListener("submit", (e) => {
    e.preventDefault();
    if (!socket || !socket.connected) {
      showError(MSG_NOT_CONNECTED);
      return;
    }
    const room = newRoomNameInput ? newRoomNameInput.value.trim() : "";
    const description = newRoomDescInput ? newRoomDescInput.value.trim() : "";
    const visibility = newRoomVisibilitySelect ? newRoomVisibilitySelect.value : "public";
    if (!room) {
      showError("Room name cannot be empty.");
      return;
    }
    showError("");
    socket.emit("create_room", { room, description, visibility });
    closeCreateRoomModal();
  });
}

// BL-27: Public room search handlers
function triggerRoomSearch() {
  if (!socket || !socket.connected) return;
  const query = roomSearchInput ? roomSearchInput.value.trim() : "";
  socket.emit("search_rooms", { query });
}

if (roomSearchBtn) {
  roomSearchBtn.addEventListener("click", triggerRoomSearch);
}
if (roomSearchInput) {
  roomSearchInput.addEventListener("input", triggerRoomSearch);
}

// BL-28: Copy Unique ID & Search User for 1-on-1 DM
if (copyUserIdBtn) {
  copyUserIdBtn.addEventListener("click", () => {
    if (!myUserId) return;
    if (navigator.clipboard && navigator.clipboard.writeText) {
      navigator.clipboard.writeText(myUserId).then(() => {
        copyUserIdBtn.textContent = "Copied!";
        setTimeout(() => { copyUserIdBtn.textContent = "Copy"; }, 1500);
      }).catch(() => {});
    }
  });
}

function triggerDmLookup() {
  if (!socket || !socket.connected) {
    showError(MSG_NOT_CONNECTED);
    return;
  }
  const queryId = dmIdSearchInput ? dmIdSearchInput.value.trim() : "";
  if (!queryId) {
    showError("Enter a User ID to search.");
    return;
  }
  showError("");
  socket.emit("lookup_user", { user_id: queryId });
}

if (dmSearchBtn) {
  dmSearchBtn.addEventListener("click", triggerDmLookup);
}
if (dmIdSearchInput) {
  dmIdSearchInput.addEventListener("keydown", (e) => {
    if (e.key === "Enter") {
      e.preventDefault();
      triggerDmLookup();
    }
  });
}

// Pre-fill username and initiate connection on initial page load
if (usernameInput) {
  usernameInput.value = generateGuestUsername();
  usernameInput.addEventListener("keydown", (e) => {
    if (e.key === "Enter") {
      showError("");
      connectToServer(usernameInput.value);
    }
  });
  connectToServer(usernameInput.value);
}
