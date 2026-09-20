"""The platform category, and the no-double-counting rule that shaped it."""

from __future__ import annotations

import io
import json

import pytest

from geo_audit import data
from geo_audit.cli import main
from geo_audit.lib.extract import extract
from geo_audit.scoring import platform as platform_scorer
from tests.fixture_server import Reply

URL = "https://example.com/page"
BASE = ["--allow-private", "--rate", "50", "--max-pages", "20"]


def run(args):
    buffer = io.StringIO()
    code = main(args + ["--json", "--quiet"], out=buffer)
    return code, json.loads(buffer.getvalue())


def doc_of(html: str):
    return extract(html, URL)


# --- no double counting ----------------------------------------------------


def test_no_signal_id_is_declared_in_two_categories():
    seen: dict[str, str] = {}
    for name, category in data.weights().items():
        for signal_id in category["signals"]:
            assert signal_id not in seen, f"{signal_id} is in both {seen.get(signal_id)} and {name}"
            seen[signal_id] = name


def test_platform_does_not_rescore_crawler_access_or_answer_types():
    """Those belong to technical and schema. One fact, one place."""
    platform_signals = set(data.weights()["platform"]["signals"])
    assert not any("crawler" in signal_id for signal_id in platform_signals)
    assert not any("schema" in signal_id for signal_id in platform_signals)


def test_open_graph_is_scored_by_platform_and_nowhere_else(site, geo_home):
    _, envelope = run(["audit", f"{site.url}/hub.html", *BASE])
    details = {signal["id"]: signal["detail"] for signal in envelope["signals"]}
    assert "open_graph_present" in details["platform.social_cards"]
    assert "open_graph" not in (details["technical.metadata"].get("breakdown") or {})


# --- the signals -----------------------------------------------------------


@pytest.mark.parametrize(
    "present,valid,expected",
    [(None, None, None), (False, None, 0.0), (True, False, 20.0), (True, True, 35.0)],
)
def test_llms_txt_scoring(present, valid, expected):
    points, _ = platform_scorer.llms_txt(present, valid)
    assert points == expected


def test_a_present_but_malformed_llms_txt_gets_partial_credit():
    points, detail = platform_scorer.llms_txt(True, False)
    assert 0 < points < 35
    assert "not in the documented structure" in detail["note"]


def test_social_cards_scale_with_the_tags_present():
    none = doc_of("<html><head><title>x</title></head><body><main><p>x</p></main></body></html>")
    partial = doc_of('<html><head><meta property="og:title" content="t"></head><body><main><p>x</p></main></body></html>')
    full = doc_of(
        '<html><head><meta property="og:title" content="t">'
        '<meta property="og:description" content="d">'
        '<meta property="og:image" content="/i.png"></head>'
        "<body><main><p>x</p></main></body></html>"
    )
    assert platform_scorer.social_cards(none)[0] == 0.0
    assert 0 < platform_scorer.social_cards(partial)[0] < 24
    assert platform_scorer.social_cards(full)[0] == 24.0


def test_twitter_tags_add_on_top_rather_than_replacing():
    both = doc_of(
        '<html><head><meta property="og:title" content="t">'
        '<meta property="og:description" content="d">'
        '<meta property="og:image" content="/i.png">'
        '<meta name="twitter:card" content="summary"></head>'
        "<body><main><p>x</p></main></body></html>"
    )
    assert platform_scorer.social_cards(both)[0] == 30.0


def test_feeds_weights_the_sitemap_above_the_feed():
    nothing = platform_scorer.feeds("<html></html>", [])
    sitemap_only = platform_scorer.feeds("<html></html>", ["https://x.test/sitemap.xml"])
    both = platform_scorer.feeds(
        '<html><head><link rel="alternate" type="application/rss+xml" href="/f"></head></html>',
        ["https://x.test/sitemap.xml"],
    )
    assert nothing[0] == 0.0
    assert sitemap_only[0] == 14.0
    assert both[0] == 20.0


def test_hreflang_does_not_apply_to_a_single_language_site():
    """Marking a site down for a problem it cannot have is worse than silence."""
    doc = doc_of('<html lang="en"><body><main><p>x</p></main></body></html>')
    points, detail = platform_scorer.hreflang(doc, "<html></html>", {"en"})
    assert points is None
    assert "does not apply" in detail["reason"]


def test_hreflang_is_scored_once_a_second_language_appears():
    doc = doc_of('<html lang="en"><body><main><p>x</p></main></body></html>')
    points, detail = platform_scorer.hreflang(doc, "<html></html>", {"en", "fr"})
    assert points == 0.0
    assert detail["languages_seen"] == ["en", "fr"]


def test_hreflang_rewards_an_x_default():
    html = (
        '<link rel="alternate" hreflang="en" href="/en">'
        '<link rel="alternate" hreflang="fr" href="/fr">'
    )
    doc = doc_of('<html lang="en"><body><main><p>x</p></main></body></html>')
    without = platform_scorer.hreflang(doc, html, {"en", "fr"})
    with_default = platform_scorer.hreflang(
        doc, html + '<link rel="alternate" hreflang="x-default" href="/">', {"en", "fr"}
    )
    assert with_default[0] > without[0]
    assert with_default[1]["x_default"] is True


def test_platform_produces_every_declared_signal():
    from tests.test_technical_schema import FakePage

    produced = {s.id for s in platform_scorer.score(FakePage(doc=doc_of("<main><p>x</p></main>")), {})}
    assert produced == set(data.weights()["platform"]["signals"])


# --- in a real audit -------------------------------------------------------


def test_an_audit_scores_all_six_categories(site, geo_home):
    _, envelope = run(["audit", f"{site.url}/hub.html", *BASE])
    assert set(envelope["scores"]["categories"]) == {
        "citability", "technical", "schema", "content", "platform"
    }


def test_site_facts_survive_aggregation_verbatim(site, geo_home):
    """llms.txt is a fact about the site, not an average of page facts."""
    _, envelope = run(["audit", f"{site.url}/hub.html", *BASE])
    detail = next(s["detail"] for s in envelope["signals"] if s["id"] == "platform.llms_txt")
    assert detail["present"] is False, "the fixture site publishes none"
    assert "mean" in detail, "it is still aggregated"


def test_publishing_an_llms_txt_moves_the_platform_score(serve, geo_home):
    from tests.fixture_server import site_routes

    routes = site_routes()
    server = serve(routes)
    _, before = run(["audit", f"{server.url}/hub.html", *BASE])

    routes["/llms.txt"] = Reply(
        body="# Fixture Press\n\n> Everything we publish.\n\n## Pages\n\n- [Home](/hub.html)\n",
        content_type="text/plain; charset=utf-8",
    )
    _, after = run(["audit", f"{server.url}/hub.html", *BASE])

    assert after["scores"]["categories"]["platform"] > before["scores"]["categories"]["platform"]
    detail = next(s["detail"] for s in after["signals"] if s["id"] == "platform.llms_txt")
    assert detail["present"] is True and detail["valid"] is True
