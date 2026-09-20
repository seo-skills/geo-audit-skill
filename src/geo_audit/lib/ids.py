"""Run identifiers.

ULIDs rather than UUID4: they sort lexicographically by creation time, so
`sort -u` over audits.jsonl is chronological and a run id is legible at a
glance. 48 bits of millisecond timestamp, 80 bits of randomness, Crockford
base32.
"""

from __future__ import annotations

import os
import time

_ALPHABET = "0123456789ABCDEFGHJKMNPQRSTVWXYZ"  # Crockford: no I, L, O, U


def _encode(value: int, length: int) -> str:
    out = []
    for _ in range(length):
        value, rem = divmod(value, 32)
        out.append(_ALPHABET[rem])
    return "".join(reversed(out))


def new_run_id(now_ms: int | None = None) -> str:
    ts = int(time.time() * 1000) if now_ms is None else now_ms
    rand = int.from_bytes(os.urandom(10), "big")
    return _encode(ts, 10) + _encode(rand, 16)


def is_run_id(value: str) -> bool:
    return len(value) == 26 and all(c in _ALPHABET for c in value)
