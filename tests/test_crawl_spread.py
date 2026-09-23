"""A capped crawl spreads its pages over the site, the same way every time.

The sitemap's URLs were read in sorted order, so a capped crawl audited the
alphabetical prefix of a site. seomator.com's fifty of 310 ran from `/` to
`/blog/how-to-*`: no tool page after "b", no post after "h", no pricing page,
and the audit skill called the site a publisher from that slice. Each section
of the site now gives a page in turn, ordered within the section by a hash of
the path, so the choice still depends on nothing but the sitemap.
"""

from __future__ import annotations

import random

from geo_audit.lib.crawl import CrawlOptions, _spread, crawl
from tests.fixture_server import Reply

SITEMAP = (
    [f"/blog/{letter}-post" for letter in "abcdefghijklmnop"]
    + ["/about", "/pricing", "/zeta-tool"]
    + [f"/tools/{name}" for name in ("audit", "checker", "zapper")]
    + ["/authors/ben", "/authors/dana"]
)


def _section(path: str) -> str:
    segments = [part for part in path.split("/") if part]
    return segments[0] if len(segments) > 1 else ""


def test_the_first_pages_cover_every_section():
    urls = [f"https://example.com{path}" for path in SITEMAP]
    first = [url.removeprefix("https://example.com") for url in _spread(urls)[:4]]
    assert {_section(path) for path in first} == {"", "authors", "blog", "tools"}


def test_the_order_depends_on_the_sitemap_alone():
    urls = [f"https://example.com{path}" for path in SITEMAP]
    shuffled = urls[:]
    random.Random(7).shuffle(shuffled)
    assert _spread(shuffled) == _spread(urls)
    elsewhere = [url.replace("https://example.com", "http://127.0.0.1:8123") for url in urls]
    assert [u.split("8123", 1)[1] for u in _spread(elsewhere)] == [u.removeprefix("https://example.com") for u in _spread(urls)]


def test_a_capped_crawl_reads_past_the_start_of_the_alphabet(serve):
    page = Reply(body="<html><body><main><h1>t</h1><p>" + "word " * 40 + "</p></main></body></html>")
    entries = "".join(f"<url><loc>{{base}}{path}</loc></url>" for path in SITEMAP)
    routes = {
        "/": page,
        "/robots.txt": Reply(body="User-agent: *\nAllow: /\nSitemap: /sitemap.xml\n", content_type="text/plain"),
        "/sitemap.xml": Reply(body=f'<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">{entries}</urlset>',
                              content_type="application/xml"),
    }
    routes.update({path: page for path in SITEMAP})
    server = serve(routes)

    reached = set()
    for _ in range(2):
        result = crawl(f"{server.url}/", CrawlOptions(allow_private=True, max_pages=9, requests_per_second=100))
        reached.add(tuple(sorted(p.url.replace(server.url, "") for p in result.pages)))
    assert len(reached) == 1
    # Sorted, these nine were `/`, `/about`, both authors and five posts from a to e.
    assert {_section(path) for path in reached.pop()} == {"", "authors", "blog", "tools"}


def test_the_sitemap_cap_keeps_a_spread_not_a_prefix(serve):
    """The cap is `MAX_SITEMAP_URLS`, and it used to keep whatever came first
    in the file. userguiding.com lists 2951 URLs with its first blog post at
    number 748, so all 950 posts - the largest section on the site, and the
    only one with articles in it - were cut before `_spread` ever saw them,
    and the audit judged freshness, authorship and Article markup from a
    sample with no article in it.
    """
    from geo_audit.lib import crawl as crawl_lib

    page = Reply(body="<html><body><main><h1>t</h1><p>" + "word " * 40 + "</p></main></body></html>")
    # Three sections, and the one that matters is listed last and is the largest.
    paths = ([f"/es/{i}" for i in range(40)] + [f"/fr/{i}" for i in range(40)]
             + [f"/blog/{i}" for i in range(40)])
    entries = "".join(f"<url><loc>{{base}}{path}</loc></url>" for path in paths)
    routes = {
        "/": page,
        "/robots.txt": Reply(body="User-agent: *\nAllow: /\nSitemap: /sitemap.xml\n", content_type="text/plain"),
        "/sitemap.xml": Reply(body=f'<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">{entries}</urlset>',
                              content_type="application/xml"),
    }
    routes.update({path: page for path in paths})
    server = serve(routes)

    original = crawl_lib.MAX_SITEMAP_URLS
    crawl_lib.MAX_SITEMAP_URLS = 60  # a cap the sitemap is comfortably larger than
    try:
        result = crawl(f"{server.url}/", CrawlOptions(allow_private=True, max_pages=9, requests_per_second=100))
    finally:
        crawl_lib.MAX_SITEMAP_URLS = original

    sections = {_section(p.url.replace(server.url, "")) for p in result.pages}
    assert "blog" in sections, "the section the file lists last is still reachable"
    assert sections == {"", "blog", "es", "fr"}
