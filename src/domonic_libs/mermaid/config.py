# Ported from mermaid-js/mermaid (MIT), tag mermaid@11.9.0. Preserve the
# upstream licence when redistributing.
"""Default configuration -- the ``sequence`` subset for now.

Mermaid's real config system (``diagram-api/diagramAPI``) merges a site config,
per-diagram defaults and inline ``%%{init}%%`` directives. The port starts with
the frozen defaults from ``schemas/config.schema.yaml`` and a plain
``get_config()`` / ``set_config()`` pair; directives come later.
"""

from __future__ import annotations

import copy

DEFAULT_CONFIG: dict = {
    "theme": "default",
    "wrap": False,
    "fontFamily": '"trebuchet ms", verdana, arial, sans-serif',
    "sequence": {
        "useMaxWidth": True,
        "hideUnusedParticipants": False,
        "activationWidth": 10,
        "diagramMarginX": 50,
        "diagramMarginY": 10,
        "actorMargin": 50,
        "width": 150,
        "height": 65,
        "boxMargin": 10,
        "boxTextMargin": 5,
        "noteMargin": 10,
        "messageMargin": 35,
        "messageAlign": "center",
        "mirrorActors": True,
        "forceMenus": False,
        "bottomMarginAdj": 1,
        "rightAngles": False,
        "showSequenceNumbers": False,
        "actorFontSize": 14,
        "actorFontFamily": '"Open Sans", sans-serif',
        "actorFontWeight": 400,
        "noteFontSize": 14,
        "noteFontFamily": '"trebuchet ms", verdana, arial, sans-serif',
        "noteFontWeight": 400,
        "noteAlign": "center",
        "messageFontSize": 16,
        "messageFontFamily": '"trebuchet ms", verdana, arial, sans-serif',
        "messageFontWeight": 400,
        "wrap": False,
        "wrapPadding": 10,
        "labelBoxWidth": 50,
        "labelBoxHeight": 20,
    },
}

_config: dict = copy.deepcopy(DEFAULT_CONFIG)


def get_config() -> dict:
    return _config


def set_config(patch: dict) -> dict:
    _deep_merge(_config, patch)
    return _config


def reset_config() -> None:
    global _config
    _config = copy.deepcopy(DEFAULT_CONFIG)


def _deep_merge(target: dict, patch: dict) -> None:
    for key, value in patch.items():
        if isinstance(value, dict) and isinstance(target.get(key), dict):
            _deep_merge(target[key], value)
        else:
            target[key] = value
