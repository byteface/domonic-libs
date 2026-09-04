# Ported from acornjs/acorn (MIT), tag acorn@8.18.0. Mirrors src/options.js
# (the ``getOptions`` half -- comment / token push helpers are dropped).
"""Option defaulting for the tokenizer."""

from __future__ import annotations

from .util import hasOwn, isArray

defaultOptions = {
    "ecmaVersion": None,
    "sourceType": "script",
    "ranges": False,
    "program": None,
    "sourceFile": None,
    "directSourceFile": None,
    "preserveParens": False,
    "locations": False,
    "onToken": None,
    "onComment": None,
    "allowReserved": None,
    "allowHashBang": None,
    "allowReturnOutsideFunction": False,
    "allowImportExportEverywhere": False,
    "allowAwaitOutsideFunction": None,
    "allowSuperOutsideMethod": None,
    "checkPrivateFields": True,
    "preserveParens": False,
    "strict": None,
    "startLocation": None,
}


def getOptions(opts):
    opts = opts or {}
    options = {}
    for opt in defaultOptions:
        options[opt] = opts[opt] if hasOwn(opts, opt) else defaultOptions[opt]

    if options["ecmaVersion"] == "latest":
        options["ecmaVersion"] = 100000000
    elif options["ecmaVersion"] is None:
        options["ecmaVersion"] = 11
    elif options["ecmaVersion"] >= 2015:
        options["ecmaVersion"] -= 2009

    if options["allowReserved"] is None:
        options["allowReserved"] = options["ecmaVersion"] < 5

    if opts.get("allowHashBang") is None:
        options["allowHashBang"] = options["ecmaVersion"] >= 14

    if isArray(options["onToken"]):
        tokens = options["onToken"]
        options["onToken"] = lambda token: tokens.append(token)

    return options
