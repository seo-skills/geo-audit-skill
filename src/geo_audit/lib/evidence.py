"""Evidence identity.

The hash covers the scorer's real inputs — the extracted content-block
sequence — plus `normalizer_version`. It deliberately does not cover ETag or
Last-Modified: those change on every redeploy even when the content is
identical, and flipping a client's report to STALE because someone rebuilt the
site is the exact noise block-hashing exists to remove. They are kept as
metadata and used only as a revalidation shortcut.
"""

from __future__ import annotations

import hashlib
from collections.abc import Iterable

from geo_audit._version import NORMALIZER_VERSION
from geo_audit.lib.extract import Block

CURRENT = "CURRENT"
PARTIAL = "PARTIAL"
STALE = "STALE"

_UNIT = "\x1f"
_RECORD = "\x1e"


def digest(blocks: Iterable[Block], normalizer_version: int = NORMALIZER_VERSION) -> str:
    payload = [f"normalizer_version{_UNIT}{normalizer_version}"]
    payload.extend(f"{b.kind}{_UNIT}{b.text}" for b in blocks)
    joined = _RECORD.join(payload).encode("utf-8")
    return hashlib.sha256(joined).hexdigest()


def short(full_digest: str) -> str:
    return full_digest[:8]


def revalidation_headers(etag: str | None, last_modified: str | None) -> dict[str, str]:
    out: dict[str, str] = {}
    if etag:
        out["If-None-Match"] = etag
    if last_modified:
        out["If-Modified-Since"] = last_modified
    return out


def stamp_for(pages_ok: int, pages_failed: list[dict], changed: int = 0) -> str:
    if changed:
        return STALE
    if pages_failed:
        return PARTIAL
    if pages_ok == 0:
        return PARTIAL
    return CURRENT
