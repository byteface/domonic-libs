# Ported from acornjs/acorn (MIT), tag acorn@8.18.0. Mirrors src/scopeflags.js.
"""Scope and binding-type bit flags."""

from __future__ import annotations

SCOPE_TOP = 1
SCOPE_FUNCTION = 2
SCOPE_ASYNC = 4
SCOPE_GENERATOR = 8
SCOPE_ARROW = 16
SCOPE_SIMPLE_CATCH = 32
SCOPE_SUPER = 64
SCOPE_DIRECT_SUPER = 128
SCOPE_CLASS_STATIC_BLOCK = 256
SCOPE_CLASS_FIELD_INIT = 512
SCOPE_SWITCH = 1024
SCOPE_VAR = SCOPE_TOP | SCOPE_FUNCTION | SCOPE_CLASS_STATIC_BLOCK


def functionFlags(async_, generator):
    return SCOPE_FUNCTION | (SCOPE_ASYNC if async_ else 0) | (SCOPE_GENERATOR if generator else 0)


BIND_NONE = 0
BIND_VAR = 1
BIND_LEXICAL = 2
BIND_FUNCTION = 3
BIND_SIMPLE_CATCH = 4
BIND_OUTSIDE = 5
