"""A brand in the possessive leaves nothing of itself in the category.

ChatGPT can answer the category line as "Popupsmart's popup builder". The brand
was removed and its "'s" left behind, so every engine was asked, at 25 credits a
call, for "the best s popup builder brands".
"""

# Regression: ISSUE-002 - a possessive brand left a stray "s" in the category question
# Found by /qa on 2026-09-29
# Report: ~/.gstack/projects/seo-skills-geo-audit-skill/qa-reports/qa-report-geo-cli-descriptive-brand-2026-09-29.md

from __future__ import annotations

import pytest

from geo_audit.assistants import sanitize_category


@pytest.mark.parametrize(("brand", "site", "raw", "category"), [
    ("Popupsmart", "popupsmart.com", "Popupsmart's popup builder", "popup builder"),
    ("Popupsmart", "popupsmart.com", "Popupsmart’s popup builder", "popup builder"),
    ("The Browser Company", None, "The Browser Company's Arc browser", "arc browser"),
])
def test_a_possessive_brand_is_removed_with_its_apostrophe_s(brand, site, raw, category):
    assert sanitize_category(raw, brand, site) == category


def test_a_word_that_merely_ends_in_s_after_the_brand_is_kept():
    assert sanitize_category("Acme sales CRM", "Acme", None) == "sales CRM"
