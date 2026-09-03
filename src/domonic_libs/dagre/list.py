# Ported from dagrejs/dagre (MIT). Mirrors lib/data/list.ts.
"""Doubly linked list used as the bucket queue in greedy-FAS."""

from __future__ import annotations


class _Node:
    __slots__ = ("_next", "_prev", "data")

    def __init__(self):
        self._next = None
        self._prev = None
        self.data = None


class List:
    def __init__(self):
        s = _Node()
        s._next = s._prev = s
        self._sentinel = s

    def dequeue(self):
        s = self._sentinel
        entry = s._prev
        if entry is not s:
            _unlink(entry)
            return entry
        return None

    def enqueue(self, entry):
        s = self._sentinel
        if entry._prev and entry._next:
            _unlink(entry)
        entry._next = s._next
        s._next._prev = entry
        s._next = entry
        entry._prev = s


def _unlink(entry):
    entry._prev._next = entry._next
    entry._next._prev = entry._prev
    entry._next = None
    entry._prev = None
