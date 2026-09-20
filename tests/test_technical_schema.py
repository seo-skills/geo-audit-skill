"""The technical and schema category scorers."""

from __future__ import annotations

from dataclasses import dataclass

import pytest

from geo_audit import data
from geo_audit.lib import robots as robots_lib
from geo_audit.lib.extract import extract
from geo_audit.scoring import schema_org, technical

URL = "https://example.com/docs/page"


@dataclass
class FakeResult:
    final_url: str = URL
    status: int = 200
    headers: dict = None
    chain: tuple = ()

    def __post_init__(self):
        self.headers = self.headers or {}


@dataclass
class FakePage:
    doc: object = None
    result: FakeResult = None
    url: str = URL

    def __post_init__(self):
        self.result = self.result or FakeResult()


def doc_of(html: str, url: str = URL):
    return extract(html, url)


ALLOW_ALL = robots_lib.parse("User-agent: *\nAllow: /\n", source_url="https://example.com/robots.txt")
BLOCK_ALL = robots_lib.parse("User-agent: *\nDisallow: /\n", source_url="https://example.com/robots.txt")


# --- technical -------------------------------------------------------------


def test_crawler_access_is_full_when_nothing_is_blocked():
    points, detail = technical.crawler_access(ALLOW_ALL, "/docs/page")
    assert points == 25.0
    assert detail["blocked_critical"] == []


def test_crawler_access_is_zero_when_everything_is_blocked():
    points, detail = technical.crawler_access(BLOCK_ALL, "/docs/page")
    assert points == 0.0
    assert len(detail["blocked_critical"]) == detail["critical_total"]


def test_blocking_only_training_crawlers_costs_nothing():
    """Refusing training while allowing search is a position, not a mistake."""
    rules = robots_lib.parse(
        "User-agent: GPTBot\nDisallow: /\n\nUser-agent: ClaudeBot\nDisallow: /\n",
        source_url="https://example.com/robots.txt",
    )
    points, detail = technical.crawler_access(rules, "/docs/page")
    assert points == 25.0
    assert set(detail["blocked_training_only"]) == {"GPTBot", "ClaudeBot"}


def test_an_unreachable_robots_file_blocks_everything():
    """RFC 9309 makes a 5xx a complete disallow, so it scores like one."""
    unreachable = robots_lib.RobotsFile(source_url="x", status=503, unreachable=True)
    points, detail = technical.crawler_access(unreachable, "/")
    assert points == 0.0
    assert "unreachable" in detail["reason"]


def test_crawler_access_is_null_when_robots_was_not_checked():
    points, detail = technical.crawler_access(None, "/")
    assert points is None
    assert "not checked" in detail["reason"]


def test_noindex_zeroes_indexability():
    doc = doc_of('<html><head><meta name="robots" content="noindex, follow"></head><body><main><p>x</p></main></body></html>')
    points, detail = technical.indexability(doc, {})
    assert points == 0.0
    assert detail["noindex"] is True


def test_an_x_robots_tag_header_counts_as_much_as_the_meta_tag():
    doc = doc_of("<html><body><main><p>x</p></main></body></html>")
    points, detail = technical.indexability(doc, {"x-robots-tag": "noindex"})
    assert points == 0.0
    assert detail["x_robots_tag"] == "noindex"


def test_a_missing_canonical_costs_points_but_is_not_fatal():
    with_canonical = doc_of('<html><head><link rel="canonical" href="/a"></head><body><main><p>x</p></main></body></html>')
    without = doc_of("<html><body><main><p>x</p></main></body></html>")
    assert technical.indexability(with_canonical, {})[0] == 20.0
    assert 0 < technical.indexability(without, {})[0] < 20.0


def test_metadata_rewards_the_documented_lengths():
    good = doc_of(
        '<html lang="en"><head><title>How server rendering changes crawling</title>'
        '<meta name="description" content="' + "a" * 100 + '"></head>'
        "<body><main><h1>One</h1><p>x</p></main></body></html>"
    )
    points, detail = technical.metadata(good)
    assert points == 20.0
    assert detail["breakdown"]["title"] == 5
    assert detail["breakdown"]["description"] == 5


def test_open_graph_is_not_scored_twice():
    """It belongs to the platform category; scoring it here as well would
    count one tag in two places."""
    plain = doc_of(
        '<html lang="en"><head><title>How server rendering changes crawling</title>'
        '<meta name="description" content="' + "a" * 100 + '"></head>'
        "<body><main><h1>One</h1><p>x</p></main></body></html>"
    )
    with_og = doc_of(
        '<html lang="en"><head><title>How server rendering changes crawling</title>'
        '<meta name="description" content="' + "a" * 100 + '">'
        '<meta property="og:title" content="x"></head>'
        "<body><main><h1>One</h1><p>x</p></main></body></html>"
    )
    assert technical.metadata(plain)[0] == technical.metadata(with_og)[0]
    assert "open_graph" not in technical.metadata(with_og)[1]["breakdown"]


def test_a_title_outside_the_range_gets_partial_credit():
    short = doc_of("<html><head><title>Hi</title></head><body><main><p>x</p></main></body></html>")
    assert technical.metadata(short)[1]["breakdown"]["title"] == 2.5


@pytest.mark.parametrize(
    "status,hops,expected",
    [(200, 0, 15.0), (200, 1, 13.0), (200, 5, 9.0), (404, 0, 0.0), (500, 0, 0.0), (None, 0, 0.0)],
)
def test_status_health(status, hops, expected):
    assert technical.status_health(status, hops)[0] == expected


def test_transport_security_needs_https_before_hsts_counts():
    assert technical.transport_security("http://x.test/a", {"strict-transport-security": "max-age=1"})[0] == 0.0
    assert technical.transport_security("https://x.test/a", {})[0] == 7.0
    assert technical.transport_security("https://x.test/a", {"strict-transport-security": "max-age=1"})[0] == 10.0


def test_url_structure_scores_each_convention_separately():
    clean = technical.url_structure("https://x.test/docs/rendering")
    messy = technical.url_structure(
        "https://x.test/Docs/Deep/Nested/Path/Segments/With_Underscores?PHPSESSID=abc"
    )
    assert clean[0] == 10.0
    assert messy[0] < 3.0
    assert messy[1]["checks"]["no_session_id"] is False
    assert messy[1]["checks"]["lowercase"] is False


def test_a_page_without_markup_is_not_measured_rather_than_failed():
    signals = {s.id: s for s in technical.score(FakePage(doc=None, result=FakeResult(status=404)), ALLOW_ALL)}
    assert signals["technical.indexability"].value is None
    assert signals["technical.metadata"].value is None
    assert signals["technical.status_health"].value == 0.0, "the 404 belongs here"


def test_technical_produces_every_declared_signal():
    doc = doc_of("<html><body><main><p>x</p></main></body></html>")
    produced = {s.id for s in technical.score(FakePage(doc=doc), ALLOW_ALL)}
    assert produced == set(data.weights()["technical"]["signals"])


# --- schema ----------------------------------------------------------------


def jsonld(payload: str) -> str:
    return (
        f'<html><head><script type="application/ld+json">{payload}</script></head>'
        "<body><main><p>x</p></main></body></html>"
    )


def test_presence_is_all_or_nothing():
    assert schema_org.presence(doc_of("<html><body><main><p>x</p></main></body></html>"))[0] == 0.0
    assert schema_org.presence(doc_of(jsonld('{"@type":"WebPage"}')))[0] == 30.0


def test_validity_punishes_a_missing_required_property():
    complete = doc_of(jsonld('{"@type":"Organization","name":"Acme"}'))
    incomplete = doc_of(jsonld('{"@type":"Organization"}'))
    assert schema_org.validity(complete)[0] == 25.0
    points, detail = schema_org.validity(incomplete)
    assert points == 0.0
    assert "Organization.name" in detail["missing_required"]


def test_unparseable_json_caps_validity():
    doc = doc_of(jsonld('{"@type":"Organization",,}'))
    points, detail = schema_org.validity(doc)
    assert points == 0.0
    assert detail["parse_errors"]


def test_organization_weights_same_as_highest():
    bare = doc_of(jsonld('{"@type":"Organization","name":"Acme"}'))
    linked = doc_of(
        jsonld('{"@type":"Organization","name":"Acme","url":"https://acme.test",'
               '"logo":"/l.png","description":"d","sameAs":["https://en.wikipedia.org/wiki/Acme"]}')
    )
    assert schema_org.organization(bare)[0] == 5.0
    assert schema_org.organization(linked)[0] == 20.0
    assert schema_org.organization(linked)[1]["same_as_count"] == 1


def test_organization_is_found_when_nested_as_a_publisher():
    doc = doc_of(jsonld('{"@type":"Article","publisher":{"@type":"Organization","name":"Acme"}}'))
    assert schema_org.organization(doc)[0] > 0


def test_article_scores_the_properties_that_date_and_attribute_it():
    full = doc_of(
        jsonld('{"@type":"Article","headline":"h","author":{"@type":"Person","name":"a"},'
               '"datePublished":"2026-01-01","dateModified":"2026-02-01","image":"/i.png"}')
    )
    assert schema_org.article(full)[0] == 15.0
    assert schema_org.article(doc_of(jsonld('{"@type":"Article","headline":"h"}')))[0] == 4.0


def test_breadth_rewards_types_that_answer_a_question():
    none = doc_of(jsonld('{"@type":"WebPage"}'))
    two = doc_of(jsonld('[{"@type":"FAQPage","mainEntity":[]},{"@type":"BreadcrumbList","itemListElement":[]}]'))
    assert schema_org.breadth(none)[0] == 0.0
    assert schema_org.breadth(two)[0] == 10.0


def test_schema_produces_every_declared_signal():
    doc = doc_of(jsonld('{"@type":"WebPage"}'))
    produced = {s.id for s in schema_org.score(FakePage(doc=doc))}
    assert produced == set(data.weights()["schema"]["signals"])


def test_every_requirement_entry_is_shaped_correctly():
    requirements = data.load("schema_requirements")
    for name, spec in requirements["types"].items():
        assert isinstance(spec["required"], list), name
        assert isinstance(spec["recommended"], list), name
    for group in ("answer_types", "entity_types", "article_types"):
        assert requirements[group], group
