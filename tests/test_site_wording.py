"""A site's verdict is not worded for one page.

The tier meanings in `data/tiers.json` are written for the single page `geo
score` reads, and a fifty-page audit of seomator.com led its client report and
its terminal output with "AI engines can lift answers from this page with almost
no rewriting." An audit of more than one page now says it of those pages.
"""

from __future__ import annotations

import io
import json
import re

import pytest

from geo_audit import data
from geo_audit.cli import main
from geo_audit.commands.audit import _said_of_pages

SINGULAR = re.compile(r"\b(this|the) page\b", re.IGNORECASE)
MEANINGS = {tier["label"]: tier["meaning"] for tier in data.load("tiers")["tiers"]}


@pytest.mark.parametrize("label", sorted(MEANINGS))
def test_no_tier_is_said_of_one_page_when_there_are_several(label):
    assert not SINGULAR.search(_said_of_pages(MEANINGS[label]))


def _audit(site, max_pages: int) -> dict:
    buffer = io.StringIO()
    main(["audit", f"{site.url}/hub.html", "--allow-private", "--rate", "50", "--max-pages", str(max_pages),
          "--json", "--quiet"], out=buffer)
    return json.loads(buffer.getvalue())


def test_a_multi_page_audit_speaks_of_its_pages(site, geo_home):
    envelope = _audit(site, 6)
    assert envelope["evidence"]["pages_ok"] > 1
    scores = envelope["scores"]
    assert scores["tier_meaning"] == _said_of_pages(MEANINGS[scores["tier"]])


def test_a_one_page_audit_keeps_the_meaning_as_written(site, geo_home):
    envelope = _audit(site, 1)
    assert envelope["evidence"]["pages_ok"] == 1
    assert envelope["scores"]["tier_meaning"] == MEANINGS[envelope["scores"]["tier"]]
