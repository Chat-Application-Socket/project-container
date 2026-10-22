"""Tests for the chat page UI served at "/" (BL-04).

Checks that the page delivered to the browser contains every element the
chat UI needs (SRS 3.1 User Interfaces):
- message input box, Send button and the form that handles Enter / click
- scrollable message list that will show sender, text and timestamp
- error banner area
- mobile viewport meta tag so the layout adapts to phone width
"""

from html.parser import HTMLParser

import pytest
from chat import create_app


class _ElementCollector(HTMLParser):
    """Collect the attributes of every element that has an id."""

    def __init__(self):
        super().__init__()
        self.by_id = {}
        self.meta = []
        self.scripts = []
        self.label_targets = []

    def handle_starttag(self, tag, attrs):
        attributes = dict(attrs)
        attributes["_tag"] = tag
        if tag == "label" and attributes.get("for"):
            self.label_targets.append(attributes["for"])
        if "id" in attributes:
            self.by_id[attributes["id"]] = attributes
        if tag == "meta":
            self.meta.append(attributes)
        if tag == "script" and attributes.get("src"):
            self.scripts.append(attributes["src"])


@pytest.fixture
def page():
    """Fetch the index page and parse its elements."""
    app = create_app()
    app.config["TESTING"] = True
    response = app.test_client().get("/")
    assert response.status_code == 200
    parser = _ElementCollector()
    parser.feed(response.get_data(as_text=True))
    return parser


def test_message_input_and_send_button_present(page):
    """Message box, Send button and submit form are rendered."""
    assert page.by_id["message-form"]["_tag"] == "form"
    assert page.by_id["message-input"]["_tag"] == "textarea"
    send_btn = page.by_id["send-btn"]
    assert send_btn["_tag"] == "button"
    assert send_btn.get("type") == "submit"


def test_message_input_limited_to_500_characters(page):
    """Input box enforces the 500 character content limit (SRS Appendix B)."""
    assert page.by_id["message-input"].get("maxlength") == "500"


def test_composer_disabled_until_connected(page):
    """Input and Send start disabled; client.js enables them after connecting (BR-1)."""
    assert "disabled" in page.by_id["message-input"]
    assert "disabled" in page.by_id["send-btn"]


def test_message_list_present_and_announced(page):
    """Scrollable message list exists and is announced to screen readers."""
    message_list = page.by_id["message-list"]
    assert message_list["_tag"] in ("ol", "ul")
    assert message_list.get("aria-live") == "polite"


def test_error_banner_present(page):
    """Error banner area exists, starts hidden and is announced."""
    banner = page.by_id["error-banner"]
    assert "hidden" in banner
    assert banner.get("aria-live") == "polite"


def test_input_has_accessible_label(page):
    """Message input has a label for screen readers (NFR-USA-1)."""
    assert "message-input" in page.label_targets


def test_mobile_viewport_meta_present(page):
    """Viewport meta tag lets the layout adapt to phone width."""
    viewports = [m for m in page.meta if m.get("name") == "viewport"]
    assert viewports
    assert "width=device-width" in viewports[0].get("content", "")


def test_client_script_and_pinned_socketio_loaded(page):
    """Page loads the pinned Socket.IO client and the app's client script."""
    assert "https://cdn.socket.io/4.7.5/socket.io.min.js" in page.scripts
    assert "/static/client.js" in page.scripts
