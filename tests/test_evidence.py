"""Hash identity: what must change the hash, and what must not."""

from __future__ import annotations

from pathlib import Path

from geo_audit.lib import evidence
from geo_audit.lib.extract import extract

FIXTURES = Path(__file__).parent / "fixtures" / "site"
URL = "https://example.com/page"


def digest_of(name: str) -> str:
    return evidence.digest(extract((FIXTURES / name).read_text(encoding="utf-8"), URL).blocks)


def test_nonce_timestamp_and_ad_rotation_do_not_move_the_hash():
    """The golden this whole design exists for.

    ssr-rich-variant.html differs from ssr-rich.html in its CSP nonce, its
    "generated at" footer timestamp and the entire body of its ad slot.
    """
    assert digest_of("ssr-rich.html") == digest_of("ssr-rich-variant.html")


def test_different_content_changes_the_hash():
    assert digest_of("ssr-rich.html") != digest_of("schema-none.html")


def test_hash_is_stable_across_calls():
    assert digest_of("ssr-rich.html") == digest_of("ssr-rich.html")


def test_normalizer_version_is_part_of_hash_identity():
    blocks = extract((FIXTURES / "ssr-rich.html").read_text(encoding="utf-8"), URL).blocks
    assert evidence.digest(blocks, 1) != evidence.digest(blocks, 2)


def test_block_order_matters():
    a = extract("<main><p>One.</p><p>Two.</p></main>", URL).blocks
    b = extract("<main><p>Two.</p><p>One.</p></main>", URL).blocks
    assert evidence.digest(a) != evidence.digest(b)


def test_block_kind_matters():
    a = extract("<main><p>Same text.</p></main>", URL).blocks
    b = extract("<main><blockquote>Same text.</blockquote></main>", URL).blocks
    assert evidence.digest(a) != evidence.digest(b)


def test_etag_is_not_part_of_identity_only_a_revalidation_shortcut():
    headers = evidence.revalidation_headers("W/\"abc\"", "Wed, 21 Oct 2026 07:28:00 GMT")
    assert headers == {
        "If-None-Match": 'W/"abc"',
        "If-Modified-Since": "Wed, 21 Oct 2026 07:28:00 GMT",
    }


def test_stamps():
    assert evidence.stamp_for(1, []) == evidence.CURRENT
    assert evidence.stamp_for(1, [{"url": "x", "reason": "bot_blocked"}]) == evidence.PARTIAL
    assert evidence.stamp_for(0, []) == evidence.PARTIAL
    assert evidence.stamp_for(5, [], changed=1) == evidence.STALE
