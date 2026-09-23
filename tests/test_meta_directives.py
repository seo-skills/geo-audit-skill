"""A second robots tag is not discarded.

`_collect_meta` kept the first value for a repeated key, so
`<meta robots="index">` before `<meta robots="noindex">` read as indexable and
the noindex vanished. Found while specifying a `nosnippet` check that would
have inherited the same gap. A page carrying repeated robots tags can score
differently now, which is why this ships with the scoring bump.
"""

from __future__ import annotations

import pytest

from geo_audit.lib.extract import extract


# --- repeated meta directives ------------------------------------------------

def _robots(*tags: str) -> str | None:
    head = "".join(f'<meta name="robots" content="{t}">' for t in tags)
    return extract(f"<html><head>{head}</head><body><p>x</p></body></html>", "https://x").meta.get("robots")


@pytest.mark.parametrize("tags", [("index", "noindex"), ("noindex", "index")])
def test_a_repeated_robots_directive_survives_in_either_order(tags):
    value = _robots(*tags)
    assert "noindex" in value and "index" in value


def test_one_robots_tag_is_left_exactly_as_written():
    assert _robots("noindex, nofollow") == "noindex, nofollow"


def test_a_repeated_single_valued_key_still_keeps_the_first():
    """Only directive keys add up; a second description does not append to the
    first."""
    doc = extract(
        '<html><head><meta name="description" content="first">'
        '<meta name="description" content="second"></head><body><p>x</p></body></html>',
        "https://x",
    )
    assert doc.meta["description"] == "first"
