from __future__ import annotations

from types import SimpleNamespace
from typing import Any

from domonic.events import (
    Event as DomonicEvent,
    FocusEvent,
    InputEvent,
    KeyboardEvent,
    MouseEvent,
    PointerEvent,
    SubmitEvent,
    WheelEvent,
)


Event = DomonicEvent


def on(node: Any, event_type: str, callback: Any, options: Any = None):
    node.addEventListener(event_type, callback, options)
    return node


def event_names(*classes: type):
    return frozenset(
        value
        for cls in classes
        for name, value in vars(cls).items()
        if name.isupper() and isinstance(value, str)
    )


MOUSE_EVENTS = frozenset(
    {
        MouseEvent.AUXCLICK,
        MouseEvent.CLICK,
        MouseEvent.CONTEXTMENU,
        MouseEvent.DBLCLICK,
        MouseEvent.MOUSEDOWN,
        MouseEvent.MOUSEENTER,
        MouseEvent.MOUSELEAVE,
        MouseEvent.MOUSEMOVE,
        MouseEvent.MOUSEOUT,
        MouseEvent.MOUSEOVER,
        MouseEvent.MOUSEUP,
    }
)
KEYBOARD_EVENTS = frozenset(
    {KeyboardEvent.KEYDOWN, KeyboardEvent.KEYPRESS, KeyboardEvent.KEYUP}
)
INPUT_EVENTS = frozenset({DomonicEvent.BEFOREINPUT, DomonicEvent.INPUT})
FOCUS_EVENTS = frozenset(
    {DomonicEvent.BLUR, DomonicEvent.FOCUS, "focusin", "focusout"}
)
POINTER_EVENTS = frozenset(
    {
        PointerEvent.POINTERCANCEL,
        PointerEvent.POINTERDOWN,
        PointerEvent.POINTERENTER,
        PointerEvent.POINTERLEAVE,
        PointerEvent.POINTERMOVE,
        PointerEvent.POINTEROUT,
        PointerEvent.POINTEROVER,
        PointerEvent.POINTERUP,
    }
)
WHEEL_EVENTS = frozenset({WheelEvent.WHEEL})
SUBMIT_EVENTS = frozenset({DomonicEvent.SUBMIT})
BROWSER_EVENTS = event_names(
    DomonicEvent,
    FocusEvent,
    InputEvent,
    KeyboardEvent,
    MouseEvent,
    PointerEvent,
    SubmitEvent,
    WheelEvent,
)


def namespace(value: Any):
    if isinstance(value, dict):
        return SimpleNamespace(
            **{key: namespace(item) for key, item in value.items()}
        )

    if isinstance(value, list):
        return [namespace(item) for item in value]

    return value


def event_class(event_type: str):
    if event_type in MOUSE_EVENTS:
        return MouseEvent
    if event_type in KEYBOARD_EVENTS:
        return KeyboardEvent
    if event_type in INPUT_EVENTS:
        return InputEvent
    if event_type in FOCUS_EVENTS:
        return FocusEvent
    if event_type in POINTER_EVENTS:
        return PointerEvent
    if event_type in WHEEL_EVENTS:
        return WheelEvent
    if event_type in SUBMIT_EVENTS:
        return SubmitEvent

    return DomonicEvent


def browser_event(event_data: dict | None):
    event_data = event_data or {}
    event_type = event_data.get("type", "")
    options = {
        key: namespace(value)
        for key, value in event_data.items()
        if key != "type"
    }
    event = event_class(event_type)(event_type, options)

    for key, value in options.items():
        try:
            setattr(event, key, value)
        except AttributeError:
            pass

    return event
