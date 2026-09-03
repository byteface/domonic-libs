# Ported from mermaid-js/mermaid (MIT), tag mermaid@11.9.0. Mirrors
# src/diagrams/sequence/sequenceDb.ts.
"""``SequenceDB`` -- the ``yy`` object the parser drives.

The parser emits a nested list of statement dicts (``{"type": "addMessage",
...}`` etc.) exactly as the upstream ``.jison`` actions do, and ``apply()``
walks it. Keeping that seam identical means the grammar's semantic actions port
verbatim and upstream changes stay diffable.

``LINETYPE`` / ``ARROWTYPE`` / ``PLACEMENT`` keep their upstream integer values.
"""

from __future__ import annotations

import json
import re

from ..common import sanitize_text
from ..config import get_config

LINETYPE = {
    "SOLID": 0,
    "DOTTED": 1,
    "NOTE": 2,
    "SOLID_CROSS": 3,
    "DOTTED_CROSS": 4,
    "SOLID_OPEN": 5,
    "DOTTED_OPEN": 6,
    "LOOP_START": 10,
    "LOOP_END": 11,
    "ALT_START": 12,
    "ALT_ELSE": 13,
    "ALT_END": 14,
    "OPT_START": 15,
    "OPT_END": 16,
    "ACTIVE_START": 17,
    "ACTIVE_END": 18,
    "PAR_START": 19,
    "PAR_AND": 20,
    "PAR_END": 21,
    "RECT_START": 22,
    "RECT_END": 23,
    "SOLID_POINT": 24,
    "DOTTED_POINT": 25,
    "AUTONUMBER": 26,
    "CRITICAL_START": 27,
    "CRITICAL_OPTION": 28,
    "CRITICAL_END": 29,
    "BREAK_START": 30,
    "BREAK_END": 31,
    "PAR_OVER_START": 32,
    "BIDIRECTIONAL_SOLID": 33,
    "BIDIRECTIONAL_DOTTED": 34,
}

ARROWTYPE = {"FILLED": 0, "OPEN": 1}

PLACEMENT = {"LEFTOF": 0, "RIGHTOF": 1, "OVER": 2}

_WRAP_RE = re.compile(r"^:?wrap:")
_NOWRAP_RE = re.compile(r"^:?nowrap:")
_WRAP_STRIP_RE = re.compile(r"^:?(?:no)?wrap:")
_BOX_RE = re.compile(r"^((?:rgba?|hsla?)\s*\(.*\)|\w*)(.*)$")


class SequenceDB:
    LINETYPE = LINETYPE
    ARROWTYPE = ARROWTYPE
    PLACEMENT = PLACEMENT

    def __init__(self):
        self.clear()

    # -- state -----------------------------------------------------------------

    def clear(self):
        self.prev_actor: str | None = None
        self.actors: dict[str, dict] = {}
        self.created_actors: dict[str, int] = {}
        self.destroyed_actors: dict[str, int] = {}
        self.boxes: list[dict] = []
        self.messages: list[dict] = []
        self.notes: list[dict] = []
        self.sequence_numbers_enabled = False
        self.wrap_enabled: bool | None = None
        self.current_box: dict | None = None
        self.last_created: str | None = None
        self.last_destroyed: str | None = None
        self._title = ""
        self._acc_title = ""
        self._acc_description = ""

    # -- wrap ----------------------------------------------------------------

    def set_wrap(self, wrap_setting: bool | None):
        self.wrap_enabled = wrap_setting

    def auto_wrap(self) -> bool:
        if self.wrap_enabled is not None:
            return self.wrap_enabled
        return (get_config().get("sequence") or {}).get("wrap", False)

    def _extract_wrap(self, text: str | None):
        if text is None:
            return {"cleanedText": None, "wrap": None}
        text = text.strip()
        if _WRAP_RE.search(text):
            wrap: bool | None = True
        elif _NOWRAP_RE.search(text):
            wrap = False
        else:
            wrap = None
        cleaned = text if wrap is None else _WRAP_STRIP_RE.sub("", text)
        return {"cleanedText": cleaned.strip(), "wrap": wrap}

    # -- actors / boxes ----------------------------------------------------

    def add_box(self, data: dict):
        box = {
            "name": data.get("text"),
            "wrap": data["wrap"] if data.get("wrap") is not None else self.auto_wrap(),
            "fill": data.get("color"),
            "actorKeys": [],
        }
        self.boxes.append(box)
        self.current_box = box

    def add_actor(self, actor_id: str, name: str, description, actor_type: str | None):
        assigned_box = self.current_box
        old = self.actors.get(actor_id)
        if old:
            if self.current_box and old.get("box") and self.current_box is not old["box"]:
                raise ValueError(
                    f"A same participant should only be defined in one Box: "
                    f"{old['name']} can't be in '{old['box']['name']}' and in "
                    f"'{self.current_box['name']}' at the same time."
                )
            assigned_box = old["box"] if old.get("box") else self.current_box
            old["box"] = assigned_box
            if name == old["name"] and description is None:
                return

        if description is None or description.get("text") is None:
            description = {"text": name, "type": actor_type}
        if actor_type is None or description.get("text") is None:
            description = {"text": name, "type": actor_type}

        self.actors[actor_id] = {
            "box": assigned_box,
            "name": name,
            "description": description["text"],
            "wrap": description["wrap"] if description.get("wrap") is not None else self.auto_wrap(),
            "prevActor": self.prev_actor,
            "nextActor": None,
            "links": {},
            "properties": {},
            "actorCnt": None,
            "rectData": None,
            "type": actor_type or "participant",
        }
        if self.prev_actor and self.prev_actor in self.actors:
            self.actors[self.prev_actor]["nextActor"] = actor_id

        if self.current_box:
            self.current_box["actorKeys"].append(actor_id)
        self.prev_actor = actor_id

    def _box_end(self):
        self.current_box = None

    # -- messages / signals ----------------------------------------------

    def _activation_count(self, part: str) -> int:
        if not part:
            return 0
        count = 0
        for message in self.messages:
            if message.get("type") == LINETYPE["ACTIVE_START"] and message.get("from") == part:
                count += 1
            if message.get("type") == LINETYPE["ACTIVE_END"] and message.get("from") == part:
                count -= 1
        return count

    def add_signal(self, id_from=None, id_to=None, message=None, message_type=None, activate=False):
        if message_type == LINETYPE["ACTIVE_END"]:
            if self._activation_count(id_from or "") < 1:
                error = ValueError(f"Trying to inactivate an inactive participant ({id_from})")
                error.hash = {  # type: ignore[attr-defined]
                    "text": "->>-",
                    "token": "->>-",
                    "line": "1",
                    "loc": {"first_line": 1, "last_line": 1, "first_column": 1, "last_column": 1},
                    "expected": ["'ACTIVE_PARTICIPANT'"],
                }
                raise error
        self.messages.append(
            {
                "id": str(len(self.messages)),
                "from": id_from,
                "to": id_to,
                "message": (message or {}).get("text", "") if isinstance(message, dict) else "",
                "wrap": (message or {}).get("wrap") if isinstance(message, dict) and (message or {}).get("wrap") is not None else self.auto_wrap(),
                "type": message_type,
                "activate": activate,
            }
        )
        return True

    def add_note(self, actor: dict, placement, message: dict):
        note = {
            "actor": actor,
            "placement": placement,
            "message": message.get("text"),
            "wrap": message["wrap"] if message.get("wrap") is not None else self.auto_wrap(),
        }
        # Upstream: `[].concat(actor, actor)` -- flattens when actor is a pair.
        actors = actor + actor if isinstance(actor, list) else [actor, actor]
        self.notes.append(note)
        self.messages.append(
            {
                "id": str(len(self.messages)),
                "from": actors[0],
                "to": actors[1],
                "message": message.get("text"),
                "wrap": message["wrap"] if message.get("wrap") is not None else self.auto_wrap(),
                "type": LINETYPE["NOTE"],
                "placement": placement,
            }
        )

    # -- links / properties -----------------------------------------------

    def get_actor(self, actor_id: str) -> dict:
        return self.actors[actor_id]

    def add_links(self, actor_id: str, text: dict):
        actor = self.get_actor(actor_id)
        try:
            sanitized = sanitize_text(text["text"], get_config())
            sanitized = sanitized.replace("&equals;", "=").replace("&amp;", "&")
            self._insert_links(actor, json.loads(sanitized))
        except Exception:  # noqa: BLE001 - upstream logs and continues
            pass

    def add_a_link(self, actor_id: str, text: dict):
        actor = self.get_actor(actor_id)
        try:
            sanitized = sanitize_text(text["text"], get_config())
            sep = sanitized.find("@")
            sanitized = sanitized.replace("&equals;", "=").replace("&amp;", "&")
            label = sanitized[: sep - 1].strip()
            link = sanitized[sep + 1 :].strip()
            self._insert_links(actor, {label: link})
        except Exception:  # noqa: BLE001
            pass

    def _insert_links(self, actor: dict, links: dict):
        if actor.get("links") is None:
            actor["links"] = links
        else:
            actor["links"].update(links)

    def add_properties(self, actor_id: str, text: dict):
        actor = self.get_actor(actor_id)
        try:
            properties = json.loads(sanitize_text(text["text"], get_config()))
            self._insert_properties(actor, properties)
        except Exception:  # noqa: BLE001
            pass

    def _insert_properties(self, actor: dict, properties: dict):
        if actor.get("properties") is None:
            actor["properties"] = properties
        else:
            actor["properties"].update(properties)

    # -- sequence numbers ------------------------------------------------

    def enable_sequence_numbers(self):
        self.sequence_numbers_enabled = True

    def disable_sequence_numbers(self):
        self.sequence_numbers_enabled = False

    def show_sequence_numbers(self) -> bool:
        return self.sequence_numbers_enabled

    # -- accessors -------------------------------------------------------

    def get_messages(self):
        return self.messages

    def get_actors(self):
        return self.actors

    def get_created_actors(self):
        return self.created_actors

    def get_destroyed_actors(self):
        return self.destroyed_actors

    def get_boxes(self):
        return self.boxes

    def get_actor_keys(self):
        return list(self.actors.keys())

    def has_at_least_one_box(self):
        return len(self.boxes) > 0

    def has_at_least_one_box_with_title(self):
        return any(b.get("name") for b in self.boxes)

    # -- common title / acc --------------------------------------------

    def set_diagram_title(self, value: str):
        self._title = value

    def get_diagram_title(self) -> str:
        return self._title

    def set_acc_title(self, value: str):
        self._acc_title = value.strip()

    def get_acc_title(self) -> str:
        return self._acc_title

    def set_acc_description(self, value: str):
        self._acc_description = value.strip()

    def get_acc_description(self) -> str:
        return self._acc_description

    # -- message parsing helpers (called from grammar actions) --------

    def parse_message(self, text: str) -> dict:
        trimmed = text.strip()
        extracted = self._extract_wrap(trimmed)
        return {"text": extracted["cleanedText"], "wrap": extracted["wrap"]}

    def parse_box_data(self, text: str) -> dict:
        match = _BOX_RE.match(text)
        color = match.group(1).strip() if match and match.group(1) else "transparent"
        title = match.group(2).strip() if match and match.group(2) else None
        # No CSS.supports() off-DOM; accept named/functional colours, else treat
        # the whole line as the title. (A domonic CSS colour check would go here.)
        if color and not _looks_like_colour(color):
            color = "transparent"
            title = text.strip()
        extracted = self._extract_wrap(title)
        cleaned = extracted["cleanedText"]
        return {
            "text": sanitize_text(cleaned, get_config()) if cleaned else None,
            "color": color,
            "wrap": extracted["wrap"],
        }

    # -- apply ---------------------------------------------------------

    def apply(self, param):
        if isinstance(param, list):
            for item in param:
                self.apply(item)
            return

        kind = param.get("type")
        if kind == "sequenceIndex":
            self.messages.append(
                {
                    "id": str(len(self.messages)),
                    "from": None,
                    "to": None,
                    "message": {
                        "start": param.get("sequenceIndex"),
                        "step": param.get("sequenceIndexStep"),
                        "visible": param.get("sequenceVisible"),
                    },
                    "wrap": False,
                    "type": param.get("signalType"),
                }
            )
        elif kind == "addParticipant":
            self.add_actor(param["actor"], param["actor"], param.get("description"), param.get("draw"))
        elif kind == "createParticipant":
            if param["actor"] in self.actors:
                raise ValueError(
                    "It is not possible to have actors with the same id, even if "
                    "one is destroyed before the next is created. Use 'AS' aliases "
                    "to simulate the behavior"
                )
            self.last_created = param["actor"]
            self.add_actor(param["actor"], param["actor"], param.get("description"), param.get("draw"))
            self.created_actors[param["actor"]] = len(self.messages)
        elif kind == "destroyParticipant":
            self.last_destroyed = param["actor"]
            self.destroyed_actors[param["actor"]] = len(self.messages)
        elif kind in ("activeStart", "activeEnd"):
            self.add_signal(param["actor"], None, None, param["signalType"])
        elif kind == "addNote":
            self.add_note(param["actor"], param["placement"], param["text"])
        elif kind == "addLinks":
            self.add_links(param["actor"], param["text"])
        elif kind == "addALink":
            self.add_a_link(param["actor"], param["text"])
        elif kind == "addProperties":
            self.add_properties(param["actor"], param["text"])
        elif kind == "addMessage":
            if self.last_created:
                if param["to"] != self.last_created:
                    raise ValueError(
                        f"The created participant {self.last_created} does not have "
                        "an associated creating message after its declaration. "
                        "Please check the sequence diagram."
                    )
                self.last_created = None
            elif self.last_destroyed:
                if param["to"] != self.last_destroyed and param["from"] != self.last_destroyed:
                    raise ValueError(
                        f"The destroyed participant {self.last_destroyed} does not "
                        "have an associated destroying message after its "
                        "declaration. Please check the sequence diagram."
                    )
                self.last_destroyed = None
            self.add_signal(
                param["from"], param["to"], param.get("msg"), param["signalType"], param.get("activate", False)
            )
        elif kind == "boxStart":
            self.add_box(param["boxData"])
        elif kind == "boxEnd":
            self._box_end()
        elif kind in (
            "loopStart", "rectStart", "optStart", "altStart", "else",
            "parStart", "and", "criticalStart", "option", "breakStart",
        ):
            text_key = {
                "loopStart": "loopText", "rectStart": "color", "optStart": "optText",
                "altStart": "altText", "else": "altText", "parStart": "parText",
                "and": "parText", "criticalStart": "criticalText",
                "option": "optionText", "breakStart": "breakText",
            }[kind]
            self.add_signal(None, None, param.get(text_key), param["signalType"])
        elif kind in (
            "loopEnd", "rectEnd", "optEnd", "altEnd", "parEnd", "criticalEnd", "breakEnd",
        ):
            self.add_signal(None, None, None, param["signalType"])
        elif kind == "setAccTitle":
            self.set_acc_title(param["text"])


def _looks_like_colour(value: str) -> bool:
    value = value.strip().lower()
    if not value or value == "transparent":
        return True
    if value.startswith(("rgb", "hsl", "#")):
        return True
    return value.isalpha()
