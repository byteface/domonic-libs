# Ported from ljharb/qs (BSD-3-Clause). Preserve the upstream license when redistributing.
"""Utilities used by the domonic port of ljharb/qs."""

from __future__ import annotations

import re
from typing import Any, Callable
from urllib.parse import unquote

from . import formats

try:
    from domonic.javascript import Array, Object, decodeURIComponent
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
            if isinstance(value, (list, tuple)):
                return [str(i) for i in range(len(value))]
            return [k for k in vars(value).keys() if not k.startswith("_")] if hasattr(value, "__dict__") else []

    def decodeURIComponent(value):
        return unquote(str(value), encoding="utf-8")


class _Undefined:
    def __repr__(self) -> str:
        return "undefined"


UNDEFINED = _Undefined()


class OverflowDict(dict):
    """Dict used when a JS array has overflowed qs' arrayLimit."""

    __slots__ = ("_qs_max_index",)

    def __init__(self, *args, max_index: int = -1, **kwargs):
        super().__init__(*args, **kwargs)
        self._qs_max_index = max_index


def _is_array(value: Any) -> bool:
    try:
        return bool(Array.isArray(value))
    except Exception:
        return isinstance(value, list)


def _object_keys(value: Any) -> list[str]:
    try:
        return list(Object.keys(value))
    except Exception:
        if isinstance(value, dict):
            return [str(k) for k in value.keys()]
        if isinstance(value, list):
            return [str(i) for i, item in enumerate(value) if item is not UNDEFINED]
        return []


def markOverflow(obj: Any, maxIndex: int):
    if isinstance(obj, OverflowDict):
        obj._qs_max_index = maxIndex
        return obj
    out = OverflowDict(obj if isinstance(obj, dict) else {}, max_index=maxIndex)
    return out


def isOverflow(obj: Any) -> bool:
    return isinstance(obj, OverflowDict)


def getMaxIndex(obj: Any) -> int:
    return obj._qs_max_index if isinstance(obj, OverflowDict) else -1


def setMaxIndex(obj: Any, maxIndex: int) -> None:
    if isinstance(obj, OverflowDict):
        obj._qs_max_index = maxIndex


def arrayToObject(source: list[Any], options: dict[str, Any] | None = None) -> dict[str, Any]:
    obj: dict[str, Any] = {}
    for i, value in enumerate(source):
        if value is not UNDEFINED:
            obj[str(i)] = value
    return obj


def setProperty(obj: dict[str, Any], key: Any, value: Any) -> None:
    obj[str(key)] = value


def _list_get(value: list[Any], index: int) -> Any:
    return value[index] if 0 <= index < len(value) else UNDEFINED


def _list_set(value: list[Any], index: int, item: Any) -> None:
    if index >= len(value):
        value.extend([UNDEFINED] * (index + 1 - len(value)))
    value[index] = item


def merge(target: Any, source: Any, options: dict[str, Any] | None = None) -> Any:
    if source is None:
        return target

    options = options or {}
    array_limit = options.get("arrayLimit")
    throw = bool(options.get("throwOnLimitExceeded"))
    strict_merge = bool(options.get("strictMerge", True))

    # Primitive source.
    if not isinstance(source, (dict, list, tuple, OverflowDict)):
        if isinstance(target, list):
            next_index = len(target)
            if isinstance(array_limit, (int, float)) and next_index >= array_limit:
                if throw:
                    raise ValueError(
                        f"Array limit exceeded. Only {int(array_limit)} element"
                        f"{'' if array_limit == 1 else 's'} allowed in an array."
                    )
                converted = arrayToObject(target, options)
                converted[str(next_index)] = source
                return markOverflow(converted, next_index)
            target.append(source)
            return target

        if isinstance(target, dict):
            if isOverflow(target):
                new_index = getMaxIndex(target) + 1
                target[str(new_index)] = source
                setMaxIndex(target, new_index)
            elif strict_merge:
                return [target, source]
            else:
                target[str(source)] = True
            return target

        return [target, source]

    # Non-object target merged with an object/array source.
    if not isinstance(target, (dict, list, tuple, OverflowDict)):
        if isOverflow(source):
            result = OverflowDict({"0": target}, max_index=getMaxIndex(source) + 1)
            for key, value in source.items():
                try:
                    result[str(int(key) + 1)] = value
                except (TypeError, ValueError):
                    result[str(key)] = value
            return result

        seq = [target]
        if isinstance(source, (list, tuple)):
            seq.extend(source)
        else:
            seq.append(source)

        if isinstance(array_limit, (int, float)) and len(seq) > array_limit:
            if throw:
                raise ValueError(
                    f"Array limit exceeded. Only {int(array_limit)} element"
                    f"{'' if array_limit == 1 else 's'} allowed in an array."
                )
            return markOverflow(arrayToObject(seq, options), len(seq) - 1)
        return seq

    # JS converts an array target to an object when source is an object.
    if isinstance(target, list) and isinstance(source, dict):
        merge_target: Any = arrayToObject(target, options)
    else:
        merge_target = target

    if isinstance(target, list) and isinstance(source, (list, tuple)):
        for i, item in enumerate(source):
            existing = _list_get(target, i)
            if existing is not UNDEFINED:
                if isinstance(existing, (dict, list)) and isinstance(item, (dict, list)):
                    _list_set(target, i, merge(existing, item, options))
                else:
                    target.append(item)
            else:
                _list_set(target, i, item)

        if isinstance(array_limit, (int, float)) and len(target) > array_limit:
            if throw:
                raise ValueError(
                    f"Array limit exceeded. Only {int(array_limit)} element"
                    f"{'' if array_limit == 1 else 's'} allowed in an array."
                )
            return markOverflow(arrayToObject(target, options), len(target) - 1)
        return target

    # Object merge.
    if isinstance(source, (list, tuple)):
        source_items = ((str(i), value) for i, value in enumerate(source) if value is not UNDEFINED)
    else:
        source_items = ((str(k), value) for k, value in source.items())

    if not isinstance(merge_target, dict):
        merge_target = arrayToObject(list(merge_target), options)

    for key, value in source_items:
        if key in merge_target:
            setProperty(merge_target, key, merge(merge_target[key], value, options))
        else:
            setProperty(merge_target, key, value)

        if isOverflow(source) and not isOverflow(merge_target):
            merge_target = markOverflow(merge_target, getMaxIndex(source))
        if isOverflow(merge_target):
            try:
                key_num = int(key)
                if str(key_num) == key and key_num >= 0 and key_num > getMaxIndex(merge_target):
                    setMaxIndex(merge_target, key_num)
            except (TypeError, ValueError):
                pass

    return merge_target


def assign(target: dict[str, Any], source: dict[str, Any]) -> dict[str, Any]:
    for key, value in source.items():
        setProperty(target, key, value)
    return target


def decode(str_: Any, defaultDecoder: Callable[..., Any] | None = None, charset: str = "utf-8", *_: Any):
    text = str(str_).replace("+", " ")
    if charset == "iso-8859-1":
        def repl(match: re.Match[str]) -> str:
            return bytes([int(match.group(0)[1:], 16)]).decode("latin-1")
        return re.sub(r"%[0-9a-fA-F]{2}", repl, text)

    try:
        # JavaScript decodeURIComponent throws on malformed UTF-8; qs catches that
        # and returns the original text. urllib's strict mode matches that behavior.
        return unquote(text, encoding="utf-8", errors="strict")
    except (UnicodeDecodeError, ValueError):
        return text


_JS_ESCAPE_SAFE = frozenset(
    "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789@*_+-./"
)


def _escape_iso_8859_1(value: str) -> str:
    out: list[str] = []
    # JS escape works on UTF-16 code units, so encode to UTF-16BE and walk units.
    data = value.encode("utf-16-be", "surrogatepass")
    for i in range(0, len(data), 2):
        unit = (data[i] << 8) | data[i + 1]
        ch = chr(unit)
        if unit < 128 and ch in _JS_ESCAPE_SAFE:
            out.append(ch)
        elif unit <= 0xFF:
            out.append(f"%{unit:02X}")
        else:
            out.append(f"%26%23{unit}%3B")
    return "".join(out)


def encode(
    str_: Any,
    defaultEncoder: Callable[..., Any] | None = None,
    charset: str = "utf-8",
    kind: str | None = None,
    format: str = formats.RFC3986,
):
    if str_ is None:
        string = ""
    elif isinstance(str_, bool):
        string = "true" if str_ else "false"
    else:
        string = str(str_)

    if not string:
        return string

    if charset == "iso-8859-1":
        return _escape_iso_8859_1(string)

    safe = "-._~()" if format == formats.RFC1738 else "-._~"
    # quote() is nearly the same operation, but importing domonic's
    # encodeURIComponent directly would keep JS's !'()* safe, which qs does not.
    from urllib.parse import quote
    return quote(string, safe=safe, encoding="utf-8", errors="strict")


def _compact_in_place(value: Any, seen: set[int]) -> Any:
    if not isinstance(value, (dict, list)):
        return value

    ident = id(value)
    if ident in seen:
        return value
    seen.add(ident)

    if isinstance(value, list):
        compacted = []
        for item in value:
            if item is UNDEFINED:
                continue
            compacted.append(_compact_in_place(item, seen))
        value[:] = compacted
        return value

    for key in list(value.keys()):
        value[key] = _compact_in_place(value[key], seen)
    return value


def compact(value: Any) -> Any:
    return _compact_in_place(value, set())


def isRegExp(obj: Any) -> bool:
    return isinstance(obj, re.Pattern)


def isBuffer(obj: Any) -> bool:
    return isinstance(obj, (bytes, bytearray, memoryview))


def combine(
    a: Any,
    b: Any,
    arrayLimit: int = 20,
    plainObjects: bool = False,
    throwOnLimitExceeded: bool = False,
):
    if isOverflow(a):
        if throwOnLimitExceeded:
            raise ValueError(
                f"Array limit exceeded. Only {arrayLimit} element"
                f"{'' if arrayLimit == 1 else 's'} allowed in an array."
            )
        values = b if isinstance(b, list) else [b]
        new_index = getMaxIndex(a)
        for item in values:
            new_index += 1
            a[str(new_index)] = item
        setMaxIndex(a, new_index)
        return a

    left = a if isinstance(a, list) else [a]
    right = b if isinstance(b, list) else [b]
    result = list(left) + list(right)

    if len(result) > arrayLimit:
        if throwOnLimitExceeded:
            raise ValueError(
                f"Array limit exceeded. Only {arrayLimit} element"
                f"{'' if arrayLimit == 1 else 's'} allowed in an array."
            )
        return markOverflow(arrayToObject(result, {"plainObjects": plainObjects}), len(result) - 1)
    return result


def maybeMap(val: Any, fn: Callable[[Any], Any]) -> Any:
    if isinstance(val, list):
        return [fn(item) for item in val]
    return fn(val)
