# Ported from markedjs/marked (MIT). Mirrors src/defaults.ts.
"""Default option set for the parser."""

from __future__ import annotations


def get_defaults():
    return {
        "async": False,
        "breaks": False,
        "extensions": None,
        "gfm": True,
        "hooks": None,
        "pedantic": False,
        "renderer": None,
        "silent": False,
        "tokenizer": None,
        "walkTokens": None,
    }


_defaults = get_defaults()


def change_defaults(new_defaults):
    global _defaults
    _defaults = new_defaults
