# Ported from mermaid-js/mermaid (MIT), tag mermaid@11.9.0. Mirrors
# src/diagrams/timeline/timelineDb.js.
"""``TimelineDB`` -- sections, and tasks (each a "period") carrying events.

A bare line is a task under the current section; a ``: ...`` line is an event
appended to the most recent task.
"""

from __future__ import annotations


class TimelineDB:
    def __init__(self):
        self.clear()

    def clear(self):
        self._current_section = ""
        self._current_task_id = 0
        self._sections: list[str] = []
        self._raw_tasks: list[dict] = []
        self._title = ""
        self._acc_title = ""
        self._acc_description = ""

    def add_section(self, text: str):
        self._current_section = text
        self._sections.append(text)

    def get_sections(self) -> list[str]:
        return self._sections

    def add_task(self, period: str, length: int = 0, event: str | None = None):
        self._raw_tasks.append(
            {
                "id": self._current_task_id,
                "section": self._current_section,
                "type": self._current_section,
                "task": period,
                "score": length or 0,
                "events": [event] if event else [],
            }
        )
        self._current_task_id += 1

    def add_event(self, event: str):
        current = next(
            (t for t in self._raw_tasks if t["id"] == self._current_task_id - 1), None
        )
        if current is not None:
            current["events"].append(event)

    def get_tasks(self) -> list[dict]:
        return self._raw_tasks

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
