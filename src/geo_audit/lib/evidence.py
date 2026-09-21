"""Evidence identity.

The hash covers the scorer's real inputs — the extracted content-block
sequence — plus `normalizer_version`. It deliberately does not cover ETag or
Last-Modified: those change on every redeploy even when the content is
identical, and flipping a client's report to STALE because someone rebuilt the
site is the exact noise block-hashing exists to remove. They are kept as
metadata. They are not a revalidation shortcut either: a 304 vouches for a
page's bytes, not its headers, and an audit scores headers too.
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


def site_digest(
    page_digests: Iterable[str], normalizer_version: int = NORMALIZER_VERSION
) -> str:
    """One hash over a set of page hashes.

    Sorted, so two crawls that visit the same pages in a different order -
    which concurrency makes routine - produce the same site hash.
    """
    payload = [f"normalizer_version{_UNIT}{normalizer_version}"]
    payload.extend(sorted(page_digests))
    return hashlib.sha256(_RECORD.join(payload).encode("utf-8")).hexdigest()


def short(full_digest: str) -> str:
    return full_digest[:8]


def stamp_for(pages_ok: int, pages_failed: list[dict], changed: int = 0) -> str:
    if changed:
        return STALE
    if pages_failed:
        return PARTIAL
    if pages_ok == 0:
        return PARTIAL
    return CURRENT
