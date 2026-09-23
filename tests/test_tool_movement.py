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


# --- suppression end to end --------------------------------------------------

def test_a_bare_page_is_not_also_told_its_markup_is_incomplete(serve, geo_home):
    """The window the unit test above describes, driven through `audit`.

    It needs a consequence the site is *not* reported for site-wide - so the
    first pass stays quiet and the page-level pass runs - on pages where the
    cause is at its floor. userguiding.com does not exercise it: its structured
    data averages 0.72 of the maximum, so `schema.organization` is reported
    site-wide and never reaches the second pass at all.
    """
    import io
    import json

    from geo_audit.cli import main
    from tests.fixture_server import Reply

    prose = "<p>" + ("A sentence with enough words in it to count as prose. " * 6) + "</p>"
    good = (
        '<html><head><title>Page</title><script type="application/ld+json">'
        '{"@context":"https://schema.org","@type":"Organization","name":"Acme",'
        '"url":"https://acme.example","logo":"https://acme.example/l.png",'
        '"description":"We make things.","sameAs":["https://x.com/acme"]}'
        f"</script></head><body><main><h1>Page</h1>{prose}</main></body></html>"
    )
    bare = f"<html><head><title>Bare</title></head><body><main><h1>Bare</h1>{prose}</main></body></html>"

    marked = [f"/p-{n}" for n in range(8)]
    links = "".join(f'<a href="{p}">{p}</a>' for p in [*marked, "/bare-1", "/bare-2"])
    routes = {
        # The links live inside <main>: the normalizer reads links from the
        # content root, so anchors outside it are never followed.
        "/": Reply(body=good.replace("<h1>Page</h1>", f"<h1>Home</h1>{links}")),
        "/robots.txt": Reply(body="User-agent: *\nAllow: /\n", content_type="text/plain"),
        "/bare-1": Reply(body=bare),
        "/bare-2": Reply(body=bare),
    }
    routes.update({p: Reply(body=good) for p in marked})
    site = serve(routes)

    buffer = io.StringIO()
    main(["audit", f"{site.url}/", "--allow-private", "--rate", "50", "--json", "--quiet"], out=buffer)
    findings = {f["id"]: f for f in json.loads(buffer.getvalue())["findings"]}

    bare_pages = {f"{site.url}/bare-1", f"{site.url}/bare-2"}
    presence = findings.get("schema.presence")
    assert presence and bare_pages <= set(presence["pages"]), "the bare pages are reported as bare"

    # Only the page-level pass is at issue. A consequence the whole site earns
    # is reported site-wide with its offenders listed, and suppression there
    # already worked: it is decided from the site's own presence value.
    for consequence in ("schema.validity", "schema.organization", "schema.article", "schema.breadth"):
        finding = findings.get(consequence)
        if not finding or not finding["page_level"]:
            continue
        assert not (set(finding["pages"]) & bare_pages), (
            f"{consequence} is named on a page that carries no structured data at all"
        )
