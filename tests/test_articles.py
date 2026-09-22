"""Authorship, attribution and article markup apply to articles only.

A home page, a product, a tool or an index was not written by anyone in the
sense those signals ask about, and scoring it at zero for lacking a byline is
the consequence-as-failure mistake again. The practitioner eval put it plainly:
the home page was "the first example page for authorship, where no byline
belongs", and a remediation asked for bylines on pages holding a calculator.

The constraint on the fix is that a real article must never be dropped, since
dropping one loses a real finding. So a page is excluded only on evidence the
site itself gives - where the page sits, what it lists beneath itself, what it
declares itself to be - and every other page is presumed an article, as every
page was before.
"""

from __future__ import annotations

import io
import json
from pathlib import Path

from geo_audit.cli import main
from geo_audit.lib.extract import extract
from geo_audit.report.context import _category_detail
from geo_audit.scoring import articles, citability, content, schema_org
from geo_audit.scoring.model import NOT_APPLICABLE, Signal, aggregate, composite
from tests.fixture_server import Reply

PROSE = "<p>" + "A sentence of real prose about the thing this page explains. " * 40 + "</p>"
ARTICLE = f"<main><h1>How we fixed it</h1>{PROSE}</main>"


def _doc(url: str, main: str = ARTICLE, jsonld: object = None, og_type: str | None = None):
    head = f'<meta property="og:type" content="{og_type}">' if og_type else ""
    if jsonld is not None:
        head += f'<script type="application/ld+json">{json.dumps(jsonld)}</script>'
    return extract(f"<html><head><title>t</title>{head}</head><body>{main}</body></html>", url)


def _index(url: str, hrefs: list[str]):
    items = "".join(f'<li><a href="{href}">{href}</a></li>' for href in hrefs)
    return _doc(url, f"<main><h1>Index</h1>{PROSE}<ul>{items}</ul></main>")


# --- which pages are plainly not articles --------------------------------------


def test_a_home_page_is_not_an_article():
    for url in ("https://example.com", "https://example.com/", "https://example.com/en-US/", "https://example.com/de"):
        assert articles.not_an_article(_doc(url)) == "the site's home page", url


def test_a_page_listing_the_pages_beneath_it_is_an_index():
    """Blog indexes, directories and docs hubs link down into their own path;
    of 31 real articles sampled, not one linked to a single page beneath it."""
    five = [f"/blog/post-{n}" for n in range(5)]
    assert articles.not_an_article(_index("https://example.com/blog", five)) == "an index of 5 pages beneath it"
    assert articles.not_an_article(_index("https://example.com/blog", five[:4])) is None


def test_a_declared_article_with_chapters_beneath_it_is_still_an_article():
    """A pillar guide with its chapters beneath it has an author; its own
    declaration outranks the shape of its links."""
    chapters = [f"/guide/chapter-{n}" for n in range(6)]
    items = "".join(f'<li><a href="{href}">{href}</a></li>' for href in chapters)
    doc = _doc("https://example.com/guide", f"<main><h1>Guide</h1>{PROSE}<ul>{items}</ul></main>",
               jsonld={"@type": "TechArticle", "headline": "Guide"})
    assert articles.not_an_article(doc) is None


def test_links_to_neighbours_do_not_make_an_index():
    siblings = [f"/blog/other-{n}" for n in range(12)]
    assert articles.not_an_article(_index("https://example.com/blog/this-post", siblings)) is None


def test_a_page_that_declares_a_product_a_tool_or_a_profile_is_not_an_article():
    for kind in ("Product", "SoftwareApplication", "WebApplication", "ProfilePage", "CollectionPage"):
        doc = _doc("https://example.com/x", jsonld={"@type": kind, "name": "x"})
        assert articles.not_an_article(doc) == f"declared a {kind}", kind
    graph = {"@context": "https://schema.org", "@graph": [{"@type": "WebSite"}, {"@type": ["SoftwareApplication", "WebApplication"]}]}
    assert articles.not_an_article(_doc("https://example.com/tool", jsonld=graph)) == "declared a SoftwareApplication"
    for og in ("product", "profile"):
        assert articles.not_an_article(_doc("https://example.com/x", og_type=og)) == f"declared og:type {og}"


def test_a_page_that_also_declares_an_article_is_one():
    """A review is an article about a product; what it says it is wins."""
    doc = _doc("https://example.com/review", jsonld=[{"@type": "BlogPosting"}, {"@type": "Product"}])
    assert articles.not_an_article(doc) is None


def test_only_what_a_page_declares_for_itself_counts():
    """A post that nests the app it reviews has not declared itself an app."""
    doc = _doc("https://example.com/post", jsonld={"@type": "Review", "itemReviewed": {"@type": "SoftwareApplication"}})
    assert articles.not_an_article(doc) is None


def test_a_page_with_no_evidence_either_way_is_presumed_an_article():
    """A Rust blog post carries no markup at all, and it is an article."""
    assert articles.not_an_article(_doc("https://blog.example.org/2014/09/15/Rust-1.0/")) is None


# --- the three signals ------------------------------------------------------------


SIGNALS = (content.expertise, citability.attribution, schema_org.article)


def test_the_article_only_signals_do_not_apply_off_articles():
    home = _doc("https://example.com/")
    for signal in SIGNALS:
        value, detail = signal(home)
        assert value is None, signal.__name__
        assert detail["reason"].startswith(NOT_APPLICABLE)
        assert detail["not_an_article"] == "the site's home page"
    post = _doc("https://example.com/blog/post")
    for signal in SIGNALS:
        assert signal(post)[0] is not None, signal.__name__


def _signal(value, reason=None, page="p"):
    return Signal(id="content.expertise", cls="deterministic", max=25, value=value, page=page, skipped_reason=reason)


def test_a_signal_that_applies_to_no_page_is_not_applicable_and_not_missing():
    """A shop with no articles is not missing its bylines. The signal leaves the
    composite, like any unmeasured one, and leaves the completeness count too,
    like a category the inputs cannot reach."""
    na = articles.ARTICLES_ONLY
    site = aggregate([[_signal(None, na, "a")], [_signal(None, na, "b")]])[0]
    assert site.value is None and site.skipped_reason == na
    other = Signal(id="technical.https", cls="deterministic", max=10, value=10)
    score, completeness = composite([site, other])
    assert score == 100
    assert completeness == {"computed": 1, "total": 1, "missing": []}


def test_a_signal_unmeasured_on_an_article_is_still_missing():
    """Not applicable on the home page, unmeasurable on the article: that is a
    gap in the audit, and the completeness note has to say so."""
    site = aggregate([[_signal(None, articles.ARTICLES_ONLY, "home")], [_signal(None, "the page returned no markup to inspect", "post")]])[0]
    assert site.skipped_reason == "the page returned no markup to inspect"
    assert composite([site])[1]["missing"] == ["content.expertise"]


def test_the_mean_is_taken_over_the_articles_only():
    site = aggregate([[_signal(None, articles.ARTICLES_ONLY, "home")], [_signal(20.0, page="a")], [_signal(10.0, page="b")]])[0]
    assert site.value == 15.0


def test_the_report_says_not_applicable_rather_than_not_measured():
    envelope = {"signals": [
        {"id": "content.expertise", "class": "deterministic", "value": None, "max": 25, "skipped_reason": articles.ARTICLES_ONLY},
        {"id": "content.freshness", "class": "deterministic", "value": None, "max": 20, "skipped_reason": "no date found"},
    ]}
    rows = {row["name"]: row for row in _category_detail(envelope, [])[0]["signals"]}
    applicable = [row for row in rows.values() if row["status"] == "Not applicable"]
    assert len(applicable) == 1 and applicable[0]["note"] == "articles only"
    assert [row["status"] for row in rows.values()].count("Not measured") == 1


# --- end to end ---------------------------------------------------------------------


BYLINE_FREE_POST = f"<html><head><title>Post</title></head><body>{ARTICLE}</body></html>"
ROBOTS = Reply(body="User-agent: *\nAllow: /\n", content_type="text/plain; charset=utf-8")


def _audit(site, path="/") -> dict:
    buffer = io.StringIO()
    main(["audit", f"{site.url}{path}", "--allow-private", "--rate", "50", "--max-pages", "20",
          "--json", "--quiet"], out=buffer)
    return json.loads(buffer.getvalue())


def test_the_authorship_finding_names_articles_and_nothing_else(serve, geo_home):
    posts = [f"/blog/post-{n}" for n in range(5)]
    product = ('<html><head><title>Kit</title><script type="application/ld+json">'
               '{"@type": "Product", "name": "Kit"}</script></head><body>' + ARTICLE + "</body></html>")
    home = ('<html><head><title>Home</title></head><body><main><h1>Home</h1>' + PROSE
            + '<a href="/blog">Blog</a> <a href="/product/kit">Kit</a></main></body></html>')
    index = ('<html><head><title>Blog</title></head><body><main><h1>Blog</h1>' + PROSE
             + "".join(f'<a href="{p}">{p}</a> ' for p in posts) + "</main></body></html>")
    routes = {"/": Reply(body=home), "/blog": Reply(body=index), "/product/kit": Reply(body=product), "/robots.txt": ROBOTS}
    routes.update({p: Reply(body=BYLINE_FREE_POST) for p in posts})
    site = serve(routes)

    envelope = _audit(site)
    finding = next(f for f in envelope["findings"] if f["id"] == "content.expertise")
    assert sorted(finding["pages"]) == sorted(f"{site.url}{p}" for p in posts)


def test_a_site_with_no_articles_is_not_missing_its_bylines(serve, geo_home):
    product = ('<html><head><title>Kit</title><script type="application/ld+json">'
               '{"@type": "Product", "name": "Kit"}</script></head><body>' + ARTICLE + "</body></html>")
    home = ('<html><head><title>Shop</title></head><body><main><h1>Shop</h1>' + PROSE
            + '<a href="/product/kit">Kit</a></main></body></html>')
    site = serve({"/": Reply(body=home), "/product/kit": Reply(body=product), "/robots.txt": ROBOTS})

    envelope = _audit(site)
    signals = {s["id"]: s for s in envelope["signals"]}
    for signal_id in ("content.expertise", "citability.attribution", "schema.article"):
        assert signals[signal_id]["value"] is None
        assert signals[signal_id]["skipped_reason"].startswith(NOT_APPLICABLE)
        assert signal_id not in envelope["completeness"]["missing"]
    assert not [f for f in envelope["findings"] if f["id"] in ("content.expertise", "citability.attribution", "schema.article")]


def test_the_operator_copy_says_not_applicable_too(serve, geo_home):
    """The operator's signal table printed "not measured" for every empty value,
    so it contradicted the client copy on exactly these three signals."""
    product = ('<html><head><title>Kit</title><script type="application/ld+json">'
               '{"@type": "Product", "name": "Kit"}</script></head><body>' + ARTICLE + "</body></html>")
    home = ('<html><head><title>Shop</title></head><body><main><h1>Shop</h1>' + PROSE
            + '<a href="/product/kit">Kit</a></main></body></html>')
    site = serve({"/": Reply(body=home), "/product/kit": Reply(body=product), "/robots.txt": ROBOTS})
    _audit(site)
    buffer = io.StringIO()
    main(["report", f"{site.url}/", "--mode", "operator", "--json", "--quiet"], out=buffer)
    html = Path(json.loads(buffer.getvalue())["report"]["path"]).read_text(encoding="utf-8")
    row = html.split("<code>content.expertise</code>", 1)[1].split("</tr>", 1)[0]
    assert "not applicable" in row and "not measured" not in row
