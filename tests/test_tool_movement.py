"""A tool change must never read as a site change.

Three defects found by reviewing the plan that proposed to build on them, each
reproduced before it was fixed:

- `comparable` collected `normalizer_version` and never compared it, so
  normalizer 3 - which stopped reading a promo banner as the page and took
  userguiding.com from 42 to 61 - would have been reported as the site gaining
  nineteen points.
- The page-level finding pass handed `findings_for` one signal at a time, so
  the `consequences` rule had no cause to suppress from and a page with no
  structured data was told four more times that its structured data was
  incomplete.
"""

from __future__ import annotations

import pytest

from geo_audit import data
from geo_audit.commands.audit import _classify, _what_is_recorded
from geo_audit.commands.compare import comparable

BASE = {"scoring_version": "4.0", "data_version": "2026.09", "normalizer_version": 2}


def _with(**changes) -> dict:
    return {**BASE, **changes}


# --- the comparison gate -----------------------------------------------------

@pytest.mark.parametrize("changed, expected", [
    ({"normalizer_version": 3}, "normalizer_version"),
    ({"data_version": "2026.10"}, "data_version"),
    ({"scoring_version": "5.0"}, "scoring_version"),
])
def test_every_version_axis_that_moves_a_score_refuses_the_comparison(changed, expected):
    ok, reason = comparable(BASE, _with(**changed))
    assert ok is False
    assert expected in reason


def test_a_scoring_minor_still_compares():
    """Documented behaviour the gate has to keep allowing: only the major is a
    formula change."""
    assert comparable(BASE, _with(scoring_version="4.1")) == (True, None)


def test_two_runs_of_the_same_build_compare():
    assert comparable(BASE, dict(BASE)) == (True, None)


# --- suppression through the page-level pass ---------------------------------

def _snapshot(**ratios) -> dict:
    return {"pages": ["https://example.com/post"], "ratios": {k: [v] for k, v in ratios.items()}}


def test_a_cause_at_its_floor_explains_its_consequences_on_that_page():
    _, severe, explained = _classify(
        _snapshot(**{"schema.presence": 0.0, "schema.organization": 0.0, "schema.article": 0.0}),
        data.thresholds("findings"),
    )
    assert "schema.organization" in severe, "the consequence is severe on the page"
    for consequence in ("schema.validity", "schema.organization", "schema.article", "schema.breadth"):
        assert explained[consequence] == {"https://example.com/post"}


def test_a_healthy_cause_explains_nothing():
    _, severe, explained = _classify(
        _snapshot(**{"schema.presence": 1.0, "schema.organization": 0.0}),
        data.thresholds("findings"),
    )
    assert "schema.organization" in severe
    assert explained == {}, "incomplete markup is still worth reporting when markup exists"


def test_the_consequences_rule_still_names_what_it_did():
    """Guards the join between this test and the data file."""
    rule = data.load("findings")["consequences"]["schema.presence"]
    assert rule["floor"] == 0
    assert set(rule["suppresses"]) == {
        "schema.validity", "schema.organization", "schema.article", "schema.breadth"
    }


# --- the hint names something that exists ------------------------------------

def test_the_missing_run_hint_names_no_command(geo_home):
    """It used to say "`geo audit --list` shows what is recorded", and the
    parser answers that with `unrecognized arguments` and exit 2."""
    assert "--list" not in _what_is_recorded(None)
    assert "`geo" not in _what_is_recorded(None)
