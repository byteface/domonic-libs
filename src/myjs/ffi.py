"""``ffi`` -- call native C libraries from JavaScript, via Python's ``ctypes``.

Exposed to scripts as the global ``ffi`` (plus a small ``os`` namespace). The
interpreter reaches arbitrary Python objects through ``getattr`` / ``setattr`` /
``__call__``, so the wrappers here are thin: a :class:`Library` yields
:class:`CFunc` proxies that marshal JS values to and from C.

    const libc = ffi.loadLibrary("c");
    libc.abs.argtypes = [ffi.types.int];
    libc.abs.restype  = ffi.types.int;
    console.log(libc.abs(-42));            // 42

Strings are encoded to UTF-8 ``bytes`` on the way in and decoded on the way out;
a :class:`Buffer` (from ``ffi.createStringBuffer``) passes its underlying storage
straight through. C -> JS callbacks are built with ``ffi.callback``.
"""

from __future__ import annotations

import ctypes
import ctypes.util
import os
import sys

# --- C type table ---------------------------------------------------------

TYPES = {
    "void": None,
    "bool": ctypes.c_bool,
    "char": ctypes.c_char,
    "schar": ctypes.c_char,
    "uchar": ctypes.c_ubyte,
    "byte": ctypes.c_ubyte,
    "short": ctypes.c_short,
    "ushort": ctypes.c_ushort,
    "int": ctypes.c_int,
    "uint": ctypes.c_uint,
    "long": ctypes.c_long,
    "ulong": ctypes.c_ulong,
    "longlong": ctypes.c_longlong,
    "ulonglong": ctypes.c_ulonglong,
    "int8": ctypes.c_int8,
    "uint8": ctypes.c_uint8,
    "int16": ctypes.c_int16,
    "uint16": ctypes.c_uint16,
    "int32": ctypes.c_int32,
    "uint32": ctypes.c_uint32,
    "int64": ctypes.c_int64,
    "uint64": ctypes.c_uint64,
    "size_t": ctypes.c_size_t,
    "ssize_t": ctypes.c_ssize_t,
    "float": ctypes.c_float,
    "double": ctypes.c_double,
    "string": ctypes.c_char_p,
    "wstring": ctypes.c_wchar_p,
    "pointer": ctypes.c_void_p,
}


# --- marshalling ---------------------------------------------------------

def _to_c(value):
    """JS value -> something ctypes accepts as an argument."""
    if isinstance(value, Buffer):
        return value._buf
    if isinstance(value, CFunc):
        return value._ptr
    if isinstance(value, str):
        return value.encode("utf-8")
    if isinstance(value, bool):
        return value
    if isinstance(value, float) and value.is_integer():
        return int(value)
    return value


def _from_c(value):
    """ctypes return value -> JS-friendly value."""
    if isinstance(value, bytes):
        return value.decode("utf-8", "replace")
    return value


# --- library / function proxies ---------------------------------------------

class CFunc:
    """A single C function. ``argtypes`` / ``restype`` accept ``ffi.types`` and
    are forwarded to the underlying ctypes pointer."""

    def __init__(self, ptr, name):
        object.__setattr__(self, "_ptr", ptr)
        object.__setattr__(self, "_name", name)

    def __call__(self, *args):
        try:
            return _from_c(self._ptr(*[_to_c(a) for a in args]))
        except Exception as exc:  # surfaced to JS as a thrown error
            raise RuntimeError(f"ffi call {self._name}(): {exc}") from exc

    def __setattr__(self, key, value):
        if key == "argtypes":
            self._ptr.argtypes = [t for t in value if t is not None] or None
        elif key == "restype":
            self._ptr.restype = value
        elif key == "errcheck":
            self._ptr.errcheck = value
        else:
            object.__setattr__(self, key, value)

    def __getattr__(self, key):
        if key.startswith("__") and key.endswith("__"):
            raise AttributeError(key)
        return getattr(object.__getattribute__(self, "_ptr"), key)

    def __repr__(self):
        return f"<ffi function {self._name}>"


def _resolve_type(t):
    """A ctypes type from ``ffi.types`` (already correct), or a plain type
    name string (``"double"``, ``"int"``, ``"string"``, ...) for `.fn()`."""
    if isinstance(t, str):
        if t not in TYPES:
            raise ValueError(f"ffi: unknown type {t!r} (see ffi.types for the full list)")
        return TYPES[t]
    return t


class Library:
    """A loaded shared library. ``lib.<name>`` resolves a :class:`CFunc`."""

    def __init__(self, cdll, name):
        object.__setattr__(self, "_cdll", cdll)
        object.__setattr__(self, "_name", name)
        object.__setattr__(self, "_cache", {})

    def __getattr__(self, key):
        if key.startswith("__") and key.endswith("__"):
            raise AttributeError(key)
        cache = object.__getattribute__(self, "_cache")
        if key not in cache:
            try:
                cache[key] = CFunc(getattr(self._cdll, key), key)
            except AttributeError:
                raise AttributeError(f"{self._name!r} has no symbol {key!r}")
        return cache[key]

    def fn(self, name, restype=None, argtypes=None):
        """Resolve ``name`` and set its ``restype`` / ``argtypes`` in one call
        -- either as ``ffi.types.x`` or a plain string, matching the two- or
        three-statement form this replaces::

            const tgamma = libm.fn("tgamma", "double", ["double"]);
            tgamma(11);

            // equivalent to:
            libm.tgamma.argtypes = [ffi.types.double];
            libm.tgamma.restype = ffi.types.double;
            libm.tgamma(11);

        There's no way to *infer* these from the call site: a whole-number
        JS value (``11``) can't tell you whether the C function wants an
        ``int`` or a ``double`` -- that's an ABI fact about the function, not
        the argument, so it still has to be declared once, just not verbosely.
        """
        f = getattr(self, name)
        if argtypes is not None:
            f.argtypes = [_resolve_type(t) for t in argtypes]
        if restype is not None:
            f.restype = _resolve_type(restype)
        return f

    def __repr__(self):
        return f"<ffi library {self._name!r}>"


class Buffer:
    """A mutable C string / byte buffer (``ffi.createStringBuffer``)."""

    def __init__(self, buf):
        object.__setattr__(self, "_buf", buf)

    @property
    def value(self):
        return self._buf.value.decode("utf-8", "replace")

    @value.setter
    def value(self, v):
        self._buf.value = v.encode("utf-8") if isinstance(v, str) else v

    @property
    def raw(self):
        return self._buf.raw

    @property
    def length(self):
        return len(self._buf)

    def __len__(self):
        return len(self._buf)

    def __repr__(self):
        return f"<ffi buffer {self.value!r}>"


# --- loading -----------------------------------------------------------------

# Windows has no "libc"/"libm" .dll to find_library() -- the C runtime (and
# libm's functions) live in msvcrt instead, so "c"/"m" need a direct alias.
_WIN32_ALIASES = {"c": "msvcrt", "m": "msvcrt"}


def load_library(name):
    """Load a shared library by short name (``"c"``, ``"m"``), by path
    (``"./libfoo.so"``), or -- on macOS -- by system-framework name
    (``"CoreFoundation"``). ``"c"`` / ``"m"`` resolve to the right thing on
    every platform: ``libc.so.6`` (Linux), ``libSystem.dylib`` (macOS), or
    ``msvcrt`` (Windows) -- see also the ``ffi.libc()`` / ``ffi.libm()``
    shorthands below."""
    if os.sep in str(name) or str(name).endswith((".so", ".dylib", ".dll")):
        return Library(ctypes.CDLL(name), name)
    if sys.platform == "win32" and str(name) in _WIN32_ALIASES:
        return Library(ctypes.CDLL(_WIN32_ALIASES[str(name)]), name)
    found = ctypes.util.find_library(name)
    if found:
        return Library(ctypes.CDLL(found), name)
    if sys.platform == "darwin":
        fw = f"/System/Library/Frameworks/{name}.framework/{name}"
        if os.path.exists(fw):
            return Library(ctypes.CDLL(fw), name)
    return Library(ctypes.CDLL(name), name)  # let ctypes raise a clear OSError


def create_string_buffer(init):
    if isinstance(init, str):
        return Buffer(ctypes.create_string_buffer(init.encode("utf-8")))
    if isinstance(init, (int, float)):
        return Buffer(ctypes.create_string_buffer(int(init)))
    if isinstance(init, (bytes, bytearray)):
        return Buffer(ctypes.create_string_buffer(bytes(init)))
    raise TypeError("createStringBuffer expects a string or a size")


def make_callback(restype, argtypes, fn):
    """Wrap a JS function as a C callback pointer (``CFUNCTYPE``)."""
    proto = ctypes.CFUNCTYPE(restype, *[t for t in (argtypes or []) if t is not None])

    def thunk(*c_args):
        return _to_c(fn(*[_from_c(a) for a in c_args]))

    holder = proto(thunk)
    _CALLBACK_KEEPALIVE.append(holder)  # ctypes callbacks must outlive the call
    return holder


_CALLBACK_KEEPALIVE = []


def c_string(ptr):
    """Read a NUL-terminated C string at ``ptr`` (an int address or c_char_p)."""
    return ctypes.cast(ptr, ctypes.c_char_p).value.decode("utf-8", "replace")


# --- the scope handed to the interpreter -----------------------------------

FFI = {
    "loadLibrary": load_library,
    "libc": lambda: load_library("c"),   # the standard C library, whatever it's called here
    "libm": lambda: load_library("m"),   # math functions -- folded into libc on Windows already
    "createStringBuffer": create_string_buffer,
    "callback": make_callback,
    "string": c_string,
    "sizeof": lambda t: ctypes.sizeof(t),
    "addressof": lambda b: ctypes.addressof(b._buf if isinstance(b, Buffer) else b),
    "cast": lambda v, t: ctypes.cast(_to_c(v), t),
    "pointer": ctypes.pointer,
    "byref": ctypes.byref,
    "NULL": None,
    "errno": lambda: ctypes.get_errno(),
    "types": dict(TYPES),
}

def scope():
    """Fresh copies so one session cannot mutate another's ``ffi.types``."""
    return {"ffi": {**FFI, "types": dict(TYPES)}}
