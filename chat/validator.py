
"""Message validation module for chat application."""

import functools
import logging

from flask import request
from flask_socketio import emit

logger = logging.getLogger(__name__)

ERROR_EVENT = "error"
MESSAGE_EVENT = "message"

E201_INVALID_REQUEST = ("E201", "Invalid request.")
E304_EMPTY_MESSAGE = ("E304", "Message cannot be empty.")

_INVISIBLE_CHARS = "​‌‍⁠﻿"
VALID_MESSAGE_TYPES = {"message", "join", "leave", "typing"}


class MessageValidationError(ValueError):
    """Raised when a message fails validation."""

    def __init__(self, error):
        code, message = error
        super().__init__(message)
        self.code = code
        self.message = message

    def to_payload(self, event=MESSAGE_EVENT):
        """Build the standard error event payload."""
        return {
            "code": self.code,
            "message": self.message,
            "event": event,
        }


def validate_message_content(content):
    """Validate message text and return it trimmed."""
    if content is None:
        raise MessageValidationError(E304_EMPTY_MESSAGE)

    if not isinstance(content, str):
        raise MessageValidationError(E201_INVALID_REQUEST)

    trimmed = content.strip()
    if not trimmed.strip(_INVISIBLE_CHARS).strip():
        raise MessageValidationError(E304_EMPTY_MESSAGE)

    return trimmed


def reject_empty_message(handler):
    """Reject invalid or empty message content before handling."""

    @functools.wraps(handler)
    def wrapper(data=None, *args, **kwargs):
        if data is not None and not isinstance(data, dict):
            error = MessageValidationError(E201_INVALID_REQUEST)
        else:
            error = None
            content = (data or {}).get("content")

            try:
                cleaned = validate_message_content(content)
            except MessageValidationError as exc:
                error = exc

        if error is not None:
            logger.info(
                "Message rejected: sid=%s code=%s",
                request.sid,
                error.code,
            )
            emit(ERROR_EVENT, error.to_payload(MESSAGE_EVENT))
            return None

        validated = dict(data)
        validated["content"] = cleaned
        return handler(validated, *args, **kwargs)

    return wrapper


def validate_message_object(message):
    """Validate a complete message object against the BL-09 schema."""
    if not isinstance(message, dict):
        raise MessageValidationError(E201_INVALID_REQUEST)

    required_fields = {
        "sender",
        "room",
        "content",
        "timestamp",
        "type",
    }

    if not required_fields.issubset(message):
        raise MessageValidationError(E201_INVALID_REQUEST)

    sender = message["sender"]
    room = message["room"]
    content = message["content"]
    timestamp = message["timestamp"]
    message_type = message["type"]

    if (
        not isinstance(sender, str)
        or not sender.strip()
        or len(sender) > 50
    ):
        raise MessageValidationError(E201_INVALID_REQUEST)

    if (
        not isinstance(room, str)
        or not room.strip()
        or len(room) > 30
    ):
        raise MessageValidationError(E201_INVALID_REQUEST)

    if (
        not isinstance(content, str)
        or not content.strip()
        or len(content) > 500
    ):
        raise MessageValidationError(E201_INVALID_REQUEST)

    if not isinstance(timestamp, str) or not timestamp.strip():
        raise MessageValidationError(E201_INVALID_REQUEST)

    if (
        not isinstance(message_type, str)
        or message_type not in VALID_MESSAGE_TYPES
    ):
        raise MessageValidationError(E201_INVALID_REQUEST)

    return message
