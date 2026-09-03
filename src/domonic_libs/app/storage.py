from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any


def default_data_dir(title: str):
    slug = re.sub(r"[^a-z0-9]+", "-", title.lower()).strip("-")
    return Path.home() / ".domonic-libs" / (slug or "app")


def load_json(path: Path, default: Any = None):
    if not path.exists():
        return default

    with path.open("r", encoding="utf-8") as file:
        return json.load(file)


def save_json(path: Path, data: Any):
    path.parent.mkdir(parents=True, exist_ok=True)

    with path.open("w", encoding="utf-8") as file:
        json.dump(data, file, indent=2, sort_keys=True)

    return path


def load_text(path: Path, default: str = "", *, encoding: str = "utf-8"):
    if not path.exists():
        return default

    return path.read_text(encoding=encoding)


def save_text(path: Path, text: str, *, encoding: str = "utf-8"):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding=encoding)
    return path


def list_files(path: Path, pattern: str = "*"):
    if not path.exists():
        return []

    return sorted(item for item in path.glob(pattern) if item.is_file())
