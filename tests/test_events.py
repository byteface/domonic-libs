from domonic.events import Event, InputEvent, MouseEvent, PointerEvent
from domonic.html import button

from domonic_libs.app.client import CLIENT_SCRIPT
from domonic_libs.app.events import BROWSER_EVENTS, browser_event, on


def test_browser_event_uses_domonic_mouse_event():
    event = browser_event(
        {
            "type": Event.CLICK,
            "target": {"id": "button"},
            "currentTarget": {"value": "42"},
            "value": "42",
        }
    )

    assert isinstance(event, MouseEvent)
    assert event.type == Event.CLICK
    assert event.target.id == "button"
    assert event.currentTarget.value == "42"
    assert event.value == "42"


def test_browser_event_uses_domonic_input_event():
    event = browser_event(
        {
            "type": Event.INPUT,
            "value": "hello",
            "target": {"name": "note", "value": "hello"},
        }
    )

    assert isinstance(event, InputEvent)
    assert event.value == "hello"
    assert event.target.name == "note"


def test_browser_event_uses_domonic_pointer_event():
    event = browser_event(
        {
            "type": PointerEvent.POINTERDOWN,
            "offsetX": 10,
            "offsetY": 20,
            "target": {},
        }
    )

    assert isinstance(event, PointerEvent)
    assert event.offsetX == 10
    assert event.offsetY == 20


def test_browser_events_include_subclass_constants():
    assert Event.CLICK in BROWSER_EVENTS
    assert PointerEvent.POINTERDOWN in BROWSER_EVENTS


def test_on_adds_domonic_listener_and_returns_node():
    node = button("Go")
    callback = lambda event: None

    result = on(node, Event.CLICK, callback)

    assert result is node
    assert node.listeners[Event.CLICK] == [callback]


def test_client_dispatch_does_not_cancel_keyboard_defaults():
    assert 'return event.type === "submit" ? false : true;' in CLIENT_SCRIPT


def test_client_submit_payload_reads_form_target():
    assert 'String(target.tagName || "").toUpperCase() === "FORM"' in CLIENT_SCRIPT
