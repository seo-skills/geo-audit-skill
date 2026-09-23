"""A finding says "incomplete" when the typical page has some of the markup.

`findings.json` carries a partial variant for the signals that can be half
present, and `findings_for` picks it from the scorer's `present` list. At site
level that list first has to survive `aggregate`, which keeps only what every
page agreed on. Two pages of fifty without Organization markup dropped it, and
userguiding.com - name, url and sameAs on 48 pages - was told "No
machine-readable publisher identity".
"""

from __future__ import annotations

from geo_audit import data
from geo_audit.scoring.model import Signal, aggregate, findings_for

ABSENT = data.load("findings")["signals"]["schema.organization"]["title"]
PARTIAL = data.load("findings")["signals"]["schema.organization"]["partial"]["title"]


def _page(present: list[str], value: float) -> list[Signal]:
    return [Signal(id="schema.organization", cls="deterministic", max=20, value=value,
                   detail={"present": present}, page="https://example.com/p")]


def _title(pages: list[list[Signal]]) -> str:
    findings = findings_for(aggregate(pages), "https://example.com")
    assert len(findings) == 1, "the signal scores low enough to report"
    return findings[0].title


def test_a_couple_of_bare_pages_do_not_speak_for_the_site():
    has = _page(["name", "url", "sameAs"], 14.0)
    assert _title([has] * 48 + [_page([], 0.0)] * 2) == PARTIAL


def test_a_site_with_none_of_it_still_says_so():
    assert _title([_page([], 0.0)] * 50) == ABSENT


def test_one_page_carrying_it_does_not_speak_for_the_site_either():
    pages = [_page(["name", "url", "sameAs"], 14.0)] + [_page([], 0.0)] * 49
    assert _title(pages) == ABSENT


def test_unanimity_still_reads_the_same_as_before():
    assert _title([_page(["name", "url", "sameAs"], 14.0)] * 50) == PARTIAL
