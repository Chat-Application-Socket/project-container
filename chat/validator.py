"""Message validation module (SAD component S4: Validator).

BL-07 / REQ-5: Reject empty or whitespace-only messages.

This module is the server-side authority for the "message cannot be empty"
rule (SAD ADR-5: validate on the client for instant feedback, and again on the
server because a client can be bypassed with a raw socket script).

It exposes:
1. validate_message_content(content)
     Pure function: returns the trimmed text or raises MessageValidationError.
2. reject_empty_message
     Decorator for the "message" event handler. When the content is empty,
     whitespace-only or not text, it sends a standard error event back to the
     sender only, and the wrapped handler is NOT called (so nothing is
     broadcast). Valid messages reach the handler with content already trimmed.

Usage in the message handler (chat/broadcast.py, BL-05):

    from chat.validator import reject_empty_message

    def register(socketio):
        @socketio.on("message")
        @reject_empty_message
        def handle_message(data):
            content = data["content"]  # guaranteed non-empty, trimmed
            ...
"""

import functools
import logging

from flask import request
from flask_socketio import emit

logger = logging.getLogger(__name__)

# Event used to tell a client its request was rejected (SAD 4.3.4).
ERROR_EVENT = "error"

# Client -> server event this validator protects (SAD 4.3.3).
MESSAGE_EVENT = "message"

# Error catalogue entries used by this module (SAD 4.4.2, Table 14).
# Messages are fixed, user-readable text with no internals (SC-9).
E201_INVALID_REQUEST = ("E201", "Invalid request.")
E304_EMPTY_MESSAGE = ("E304", "Message cannot be empty.")

# Invisible characters that str.strip() does not remove but which still render
# as a blank message (zero-width space/joiners, word joiner, byte order mark).
_INVISIBLE_CHARS = "​‌‍⁠﻿"


class MessageValidationError(ValueError):
    """Raised when a message fails validation.

    Carries an error code and a fixed, user-readable message.
    """

    def __init__(self, error):
        code, message = error
        super().__init__(message)
        self.code = code
        self.message = message

    def to_payload(self, event=MESSAGE_EVENT):
        """Build the standard error event payload {code, message, event}."""
        return {"code": self.code, "message": self.message, "event": event}


def validate_message_content(content):
    """Validate message text and return it trimmed.

    Rules (REQ-5 / Test Plan UT-05A to UT-05C):
    - content must be a string, otherwise E201 "Invalid request."
    - content must not be empty or whitespace-only after trimming,
      otherwise E304 "Message cannot be empty."

    Args:
        content: The raw "content" value received from the client.

    Returns:
        str: The content with leading and trailing whitespace removed.

    Raises:
        MessageValidationError: If the content is not text or is blank.
    """
    if content is None:
        raise MessageValidationError(E304_EMPTY_MESSAGE)

    if not isinstance(content, str):
        raise MessageValidationError(E201_INVALID_REQUEST)

    trimmed = content.strip()
    if not trimmed.strip(_INVISIBLE_CHARS).strip():
        raise MessageValidationError(E304_EMPTY_MESSAGE)

    return trimmed


def reject_empty_message(handler):
    """Decorator that stops empty / invalid messages before the handler runs.

    On a bad message the sender alone receives an "error" event, the event is
    logged without its content (SC-10), and the wrapped handler is skipped,
    so the message is never broadcast. Bad input never raises out of the
    handler, so the server keeps running (no crash on bad input).
    """

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
                "Message rejected: sid=%s code=%s", request.sid, error.code
            )
            emit(ERROR_EVENT, error.to_payload(MESSAGE_EVENT))
            return None

        validated = dict(data)
        validated["content"] = cleaned
        return handler(validated, *args, **kwargs)

    return wrapper
