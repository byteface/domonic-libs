# Ported from mixmark-io/turndown (MIT). Preserve the upstream licence when
# redistributing.
"""Python port of turndown.js -- an HTML-to-Markdown converter for domonic."""

from ._turndown import TurndownService, turndown

__all__ = ["TurndownService", "turndown"]
