"""A brand inside a hyphenated compound takes the compound with it.

Removing the brand as a whole name left "Notion-style note-taking app" as
"-style note-taking app", and every engine was asked for the best "-style
note-taking app" brands. A compound built on the brand describes the brand, so
it goes with the name.
"""

# Regression: ISSUE-003 - a hyphenated brand compound left "-style" in the category question
# Found by /qa on 2026-09-29
# Report: ~/.gstack/projects/seo-skills-geo-audit-skill/qa-reports/qa-report-geo-cli-descriptive-brand-2026-09-29.md

from __future__ import annotations

import pytest

from geo_audit.assistants import sanitize_category


@pytest.mark.parametrize(("brand", "raw", "category"), [
    ("Notion", "Notion-style note-taking app", "note-taking app"),
    ("Acme", "Acme-powered popup builder", "popup builder"),
    ("Acme", "AI-Acme chatbot platform", "chatbot platform"),
])
def test_a_compound_built_on_the_brand_is_removed_with_it(brand, raw, category):
    assert sanitize_category(raw, brand, None) == category


def test_hyphenated_category_words_without_the_brand_are_kept():
    assert sanitize_category("Acme e-commerce marketplace", "Acme", None) == "e-commerce marketplace"
