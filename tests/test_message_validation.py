"""Tests for rejecting empty or whitespace-only messages (BL-07, REQ-5).

Maps to Test Plan:
- UT-05A: Validator rejects an empty string
- UT-05B: Validator rejects whitespace-only text
- UT-05C: Validator accepts normal text
- IT-05B: Server rejects an empty message sent outside the UI
          (no broadcast, error event to the sender, other users receive nothing)
- "No crash on bad input": malformed payloads are rejected and the
  connection stays open
"""

import pytest
from chat import create_app, socketio
from chat.validator import (
    MessageValidationError,
    reject_empty_message,
    validate_message_content,
)

# Test-only event wired with the same decorator the real "message" handler uses.
PROBE_EVENT = "bl07_probe_message"
DELIVERED_EVENT = "bl07_probe_delivered"


@reject_empty_message
def _probe_handler(data):
    """Stand-in for the broadcast handler: re-emits valid messages to everyone."""
    socketio.emit(DELIVERED_EVENT, {"content": data["content"]})


@pytest.fixture
def app():
    """Create the app and register the probe handler on its Socket.IO server."""
    app = create_app()
    app.config["TESTING"] = True
    socketio.on(PROBE_EVENT)(_probe_handler)
    return app


def _events(client, name):
    """Return the payloads of all received events with the given name."""
    return [m["args"][0] for m in client.get_received() if m["name"] == name]


# ---------------------------------------------------------------------------
# Unit tests: validate_message_content()
# ---------------------------------------------------------------------------

def test_validator_rejects_empty_string():
    """UT-05A: '' is rejected with 'Message cannot be empty.'"""
    with pytest.raises(MessageValidationError) as exc_info:
        validate_message_content("")
    assert exc_info.value.code == "E304"
    assert exc_info.value.message == "Message cannot be empty."


@pytest.mark.parametrize("blank", [
    "   ",
    "\t\n",
    " \r\n \t ",
    " 　",          # no-break space, ideographic space
    "​‍﻿",    # zero-width characters render as nothing
])
def test_validator_rejects_whitespace_only(blank):
    """UT-05B: whitespace-only (and invisible-only) text is rejected."""
    with pytest.raises(MessageValidationError) as exc_info:
        validate_message_content(blank)
    assert exc_info.value.code == "E304"


def test_validator_rejects_missing_content():
    """A missing content value counts as an empty message."""
    with pytest.raises(MessageValidationError) as exc_info:
        validate_message_content(None)
    assert exc_info.value.code == "E304"


@pytest.mark.parametrize("not_text", [123, 4.5, True, ["hi"], {"text": "hi"}])
def test_validator_rejects_non_text_content(not_text):
    """Non-string content is rejected as an invalid request, not crashed on."""
    with pytest.raises(MessageValidationError) as exc_info:
        validate_message_content(not_text)
    assert exc_info.value.code == "E201"


def test_validator_accepts_and_trims_normal_text():
    """UT-05C: '  hi ' is accepted and returned trimmed."""
    assert validate_message_content("  hi ") == "hi"


def test_validator_keeps_inner_whitespace_and_newlines():
    """Only the ends are trimmed; text inside the message is untouched."""
    assert validate_message_content("\n line one\n  line two \n") == "line one\n  line two"


def test_error_payload_matches_api_contract():
    """Error payload follows the standard {code, message, event} shape (SAD 4.4)."""
    with pytest.raises(MessageValidationError) as exc_info:
        validate_message_content("   ")
    assert exc_info.value.to_payload() == {
        "code": "E304",
        "message": "Message cannot be empty.",
        "event": "message",
    }


# ---------------------------------------------------------------------------
# Integration tests: reject_empty_message on a live Socket.IO handler
# ---------------------------------------------------------------------------

def test_server_rejects_blank_message_and_does_not_broadcast(app):
    """IT-05B: blank content from A is not broadcast; A gets E304; B gets nothing."""
    sender = socketio.test_client(app, auth={"username": "alice"})
    receiver = socketio.test_client(app, auth={"username": "bob"})
    try:
        sender.get_received()
        receiver.get_received()

        for blank in ["", "   ", "\t\n"]:
            sender.emit(PROBE_EVENT, {"content": blank})

        errors = _events(sender, "error")
        assert len(errors) == 3
        assert all(e["code"] == "E304" for e in errors)
        assert all(e["message"] == "Message cannot be empty." for e in errors)
        assert all(e["event"] == "message" for e in errors)

        assert _events(receiver, DELIVERED_EVENT) == []
        assert _events(receiver, "error") == []
    finally:
        sender.disconnect()
        receiver.disconnect()


def test_valid_message_after_blank_attempts_is_delivered(app):
    """ST-05B (server side): after blank attempts, a real message still goes through."""
    sender = socketio.test_client(app, auth={"username": "alice"})
    receiver = socketio.test_client(app, auth={"username": "bob"})
    try:
        sender.emit(PROBE_EVENT, {"content": "   "})
        sender.emit(PROBE_EVENT, {"content": ""})
        sender.emit(PROBE_EVENT, {"content": "  hello  "})

        delivered = _events(receiver, DELIVERED_EVENT)
        assert delivered == [{"content": "hello"}]
    finally:
        sender.disconnect()
        receiver.disconnect()


@pytest.mark.parametrize("bad_payload", [
    "just a string",
    123,
    ["content", "hi"],
    {},
    {"content": None},
    {"content": 42},
    {"text": "wrong field"},
])
def test_malformed_payload_rejected_without_crash(app, bad_payload):
    """Bad input is rejected with an error event and the connection stays open."""
    client = socketio.test_client(app, auth={"username": "mallory"})
    try:
        client.get_received()
        client.emit(PROBE_EVENT, bad_payload)

        errors = _events(client, "error")
        assert len(errors) == 1
        assert errors[0]["code"] in ("E201", "E304")
        assert client.is_connected()

        # The same connection still works for a valid message afterwards
        client.emit(PROBE_EVENT, {"content": "still here"})
        assert _events(client, DELIVERED_EVENT) == [{"content": "still here"}]
    finally:
        client.disconnect()


def test_missing_payload_rejected_without_crash(app):
    """An event sent with no payload at all is rejected, not crashed on."""
    client = socketio.test_client(app, auth={"username": "mallory"})
    try:
        client.get_received()
        client.emit(PROBE_EVENT)
        errors = _events(client, "error")
        assert len(errors) == 1
        assert errors[0]["code"] == "E304"
        assert client.is_connected()
    finally:
        client.disconnect()
