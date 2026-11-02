# BL-22: Performance Test Results

Story: *As a project manager, I want proof that the server handles 100 simultaneous connections within 1 s latency, so the NFR is verified.* (issue #39)

Requirements: SRS 5.1 **NFR-PERF-1** (delivery latency at most 1 second with up to 100 concurrent users on one server instance) and **NFR-PERF-2** (at least 100 simultaneous connections). Test Plan cases NT-01 to NT-04.

## 1. Summary

| Test case | Requirement | What was run | Key result | Result |
| :--- | :--- | :--- | :--- | :--- |
| NT-01 | NFR-PERF-1 | 100 clients in one room; each sent 1 message every 10 s for 2 minutes | p95 delivery **41.3 ms** (max 79.8 ms); 118,800 / 118,800 deliveries; 0 drops; 0 errors | **Pass** |
| NT-02 | NFR-PERF-1 | 2 clients exchanged 50 messages | Every message within **40.4 ms** (limit 1000 ms) | **Pass** |
| NT-03 | NFR-PERF-2 | 100 WebSocket connections held open for 5 minutes | 100 / 100 connected for the whole run; 0 dropped | **Pass** |
| NT-04 | NFR-PERF-2 | Ramped to 120 connections (10 more per second), then chatted for 30 s | All 120 connected; page load 2.3 ms at peak; p95 delivery 50.1 ms; 0 drops | **Pass** |

All four acceptance criteria of BL-22 are met: the load script opens 100 clients, p95 delivery is at most 1 s (41.3 ms), no connection was dropped, and the results are recorded here for the system test report (BL-25).

## 2. Test environment

| Item | Value |
| :--- | :--- |
| Date | 2 November 2026 (runs started 05:34 to 05:38 UTC) |
| Server | `python app.py` (Flask 3.1.3, Flask-SocketIO 5.7.0, python-engineio 4.15.1, simple-websocket 1.1.0, Werkzeug 3.1.9 development server, `async_mode="threading"`), one process, default configuration, heartbeat 25 s / 20 s |
| Load generator | `perf/load_test.py`, real Socket.IO clients (python-socketio + websocket-client 1.8.0), WebSocket transport only |
| Machine | Linux x86_64, 2 CPU cores, Python 3.13.18; server and load generator on the **same** machine over `127.0.0.1` |
| Branch | `bl-22-performance-test` (includes BL-20 and BL-21) |

The server and all simulated clients shared the same 2 CPU cores, which is a harsher setup than a real deployment where clients run on their own devices. Localhost removes most network delay, so on a LAN or the internet each delivery will take longer by roughly the network round trip; the SAD budgets 100-200 ms for that, which still leaves a wide margin under 1 s.

## 3. How latency was measured

For every message the script records the send time just before emitting it. When any *other* client in the room receives that message, the receive time is taken from the same clock, so latency = receive time - send time for that recipient. The sender's own echo is not counted. One message sent in a room of 100 clients therefore gives 99 latency samples. Percentiles use the nearest-rank method.

A delivery is "missing" if an expected (message, recipient) pair never arrived within 5 s after the last message was sent. A connection is "dropped" if a client received a `disconnect` it did not ask for.

## 4. Detailed results

### NT-01: Latency with 100 concurrent users (NFR-PERF-1)

Command: `python perf/load_test.py --scenario nt01`

Expected: 95th-percentile delivery time is 1000 ms or less; no errors.

| Metric | Value |
| :--- | :--- |
| Clients connected | 100 / 100 |
| Connect failures | 0 |
| Dropped connections | 0 |
| Messages sent | 1,200 (12 per client) |
| Deliveries received / expected | 118,800 / 118,800 |
| Missing deliveries | 0 |
| Server error events | 0 |
| Latency min / p50 / p95 / p99 / max | 2.6 / 25.7 / **41.3** / 48.4 / 79.8 ms |
| Deliveries over 1000 ms | 0 |
| Connect time p95 | 180.3 ms |
| Run time | 129.8 s |

Actual result: p95 was 41.3 ms and the slowest of 118,800 deliveries took 79.8 ms. No errors, no drops, nothing missing. **Pass.**

### NT-02: Baseline latency with 2 users (NFR-PERF-1)

Command: `python perf/load_test.py --scenario nt02`

Expected: every message is delivered in 1000 ms or less.

| Metric | Value |
| :--- | :--- |
| Clients connected | 2 / 2 |
| Messages sent | 50 (25 per client, 0.2 s apart) |
| Deliveries received / expected | 50 / 50 |
| Latency min / p50 / p95 / p99 / max | 1.9 / 2.3 / 4.6 / 40.4 / **40.4** ms |
| Dropped connections / server errors | 0 / 0 |

Actual result: every message arrived within 40.4 ms. **Pass.**

### NT-03: 100 simultaneous connections for 5 minutes (NFR-PERF-2)

Command: `python perf/load_test.py --scenario nt03`

Expected: all 100 stay connected; none dropped.

| Metric | Value |
| :--- | :--- |
| Clients connected | 100 / 100 |
| Connect failures | 0 |
| Connections still open, checked every 5 s | 100 / 100 at every one of the 60 checks |
| Dropped connections | 0 |
| Connect time p95 | 157.6 ms |
| Run time | 304.8 s |

Actual result: all 100 connections stayed open for the full 5 minutes, through 12 heartbeat cycles. **Pass.**

### NT-04: Behaviour above the limit, 120 connections (NFR-PERF-2)

Command: `python perf/load_test.py --scenario nt04`

Expected: the server remains responsive; results recorded in the test report.

| Metric | Value |
| :--- | :--- |
| Clients connected | 120 / 120 (ramped 10 per second) |
| Connect failures | 0 |
| Dropped connections | 0 |
| Messages sent | 360 (3 per client, 10 s apart) |
| Deliveries received / expected | 42,840 / 42,840 |
| Latency min / p50 / p95 / p99 / max | 2.9 / 31.3 / **50.1** / 57.4 / 82.8 ms |
| `GET /` page load at peak | 2.3 ms |
| Server error events | 0 |

Actual result: at 120 connections the page still loaded in 2.3 ms and p95 delivery was 50.1 ms. No connection was refused: the server has no connection cap yet (the SAD's `MAX_CONNECTIONS=200` / per-IP limit is not implemented). **Pass.**

## 5. Observations

1. **Latency grows slowly with room size.** p50 went from 2.3 ms (2 users) to 25.7 ms (100 users) to 31.3 ms (120 users). A message to a room of N users is written to N sockets, so the cost grows with N, but it stays far below 1 s at the target load.
2. **Harmless log lines when many clients close at once.** At the end of each scenario the server log shows `code 400, message Bad request ...` from Werkzeug, roughly one per closing client (309 lines for 322 closed clients, all in the few seconds after a run ended). The development server appears to read the client's WebSocket close frame as a new HTTP request after the WebSocket handler has finished. They did not affect any delivery or connection, and the log has no tracebacks or `E500` errors. This comes from the development server; it is worth checking again once the app runs on a production server behind Nginx (BL-23).
3. **Not covered here:** latency over a real network or Wi-Fi, more than one room under load, and slow or flooding clients (the SAD's rate limit `E401` is not implemented yet).

## 6. Raw data

The full JSON output of each run is in [`docs/BL-22-results/`](BL-22-results/) (`nt01.json` to `nt04.json`).

## 7. How to repeat

```bash
python app.py                                   # terminal 1
python perf/load_test.py --scenario nt01        # terminal 2 (then nt02, nt03, nt04)
python perf/load_test.py --scenario nt01 --json docs/BL-22-results/nt01.json
```

A scaled-down version (20 clients, about 8 s) runs in every CI build as `tests/test_performance.py::test_scaled_load_run_delivers_everything_within_one_second`.
