// Client connection handling logic for Chat Application
// Enforces WebSocket transport only and uses textContent for XSS prevention.

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

// Pre-fill username input on load
if (usernameInput) {
  usernameInput.value = generateGuestUsername();
}

// Helper to display error messages safely via textContent (prevent XSS per NFR-SEC-2)
function showError(message) {
  if (errorBanner) {
    if (message) {
      errorBanner.textContent = message;
      errorBanner.removeAttribute("hidden");
    } else {
      errorBanner.textContent = "";
      errorBanner.setAttribute("hidden", "true");
    }
  }
}

// Helper to update connection status
function updateStatus(statusText, isConnected) {
  if (statusEl) {
    statusEl.textContent = statusText;
    if (isConnected) {
      statusEl.classList.add("connected");
      if (connectBtn) connectBtn.textContent = "Disconnect";
    } else {
      statusEl.classList.remove("connected");
      if (connectBtn) connectBtn.textContent = "Connect";
    }
  }
}
