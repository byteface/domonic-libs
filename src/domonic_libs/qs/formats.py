# Ported from ljharb/qs (BSD-3-Clause). Preserve the upstream license when redistributing.
"""Formatting modes for the domonic port of ljharb/qs."""

RFC1738 = "RFC1738"
RFC3986 = "RFC3986"
default = RFC3986

def _rfc1738(value):
    return str(value).replace("%20", "+")

def _rfc3986(value):
    return str(value)

formatters = {
    RFC1738: _rfc1738,
    RFC3986: _rfc3986,
}
