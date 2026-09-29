"""A brand written with punctuation is still removed from its category.

The name reaches the category sanitizer after `sanitize_brand`, which turns
"Yes/No Apps" into "Yes No Apps"; the engine writes the category with the
brand's own punctuation, "Yes/No Apps survey tool", so the name was never found
and every engine was asked for "the best yes/no apps survey tool brands", a
question that names the brand it is meant to leave out.
"""

# Regression: ISSUE-001 - a brand with punctuation stayed in the unbranded question
# Found by /qa on 2026-09-29
# Report: ~/.gstack/projects/seo-skills-geo-audit-skill/qa-reports/qa-report-geo-cli-descriptive-brand-2026-09-29.md

from __future__ import annotations

import pytest

from geo_audit.assistants import sanitize_brand, sanitize_category


@pytest.mark.parametrize(("brand", "raw", "category"), [
    ("Yes/No Apps", "Yes/No Apps survey tool", "survey tool"),
    ("AT&T", "AT&T telecom provider", "telecom provider"),
    ("C++ Builder", "C++ Builder IDE for Windows", "IDE for windows"),
    ("Acme Inc.", "Acme, Inc. CRM software", "CRM software"),
])
def test_the_brand_is_found_whatever_punctuation_joins_its_words(brand, raw, category):
    assert sanitize_category(raw, sanitize_brand(brand, None), None) == category


def test_a_descriptive_brand_still_keeps_its_category_whole():
    assert sanitize_category("Dynamic QR code generator", "QR Code Dynamic", "qrcodedynamic.com") == (
        "dynamic QR code generator"
    )
