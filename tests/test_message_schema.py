import pytest

from chat.validator import (
    MessageValidationError,
    validate_message_object,
)


def valid_message():
    return {
        "sender": "Alice",
        "room": "global",
        "content": "Hello everyone",
        "timestamp": "2026-10-28T10:00:00+00:00",
        "type": "message",
    }


def test_valid_message_is_accepted():
    message = valid_message()
    assert validate_message_object(message) == message


@pytest.mark.parametrize(
    "field",
    ["sender", "room", "content", "timestamp", "type"],
)
def test_missing_required_field_is_rejected(field):
    message = valid_message()
    del message[field]

    with pytest.raises(MessageValidationError):
        validate_message_object(message)


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("sender", "A" * 51),
        ("room", "R" * 31),
        ("content", "C" * 501),
        ("sender", ""),
        ("room", ""),
        ("content", ""),
        ("timestamp", ""),
        ("type", "invalid"),
        ("type", None),
    ],
)
def test_invalid_field_is_rejected(field, value):
    message = valid_message()
    message[field] = value

    with pytest.raises(MessageValidationError):
        validate_message_object(message)


@pytest.mark.parametrize("message", [None, [], "invalid"])
def test_non_dictionary_message_is_rejected(message):
    with pytest.raises(MessageValidationError):
        validate_message_object(message)


@pytest.mark.parametrize(
    "message_type",
    ["message", "join", "leave", "typing"],
)
def test_allowed_message_types_are_accepted(message_type):
    message = valid_message()
    message["type"] = message_type

    assert validate_message_object(message) == message
