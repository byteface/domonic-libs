# Ported from ljharb/qs (BSD-3-Clause). Preserve the upstream license when redistributing.
"""Stringifier for the domonic port of ljharb/qs."""

from __future__ import annotations

import datetime as _datetime
from functools import cmp_to_key
from typing import Any, Callable

from . import formats, utils

try:
    from domonic.javascript import Array, Date as JSDate, Object
except ImportError:  # standalone smoke-test fallback
    JSDate = ()  # type: ignore[assignment]

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
            return []


def _brackets(prefix: str, key: str | None = None) -> str:
    return prefix + "[]"


def _indices(prefix: str, key: str) -> str:
    return f"{prefix}[{key}]"


def _repeat(prefix: str, key: str | None = None) -> str:
    return prefix


arrayPrefixGenerators = {
    "brackets": _brackets,
    "comma": "comma",
    "indices": _indices,
    "repeat": _repeat,
}

defaultFormat = formats.default
defaults = {
    "addQueryPrefix": False,
    "allowDots": False,
    "allowEmptyArrays": False,
    "arrayFormat": "indices",
    "charset": "utf-8",
    "charsetSentinel": False,
    "commaRoundTrip": False,
    "delimiter": "&",
    "depth": float("inf"),
    "encode": True,
    "encodeDotInKeys": False,
    "encoder": utils.encode,
    "encodeValuesOnly": False,
    "filter": None,
    "format": defaultFormat,
    "formatter": formats.formatters[defaultFormat],
    "indices": False,
    "serializeDate": None,
    "skipNulls": False,
    "sort": None,
    "strictNullHandling": False,
}


def _js_string(value: Any) -> str:
    if isinstance(value, bool):
        return "true" if value else "false"
    if value is None:
        return ""
    return str(value)


def _is_array(value: Any) -> bool:
    try:
        return bool(Array.isArray(value))
    except Exception:
        return isinstance(value, list)


def _object_keys(value: Any) -> list[str]:
    if isinstance(value, dict):
        return [str(k) for k in value.keys()]
    if isinstance(value, list):
        return [str(i) for i, item in enumerate(value) if item is not utils.UNDEFINED]
    try:
        return list(Object.keys(value))
    except Exception:
        return []


def _mapping_get(mapping: dict[Any, Any], key: Any) -> Any:
    if key in mapping:
        return mapping[key]
    wanted = str(key)
    for actual_key, value in mapping.items():
        if str(actual_key) == wanted:
            return value
    return utils.UNDEFINED


def _is_date(value: Any) -> bool:
    if isinstance(value, (_datetime.datetime, _datetime.date)):
        return True
    try:
        return isinstance(value, JSDate)
    except TypeError:
        return False


def _default_serialize_date(value: Any) -> str:
    if isinstance(value, _datetime.datetime):
        dt = value
        if dt.tzinfo is not None:
            dt = dt.astimezone(_datetime.timezone.utc)
        text = dt.isoformat(timespec="milliseconds")
        return text.replace("+00:00", "Z")
    if isinstance(value, _datetime.date):
        return value.isoformat()
    js_date_value = getattr(value, "date", None)
    if isinstance(js_date_value, _datetime.datetime):
        dt = js_date_value
        if dt.tzinfo is not None:
            dt = dt.astimezone(_datetime.timezone.utc)
        text = dt.isoformat(timespec="milliseconds")
        return text.replace("+00:00", "Z")
    if isinstance(js_date_value, _datetime.date):
        return js_date_value.isoformat()
    if hasattr(value, "toISOString"):
        return value.toISOString()
    return str(value)


defaults["serializeDate"] = _default_serialize_date


def isNonNullishPrimitive(value: Any) -> bool:
    return isinstance(value, (str, int, float, bool))


def _sorted_keys(keys: list[Any], sort: Callable[..., Any] | None) -> list[Any]:
    if not sort:
        return keys
    try:
        return sorted(keys, key=cmp_to_key(sort))
    except TypeError:
        return sorted(keys, key=sort)


def _format_value(value: Any, formatter: Callable[[Any], str]) -> str:
    return formatter(value)


def _stringify(
    object_: Any,
    prefix: str,
    generateArrayPrefix: Any,
    commaRoundTrip: bool,
    allowEmptyArrays: bool,
    strictNullHandling: bool,
    skipNulls: bool,
    encodeDotInKeys: bool,
    encoder: Callable[..., Any] | None,
    filter_: Any,
    sort: Callable[..., Any] | None,
    allowDots: bool,
    serializeDate: Callable[[Any], str],
    format_: str,
    formatter: Callable[[Any], str],
    encodeValuesOnly: bool,
    charset: str,
    ancestry: set[int],
    depth: float,
    currentDepth: int,
) -> list[str]:
    if currentDepth > depth:
        raise ValueError(f"Input depth exceeded depth option of {depth}")

    obj = object_

    if callable(filter_):
        obj = filter_(prefix, obj)

    if _is_date(obj):
        obj = serializeDate(obj)
    elif generateArrayPrefix == "comma" and _is_array(obj):
        obj = [serializeDate(v) if _is_date(v) else v for v in obj]

    if obj is None:
        if strictNullHandling:
            rendered = encoder(prefix, defaults["encoder"], charset, "key", format_) if encoder and not encodeValuesOnly else prefix
            return [_format_value(rendered, formatter)]
        obj = ""

    if isNonNullishPrimitive(obj) or utils.isBuffer(obj):
        if encoder:
            key_value = prefix if encodeValuesOnly else encoder(prefix, defaults["encoder"], charset, "key", format_)
            return [
                _format_value(key_value, formatter)
                + "="
                + _format_value(encoder(obj, defaults["encoder"], charset, "value", format_), formatter)
            ]
        return [_format_value(prefix, formatter) + "=" + _format_value(_js_string(obj), formatter)]

    if obj is utils.UNDEFINED:
        return []

    if not isinstance(obj, (dict, list, tuple)):
        return []

    ident = id(obj)
    if ident in ancestry:
        raise ValueError("Cyclic object value")
    next_ancestry = set(ancestry)
    next_ancestry.add(ident)

    values: list[str] = []

    if generateArrayPrefix == "comma" and _is_array(obj):
        seq = list(obj)
        if encodeValuesOnly and encoder:
            seq = [v if v is None else encoder(v, defaults["encoder"], charset, "value", format_) for v in seq]
        joined = ",".join("" if v is None else _js_string(v) for v in seq)
        obj_keys: list[Any] = [{"value": joined if len(seq) > 0 and joined != "" else (None if len(seq) > 0 else utils.UNDEFINED)}]
    elif isinstance(filter_, list):
        obj_keys = list(filter_)
    else:
        obj_keys = _sorted_keys(_object_keys(obj), sort)

    encoded_prefix = str(prefix).replace(".", "%2E") if encodeDotInKeys else str(prefix)
    adjusted_prefix = encoded_prefix + "[]" if commaRoundTrip and _is_array(obj) and len(obj) == 1 else encoded_prefix

    if allowEmptyArrays and _is_array(obj) and len(obj) == 0:
        return [adjusted_prefix + "[]"]

    for key in obj_keys:
        if isinstance(key, dict) and "value" in key:
            value = key["value"]
            encoded_key = ""
        else:
            if isinstance(obj, dict):
                value = _mapping_get(obj, key)
            else:
                try:
                    value = obj[int(key)]
                except (ValueError, TypeError, IndexError):
                    value = utils.UNDEFINED
            encoded_key = str(key).replace(".", "%2E") if allowDots and encodeDotInKeys else str(key)

        if skipNulls and value is None:
            continue
        if value is utils.UNDEFINED:
            continue

        if _is_array(obj):
            if callable(generateArrayPrefix):
                key_prefix = generateArrayPrefix(adjusted_prefix, encoded_key)
            else:
                key_prefix = adjusted_prefix
        else:
            key_prefix = adjusted_prefix + (("." + encoded_key) if allowDots else ("[" + encoded_key + "]"))

        nested_encoder = None if generateArrayPrefix == "comma" and encodeValuesOnly and _is_array(obj) else encoder
        values.extend(
            _stringify(
                value,
                key_prefix,
                generateArrayPrefix,
                commaRoundTrip,
                allowEmptyArrays,
                strictNullHandling,
                skipNulls,
                encodeDotInKeys,
                nested_encoder,
                filter_,
                sort,
                allowDots,
                serializeDate,
                format_,
                formatter,
                encodeValuesOnly,
                charset,
                next_ancestry,
                depth,
                currentDepth + 1,
            )
        )

    return values


def normalizeStringifyOptions(opts: dict[str, Any] | None):
    if not opts:
        return defaults.copy()

    if "allowEmptyArrays" in opts and not isinstance(opts["allowEmptyArrays"], bool):
        raise TypeError("`allowEmptyArrays` option can only be `true` or `false`, when provided")
    if "encodeDotInKeys" in opts and not isinstance(opts["encodeDotInKeys"], bool):
        raise TypeError("`encodeDotInKeys` option can only be `true` or `false`, when provided")
    if "encoder" in opts and opts["encoder"] is not None and not callable(opts["encoder"]):
        raise TypeError("Encoder has to be a function.")

    charset = opts.get("charset") or defaults["charset"]
    if "charset" in opts and opts["charset"] not in ("utf-8", "iso-8859-1"):
        raise TypeError("The charset option must be either utf-8, iso-8859-1, or undefined")

    format_ = opts.get("format", formats.default)
    if format_ not in formats.formatters:
        raise TypeError("Unknown format option provided.")
    formatter = formats.formatters[format_]

    filter_ = opts.get("filter", defaults["filter"])
    if not callable(filter_) and not isinstance(filter_, list):
        filter_ = defaults["filter"]

    if opts.get("arrayFormat") in arrayPrefixGenerators:
        array_format = opts["arrayFormat"]
    elif "indices" in opts:
        array_format = "indices" if opts["indices"] else "repeat"
    else:
        array_format = defaults["arrayFormat"]

    if "commaRoundTrip" in opts and not isinstance(opts["commaRoundTrip"], bool):
        raise TypeError("`commaRoundTrip` must be a boolean, or absent")

    allow_dots = (
        bool(opts.get("encodeDotInKeys"))
        if "allowDots" not in opts and opts.get("encodeDotInKeys") is True
        else bool(opts.get("allowDots", defaults["allowDots"]))
    )

    return {
        "addQueryPrefix": bool(opts.get("addQueryPrefix", defaults["addQueryPrefix"])),
        "allowDots": allow_dots,
        "allowEmptyArrays": bool(opts.get("allowEmptyArrays", defaults["allowEmptyArrays"])),
        "arrayFormat": array_format,
        "charset": charset,
        "charsetSentinel": bool(opts.get("charsetSentinel", defaults["charsetSentinel"])),
        "commaRoundTrip": bool(opts.get("commaRoundTrip", False)),
        "delimiter": opts.get("delimiter", defaults["delimiter"]),
        "depth": opts["depth"] if isinstance(opts.get("depth"), (int, float)) else defaults["depth"],
        "encode": bool(opts.get("encode", defaults["encode"])),
        "encodeDotInKeys": bool(opts.get("encodeDotInKeys", defaults["encodeDotInKeys"])),
        "encoder": opts["encoder"] if callable(opts.get("encoder")) else defaults["encoder"],
        "encodeValuesOnly": bool(opts.get("encodeValuesOnly", defaults["encodeValuesOnly"])),
        "filter": filter_,
        "format": format_,
        "formatter": formatter,
        "serializeDate": opts["serializeDate"] if callable(opts.get("serializeDate")) else defaults["serializeDate"],
        "skipNulls": bool(opts.get("skipNulls", defaults["skipNulls"])),
        "sort": opts["sort"] if callable(opts.get("sort")) else None,
        "strictNullHandling": bool(opts.get("strictNullHandling", defaults["strictNullHandling"])),
    }


def stringify(object_: Any, opts: dict[str, Any] | None = None) -> str:
    obj = object_
    options = normalizeStringifyOptions(opts)

    obj_keys = None
    filter_ = None

    if callable(options["filter"]):
        filter_ = options["filter"]
        obj = filter_("", obj)
    elif isinstance(options["filter"], list):
        filter_ = options["filter"]
        obj_keys = filter_

    if not isinstance(obj, (dict, list, tuple)):
        return ""

    generate_array_prefix = arrayPrefixGenerators[options["arrayFormat"]]
    comma_round_trip = generate_array_prefix == "comma" and options["commaRoundTrip"]

    if obj_keys is None:
        obj_keys = _object_keys(obj)
    obj_keys = _sorted_keys(list(obj_keys), options["sort"])

    keys: list[str] = []
    for key in obj_keys:
        if key is None:
            continue

        if isinstance(obj, dict):
            value = _mapping_get(obj, key)
        else:
            try:
                value = obj[int(key)]
            except (ValueError, TypeError, IndexError):
                value = utils.UNDEFINED

        if options["skipNulls"] and value is None:
            continue
        if value is utils.UNDEFINED:
            continue

        encoded_key = str(key).replace(".", "%2E") if options["encodeDotInKeys"] else str(key)
        keys.extend(
            _stringify(
                value,
                encoded_key,
                generate_array_prefix,
                comma_round_trip,
                options["allowEmptyArrays"],
                options["strictNullHandling"],
                options["skipNulls"],
                options["encodeDotInKeys"],
                options["encoder"] if options["encode"] else None,
                options["filter"],
                options["sort"],
                options["allowDots"],
                options["serializeDate"],
                options["format"],
                options["formatter"],
                options["encodeValuesOnly"],
                options["charset"],
                set(),
                options["depth"],
                0,
            )
        )

    joined = str(options["delimiter"]).join(keys)
    prefix = "?" if options["addQueryPrefix"] else ""

    if options["charsetSentinel"]:
        if options["charset"] == "iso-8859-1":
            prefix += "utf8=%26%2310003%3B" + str(options["delimiter"])
        else:
            prefix += "utf8=%E2%9C%93" + str(options["delimiter"])

    return prefix + joined if joined else ""


__all__ = ["stringify", "normalizeStringifyOptions"]
