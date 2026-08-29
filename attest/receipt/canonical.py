"""JSON Canonicalization Scheme (RFC 8785), as much of it as this project needs.

Why this exists at all: a signature is over bytes, but a receipt is a document.
Without an agreed byte rendering, two honest parties can disagree about whether a
valid receipt is valid — and a validator must never see that. So verification
**recomputes the canonical form from the parsed document** and never trusts the
bytes on disk (LLD §4.1).

Scope: the value types receipts actually contain — object, array, string, number,
bool, null. Numbers are restricted further, see :func:`_number`.
"""

from __future__ import annotations

import json
import math
import re
from typing import Any

_ESCAPES = {
    '"': '\\"',
    "\\": "\\\\",
    "\b": "\\b",
    "\f": "\\f",
    "\n": "\\n",
    "\r": "\\r",
    "\t": "\\t",
}


class CanonicalizationError(ValueError):
    """A value that cannot be canonicalised deterministically."""


def _string(value: str) -> str:
    out = ['"']
    for ch in value:
        if ch in _ESCAPES:
            out.append(_ESCAPES[ch])
        elif ord(ch) < 0x20:
            out.append(f"\\u{ord(ch):04x}")
        else:
            out.append(ch)
    out.append('"')
    return "".join(out)


def _number(value: int | float) -> str:
    """Serialise a number the way ECMAScript ``JSON.stringify`` would.

    NaN and infinities are refused rather than coerced: a receipt field that
    cannot round-trip is not evidence of anything.
    """
    if isinstance(value, bool):  # bool is an int subclass — guard before int
        raise CanonicalizationError("bool reached the number path")
    if isinstance(value, int):
        return str(value)
    if math.isnan(value) or math.isinf(value):
        raise CanonicalizationError(f"non-finite number cannot be canonicalised: {value!r}")
    if value == int(value) and abs(value) < 1e21:
        # ES6 prints integral doubles without a fractional part: 1.0 -> "1"
        return str(int(value))
    text = repr(value)  # shortest round-trip, matches ES6 for the non-exponent range
    # Normalise Python's exponent spelling ("1e-05") to ES6's ("1e-5").
    return re.sub(r"e([+-])0*(\d)", r"e\1\2", text)


def canonicalize(value: Any) -> str:
    """Return the RFC 8785 canonical JSON text for *value*."""
    if value is None:
        return "null"
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, (int, float)):
        return _number(value)
    if isinstance(value, str):
        return _string(value)
    if isinstance(value, (list, tuple)):
        return "[" + ",".join(canonicalize(v) for v in value) + "]"
    if isinstance(value, dict):
        for key in value:
            if not isinstance(key, str):
                raise CanonicalizationError(f"object keys must be strings, got {type(key)!r}")
        # RFC 8785 sorts by UTF-16 code units, which is what encoding to
        # UTF-16-BE and comparing bytes gives us.
        items = sorted(value.items(), key=lambda kv: kv[0].encode("utf-16-be"))
        return "{" + ",".join(f"{_string(k)}:{canonicalize(v)}" for k, v in items) + "}"
    raise CanonicalizationError(f"cannot canonicalise value of type {type(value)!r}")


def canonical_bytes(value: Any) -> bytes:
    """UTF-8 bytes of the canonical form — the exact bytes that get signed."""
    return canonicalize(value).encode("utf-8")


def recanonicalize(raw: str | bytes) -> bytes:
    """Parse *raw* and re-emit it canonically.

    Always prefer this over hashing bytes read from disk: it is what makes a
    signature check independent of how the file happened to be formatted.
    """
    if isinstance(raw, bytes):
        raw = raw.decode("utf-8")
    return canonical_bytes(json.loads(raw))
