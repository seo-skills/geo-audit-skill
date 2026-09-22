"""A site that marks its articles has answered for the pages it left unmarked.

Presuming every undeclared page is an article kept real articles, but it asked
careers pages, plans pages and a German privacy policy for a byline as soon as
a crawl reached them - and on seomator.com it left `/about` in three findings
of one page each. Where a site marks its articles, in JSON-LD or `og:type`, the
pages it does not mark are not articles.

Only an audit can ask: `geo score` reads one page and has no other page of the
same site to compare it with, so a page scored alone is presumed an article as
before.
"""

from __future__ import annotations

import io
import json

from geo_audit.cli import main
from geo_audit.lib.extract import extract
from geo_audit.scoring import articles
from geo_audit.scoring.model import NOT_APPLICABLE
from tests.fixture_server import Reply

PROSE = "<p>" + "A sentence of real prose about the thing this page explains. " * 40 + "</p>"
POST = ('<html><head><title>Post</title><meta property="og:type" content="article">'
        '<script type="application/ld+json">{"@type": "BlogPosting", "headline": "h"}</script>'
        f"</head><body><main><h1>Post</h1>{PROSE}</main></body></html>")
PLAIN = f"<html><head><title>About</title></head><body><main><h1>About</h1>{PROSE}</main></body></html>"
ROBOTS = Reply(body="User-agent: *\nAllow: /\n", content_type="text/plain")


def _doc(html: str, path: str = "/about"):
    return extract(html, f"https://example.com{path}")


def test_one_marked_page_is_not_a_convention():
    """A stray Article blob on a landing page says nothing about the rest."""
    assert articles.marks_its_articles([_doc(POST, "/blog/a")]) is False
    assert articles.marks_its_articles([_doc(POST, "/blog/a"), _doc(POST, "/blog/b")]) is True
    assert articles.marks_its_articles([_doc(PLAIN), _doc(PLAIN)]) is False


def test_either_place_a_site_says_it_counts():
    jsonld = '<script type="application/ld+json">{"@type": "NewsArticle", "headline": "h"}</script>'
    assert articles.marks_an_article(_doc(f"<html><head>{jsonld}</head><body>{PROSE}</body></html>"))
    og = '<meta property="og:type" content="article">'
    assert articles.marks_an_article(_doc(f"<html><head>{og}</head><body>{PROSE}</body></html>"))
    assert not articles.marks_an_article(_doc(PLAIN))


def test_an_unmarked_page_is_not_an_article_where_the_site_marks_them():
    plain = _doc(PLAIN)
    assert articles.not_an_article(plain) is None, "alone, it is presumed an article"
    assert articles.not_an_article(plain, True) == "the site marks its articles and not this page"
    assert articles.not_an_article(_doc(POST, "/blog/a"), True) is None


def _audit(site, path: str = "/") -> dict:
    buffer = io.StringIO()
    main(["audit", f"{site.url}{path}", "--allow-private", "--rate", "50", "--json", "--quiet"], out=buffer)
    return json.loads(buffer.getvalue())


def _marked_site(serve):
    posts = [f"/blog/post-{n}" for n in range(3)]
    home = ('<html><head><title>Home</title></head><body><main><h1>Home</h1>' + PROSE
            + "".join(f'<a href="{p}">{p}</a> ' for p in posts)
            + '<a href="/about">About</a> <a href="/pricing">Plans</a></main></body></html>')
    routes = {"/": Reply(body=home), "/about": Reply(body=PLAIN), "/pricing": Reply(body=PLAIN), "/robots.txt": ROBOTS}
    routes.update({p: Reply(body=POST) for p in posts})
    return serve(routes)


def test_the_findings_name_the_articles_and_not_the_rest(serve, geo_home):
    envelope = _audit(_marked_site(serve))
    named = {url for f in envelope["findings"]
             if f["id"] in ("content.expertise", "citability.attribution", "schema.article") for url in f["pages"]}
    assert not [url for url in named if url.endswith(("/about", "/pricing"))]


def test_a_site_that_marks_nothing_keeps_the_presumption(serve, geo_home):
    """The rule only applies where the site itself answered the question."""
    posts = [f"/post-{n}" for n in range(3)]
    home = ('<html><head><title>Home</title></head><body><main><h1>Home</h1>' + PROSE
            + "".join(f'<a href="{p}">{p}</a> ' for p in posts) + "</main></body></html>")
    routes = {"/": Reply(body=home), "/robots.txt": ROBOTS}
    routes.update({p: Reply(body=PLAIN) for p in posts})
    envelope = _audit(serve(routes))
    finding = next(f for f in envelope["findings"] if f["id"] == "citability.attribution")
    assert sorted(url.rsplit("/", 1)[-1] for url in finding["pages"]) == sorted(p.strip("/") for p in posts)


def test_one_page_read_alone_is_still_presumed_an_article(serve, geo_home):
    site = _marked_site(serve)
    buffer = io.StringIO()
    main(["score", f"{site.url}/about", "--allow-private", "--no-render", "--json", "--quiet"], out=buffer)
    attribution = next(s for s in json.loads(buffer.getvalue())["signals"] if s["id"] == "citability.attribution")
    assert attribution["value"] is not None
    assert not (attribution.get("skipped_reason") or "").startswith(NOT_APPLICABLE)
