// Reconnection policy for the chat client (SAD component C2: Connection Manager).
//
// BL-21: Auto-reconnect with a "Connection lost, reconnecting..." message.
//
// SAD 4.4.4 Reconnection algorithm (REQ-15 / NFR-REL-1):
// - Delay before attempt n (n starting at 0) = min(30 s, 1 s x 2^n) plus random
//   jitter of up to 20 percent, so clients do not all retry at the same moment
//   after a server restart (risk R7, "reconnect storm").
// - After 10 failed attempts the client stops and asks the user to click
//   Reconnect (message C03); clicking it starts the sequence again.
//
// This file has no DOM or Socket.IO code so it can be unit tested with Node.js
// (tests/js/test_reconnect.js) and used in the browser as window.ChatReconnect.

(function (root) {
  "use strict";

  var DEFAULTS = {
    baseDelayMs: 1000, // first retry after about 1 s
    maxDelayMs: 30000, // never wait more than 30 s (+ jitter) between tries
    jitterRatio: 0.2, // add up to 20 % random extra delay
    maxAttempts: 10, // then give up and show the Reconnect button (C03)
  };

  // Client-side messages (SAD 4.4.2, Table 15). C02 uses the exact wording of
  // SRS NFR-REL-1 / Test Plan NT-10.
  var MESSAGES = {
    C01_UNREACHABLE: "Cannot reach the server. Retrying...",
    C02_CONNECTION_LOST: "Connection lost, reconnecting...",
    C03_GAVE_UP: "Could not reconnect. Click Reconnect to try again.",
    SERVER_CLOSED: "The server closed the connection. Click Reconnect to try again.",
    RECONNECTED: "Reconnected.",
  };

  function mergeOptions(options) {
    var merged = {};
    var key;
    for (key in DEFAULTS) {
      if (Object.prototype.hasOwnProperty.call(DEFAULTS, key)) merged[key] = DEFAULTS[key];
    }
    if (options) {
      for (key in options) {
        if (Object.prototype.hasOwnProperty.call(options, key) && options[key] !== undefined) {
          merged[key] = options[key];
        }
      }
    }
    return merged;
  }

  // Delay in ms before attempt `attempt` (0-based).
  // `random` returns a number in [0, 1); it is injectable for tests.
  function computeDelay(attempt, options, random) {
    var opts = mergeOptions(options);
    var rand = typeof random === "function" ? random : Math.random;
    var n = Math.max(0, Math.floor(attempt) || 0);
    // Cap the exponent first so 2^n never overflows for large n.
    var exp = Math.min(n, 30);
    var base = Math.min(opts.maxDelayMs, opts.baseDelayMs * Math.pow(2, exp));
    var jitter = base * opts.jitterRatio * rand();
    return Math.round(base + jitter);
  }

  // Socket.IO "disconnect" reasons that mean the network or server failed and
  // the client should retry by itself. Not included:
  // - "io client disconnect": the user clicked Disconnect.
  // - "io server disconnect": the server closed the session on purpose; the
  //   user is offered a Reconnect button instead of an automatic loop.
  var AUTO_RECONNECT_REASONS = {
    "transport close": true, // server stopped or TCP connection closed
    "transport error": true, // network error on the socket
    "ping timeout": true, // heartbeat missed (silent connection loss)
    "parse error": true, // corrupted frame
    "forced close": true, // we closed the transport ourselves (browser went offline)
  };

  function shouldAutoReconnect(reason) {
    return AUTO_RECONNECT_REASONS[reason] === true;
  }

  // Socket.IO raises "connect_error" both when the server refuses the
  // handshake (bad username: do NOT retry, show the reason) and when the
  // server cannot be reached (retry). After a refusal Socket.IO deactivates
  // the socket, so `socket.active` is false; for network failures it stays true.
  function isHandshakeRefusal(err, socketActive) {
    if (socketActive === false) return true;
    if (err && err.data && typeof err.data === "object" && err.data.message) return true;
    return false;
  }

  // Schedules reconnect attempts with back-off. It does not know about
  // Socket.IO: `onAttempt(attemptNumber)` is called when it is time to try,
  // and `onGiveUp()` once `maxAttempts` tries have failed.
  function ReconnectScheduler(options) {
    var opts = options || {};
    this.options = mergeOptions(opts);
    this.random = typeof opts.random === "function" ? opts.random : Math.random;
    // Wrapped so the browser's setTimeout is never called with `this` set to
    // the scheduler (that throws "Illegal invocation" in browsers).
    this.setTimer = typeof opts.setTimer === "function" ? opts.setTimer : function (fn, ms) {
      return setTimeout(fn, ms);
    };
    this.clearTimer = typeof opts.clearTimer === "function" ? opts.clearTimer : function (id) {
      clearTimeout(id);
    };
    this.onAttempt = typeof opts.onAttempt === "function" ? opts.onAttempt : function () {};
    this.onGiveUp = typeof opts.onGiveUp === "function" ? opts.onGiveUp : function () {};
    this.attempts = 0; // attempts scheduled since the last reset()
    this.timer = null;
    this.gaveUp = false;
  }

  // Schedule the next attempt. Returns the delay in ms, or -1 if the maximum
  // number of attempts has been used (onGiveUp is then called once).
  ReconnectScheduler.prototype.scheduleNext = function () {
    this.cancel();
    if (this.attempts >= this.options.maxAttempts) {
      if (!this.gaveUp) {
        this.gaveUp = true;
        this.onGiveUp();
      }
      return -1;
    }
    var delay = computeDelay(this.attempts, this.options, this.random);
    this.attempts += 1;
    var attemptNumber = this.attempts;
    var self = this;
    this.timer = this.setTimer(function () {
      self.timer = null;
      self.onAttempt(attemptNumber);
    }, delay);
    return delay;
  };

  // Manual reconnect (Reconnect button, or the browser came back online):
  // start a fresh sequence and try straight away.
  ReconnectScheduler.prototype.retryNow = function () {
    this.reset();
    this.attempts = 1;
    this.onAttempt(1);
  };

  // Stop any pending attempt without resetting the counter.
  ReconnectScheduler.prototype.cancel = function () {
    if (this.timer !== null) {
      this.clearTimer(this.timer);
      this.timer = null;
    }
  };

  // Forget previous failures (after a successful connect or a manual action).
  ReconnectScheduler.prototype.reset = function () {
    this.cancel();
    this.attempts = 0;
    this.gaveUp = false;
  };

  ReconnectScheduler.prototype.isPending = function () {
    return this.timer !== null;
  };

  var api = {
    DEFAULTS: DEFAULTS,
    MESSAGES: MESSAGES,
    computeDelay: computeDelay,
    shouldAutoReconnect: shouldAutoReconnect,
    isHandshakeRefusal: isHandshakeRefusal,
    ReconnectScheduler: ReconnectScheduler,
  };

  if (typeof module !== "undefined" && module.exports) {
    module.exports = api;
  } else {
    root.ChatReconnect = api;
  }
})(typeof window !== "undefined" ? window : this);
