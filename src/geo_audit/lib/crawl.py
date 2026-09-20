"""The crawl engine.

Three properties the rest of the product depends on:

* **The rate limit is global, not per worker.** Five workers running at one
  request per second each is five requests per second at the site, which is
  not what "one request per second" means to the person whose server it is.
  Concurrency exists to stop one slow page stalling the queue, not to go
  faster.
* **robots.txt governs discovery.** A URL the user typed is fetched; a URL we
  found by following a link is not fetched if robots disallows it. Etiquette
  applies to what we discover, not to what we were asked for.
* **A failed page is data.** Blocked, timed out and disallowed pages are
  recorded with a reason and reported, never raised. The crawl is PARTIAL, not
  aborted.
"""

from __future__ import annotations

import threading
import time
from collections import deque
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from urllib.parse import urldefrag, urlsplit, urlunsplit

import requests

from geo_audit.commands.common import Options, Page, load_page
from geo_audit.errors import GeoError
from geo_audit.lib import http, robots as robots_lib
from geo_audit.lib.slug import host_of

MAX_PAGES = 50
REQUESTS_PER_SECOND = 1.0
CONCURRENCY = 5
MAX_SITEMAP_URLS = 500
MAX_SITEMAP_BYTES = 5_000_000

# Extensions that are never a page. Cheaper than fetching and rejecting on
# content type, and it keeps the request budget for pages.
SKIP_SUFFIXES = (
    ".pdf", ".zip", ".gz", ".tar", ".rar", ".7z", ".dmg", ".exe", ".msi",
    ".jpg", ".jpeg", ".png", ".gif", ".webp", ".avif", ".svg", ".ico", ".bmp",
    ".mp3", ".mp4", ".mov", ".avi", ".webm", ".wav", ".ogg",
    ".css", ".js", ".mjs", ".map", ".json", ".xml", ".rss", ".atom",
    ".woff", ".woff2", ".ttf", ".otf", ".eot", ".csv", ".doc", ".docx", ".xls",
    ".xlsx", ".ppt", ".pptx",
)

# Parameters that identify a campaign, not a page. Dropping them stops one
# page being crawled once per inbound campaign.
TRACKING_PARAMS = (
    "utm_source", "utm_medium", "utm_campaign", "utm_term", "utm_content",
    "utm_id", "gclid", "fbclid", "msclkid", "mc_cid", "mc_eid", "ref",
    "_ga", "igshid", "si", "yclid", "dclid",
)


def normalize_url(url: str) -> str:
    """Collapse the forms of a URL that address the same page.

    Fragment dropped, host lowercased, default port dropped, tracking
    parameters removed, remaining query preserved and ordered.
    """
    url, _ = urldefrag(url.strip())
    parts = urlsplit(url)
    scheme = parts.scheme.lower()
    host = (parts.hostname or "").lower()
    port = parts.port
    if port and not ((scheme == "http" and port == 80) or (scheme == "https" and port == 443)):
        host = f"{host}:{port}"
    path = parts.path or "/"
    if len(path) > 1 and path.endswith("/"):
        path = path.rstrip("/") or "/"
    kept = []
    for pair in parts.query.split("&"):
        if not pair:
            continue
        name = pair.split("=", 1)[0].lower()
        if name in TRACKING_PARAMS:
            continue
        kept.append(pair)
    return urlunsplit((scheme, host, path, "&".join(sorted(kept)), ""))


def is_crawlable(url: str) -> bool:
    parts = urlsplit(url)
    if parts.scheme.lower() not in ("http", "https"):
        return False
    return not parts.path.lower().endswith(SKIP_SUFFIXES)


class Pacer:
    """A global request pacer.

    Reserves the next slot under a lock and then sleeps outside it, so five
    workers queue up behind one clock rather than each keeping their own.
    """

    def __init__(self, per_second: float) -> None:
        self.interval = 1.0 / per_second if per_second > 0 else 0.0
        self._lock = threading.Lock()
        self._next = 0.0

    def wait(self) -> None:
        if not self.interval:
            return
        with self._lock:
            start = max(time.monotonic(), self._next)
            self._next = start + self.interval
        delay = start - time.monotonic()
        if delay > 0:
            time.sleep(delay)


@dataclass
class CrawlOptions(Options):
    max_pages: int = MAX_PAGES
    requests_per_second: float = REQUESTS_PER_SECOND
    concurrency: int = CONCURRENCY
    use_sitemap: bool = True
    same_host_only: bool = True


@dataclass
class CrawlResult:
    start_url: str
    pages: list[Page] = field(default_factory=list)
    failures: list[dict] = field(default_factory=list)
    robots: robots_lib.RobotsFile | None = None
    discovered: int = 0
    disallowed: list[str] = field(default_factory=list)
    seeded_from_sitemap: int = 0
    elapsed_ms: int = 0
    stopped_because: str = "exhausted"

    @property
    def ok_pages(self) -> list[Page]:
        return [p for p in self.pages if p.scorable]


class _Sessions:
    """One keep-alive session per worker thread, closed together at the end."""

    def __init__(self) -> None:
        self._local = threading.local()
        self._all: list[requests.Session] = []
        self._lock = threading.Lock()

    def get(self) -> requests.Session:
        session = getattr(self._local, "session", None)
        if session is None:
            session = http.new_session()
            self._local.session = session
            with self._lock:
                self._all.append(session)
        return session

    def close(self) -> None:
        with self._lock:
            for session in self._all:
                session.close()
            self._all.clear()


def _sitemap_urls(
    robots: robots_lib.RobotsFile,
    options: CrawlOptions,
    session: requests.Session,
    pacer: "Pacer | None" = None,
) -> list[str]:
    """Seed from the sitemaps robots.txt advertises.

    A crawl that only follows links sees whatever the homepage links to, which
    on most sites is a fraction of the pages worth auditing. One level of
    sitemap index is followed; no deeper.
    """
    import re

    found: list[str] = []
    queue = deque(robots.sitemaps[:5])
    seen_sitemaps: set[str] = set()

    while queue and len(found) < MAX_SITEMAP_URLS:
        target = queue.popleft()
        if target in seen_sitemaps:
            continue
        seen_sitemaps.add(target)
        if pacer:
            pacer.wait()
        try:
            result = http.fetch(
                target,
                allow_private=options.allow_private,
                timeout=min(options.timeout, 15.0),
                max_bytes=MAX_SITEMAP_BYTES,
                accept_types=None,
                session=session,
            )
        except GeoError:
            continue
        if not result.ok:
            continue
        locations = re.findall(r"<loc>\s*([^<\s]+)\s*</loc>", result.body, re.IGNORECASE)
        if "<sitemapindex" in result.body[:2000].lower():
            for location in locations[:5]:
                if location not in seen_sitemaps:
                    queue.append(location)
            continue
        found.extend(locations)

    return found[:MAX_SITEMAP_URLS]


def crawl(
    start_url: str,
    options: CrawlOptions | None = None,
    progress=None,
) -> CrawlResult:
    options = options or CrawlOptions()
    started = time.monotonic()
    result = CrawlResult(start_url=start_url)
    sessions = _Sessions()
    pacer = Pacer(options.requests_per_second)

    try:
        if options.check_robots:
            pacer.wait()
            result.robots = robots_lib.load(
                start_url,
                session=sessions.get(),
                allow_private=options.allow_private,
                timeout=min(options.timeout, 10.0),
            )

        start_host = host_of(start_url)
        seen: set[str] = {normalize_url(start_url)}
        # The start URL first, then whatever the sitemap advertises, sorted.
        # Level one is therefore deterministic before a single page is fetched.
        seeds: list[str] = []

        if options.use_sitemap and result.robots is not None and result.robots.sitemaps:
            for url in _sitemap_urls(result.robots, options, sessions.get(), pacer):
                if not _acceptable(url, start_host, options, result, seen):
                    continue
                seen.add(normalize_url(url))
                seeds.append(url)
                result.seeded_from_sitemap += 1

        def fetch_one(url: str) -> Page:
            pacer.wait()
            return load_page(url, options, session=sessions.get(), robots=result.robots)

        # Level-synchronous breadth-first search. A whole level is dispatched,
        # every page in it is awaited, and only then are the links it found
        # sorted and promoted to the next level.
        #
        # The obvious alternative - enqueue links the moment a page returns -
        # makes the crawl depend on which pages answered fastest. With a page
        # cap that decides *which* pages get crawled, so the same site yields a
        # different set on a slower machine and `compare` reports pages as
        # added and removed when nothing changed. A crawl is rate-limited, not
        # latency-limited, so waiting out a level costs almost nothing.
        with ThreadPoolExecutor(max_workers=max(1, options.concurrency)) as pool:
            frontier = [start_url] + sorted(seeds, key=normalize_url)
            while frontier and len(result.pages) < options.max_pages:
                budget = options.max_pages - len(result.pages)
                level, frontier = frontier[:budget], frontier[budget:]

                futures = {pool.submit(fetch_one, url): url for url in level}
                discovered: list[str] = []
                for future in futures:
                    url = futures[future]
                    try:
                        page = future.result()
                    except GeoError as error:
                        result.failures.append(
                            {"url": url, "reason": _reason_for(error), "status": None}
                        )
                        continue

                    result.pages.append(page)
                    if page.failure:
                        result.failures.append(page.failure)
                    if progress:
                        progress(len(result.pages), options.max_pages, len(result.failures))

                    if page.doc is None:
                        continue
                    for link in page.doc.internal_links:
                        if not _acceptable(link, start_host, options, result, seen):
                            continue
                        seen.add(normalize_url(link))
                        result.discovered += 1
                        discovered.append(link)

                # Sorted, so the next level does not depend on which page in
                # this one happened to finish first.
                frontier.extend(sorted(discovered, key=normalize_url))

            if frontier and len(result.pages) >= options.max_pages:
                result.stopped_because = "max_pages"
    finally:
        sessions.close()

    result.elapsed_ms = int((time.monotonic() - started) * 1000)
    return result


def _acceptable(
    url: str,
    start_host: str,
    options: CrawlOptions,
    result: CrawlResult,
    seen: set[str],
) -> bool:
    if not is_crawlable(url):
        return False
    normalized = normalize_url(url)
    if normalized in seen:
        return False
    if options.same_host_only and host_of(url) != start_host:
        return False
    if result.robots is not None:
        path = urlsplit(url).path or "/"
        if not robots_lib.self_allows(result.robots, path):
            if len(result.disallowed) < 50:
                result.disallowed.append(url)
            return False
    return True


def _reason_for(error: GeoError) -> str:
    return {
        "GEO_E_TIMEOUT": "timeout",
        "GEO_E_DNS": "dns",
        "GEO_E_CONNECT": "connect",
        "GEO_E_TLS": "tls",
        "GEO_E_TOO_LARGE": "too_large",
        "GEO_E_BAD_CONTENT_TYPE": "not_html",
        "GEO_E_TOO_MANY_REDIRECTS": "redirect_loop",
        "GEO_E_REDIRECT_BLOCKED": "redirect_blocked",
        "GEO_E_PRIVATE_ADDRESS": "private_address",
    }.get(error.code, "error")
