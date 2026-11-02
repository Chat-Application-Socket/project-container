"""Load test for the chat server (BL-22, SRS 5.1 NFR-PERF-1 / NFR-PERF-2).

Opens many real Socket.IO clients over WebSocket, puts them in one room, has
them send messages and measures how long each message takes to reach every
other client in the room.

Scenarios (Test Plan section NT):
  nt01  100 clients in one room; each sends 1 message every 10 s for 2 minutes.
        Pass: p95 delivery <= 1000 ms, no errors, no dropped connections,
        no missing deliveries.
  nt02  Baseline: 2 clients exchange 50 messages.
        Pass: every message delivered in <= 1000 ms.
  nt03  100 connections kept open for 5 minutes (no messages).
        Pass: all 100 stay connected; none dropped.
  nt04  Ramp to 120 connections (10 more every second), then chat for 30 s.
        Pass: server stays responsive (page loads and message p95 <= 1000 ms).
  custom  Any combination of --clients / --interval / --duration.

Usage (server already running, e.g. ``python app.py``):
  python perf/load_test.py --scenario nt01
  python perf/load_test.py --scenario nt03 --url http://127.0.0.1:5000
  python perf/load_test.py --clients 50 --interval 2 --duration 30
  python perf/load_test.py --scenario nt01 --json results/nt01.json

Latency is measured on one machine with one clock: the send time is stored
when a client emits, and the receive time is taken when another client's
``message`` event arrives. Run the script on the same machine as the server or
on a machine on the same LAN; the result includes the network round trip and
the client's own processing, so it is an upper bound on server time.

Exit code: 0 if the scenario passed, 1 if it failed, 2 on a setup error.
"""

import argparse
import json
import math
import os
import platform
import random
import sys
import threading
import time
import urllib.request
from dataclasses import asdict, dataclass, field

import socketio

LATENCY_LIMIT_MS = 1000.0

SCENARIOS = {
    "nt01": dict(clients=100, interval=10.0, duration=120.0, pass_rule="p95"),
    "nt02": dict(clients=2, interval=0.2, messages_per_client=25, pass_rule="max"),
    "nt03": dict(clients=100, interval=0.0, duration=300.0, pass_rule="hold"),
    "nt04": dict(clients=120, interval=10.0, duration=30.0, ramp_step=10, ramp_every=1.0,
                 pass_rule="responsive"),
}


def percentile(values, pct):
    """Nearest-rank percentile (pct in 0..100) of a list; None when empty."""
    if not values:
        return None
    ordered = sorted(values)
    rank = max(1, int(math.ceil(pct / 100.0 * len(ordered))))
    return ordered[rank - 1]


@dataclass
class Result:
    scenario: str
    url: str
    clients_requested: int
    clients_connected: int = 0
    connect_failures: int = 0
    connect_errors: list = field(default_factory=list)
    dropped_connections: int = 0
    messages_sent: int = 0
    deliveries_expected: int = 0
    deliveries_received: int = 0
    deliveries_missing: int = 0
    server_errors: int = 0
    latency_ms_min: float = None
    latency_ms_p50: float = None
    latency_ms_p95: float = None
    latency_ms_p99: float = None
    latency_ms_max: float = None
    over_limit: int = 0
    connect_ms_p95: float = None
    page_load_ms: float = None
    duration_s: float = 0.0
    passed: bool = False
    verdict: str = ""
    environment: dict = field(default_factory=dict)


class LoadClient:
    """One simulated chat user."""

    def __init__(self, index, run):
        self.index = index
        self.run = run
        self.name = f"lt-{index:03d}"
        self.sio = socketio.Client(reconnection=False)
        self.joined = threading.Event()
        self.connected = False
        self.dropped = False
        self.closing = False
        self.sio.on("connect", self._on_connect)
        self.sio.on("disconnect", self._on_disconnect)
        self.sio.on("joined", self._on_joined)
        self.sio.on("message", self._on_message)
        self.sio.on("error", self._on_error)

    def _on_connect(self):
        self.connected = True

    def _on_disconnect(self, *args):
        if not self.closing:
            self.dropped = True
        self.connected = False

    def _on_joined(self, data):
        if isinstance(data, dict) and data.get("room") == self.run.room:
            self.joined.set()

    def _on_message(self, data):
        received_at = time.perf_counter()
        if not isinstance(data, dict):
            return
        key = data.get("content", "")
        sent = self.run.sent_at.get(key)
        if sent is None:
            return
        sender_index, sent_at = sent
        if sender_index == self.index:
            return  # own echo: not a delivery to another user
        with self.run.lock:
            self.run.latencies_ms.append((received_at - sent_at) * 1000.0)

    def _on_error(self, data):
        with self.run.lock:
            self.run.server_errors += 1

    def connect(self, timeout):
        started = time.perf_counter()
        self.sio.connect(
            self.run.url,
            transports=["websocket"],
            auth={"username": self.name},
            wait_timeout=timeout,
        )
        self.sio.emit("join_room", {"room": self.run.room})
        if not self.joined.wait(timeout):
            raise TimeoutError(f"{self.name}: no 'joined' within {timeout}s")
        return (time.perf_counter() - started) * 1000.0

    def send(self, seq):
        content = f"lt|{self.index}|{seq}|{random.getrandbits(32):08x}"
        with self.run.lock:
            self.run.sent_at[content] = (self.index, time.perf_counter())
            self.run.messages_sent += 1
        self.sio.emit("message", {"content": content})

    def close(self):
        self.closing = True
        try:
            self.sio.disconnect()
        except Exception:
            pass


class LoadRun:
    def __init__(self, url, room):
        self.url = url.rstrip("/")
        self.room = room
        self.lock = threading.Lock()
        self.sent_at = {}
        self.latencies_ms = []
        self.messages_sent = 0
        self.server_errors = 0


def _connect_all(run, count, start_index, timeout, result, connect_ms, batch=10, pause=0.0):
    """Connect ``count`` clients, ``batch`` at a time, in parallel threads."""
    clients = []
    lock = threading.Lock()

    def worker(i):
        client = LoadClient(i, run)
        try:
            ms = client.connect(timeout)
        except Exception as exc:
            with lock:
                result.connect_failures += 1
                if len(result.connect_errors) < 5:
                    result.connect_errors.append(f"{client.name}: {exc}")
            client.close()
            return
        with lock:
            clients.append(client)
            connect_ms.append(ms)

    for first in range(start_index, start_index + count, batch):
        threads = [
            threading.Thread(target=worker, args=(i,), daemon=True)
            for i in range(first, min(first + batch, start_index + count))
        ]
        for t in threads:
            t.start()
        for t in threads:
            t.join(timeout + 5)
        if pause:
            time.sleep(pause)
    return clients


def _close_all(clients):
    """Disconnect every client in parallel (each disconnect waits for its threads)."""
    threads = [threading.Thread(target=c.close, daemon=True) for c in clients]
    for t in threads:
        t.start()
    for t in threads:
        t.join(10)


def _page_load_ms(url):
    started = time.perf_counter()
    with urllib.request.urlopen(url + "/", timeout=5) as resp:
        resp.read()
        if resp.status != 200:
            raise RuntimeError(f"GET / returned {resp.status}")
    return (time.perf_counter() - started) * 1000.0


def _send_phase(clients, interval, duration, messages_per_client):
    """Each client sends on its own schedule, start times spread over one interval."""
    if messages_per_client is None:
        messages_per_client = max(1, int(round(duration / interval)))
    stop = threading.Event()

    def sender(client, offset):
        time.sleep(offset)
        for seq in range(messages_per_client):
            if stop.is_set() or not client.connected:
                return
            planned = time.perf_counter()
            try:
                client.send(seq)
            except Exception:
                return
            delay = interval - (time.perf_counter() - planned)
            if delay > 0 and seq < messages_per_client - 1:
                if stop.wait(delay):
                    return

    threads = []
    for i, client in enumerate(clients):
        offset = (i / max(1, len(clients))) * interval
        t = threading.Thread(target=sender, args=(client, offset), daemon=True)
        threads.append(t)
        t.start()
    total = interval * messages_per_client + interval + 30
    for t in threads:
        t.join(total)
    stop.set()


def run_scenario(name, url="http://127.0.0.1:5000", room="loadtest", clients=None,
                 interval=None, duration=None, messages_per_client=None, connect_timeout=15.0,
                 drain=5.0, quiet=False):
    """Run a scenario and return a :class:`Result`. Usable from tests."""
    preset = dict(SCENARIOS.get(name, {}))
    clients = clients if clients is not None else preset.get("clients", 10)
    interval = interval if interval is not None else preset.get("interval", 1.0)
    duration = duration if duration is not None else preset.get("duration", 10.0)
    if messages_per_client is None:
        messages_per_client = preset.get("messages_per_client")
    pass_rule = preset.get("pass_rule", "p95")
    ramp_step = preset.get("ramp_step")
    ramp_every = preset.get("ramp_every", 0.0)

    def log(msg):
        if not quiet:
            print(msg, flush=True)

    run = LoadRun(url, room)
    result = Result(scenario=name, url=run.url, clients_requested=clients)
    result.environment = {
        "python": platform.python_version(),
        "platform": platform.platform(),
        "cpu_count": os.cpu_count(),
        "started_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
    }
    started = time.perf_counter()

    try:
        _page_load_ms(run.url)
    except Exception as exc:
        result.verdict = f"Server not reachable at {run.url}: {exc}"
        return result

    connect_ms = []
    log(f"[{name}] connecting {clients} clients to {run.url} (room '{room}')...")
    if ramp_step:
        connected = _connect_all(run, clients, 0, connect_timeout, result, connect_ms,
                                 batch=ramp_step, pause=ramp_every)
    else:
        connected = _connect_all(run, clients, 0, connect_timeout, result, connect_ms)
    result.clients_connected = len(connected)
    result.connect_ms_p95 = _round(percentile(connect_ms, 95))
    log(f"[{name}] connected {len(connected)}/{clients} "
        f"(p95 connect {result.connect_ms_p95} ms, failures {result.connect_failures})")

    try:
        if pass_rule == "hold":
            log(f"[{name}] holding connections for {duration:.0f} s...")
            deadline = time.monotonic() + duration
            while time.monotonic() < deadline:
                time.sleep(min(5.0, max(0.0, deadline - time.monotonic())))
                alive = sum(1 for c in connected if c.connected)
                log(f"[{name}]   {alive}/{len(connected)} connected")
        else:
            per_client = messages_per_client or max(1, int(round(duration / interval)))
            log(f"[{name}] sending: {per_client} message(s) per client every {interval} s...")
            _send_phase(connected, interval, duration, messages_per_client)
            time.sleep(drain)  # let the last deliveries arrive
        if pass_rule == "responsive":
            result.page_load_ms = _round(_page_load_ms(run.url))
    finally:
        result.dropped_connections = sum(1 for c in connected if c.dropped)
        _close_all(connected)

    latencies = list(run.latencies_ms)
    receivers = max(0, len(connected) - 1)
    result.messages_sent = run.messages_sent
    result.deliveries_expected = run.messages_sent * receivers
    result.deliveries_received = len(latencies)
    result.deliveries_missing = max(0, result.deliveries_expected - result.deliveries_received)
    result.server_errors = run.server_errors
    result.latency_ms_min = _round(min(latencies)) if latencies else None
    result.latency_ms_p50 = _round(percentile(latencies, 50))
    result.latency_ms_p95 = _round(percentile(latencies, 95))
    result.latency_ms_p99 = _round(percentile(latencies, 99))
    result.latency_ms_max = _round(max(latencies)) if latencies else None
    result.over_limit = sum(1 for v in latencies if v > LATENCY_LIMIT_MS)
    result.duration_s = round(time.perf_counter() - started, 1)
    _judge(result, pass_rule)
    return result


def _round(value):
    return None if value is None else round(value, 1)


def _judge(result, rule):
    problems = []
    if result.clients_connected < result.clients_requested:
        problems.append(f"{result.clients_requested - result.clients_connected} client(s) "
                        f"could not connect")
    if result.dropped_connections:
        problems.append(f"{result.dropped_connections} connection(s) dropped")
    if result.server_errors:
        problems.append(f"{result.server_errors} error event(s) from the server")
    if rule != "hold":
        if result.messages_sent == 0:
            problems.append("no messages were sent")
        if result.deliveries_missing:
            problems.append(f"{result.deliveries_missing} delivery(ies) missing")
    p95, worst = result.latency_ms_p95, result.latency_ms_max
    if rule == "p95" and (p95 is None or p95 > LATENCY_LIMIT_MS):
        problems.append(f"p95 latency {p95} ms > {LATENCY_LIMIT_MS:.0f} ms")
    if rule == "max" and (worst is None or worst > LATENCY_LIMIT_MS):
        problems.append(f"max latency {worst} ms > {LATENCY_LIMIT_MS:.0f} ms")
    if rule == "responsive":
        # NT-04 is about staying responsive above the target load: the page
        # must still load and messages must still arrive within 1 s (p95).
        problems = [p for p in problems if "could not connect" not in p]
        if result.page_load_ms is None or result.page_load_ms > LATENCY_LIMIT_MS:
            problems.append(f"page load {result.page_load_ms} ms > {LATENCY_LIMIT_MS:.0f} ms")
        if result.latency_ms_p95 is None or result.latency_ms_p95 > LATENCY_LIMIT_MS:
            problems.append(f"p95 latency {result.latency_ms_p95} ms > {LATENCY_LIMIT_MS:.0f} ms")
    result.passed = not problems
    result.verdict = "PASS" if not problems else "FAIL: " + "; ".join(problems)


def format_summary(result):
    """Human-readable summary (also valid Markdown)."""
    rows = [
        ("Scenario", result.scenario),
        ("Server", result.url),
        ("Clients connected", f"{result.clients_connected} / {result.clients_requested}"),
        ("Connect failures", result.connect_failures),
        ("Dropped connections", result.dropped_connections),
        ("Messages sent", result.messages_sent),
        ("Deliveries received / expected",
         f"{result.deliveries_received} / {result.deliveries_expected}"),
        ("Missing deliveries", result.deliveries_missing),
        ("Server error events", result.server_errors),
        ("Latency min / p50 / p95 / p99 / max (ms)",
         f"{result.latency_ms_min} / {result.latency_ms_p50} / {result.latency_ms_p95} / "
         f"{result.latency_ms_p99} / {result.latency_ms_max}"),
        ("Deliveries over 1000 ms", result.over_limit),
        ("Connect time p95 (ms)", result.connect_ms_p95),
        ("Page load at peak (ms)", result.page_load_ms),
        ("Run time (s)", result.duration_s),
        ("Result", result.verdict),
    ]
    lines = ["| Metric | Value |", "| :--- | :--- |"]
    lines += [f"| {k} | {v} |" for k, v in rows]
    if result.connect_errors:
        lines.append("")
        lines.append("First connect errors: " + "; ".join(result.connect_errors))
    return "\n".join(lines)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--scenario", default="custom", choices=sorted(SCENARIOS) + ["custom"])
    parser.add_argument("--url", default=os.environ.get("CHAT_URL", "http://127.0.0.1:5000"))
    parser.add_argument("--room", default="loadtest")
    parser.add_argument("--clients", type=int)
    parser.add_argument("--interval", type=float, help="seconds between a client's messages")
    parser.add_argument("--duration", type=float, help="seconds to send (or hold) for")
    parser.add_argument("--messages-per-client", type=int)
    parser.add_argument("--connect-timeout", type=float, default=15.0)
    parser.add_argument("--json", help="write the full result as JSON to this file")
    args = parser.parse_args(argv)

    result = run_scenario(
        args.scenario,
        url=args.url,
        room=args.room,
        clients=args.clients,
        interval=args.interval,
        duration=args.duration,
        messages_per_client=args.messages_per_client,
        connect_timeout=args.connect_timeout,
    )
    print()
    print(format_summary(result))
    if args.json:
        os.makedirs(os.path.dirname(os.path.abspath(args.json)), exist_ok=True)
        with open(args.json, "w", encoding="utf-8") as fh:
            json.dump(asdict(result), fh, indent=2)
    if result.verdict.startswith("Server not reachable"):
        return 2
    return 0 if result.passed else 1


if __name__ == "__main__":
    sys.exit(main())
