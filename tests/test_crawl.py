"""The crawl engine: the frontier rules, the rate limit, and what is never fetched."""

from __future__ import annotations

import io
import json
import time

import pytest

from geo_audit.cli import main
from geo_audit.lib import evidence
from geo_audit.lib.crawl import (
    CONCURRENCY,
    MAX_PAGES,
    REQUESTS_PER_SECOND,
    CrawlOptions,
    Pacer,
    crawl,
    is_crawlable,
    normalize_url,
)

FAST = dict(allow_private=True, requests_per_second=50.0)


def run_crawl(site, **kwargs):
    options = CrawlOptions(**{**FAST, **kwargs})
    return crawl(f"{site.url}/hub.html", options)


# --- URL normalisation -----------------------------------------------------


@pytest.mark.parametrize(
    "raw,expected",
    [
        ("https://Example.com/a", "https://example.com/a"),
        ("https://example.com", "https://example.com/"),
        ("https://example.com/a/", "https://example.com/a"),
        ("https://example.com/a#section", "https://example.com/a"),
        ("https://example.com/a?utm_source=x", "https://example.com/a"),
        ("https://example.com/a?utm_source=x&id=7", "https://example.com/a?id=7"),
        ("https://example.com/a?b=2&a=1", "https://example.com/a?a=1&b=2"),
        ("https://example.com:443/a", "https://example.com/a"),
        ("http://example.com:80/a", "http://example.com/a"),
        ("http://example.com:8080/a", "http://example.com:8080/a"),
    ],
)
def test_normalize_url(raw, expected):
    assert normalize_url(raw) == expected


def test_a_real_query_parameter_is_not_a_tracking_parameter():
    assert normalize_url("https://x.test/p?page=2") == "https://x.test/p?page=2"


@pytest.mark.parametrize(
    "url,ok",
    [
        ("https://x.test/page", True),
        ("https://x.test/page.html", True),
        ("https://x.test/a.PDF", False),
        ("https://x.test/a.jpg", False),
        ("https://x.test/bundle.js", False),
        ("https://x.test/feed.xml", False),
        ("mailto:a@b.c", False),
        ("javascript:void(0)", False),
    ],
)
def test_is_crawlable(url, ok):
    assert is_crawlable(url) is ok


# --- the rate limit --------------------------------------------------------


def test_the_pacer_spaces_slots_evenly():
    pacer = Pacer(20.0)
    started = time.monotonic()
    for _ in range(5):
        pacer.wait()
    assert 0.15 < time.monotonic() - started < 0.6


def test_the_rate_limit_is_global_not_per_worker(site):
    """Five workers at one request per second each is five per second.

    That is not what "one request per second" means to the person whose
    server it is, so concurrency must not multiply the rate.
    """
    timings = {}
    for concurrency in (1, 5):
        started = time.monotonic()
        result = crawl(
            f"{site.url}/hub.html",
            CrawlOptions(
                allow_private=True,
                max_pages=5,
                requests_per_second=8.0,
                concurrency=concurrency,
                use_sitemap=False,
            ),
        )
        timings[concurrency] = (time.monotonic() - started, len(result.pages))

    (serial, pages_serial), (parallel, pages_parallel) = timings[1], timings[5]
    assert pages_serial == pages_parallel == 5
    assert parallel > 0.35, "five pages at 8/s cannot finish faster than the limit"
    assert abs(parallel - serial) < serial, "concurrency must not multiply the rate"


def test_a_zero_rate_disables_pacing():
    pacer = Pacer(0)
    started = time.monotonic()
    for _ in range(50):
        pacer.wait()
    assert time.monotonic() - started < 0.1


# --- the frontier ----------------------------------------------------------


def test_a_crawl_follows_internal_links(site):
    result = run_crawl(site, max_pages=20)
    found = {page.url.replace(site.url, "") for page in result.pages}
    assert "/hub.html" in found
    assert "/ssr-rich.html" in found
    assert "/weak-prose.html" in found


def test_a_disallowed_page_is_never_requested(site):
    """Not merely filtered from the results: never asked for."""
    site.reset_requests()
    result = run_crawl(site, max_pages=20)
    assert any(url.endswith("/private/secret.html") for url in result.disallowed)
    assert not any("/private/" in path for path in site.requests_seen)


def test_a_non_page_extension_is_never_requested(site):
    site.reset_requests()
    result = run_crawl(site, max_pages=20)
    assert not any("whitepaper.pdf" in path for path in site.requests_seen)
    assert not any("whitepaper" in failure["url"] for failure in result.failures)


def test_another_host_is_not_crawled(site):
    result = run_crawl(site, max_pages=20)
    assert all("elsewhere.example" not in page.url for page in result.pages)


def test_tracking_parameters_do_not_produce_duplicate_pages(site):
    """The hub links the same article three ways."""
    site.reset_requests()
    run_crawl(site, max_pages=20)
    fetched = [p for p in site.requests_seen if p.split("?")[0].endswith("/ssr-rich.html")]
    assert len(fetched) == 1, f"fetched the same article {len(fetched)} times: {fetched}"


def test_the_sitemap_seeds_pages_no_link_points_at(site):
    with_sitemap = run_crawl(site, max_pages=20, use_sitemap=True)
    without = run_crawl(site, max_pages=20, use_sitemap=False)

    assert with_sitemap.seeded_from_sitemap == 2
    assert without.seeded_from_sitemap == 0

    only_in_sitemap = {"/schema-broken.html", "/injection.html"}
    reachable = {p.url.replace(site.url, "") for p in with_sitemap.pages}
    linked_only = {p.url.replace(site.url, "") for p in without.pages}
    assert only_in_sitemap <= reachable
    assert not (only_in_sitemap & linked_only)


def test_max_pages_stops_the_crawl_and_says_so(site):
    result = run_crawl(site, max_pages=3)
    assert len(result.pages) == 3
    assert result.stopped_because == "max_pages"


def test_a_capped_crawl_reaches_the_same_pages_every_time(site):
    """Found on CI: macOS and Windows crawled a different eight than Ubuntu.

    Completions were processed in whichever order they finished, so discovery
    order - and therefore which pages a cap reaches - depended on machine
    speed. `compare` would then report pages as added and removed on a site
    where nothing had changed.
    """
    visited = set()
    for concurrency in (1, 2, 5, 5):
        result = run_crawl(site, max_pages=8, concurrency=concurrency)
        visited.add(tuple(sorted(page.url for page in result.pages)))
    assert len(visited) == 1, f"a capped crawl reached {len(visited)} different page sets"


def test_completion_order_does_not_decide_which_pages_a_cap_reaches(serve):
    """The race, forced rather than hoped for.

    Each first-level page links to one second-level page and answers at a
    different speed, so the order they *finish* is the reverse of their URL
    order. Without sorting completions, the fast page's link is discovered
    first and a capped crawl reaches a different set.
    """
    from tests.fixture_server import Reply

    def page(body: str, delay: float = 0.0) -> Reply:
        return Reply(
            body=f"<html><body><main><h1>t</h1><p>{'word ' * 40}</p>{body}</main></body></html>",
            delay=delay,
        )

    routes = {
        "/robots.txt": Reply(body="User-agent: *\nAllow: /\n", content_type="text/plain"),
        "/hub.html": page(
            '<a href="/a.html">a</a><a href="/b.html">b</a><a href="/c.html">c</a>'
        ),
        # Reverse-speed: `a` is slowest, `c` is fastest.
        "/a.html": page('<a href="/a2.html">a2</a>', delay=0.30),
        "/b.html": page('<a href="/b2.html">b2</a>', delay=0.15),
        "/c.html": page('<a href="/c2.html">c2</a>', delay=0.0),
        "/a2.html": page(""),
        "/b2.html": page(""),
        "/c2.html": page(""),
    }
    server = serve(routes)

    reached = set()
    for _ in range(3):
        result = crawl(
            f"{server.url}/hub.html",
            CrawlOptions(allow_private=True, max_pages=5, requests_per_second=100,
                         concurrency=3, use_sitemap=False),
        )
        reached.add(tuple(sorted(p.url.replace(server.url, "") for p in result.pages)))

    assert len(reached) == 1, f"a capped crawl reached {len(reached)} different sets: {reached}"
    pages = reached.pop()
    assert "/a2.html" in pages, (
        "the slowest branch was dropped, so completion order decided the frontier"
    )


def test_failures_are_reported_in_a_stable_order(site, geo_home):
    """The order pages happened to fail is a property of the race, not the site."""
    orders = set()
    for concurrency in (1, 5, 5):
        _, envelope = run_cli(
            ["crawl", f"{site.url}/hub.html", "--allow-private", "--rate", "50",
             "--max-pages", "20", "--concurrency", str(concurrency)]
        )
        failures = envelope["evidence"]["pages_failed"]
        assert failures == sorted(failures, key=lambda entry: entry["url"])
        orders.add(tuple(entry["url"] for entry in failures))
    assert len(orders) == 1


def test_an_exhausted_frontier_reports_exhausted(site):
    result = run_crawl(site, max_pages=50)
    assert result.stopped_because == "exhausted"


# --- failures are data -----------------------------------------------------


def test_a_failing_page_is_recorded_not_raised(site):
    result = run_crawl(site, max_pages=20)
    reasons = {failure["reason"] for failure in result.failures}
    assert "not_found" in reasons, "the 404 must be reported"
    assert "not_html" in reasons, "the JSON endpoint must be reported"
    assert result.ok_pages, "one bad page must not sink the crawl"


def test_a_broken_link_is_not_called_a_server_error(site, geo_home):
    """Different cause, different fix: one is your link, one is your server."""
    _, envelope = run_cli(
        ["crawl", f"{site.url}/hub.html", "--allow-private", "--rate", "50", "--max-pages", "20"]
    )
    ids = {finding["id"] for finding in envelope["findings"]}
    assert "fetch.not_found" in ids
    assert "fetch.server_error" not in ids


def _soft_404_site(serve):
    from tests.fixture_server import Reply

    article = "<p>" + "A static host answers 404 for a path it has no file for. " * 40 + "</p>"
    return serve({
        "/missing": Reply(body="<html><head><title>Page not found | Example</title></head><body>"
                               "<main><h1>Page not found</h1><p>Sorry, that page is gone.</p></main></body></html>"),
        "/about-404s": Reply(body="<html><head><title>Fixing 404 errors on a static site</title></head>"
                                  f"<body><main><h1>Fixing 404 errors</h1>{article}</main></body></html>"),
        "/contact": Reply(body="<html><head><title>Contact us</title></head><body><main>"
                               "<h1>Contact us</h1><p>Write to hello@example.com.</p></main></body></html>"),
    })


def test_a_missing_page_served_with_200_is_not_scored_as_content(serve):
    """Round three's dry run, MDN: /en-US/404 answers 200 with "Page not found"
    and 58 characters. It was scored like any page and turned up as an example
    on every finding - the report asked for llms.txt and schema on a 404 page.
    """
    from geo_audit.commands.common import Options, load_page

    site = _soft_404_site(serve)
    page = load_page(f"{site.url}/missing", Options(allow_private=True, check_robots=False))
    assert not page.scorable
    assert page.failure["reason"] == "soft_404" and page.failure["status"] == 200
    assert [f.id for f in page.findings] == ["fetch.soft_404"]


@pytest.mark.parametrize("path", ["/about-404s", "/contact"])
def test_only_a_short_page_that_says_it_is_missing_is_a_soft_404(serve, path):
    """Each condition alone is ordinary: an article about 404s has one in its
    title, and plenty of real pages are short."""
    from geo_audit.commands.common import Options, load_page

    site = _soft_404_site(serve)
    page = load_page(f"{site.url}{path}", Options(allow_private=True, check_robots=False))
    assert page.scorable and page.failure is None


def test_a_finding_seen_on_several_pages_is_one_finding_with_a_page_list(site, geo_home):
    """Twelve copies of one problem is one problem affecting twelve pages."""
    _, envelope = run_cli(
        ["crawl", f"{site.url}/hub.html", "--allow-private", "--rate", "50", "--max-pages", "20"]
    )
    ids = [finding["id"] for finding in envelope["findings"]]
    assert len(ids) == len(set(ids)), "findings must not repeat"
    blocked = [f for f in envelope["findings"] if f["id"] == "robots.ai_crawler_blocked"]
    if blocked:
        assert len(blocked[0]["pages"]) > 1, "one finding should carry every page it affects"
        assert blocked[0]["pages"] == sorted(blocked[0]["pages"])


def test_robots_is_fetched_once_for_the_whole_crawl(site):
    site.reset_requests()
    run_crawl(site, max_pages=20)
    assert [p for p in site.requests_seen if p == "/robots.txt"] == ["/robots.txt"]


# --- evidence --------------------------------------------------------------


def test_the_site_hash_does_not_depend_on_visit_order(site):
    first = run_crawl(site, max_pages=20, concurrency=1)
    second = run_crawl(site, max_pages=20, concurrency=5)
    digest = lambda result: evidence.site_digest(  # noqa: E731
        [evidence.digest(page.doc.blocks) for page in result.ok_pages]
    )
    assert digest(first) == digest(second)


def test_the_site_hash_changes_when_a_page_changes():
    a = evidence.site_digest(["aa", "bb"])
    b = evidence.site_digest(["aa", "cc"])
    assert a != b
    assert evidence.site_digest(["bb", "aa"]) == a


# --- the command -----------------------------------------------------------


def run_cli(args):
    buffer = io.StringIO()
    code = main(args + ["--json", "--quiet"], out=buffer)
    return code, json.loads(buffer.getvalue())


def test_the_crawl_command_reports_the_frontier(site, geo_home):
    code, envelope = run_cli(
        ["crawl", f"{site.url}/hub.html", "--allow-private", "--rate", "50", "--max-pages", "20"]
    )
    assert code == 0
    block = envelope["crawl"]
    assert block["pages_ok"] >= 6
    assert block["disallowed_by_robots"]
    assert block["seeded_from_sitemap"] == 2
    assert block["limits"]["requests_per_second"] == 50
    assert envelope["evidence"]["stamp"] == "PARTIAL", "the 404 and the JSON endpoint failed"
    assert envelope["evidence"]["content_hash"]


def test_crawl_defaults_are_the_documented_ones():
    from geo_audit.cli import _fill_defaults, build_parser

    # The numeric defaults are filled after `--config` is read rather than by
    # argparse, so that a config file can tell "unset" from "passed".
    args = build_parser().parse_args(["crawl", "https://example.com"])
    _fill_defaults(args)
    assert args.max_pages == MAX_PAGES == 50
    assert args.rate == REQUESTS_PER_SECOND == 1.0
    assert args.concurrency == CONCURRENCY == 5
    assert args.timeout == 30.0
    assert args.no_robots is False
    assert args.no_sitemap is False


def test_a_partial_crawl_exits_zero_unless_asked_otherwise(site, geo_home):
    args = ["crawl", f"{site.url}/hub.html", "--allow-private", "--rate", "50", "--max-pages", "20"]
    assert run_cli(args)[0] == 0
    buffer = io.StringIO()
    assert main(args + ["--json", "--quiet", "--fail-on-partial"], out=buffer) == 5


def test_crawl_output_carries_no_page_text(site, geo_home):
    buffer = io.StringIO()
    main(
        ["crawl", f"{site.url}/hub.html", "--allow-private", "--rate", "50",
         "--max-pages", "20", "--json", "--quiet"],
        out=buffer,
    )
    raw = buffer.getvalue()
    assert "Server-side rendering puts the full text" not in raw
    assert "Fixture Press publishes four articles" not in raw
    for page in json.loads(raw)["crawl"]["pages"]:
        assert set(page) <= {
            "url", "status", "blocks", "content_chars", "content_root",
            "content_hash", "headings", "jsonld_types", "scorable",
        }


def test_a_start_url_that_redirects_into_the_sitemap_is_scored_once(serve):
    """Round three's dry run, MDN: the start URL redirects to /en-US/ and the
    sitemap lists /en-US/ too. Two requests, one page - fetched twice, scored
    twice, so the homepage carried double weight in every average and the
    report said "8 pages scored" over seven. The same shape as any apex-to-www
    or locale redirect, which is most sites.
    """
    from tests.fixture_server import Reply, site_routes

    routes = site_routes()
    routes["/start"] = Reply(status=302, body="moved", headers={"Location": "/schema-broken.html"})
    site = serve(routes)

    result = crawl(f"{site.url}/start", CrawlOptions(**{**FAST, "use_sitemap": True, "max_pages": 10}))
    landed = [normalize_url(p.result.final_url if p.result else p.url) for p in result.pages]
    assert len(landed) == len(set(landed)), f"scored twice: {sorted(landed)}"
    assert normalize_url(f"{site.url}/schema-broken.html") in landed


# --- bot challenges ------------------------------------------------------------


def _challenge_site(serve):
    from tests.fixture_server import Reply

    interstitial = ("<html><head><title>Just a moment...</title></head><body>"
                    "<div id='cf-chl-widget'>Checking your browser before accessing the site.</div></body></html>")
    real = "<p>" + "A page that happens to carry a signup form with a challenge-platform widget. " * 30 + "</p>"
    return serve({
        "/challenge-503": Reply(status=503, body=interstitial),
        "/challenge-header": Reply(body=interstitial, headers={"cf-mitigated": "challenge"}),
        "/widget-page": Reply(body=f"<html><head><title>Sign up</title></head><body><main><h1>Sign up</h1>{real}</main></body></html>"),
        "/down": Reply(status=503, body="<html><body><h1>Service Unavailable</h1></body></html>"),
    })


@pytest.mark.parametrize("path", ["/challenge-503", "/challenge-header"])
def test_a_bot_challenge_is_blocked_whatever_its_status(serve, path):
    """PRD §3.2: bot-blocked means 403 *or challenge*. A Cloudflare interstitial
    served with 503 was called a server error - telling a client to repair a
    server that works - and one served with 200 would have been scored."""
    from geo_audit.commands.common import Options, load_page

    site = _challenge_site(serve)
    page = load_page(f"{site.url}{path}", Options(allow_private=True, check_robots=False))
    assert page.failure["reason"] == "bot_blocked"
    assert [f.id for f in page.findings] == ["fetch.blocked"]


@pytest.mark.parametrize("path, reason", [("/widget-page", None), ("/down", "server_error")])
def test_a_widget_or_a_real_outage_is_not_a_challenge(serve, path, reason):
    """A real page may carry a captcha widget, and a real 503 is a real outage."""
    from geo_audit.commands.common import Options, load_page

    site = _challenge_site(serve)
    page = load_page(f"{site.url}{path}", Options(allow_private=True, check_robots=False))
    assert (page.failure or {}).get("reason") == reason
