"""A category, tag or author archive is not an article.

seomator.com files its posts at `/blog/<slug>` and lists them at
`/blog/category/<name>`. The archives link across to the posts rather than down
beneath themselves, so the index rule never saw them, and on the site's audit
*The page does not say who wrote it or when* and *Content pages are not
described as articles* named seven archives and an about page - and no article.
"""

from __future__ import annotations

import io
import json

import pytest

from geo_audit.cli import main
from geo_audit.lib.extract import extract
from geo_audit.scoring import articles
from tests.fixture_server import Reply

PROSE = "<p>" + "A sentence of real prose about the thing this page explains. " * 40 + "</p>"


def _doc(url: str, jsonld: object = None):
    head = f'<script type="application/ld+json">{json.dumps(jsonld)}</script>' if jsonld else ""
    return extract(f"<html><head><title>t</title>{head}</head><body><main><h1>x</h1>{PROSE}</main></body></html>", url)


@pytest.mark.parametrize("path, reason", [
    ("/blog/category/backlinks", "a category archive"),
    ("/categories/news/", "a category archive"),
    ("/de/blog/kategorie/content", "a category archive"),
    ("/tag/python", "a tag archive"),
    ("/blog/tags/python/page/3", "a tag archive"),
    ("/author/jane", "an author archive"),
    ("/authors/ben-kaiser/", "an author archive"),
])
def test_an_archive_path_is_not_an_article(path, reason):
    assert articles.not_an_article(_doc(f"https://example.com{path}")) == reason


@pytest.mark.parametrize("path", ["/category/news/my-post", "/blog/tagging-guide", "/tag", "/blog/authoring-tips"])
def test_a_post_near_an_archive_is_still_an_article(path):
    assert articles.not_an_article(_doc(f"https://example.com{path}")) is None


def test_what_a_page_declares_outranks_where_it_sits():
    doc = _doc("https://example.com/category/news", {"@type": "NewsArticle", "headline": "h"})
    assert articles.not_an_article(doc) is None


def test_the_article_findings_do_not_name_the_archives(serve, geo_home):
    posts = [f"/blog/post-{n}" for n in range(3)]
    post = f"<html><head><title>Post</title></head><body><main><h1>Post</h1>{PROSE}</main></body></html>"
    archive = ("<html><head><title>Backlinks</title></head><body><main><h1>Backlinks</h1>" + PROSE
               + "".join(f'<a href="{p}">{p}</a> ' for p in posts) + "</main></body></html>")
    home = ('<html><head><title>Home</title></head><body><main><h1>Home</h1>' + PROSE
            + '<a href="/blog/category/backlinks">Backlinks</a></main></body></html>')
    routes = {"/": Reply(body=home), "/blog/category/backlinks": Reply(body=archive),
              "/robots.txt": Reply(body="User-agent: *\nAllow: /\n", content_type="text/plain")}
    routes.update({p: Reply(body=post) for p in posts})
    site = serve(routes)

    buffer = io.StringIO()
    main(["audit", f"{site.url}/", "--allow-private", "--rate", "50", "--json", "--quiet"], out=buffer)
    envelope = json.loads(buffer.getvalue())
    named = {page for f in envelope["findings"]
             if f["id"] in ("content.expertise", "citability.attribution", "schema.article") for page in f["pages"]}
    assert named, "the byline-free posts are still reported"
    assert f"{site.url}/blog/category/backlinks" not in named
