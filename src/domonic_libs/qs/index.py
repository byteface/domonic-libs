# Ported from ljharb/qs (BSD-3-Clause). Preserve the upstream license when redistributing.
"""Public namespace matching lib/index.js."""

from . import formats
from .parse import parse
from .stringify import stringify

__all__ = ["formats", "parse", "stringify"]
