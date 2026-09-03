import json
import queue
import re
import subprocess
import threading

from domonic.dom import document
from domonic.html import main
from domonic_libs import App, preact
from domonic_libs.preact import h

app = App("Type & Speak", width=600, height=420)
container = document.createElement("div")

BATCH_SIZE = 3          # words spoken together while typing quickly
PAUSE_SECONDS = 1.0     # a gap at least this long flushes whatever is buffered
WORD_BREAKS = set(" \t\n.,;:!?")

state = {"text": "", "speaking": ""}

_buffer: list[str] = []   # completed words not yet handed to the speaker
_consumed = 0             # completed words already taken from the field
_guard = threading.Lock()
_pause_timer: threading.Timer | None = None
_to_speak: "queue.Queue[str]" = queue.Queue()


def _speaker_loop():
    """One worker, one utterance at a time -- speech never overlaps."""
    while True:
        phrase = _to_speak.get()
        spoken = re.sub(r"[^A-Za-z0-9 ]", "", phrase).strip()
        if spoken:
            _set_status(spoken)
            subprocess.run(["say", spoken])   # blocks until it finishes talking
            _set_status("")
        _to_speak.task_done()


threading.Thread(target=_speaker_loop, daemon=True).start()


def _set_status(text: str):
    """Push the 'now speaking' line to the window without a round-trip."""
    state["speaking"] = text
    label = f"\U0001f50a {text}" if text else "…"
    try:
        app.evaluate_js(
            'var el = document.getElementById("status");'
            f"if (el) el.textContent = {json.dumps(label)};"
        )
    except Exception:
        pass  # window not up yet, or already closed


def _completed_words(text: str) -> list[str]:
    """Words the user has finished -- i.e. everything before the word in progress."""
    words = text.split()
    if not words:
        return []
    return words if text[-1] in WORD_BREAKS else words[:-1]


def _drain_full_batches():
    """Hand every whole group of BATCH_SIZE words to the speaker."""
    global _buffer
    while len(_buffer) >= BATCH_SIZE:
        _to_speak.put(" ".join(_buffer[:BATCH_SIZE]))
        _buffer = _buffer[BATCH_SIZE:]


def _flush_remainder():
    """Typing paused: say whatever is left, even if it's fewer than BATCH_SIZE."""
    global _buffer
    with _guard:
        _drain_full_batches()
        if _buffer:
            _to_speak.put(" ".join(_buffer))
            _buffer = []


def _restart_pause_timer():
    global _pause_timer
    if _pause_timer is not None:
        _pause_timer.cancel()
    _pause_timer = threading.Timer(PAUSE_SECONDS, _flush_remainder)
    _pause_timer.daemon = True
    _pause_timer.start()


def on_input(e):
    global _consumed, _buffer
    text = e.target.value
    state["text"] = text

    with _guard:
        completed = _completed_words(text)
        if len(completed) < _consumed:      # user deleted / edited earlier text
            _consumed = len(completed)
            _buffer = []
        fresh = completed[_consumed:]
        if fresh:
            _buffer.extend(fresh)
            _consumed = len(completed)
            _drain_full_batches()
        pending = bool(_buffer)

    if pending:
        _restart_pause_timer()

    render_ui()


def render_ui():
    buffered = len(_buffer)
    ui = h("div", {"style": "padding: 40px; font-family: system-ui; background: #0f172a; min-height: 100vh; color: #fff;"},
        h("h1", {"style": "margin: 0 0 10px; font-size: 24px; color: #38bdf8;"}, "\U0001f5e3️ Talk-As-You-Type"),
        h("p", {"style": "margin: 0 0 20px; color: #94a3b8; font-size: 14px;"},
          f"Speaks {BATCH_SIZE} words at a time as you type, then whatever is left "
          f"after a {PAUSE_SECONDS:g}s pause. Utterances never overlap."),
        h("input", {
            "type": "text",
            "value": state["text"],
            "placeholder": "Type something here...",
            "autofocus": "true",
            "style": "width: 100%; padding: 16px; font-size: 18px; border-radius: 8px; border: 1px solid #334155; background: #1e293b; color: #fff; box-sizing: border-box;",
            "_oninput": on_input,
        }),
        h("div", {"style": "margin-top: 20px; display: flex; gap: 12px; font-size: 14px;"},
            h("div", {"style": "flex: 1; padding: 12px; background: #1e293b; border-radius: 6px; color: #a855f7;"},
              f"Buffered: {buffered} word{'' if buffered == 1 else 's'}"),
            h("div", {"id": "status", "style": "flex: 1; padding: 12px; background: #1e293b; border-radius: 6px; color: #38bdf8;"},
              f"\U0001f50a {state['speaking']}" if state["speaking"] else "…"),
        ),
    )
    preact.render(ui, container)


render_ui()


@app.route("/")
def index():
    return main(container)


if __name__ == "__main__":
    app.run()
