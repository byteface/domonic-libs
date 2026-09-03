# Ported from ljharb/qs (BSD-3-Clause). Preserve the upstream license when redistributing.
"""Parser for the domonic port of ljharb/qs."""

from __future__ import annotations

import re
from typing import Any, Callable

from . import utils

try:
    from domonic.javascript import Array, Object
except ImportError:  # standalone smoke-test fallback
    class Array:
        @staticmethod
        def isArray(value):
            return isinstance(value, list)

    class Object:
        @staticmethod
        def keys(value):
            if isinstance(value, dict):
                return [str(k) for k in value.keys()]
            return []


defaults = {
    "allowDots": False,
    "allowEmptyArrays": False,
    "allowPrototypes": False,
    "allowSparse": False,
    "arrayLimit": 20,
    "charset": "utf-8",
    "charsetSentinel": False,
    "comma": False,
    "decodeDotInKeys": False,
    "decoder": utils.decode,
    "delimiter": "&",
    "depth": 5,
    "duplicates": "combine",
    "ignoreQueryPrefix": False,
    "interpretNumericEntities": False,
    "parameterLimit": 1000,
    "parseArrays": True,
    "plainObjects": False,
    "strictDepth": False,
    "strictMerge": True,
    "strictNullHandling": False,
    "throwOnLimitExceeded": False,
}

isoSentinel = "utf8=%26%2310003%3B"
charsetSentinel = "utf8=%E2%9C%93"

# Own properties normally present on Object.prototype. qs rejects these names by
# default in bracket paths; Python has no prototype chain, so we model the guard.
_OBJECT_PROTOTYPE_NAMES = {
    "__defineGetter__", "__defineSetter__", "__lookupGetter__", "__lookupSetter__",
    "__proto__", "constructor", "hasOwnProperty", "isPrototypeOf",
    "propertyIsEnumerable", "toLocaleString", "toString", "valueOf",
}


def _is_array(value: Any) -> bool:
    try:
        return bool(Array.isArray(value))
    except Exception:
        return isinstance(value, list)


def _invoke_decoder(decoder: Callable[..., Any], value: Any, charset: str, kind: str):
    return decoder(value, defaults["decoder"], charset, kind)


def interpretNumericEntities(value: str) -> str:
    return re.sub(r"&#(\d+);", lambda m: chr(int(m.group(1), 10)), value)


def parseArrayValue(val: Any, options: dict[str, Any], currentArrayLength: int):
    if val and isinstance(val, str) and options["comma"] and "," in val:
        if options["throwOnLimitExceeded"]:
            comma_count = val.count(",")
            if comma_count >= options["arrayLimit"]:
                limit = options["arrayLimit"]
                raise ValueError(
                    f"Array limit exceeded. Only {limit} element"
                    f"{'' if limit == 1 else 's'} allowed in an array."
                )
        return val.split(",")

    if options["throwOnLimitExceeded"] and currentArrayLength >= options["arrayLimit"]:
        limit = options["arrayLimit"]
        raise ValueError(
            f"Array limit exceeded. Only {limit} element"
            f"{'' if limit == 1 else 's'} allowed in an array."
        )
    return val


def _split_parts(clean: str, delimiter: Any, limit: int | None, throw: bool) -> list[str]:
    max_parts = (limit + 1) if throw and limit is not None else limit
    if isinstance(delimiter, re.Pattern):
        parts = delimiter.split(clean)
        return parts if max_parts is None else parts[:max_parts]
    parts = clean.split(str(delimiter))
    # JS String.prototype.split(separator, limit) discards anything after the
    # requested result count; Python maxsplit would fold the remainder into the
    # final element, which is not qs-compatible.
    return parts if max_parts is None else parts[:max_parts]


def parseValues(str_: str, options: dict[str, Any]) -> dict[str, Any]:
    obj: dict[str, Any] = {}

    clean = re.sub(r"^\?", "", str_, count=1) if options["ignoreQueryPrefix"] else str_
    clean = re.sub(r"%5B", "[", clean, flags=re.I)
    clean = re.sub(r"%5D", "]", clean, flags=re.I)

    limit = None if options["parameterLimit"] == float("inf") else int(options["parameterLimit"])
    parts = _split_parts(clean, options["delimiter"], limit, options["throwOnLimitExceeded"])

    if options["throwOnLimitExceeded"] and limit is not None and len(parts) > limit:
        raise ValueError(
            f"Parameter limit exceeded. Only {limit} parameter"
            f"{'' if limit == 1 else 's'} allowed."
        )

    skip_index = -1
    charset = options["charset"]
    if options["charsetSentinel"]:
        for i, part in enumerate(parts):
            if part.startswith("utf8="):
                if part == charsetSentinel:
                    charset = "utf-8"
                elif part == isoSentinel:
                    charset = "iso-8859-1"
                skip_index = i
                break

    for i, part in enumerate(parts):
        if i == skip_index:
            continue

        bracket_equals = part.find("]=")
        pos = part.find("=") if bracket_equals == -1 else bracket_equals + 1

        key = None
        val: Any = None
        if pos == -1:
            key = _invoke_decoder(options["decoder"], part, charset, "key")
            val = None if options["strictNullHandling"] else ""
        else:
            key = _invoke_decoder(options["decoder"], part[:pos], charset, "key")
            if key is not None:
                existing_val = obj.get(key)
                current_length = len(existing_val) if isinstance(existing_val, list) else 0
                parsed = parseArrayValue(part[pos + 1 :], options, current_length)
                val = utils.maybeMap(
                    parsed,
                    lambda encoded: _invoke_decoder(options["decoder"], encoded, charset, "value"),
                )

        if val and options["interpretNumericEntities"] and charset == "iso-8859-1":
            val = interpretNumericEntities(str(val))

        if "[]=" in part:
            val = [val] if isinstance(val, list) else val

        if options["comma"] and isinstance(val, list) and len(val) > options["arrayLimit"]:
            val = utils.combine(
                [], val, options["arrayLimit"], options["plainObjects"], options["throwOnLimitExceeded"]
            )

        if key is not None:
            existing = key in obj
            if existing and (options["duplicates"] == "combine" or "[]=" in part):
                obj[key] = utils.combine(
                    obj[key], val, options["arrayLimit"], options["plainObjects"], options["throwOnLimitExceeded"]
                )
            elif not existing or options["duplicates"] == "last":
                obj[key] = val

    return obj


def _set_list_index(target: list[Any], index: int, value: Any) -> None:
    if index >= len(target):
        target.extend([utils.UNDEFINED] * (index + 1 - len(target)))
    target[index] = value


def parseObject(chain: list[str], val: Any, options: dict[str, Any], valuesParsed: bool):
    current_array_length = len(val) if chain and chain[-1] == "[]" and isinstance(val, list) else 0
    leaf = val if valuesParsed else parseArrayValue(val, options, current_array_length)

    for root in reversed(chain):
        if root == "[]" and options["parseArrays"]:
            if utils.isOverflow(leaf):
                obj: Any = leaf
            elif options["allowEmptyArrays"] and (
                leaf == "" or (options["strictNullHandling"] and leaf is None)
            ):
                obj = []
            else:
                obj = utils.combine(
                    [], leaf, options["arrayLimit"], options["plainObjects"], options["throwOnLimitExceeded"]
                )
        else:
            clean_root = root[1:-1] if root.startswith("[") and root.endswith("]") else root
            decoded_root = re.sub(r"%2E", ".", clean_root, flags=re.I) if options["decodeDotInKeys"] else clean_root

            try:
                index = int(decoded_root, 10)
                valid_index = (
                    root != decoded_root
                    and str(index) == decoded_root
                    and index >= 0
                    and options["parseArrays"]
                )
            except (TypeError, ValueError):
                index = -1
                valid_index = False

            if not options["parseArrays"] and decoded_root == "":
                obj = {"0": leaf}
            elif valid_index and index < options["arrayLimit"]:
                obj = []
                _set_list_index(obj, index, leaf)
            elif valid_index and options["throwOnLimitExceeded"]:
                limit = options["arrayLimit"]
                raise ValueError(
                    f"Array limit exceeded. Only {limit} element"
                    f"{'' if limit == 1 else 's'} allowed in an array."
                )
            elif valid_index:
                obj = utils.markOverflow({str(index): leaf}, index)
            elif decoded_root != "__proto__":
                obj = {decoded_root: leaf}
            else:
                obj = {}

        leaf = obj

    return leaf


def splitKeyIntoSegments(originalKey: str, options: dict[str, Any]):
    key = re.sub(r"\.([^.[]+)", r"[\1]", originalKey) if options["allowDots"] else originalKey

    if options["depth"] <= 0:
        if not options["plainObjects"] and key in _OBJECT_PROTOTYPE_NAMES and not options["allowPrototypes"]:
            return None
        return [key]

    segments: list[str] = []
    first = key.find("[")
    parent = key[:first] if first >= 0 else key
    if parent:
        if not options["plainObjects"] and parent in _OBJECT_PROTOTYPE_NAMES and not options["allowPrototypes"]:
            return None
        segments.append(parent)

    n = len(key)
    open_pos = first
    collected = 0

    while open_pos >= 0 and collected < options["depth"]:
        level = 1
        i = open_pos + 1
        close = -1

        while i < n and close < 0:
            if key[i] == "[":
                level += 1
            elif key[i] == "]":
                level -= 1
                if level == 0:
                    close = i
            i += 1

        if close < 0:
            segments.append("[" + key[open_pos:] + "]")
            return segments

        seg = key[open_pos : close + 1]
        content = seg[1:-1]
        if not options["plainObjects"] and content in _OBJECT_PROTOTYPE_NAMES and not options["allowPrototypes"]:
            return None

        segments.append(seg)
        collected += 1
        open_pos = key.find("[", close + 1)

    if open_pos >= 0:
        if options["strictDepth"] is True:
            raise ValueError(
                f"Input depth exceeded depth option of {options['depth']} and strictDepth is true"
            )
        segments.append("[" + key[open_pos:] + "]")

    return segments


def parseKeys(givenKey: str, val: Any, options: dict[str, Any], valuesParsed: bool):
    if not givenKey:
        return None
    keys = splitKeyIntoSegments(givenKey, options)
    if not keys:
        return None
    return parseObject(keys, val, options, valuesParsed)


def normalizeParseOptions(opts: dict[str, Any] | None):
    if not opts:
        return defaults.copy()

    if "allowEmptyArrays" in opts and not isinstance(opts["allowEmptyArrays"], bool):
        raise TypeError("`allowEmptyArrays` option can only be `true` or `false`, when provided")
    if "decodeDotInKeys" in opts and not isinstance(opts["decodeDotInKeys"], bool):
        raise TypeError("`decodeDotInKeys` option can only be `true` or `false`, when provided")
    if opts.get("decoder", utils.UNDEFINED) is not utils.UNDEFINED and opts.get("decoder") is not None and not callable(opts.get("decoder")):
        raise TypeError("Decoder has to be a function.")
    if "charset" in opts and opts["charset"] not in ("utf-8", "iso-8859-1"):
        raise TypeError("The charset option must be either utf-8, iso-8859-1, or undefined")
    if "throwOnLimitExceeded" in opts and not isinstance(opts["throwOnLimitExceeded"], bool):
        raise TypeError("`throwOnLimitExceeded` option must be a boolean")

    charset = opts.get("charset", defaults["charset"])
    duplicates = opts.get("duplicates", defaults["duplicates"])
    if duplicates not in ("combine", "first", "last"):
        raise TypeError("The duplicates option must be either combine, first, or last")

    allow_dots = (
        bool(opts.get("decodeDotInKeys"))
        if "allowDots" not in opts and opts.get("decodeDotInKeys") is True
        else bool(opts.get("allowDots", defaults["allowDots"]))
    )

    depth_opt = opts.get("depth", defaults["depth"])
    depth = 0 if depth_opt is False else depth_opt

    return {
        "allowDots": allow_dots,
        "allowEmptyArrays": bool(opts.get("allowEmptyArrays", defaults["allowEmptyArrays"])),
        "allowPrototypes": bool(opts.get("allowPrototypes", defaults["allowPrototypes"])),
        "allowSparse": bool(opts.get("allowSparse", defaults["allowSparse"])),
        "arrayLimit": opts["arrayLimit"] if isinstance(opts.get("arrayLimit"), (int, float)) else defaults["arrayLimit"],
        "charset": charset,
        "charsetSentinel": bool(opts.get("charsetSentinel", defaults["charsetSentinel"])),
        "comma": bool(opts.get("comma", defaults["comma"])),
        "decodeDotInKeys": bool(opts.get("decodeDotInKeys", defaults["decodeDotInKeys"])),
        "decoder": opts["decoder"] if callable(opts.get("decoder")) else defaults["decoder"],
        "delimiter": opts["delimiter"] if isinstance(opts.get("delimiter"), (str, re.Pattern)) else defaults["delimiter"],
        "depth": depth,
        "duplicates": duplicates,
        "ignoreQueryPrefix": opts.get("ignoreQueryPrefix") is True,
        "interpretNumericEntities": bool(opts.get("interpretNumericEntities", defaults["interpretNumericEntities"])),
        "parameterLimit": opts["parameterLimit"] if isinstance(opts.get("parameterLimit"), (int, float)) else defaults["parameterLimit"],
        "parseArrays": opts.get("parseArrays") is not False,
        "plainObjects": bool(opts.get("plainObjects", defaults["plainObjects"])),
        "strictDepth": bool(opts.get("strictDepth", defaults["strictDepth"])),
        "strictMerge": bool(opts.get("strictMerge", defaults["strictMerge"])),
        "strictNullHandling": bool(opts.get("strictNullHandling", defaults["strictNullHandling"])),
        "throwOnLimitExceeded": bool(opts.get("throwOnLimitExceeded", False)),
    }


def parse(str_: Any, opts: dict[str, Any] | None = None):
    options = normalizeParseOptions(opts)

    if str_ in ("", None):
        return {}

    temp_obj = parseValues(str_, options) if isinstance(str_, str) else str_
    obj: Any = {}

    keys = list(temp_obj.keys()) if isinstance(temp_obj, dict) else []
    for key in keys:
        new_obj = parseKeys(str(key), temp_obj[key], options, isinstance(str_, str))
        obj = utils.merge(obj, new_obj, options)

    if options["allowSparse"] is True:
        return obj
    return utils.compact(obj)


__all__ = ["parse", "normalizeParseOptions"]
