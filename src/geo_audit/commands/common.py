"""The page pipeline shared by `fetch` and `score`.

Fetch, extract, check robots, hash. Written once here because the moment it
exists twice the two copies start disagreeing about what a content block is,
and the evidence hash stops meaning anything.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import requests

from geo_audit import data
from geo_audit._version import NORMALIZER_VERSION
from geo_audit.errors import GeoError
from geo_audit.lib import evidence as evidence_lib
from geo_audit.lib import http, robots as robots_lib
from geo_audit.lib.extract import Document, extract
from geo_audit.scoring.model import Finding

# Statuses that mean "a crawler was turned away" rather than "the page moved".
BLOCKED_STATUSES = frozenset({401, 402, 403, 405, 406, 429, 451})


@dataclass
class Options:
    allow_private: bool = False
    timeout: float = http.DEFAULT_TIMEOUT
    max_bytes: int = http.DEFAULT_MAX_BYTES
    max_redirects: int = http.DEFAULT_MAX_REDIRECTS
    check_robots: bool = True
    render: bool = False


@dataclass
class Page:
    url: str
    result: http.FetchResult | None = None
    doc: Document | None = None
    robots: robots_lib.RobotsFile | None = None
    failure: dict | None = None
    findings: list[Finding] = field(default_factory=list)

    @property
    def scorable(self) -> bool:
        return self.doc is not None


def _check_finding(key: str, page_url: str, detail: str | None = None) -> Finding:
    template = data.finding_template("checks", key)
    return Finding(
        id=key,
        severity=template["severity"],
        effort=template["effort"],
        title=template["title"],
        remediation=template["remediation"],
        pages=[page_url],
        excerpt=detail,
        points_lost=0.0,
    )


def load_page(url: str, options: Options, session: requests.Session | None = None) -> Page:
    """Fetch and normalize one page.

    A blocked or erroring page is not an exception: it comes back as a Page
    with `failure` set and a critical finding attached. Refusing to report on
    a site because its bot protection works would abort exactly the audits
    that most need writing.
    """
    page = Page(url=url)
    owned = session is None
    session = session or http.new_session()

    try:
        if options.check_robots:
            page.robots = robots_lib.load(
                url,
                session=session,
                allow_private=options.allow_private,
                timeout=min(options.timeout, 10.0),
            )
            if page.robots.unreachable and page.robots.status and page.robots.status >= 500:
                page.findings.append(
                    _check_finding(
                        "robots.unreachable",
                        url,
                        f"{page.robots.source_url} returned {page.robots.status}",
                    )
                )

        result = http.fetch(
            url,
            allow_private=options.allow_private,
            timeout=options.timeout,
            max_bytes=options.max_bytes,
            max_redirects=options.max_redirects,
            session=session,
        )
        page.result = result

        if result.status in BLOCKED_STATUSES:
            page.failure = {"url": result.final_url, "reason": "bot_blocked", "status": result.status}
            page.findings.append(
                _check_finding("fetch.blocked", result.final_url, f"HTTP {result.status}")
            )
        elif result.status >= 500:
            page.failure = {"url": result.final_url, "reason": "server_error", "status": result.status}
            page.findings.append(
                _check_finding("fetch.server_error", result.final_url, f"HTTP {result.status}")
            )
        elif not result.ok:
            page.failure = {"url": result.final_url, "reason": "http_error", "status": result.status}
            page.findings.append(
                _check_finding("fetch.server_error", result.final_url, f"HTTP {result.status}")
            )
        else:
            page.doc = extract(result.body, result.final_url)

        if page.robots is not None and page.result is not None:
            page.findings.extend(_crawler_findings(page))
    finally:
        if owned:
            session.close()

    return page


def _crawler_findings(page: Page) -> list[Finding]:
    from urllib.parse import urlsplit

    assert page.robots is not None and page.result is not None
    path = urlsplit(page.result.final_url).path or "/"
    blocked = [
        entry["token"]
        for entry in data.crawlers()
        if entry["critical"] and not page.robots.allows(entry["token"], path)
    ]
    if not blocked:
        return []
    finding = _check_finding(
        "robots.ai_crawler_blocked",
        page.result.final_url,
        "blocked: " + ", ".join(blocked),
    )
    return [finding]


def robots_block(page: Page) -> dict | None:
    if page.robots is None:
        return None
    from urllib.parse import urlsplit

    target = page.result.final_url if page.result else page.url
    path = urlsplit(target).path or "/"
    return {
        "source_url": page.robots.source_url,
        "status": page.robots.status,
        "unavailable": page.robots.unavailable,
        "unreachable": page.robots.unreachable,
        "sitemaps": page.robots.sitemaps,
        "self_allowed": robots_lib.self_allows(page.robots, path),
        "access": robots_lib.access_matrix(page.robots, data.crawler_tokens(), path),
    }


def page_block(page: Page) -> dict:
    result = page.result
    block: dict = {
        "requested_url": page.url,
        "status": result.status if result else None,
        "final_url": result.final_url if result else page.url,
        "content_type": result.content_type if result else None,
        "bytes": result.body_bytes if result else 0,
        "elapsed_ms": result.elapsed_ms if result else 0,
        "encoding": result.encoding if result else None,
        "peer_verified": result.peer_verified if result else False,
        "redirect_chain": [
            {"url": hop.url, "status": hop.status, "location": hop.location}
            for hop in (result.chain if result else [])
        ],
        "blocks": len(page.doc.blocks) if page.doc else 0,
        "content_chars": page.doc.content_chars if page.doc else 0,
        "content_root": page.doc.content_root if page.doc else None,
        "headings": len(page.doc.headings) if page.doc else 0,
        "internal_links": len(page.doc.internal_links) if page.doc else 0,
        "external_links": len(page.doc.external_links) if page.doc else 0,
        "jsonld_types": sorted(
            {
                str(t)
                for node in (page.doc.jsonld if page.doc else [])
                for t in (
                    node["@type"] if isinstance(node.get("@type"), list) else [node.get("@type")]
                )
                if t
            }
        ),
        "jsonld_errors": page.doc.jsonld_errors if page.doc else [],
        "robots": robots_block(page),
    }
    if result:
        block["cache"] = {
            "etag": result.headers.get("etag"),
            "last_modified": result.headers.get("last-modified"),
        }
    return block


def evidence_block(page: Page) -> dict:
    content_hash = evidence_lib.digest(page.doc.blocks) if page.doc else None
    failed = [page.failure] if page.failure else []
    return {
        "stamp": evidence_lib.stamp_for(1 if page.scorable else 0, failed),
        "content_hash": content_hash,
        "normalizer_version": NORMALIZER_VERSION,
        "pages_ok": 1 if page.scorable else 0,
        "pages_failed": failed,
    }


def network_error_is_fatal(error: GeoError) -> bool:
    return error.exit_code == 3
