# Ported from mermaid-js/mermaid (MIT), tag mermaid@11.9.0. Mirrors
# src/diagrams/pie/pieDb.ts.
"""``PieDB`` -- ordered ``label -> value`` sections plus the common title/acc state.

``add_section`` keeps the first value seen for a label (upstream ``Map`` insert
guard); ``get_sections`` returns insertion order -- the renderer sorts by value.
"""

from __future__ import annotations


class PieDB:
    def __init__(self):
        self.clear()

    def clear(self):
        self._sections: dict[str, float] = {}
        self._show_data = False
        self._title = ""
        self._acc_title = ""
        self._acc_description = ""

    def add_section(self, label: str, value: float):
        if label not in self._sections:
            self._sections[label] = value

    def get_sections(self) -> dict[str, float]:
        return self._sections

    def set_show_data(self, toggle: bool):
        self._show_data = bool(toggle)

    def get_show_data(self) -> bool:
        return self._show_data

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
