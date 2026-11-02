"""Tests for BL-22: performance test tooling (SRS 5.1, NFR-PERF-1 / NFR-PERF-2).

The full Test Plan runs (NT-01: 100 clients for 2 minutes, NT-03: 100
connections for 5 minutes, ...) take minutes, so they are run by hand with
``perf/load_test.py`` and recorded in docs/BL-22-Performance-Test-Results.md.

This file keeps the tooling honest in every CI run:
- the percentile and pass/fail rules are unit tested, and
- a scaled-down load run (20 clients, a few seconds) against a real server
  must deliver every message to every other client within 1 second.
"""

import pytest

from perf.load_test import Result, _judge, format_summary, percentile, run_scenario


def test_percentile_nearest_rank():
    values = list(range(1, 101))  # 1..100
    assert percentile(values, 50) == 50
    assert percentile(values, 95) == 95
    assert percentile(values, 100) == 100
    assert percentile([7], 95) == 7
    assert percentile([], 95) is None


def _result(**overrides):
    base = dict(
        scenario="nt01", url="http://x", clients_requested=100, clients_connected=100,
        messages_sent=1200, deliveries_expected=118800, deliveries_received=118800,
        latency_ms_p95=120.0, latency_ms_max=400.0,
    )
    base.update(overrides)
    return Result(**base)


def test_judge_passes_within_limits():
    r = _result()
    _judge(r, "p95")
    assert r.passed and r.verdict == "PASS"


@pytest.mark.parametrize(
    "overrides, reason",
    [
        ({"latency_ms_p95": 1000.1}, "p95 latency"),
        ({"dropped_connections": 1}, "dropped"),
        ({"deliveries_received": 118799, "deliveries_missing": 1}, "missing"),
        ({"clients_connected": 99}, "could not connect"),
        ({"server_errors": 3}, "error event"),
    ],
)
def test_judge_fails_each_acceptance_criterion(overrides, reason):
    r = _result(**overrides)
    _judge(r, "p95")
    assert not r.passed
    assert reason in r.verdict


def test_judge_baseline_uses_max_latency():
    r = _result(clients_requested=2, clients_connected=2, latency_ms_p95=10.0,
                latency_ms_max=1200.0)
    _judge(r, "max")
    assert not r.passed and "max latency" in r.verdict


def test_judge_hold_scenario_needs_no_messages():
    r = _result(messages_sent=0, deliveries_expected=0, deliveries_received=0,
                latency_ms_p95=None, latency_ms_max=None)
    _judge(r, "hold")
    assert r.passed


def test_summary_is_a_markdown_table():
    r = _result()
    _judge(r, "p95")
    text = format_summary(r)
    assert text.startswith("| Metric | Value |")
    assert "| Result | PASS |" in text


def test_scaled_load_run_delivers_everything_within_one_second(live_server):
    """20 real WebSocket clients in one room, 4 messages each, 0.5 s apart."""
    result = run_scenario(
        "ci-smoke",
        url=live_server,
        room="ci-load",
        clients=20,
        interval=0.5,
        messages_per_client=4,
        drain=2.0,
        quiet=True,
    )
    assert result.clients_connected == 20, result.connect_errors
    assert result.messages_sent == 80
    assert result.deliveries_expected == 80 * 19
    assert result.deliveries_missing == 0
    assert result.dropped_connections == 0
    assert result.server_errors == 0
    assert result.latency_ms_p95 <= 1000.0
    assert result.passed, result.verdict
