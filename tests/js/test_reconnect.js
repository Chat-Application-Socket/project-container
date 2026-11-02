// Unit tests for static/reconnect.js (BL-21: auto-reconnect with back-off).
// Run directly with:  node tests/js/test_reconnect.js
// Also run by pytest through tests/test_reconnect.py.
//
// Maps to Test Plan NFR-REL-1 (NT-10, NT-11, NT-12) and SAD 4.4.4.

"use strict";

const assert = require("assert");
const path = require("path");
const {
  DEFAULTS,
  MESSAGES,
  computeDelay,
  shouldAutoReconnect,
  isHandshakeRefusal,
  ReconnectScheduler,
} = require(path.join(__dirname, "..", "..", "static", "reconnect.js"));

const tests = [];
function test(name, fn) {
  tests.push({ name, fn });
}

// Fake timers so tests run instantly and deterministically
function fakeTimers() {
  const pending = new Map();
  let nextId = 1;
  return {
    setTimer(fn, delay) {
      const id = nextId++;
      pending.set(id, { fn, delay });
      return id;
    },
    clearTimer(id) {
      pending.delete(id);
    },
    pending,
    // Run the oldest pending timer; return its delay
    fireNext() {
      const [id, entry] = pending.entries().next().value;
      pending.delete(id);
      entry.fn();
      return entry.delay;
    },
  };
}

// ---------------------------------------------------------------------------
// Back-off formula: min(30 s, 1 s x 2^n) + up to 20 % jitter (SAD 4.4.4)
// ---------------------------------------------------------------------------

test("defaults follow SAD 4.4.4", () => {
  assert.strictEqual(DEFAULTS.baseDelayMs, 1000);
  assert.strictEqual(DEFAULTS.maxDelayMs, 30000);
  assert.strictEqual(DEFAULTS.jitterRatio, 0.2);
  assert.strictEqual(DEFAULTS.maxAttempts, 10);
});

test("delay doubles from 1 s without jitter", () => {
  const noJitter = () => 0;
  const delays = [0, 1, 2, 3, 4].map((n) => computeDelay(n, {}, noJitter));
  assert.deepStrictEqual(delays, [1000, 2000, 4000, 8000, 16000]);
});

test("delay is capped at 30 s", () => {
  const noJitter = () => 0;
  assert.strictEqual(computeDelay(5, {}, noJitter), 30000); // 32 s -> 30 s
  assert.strictEqual(computeDelay(9, {}, noJitter), 30000);
  assert.strictEqual(computeDelay(1000, {}, noJitter), 30000); // no overflow
});

test("jitter adds at most 20 percent", () => {
  const almostOne = () => 0.999999;
  assert.strictEqual(computeDelay(0, {}, almostOne), 1200);
  assert.strictEqual(computeDelay(5, {}, almostOne), 36000);
  for (let i = 0; i < 200; i++) {
    const n = i % 12;
    const base = Math.min(30000, 1000 * 2 ** n);
    const d = computeDelay(n, {});
    assert.ok(d >= base && d <= base * 1.2, `delay ${d} out of range for n=${n}`);
  }
});

test("negative or invalid attempt numbers are treated as 0", () => {
  const noJitter = () => 0;
  assert.strictEqual(computeDelay(-3, {}, noJitter), 1000);
  assert.strictEqual(computeDelay(undefined, {}, noJitter), 1000);
});

// ---------------------------------------------------------------------------
// Which failures are retried
// ---------------------------------------------------------------------------

test("network and heartbeat failures are retried automatically", () => {
  ["transport close", "transport error", "ping timeout", "parse error", "forced close"].forEach(
    (reason) => assert.strictEqual(shouldAutoReconnect(reason), true, reason)
  );
});

test("manual disconnect and server kick are not retried automatically", () => {
  assert.strictEqual(shouldAutoReconnect("io client disconnect"), false);
  assert.strictEqual(shouldAutoReconnect("io server disconnect"), false);
  assert.strictEqual(shouldAutoReconnect(undefined), false);
});

test("handshake refusal is told apart from an unreachable server", () => {
  // Server refused (bad username): Socket.IO deactivates the socket
  assert.strictEqual(isHandshakeRefusal(new Error("Username cannot be empty"), false), true);
  // Refusal that carries data
  const withData = Object.assign(new Error("x"), { data: { message: "Username cannot be empty" } });
  assert.strictEqual(isHandshakeRefusal(withData, true), true);
  // Server down / network error: socket stays active and will be retried
  assert.strictEqual(isHandshakeRefusal(new Error("websocket error"), true), false);
  assert.strictEqual(isHandshakeRefusal(null, true), false);
});

test("user-facing messages use the agreed wording", () => {
  assert.strictEqual(MESSAGES.C02_CONNECTION_LOST, "Connection lost, reconnecting...");
  assert.strictEqual(MESSAGES.C01_UNREACHABLE, "Cannot reach the server. Retrying...");
  assert.strictEqual(MESSAGES.C03_GAVE_UP, "Could not reconnect. Click Reconnect to try again.");
});

// ---------------------------------------------------------------------------
// Scheduler behaviour
// ---------------------------------------------------------------------------

test("scheduler retries with growing delays then gives up after 10 attempts", () => {
  const timers = fakeTimers();
  const attempts = [];
  let gaveUp = 0;
  const s = new ReconnectScheduler({
    random: () => 0,
    setTimer: timers.setTimer,
    clearTimer: timers.clearTimer,
    onAttempt: (n) => attempts.push(n),
    onGiveUp: () => gaveUp++,
  });

  const delays = [];
  for (let i = 0; i < 10; i++) {
    const d = s.scheduleNext();
    assert.ok(d > 0);
    assert.strictEqual(s.isPending(), true);
    delays.push(timers.fireNext()); // the attempt "fails"; schedule the next one
  }
  assert.deepStrictEqual(attempts, [1, 2, 3, 4, 5, 6, 7, 8, 9, 10]);
  assert.deepStrictEqual(delays, [1000, 2000, 4000, 8000, 16000, 30000, 30000, 30000, 30000, 30000]);

  assert.strictEqual(s.scheduleNext(), -1);
  assert.strictEqual(s.scheduleNext(), -1);
  assert.strictEqual(gaveUp, 1, "onGiveUp is called exactly once");
  assert.strictEqual(timers.pending.size, 0);
});

test("a successful connect resets the back-off", () => {
  const timers = fakeTimers();
  const s = new ReconnectScheduler({
    random: () => 0,
    setTimer: timers.setTimer,
    clearTimer: timers.clearTimer,
  });
  s.scheduleNext();
  timers.fireNext();
  s.scheduleNext();
  timers.fireNext();
  assert.strictEqual(s.attempts, 2);

  s.reset();
  assert.strictEqual(s.attempts, 0);
  assert.strictEqual(s.scheduleNext(), 1000, "starts again from 1 s");
});

test("reset cancels a pending attempt", () => {
  const timers = fakeTimers();
  let fired = 0;
  const s = new ReconnectScheduler({
    setTimer: timers.setTimer,
    clearTimer: timers.clearTimer,
    onAttempt: () => fired++,
  });
  s.scheduleNext();
  s.reset();
  assert.strictEqual(s.isPending(), false);
  assert.strictEqual(timers.pending.size, 0);
  assert.strictEqual(fired, 0);
});

test("scheduleNext never leaves two timers running", () => {
  const timers = fakeTimers();
  const s = new ReconnectScheduler({ setTimer: timers.setTimer, clearTimer: timers.clearTimer });
  s.scheduleNext();
  s.scheduleNext();
  assert.strictEqual(timers.pending.size, 1);
});

test("manual retry after giving up starts a fresh sequence immediately", () => {
  const timers = fakeTimers();
  const attempts = [];
  let gaveUp = 0;
  const s = new ReconnectScheduler({
    random: () => 0,
    maxAttempts: 2,
    setTimer: timers.setTimer,
    clearTimer: timers.clearTimer,
    onAttempt: (n) => attempts.push(n),
    onGiveUp: () => gaveUp++,
  });
  s.scheduleNext();
  timers.fireNext();
  s.scheduleNext();
  timers.fireNext();
  assert.strictEqual(s.scheduleNext(), -1);
  assert.strictEqual(gaveUp, 1);

  s.retryNow(); // user clicks Reconnect
  assert.deepStrictEqual(attempts, [1, 2, 1], "attempt runs at once, counter restarted");
  assert.strictEqual(s.scheduleNext(), 2000, "next wait continues the new sequence");
  timers.fireNext();
  assert.strictEqual(s.scheduleNext(), -1);
  assert.strictEqual(gaveUp, 2, "can give up again after a manual retry");
});

test("works with real timers", (done) => {
  return new Promise((resolve) => {
    const s = new ReconnectScheduler({
      baseDelayMs: 5,
      onAttempt: (n) => {
        assert.strictEqual(n, 1);
        resolve();
      },
    });
    s.scheduleNext();
  });
});

test("default timers are not called with the scheduler as `this`", () => {
  // Browsers throw "Illegal invocation" if setTimeout runs with a foreign `this`.
  const realSet = global.setTimeout;
  const realClear = global.clearTimeout;
  const strictSet = function (fn, ms) {
    if (this !== undefined && this !== global) throw new TypeError("Illegal invocation");
    return realSet(fn, ms);
  };
  const strictClear = function (id) {
    if (this !== undefined && this !== global) throw new TypeError("Illegal invocation");
    return realClear(id);
  };
  global.setTimeout = strictSet;
  global.clearTimeout = strictClear;
  try {
    const s = new ReconnectScheduler({ baseDelayMs: 60000 });
    s.scheduleNext();
    s.reset();
  } finally {
    global.setTimeout = realSet;
    global.clearTimeout = realClear;
  }
});

(async () => {
  let failed = 0;
  for (const { name, fn } of tests) {
    try {
      await fn();
      console.log(`ok - ${name}`);
    } catch (err) {
      failed++;
      console.log(`not ok - ${name}`);
      console.log(err && err.stack ? err.stack : err);
    }
  }
  console.log(`\n${tests.length - failed}/${tests.length} passed`);
  process.exit(failed ? 1 : 0);
})();
