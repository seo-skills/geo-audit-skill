"""Technical signals: can a crawler reach, read and index the page at all?

Everything here is deterministic - parsed facts about the response and the
markup - except URL structure, which is a stated convention rather than a
rule. These signals gate the others: a page no crawler may fetch cannot be
cited no matter how well it is written.
"""

from __future__ import annotations

import re
from urllib.parse import urlsplit

from geo_audit import data
from geo_audit.lib.extract import Document
from geo_audit.scoring.model import Signal

NOINDEX = re.compile(r"\bnoindex\b", re.IGNORECASE)
NOFOLLOW = re.compile(r"\bnofollow\b", re.IGNORECASE)
SESSION_PARAM = re.compile(r"\b(?:phpsessid|jsessionid|sid|sessionid|session_id)=", re.IGNORECASE)

MAX_TITLE = 65
MIN_TITLE = 15
MAX_DESCRIPTION = 160
MIN_DESCRIPTION = 70
MAX_PATH_DEPTH = 4
MAX_PATH_LENGTH = 100


def crawler_access(robots, path: str) -> tuple[float | None, dict]:
    """Are the crawlers that gate an answer surface allowed to read this?

    Training tokens and search tokens are scored differently on purpose.
    Refusing GPTBot while allowing OAI-SearchBot is a coherent position; being
    absent from the search index is not a position, it is an outcome.
    """
    crawlers = data.crawlers()
    if robots is None:
        return None, {"reason": "robots.txt was not checked"}

    critical = [c for c in crawlers if c["critical"]]
    optional = [c for c in crawlers if not c["critical"]]
    blocked_critical = [c["token"] for c in critical if not robots.allows(c["token"], path)]
    blocked_optional = [c["token"] for c in optional if not robots.allows(c["token"], path)]

    if robots.unreachable:
        return 0.0, {
            "reason": "robots.txt is unreachable, which RFC 9309 makes a complete disallow",
            "robots_status": robots.status,
            "blocked_critical": [c["token"] for c in critical],
        }

    allowed = len(critical) - len(blocked_critical)
    points = 25 * (allowed / len(critical)) if critical else 25.0
    return points, {
        "critical_total": len(critical),
        "critical_allowed": allowed,
        "blocked_critical": blocked_critical,
        "blocked_training_only": blocked_optional,
        "robots_status": robots.status,
    }


def indexability(doc: Document, headers: dict) -> tuple[float | None, dict]:
    meta_robots = doc.meta.get("robots", "")
    header_robots = headers.get("x-robots-tag", "")
    combined = f"{meta_robots} {header_robots}"

    noindex = bool(NOINDEX.search(combined))
    nofollow = bool(NOFOLLOW.search(combined))
    canonical = doc.meta.get("canonical")

    points = 20.0
    if noindex:
        points = 0.0
    else:
        if nofollow:
            points -= 6
        if not canonical:
            points -= 4
    return max(points, 0.0), {
        "noindex": noindex,
        "nofollow": nofollow,
        "meta_robots": meta_robots or None,
        "x_robots_tag": header_robots or None,
        "canonical": canonical,
    }


def metadata(doc: Document) -> tuple[float | None, dict]:
    title = doc.title or ""
    description = doc.meta.get("description", "")

    title_points = 0.0
    if title:
        title_points = 4.0 if MIN_TITLE <= len(title) <= MAX_TITLE else 2.0
    description_points = 0.0
    if description:
        description_points = 4.0 if MIN_DESCRIPTION <= len(description) <= MAX_DESCRIPTION else 2.0

    lang_points = 3.0 if doc.lang else 0.0
    h1_points = 3.0 if sum(1 for level, _ in doc.headings if level == 1) == 1 else 0.0
    og_points = 3.0 if any(key.startswith("og:") for key in doc.meta) else 0.0
    alt_points = 0.0
    if doc.images:
        alt_points = 3.0 * (doc.images_with_alt / doc.images)
    else:
        alt_points = 3.0

    points = title_points + description_points + lang_points + h1_points + og_points + alt_points
    return points, {
        "title_chars": len(title) or None,
        "description_chars": len(description) or None,
        "lang": doc.lang,
        "h1_count": sum(1 for level, _ in doc.headings if level == 1),
        "open_graph": og_points > 0,
        "images": doc.images,
        "images_with_alt": doc.images_with_alt,
        "breakdown": {
            "title": round(title_points, 2),
            "description": round(description_points, 2),
            "lang": lang_points,
            "single_h1": h1_points,
            "open_graph": og_points,
            "image_alt": round(alt_points, 2),
        },
        "limits": {
            "title_chars": [MIN_TITLE, MAX_TITLE],
            "description_chars": [MIN_DESCRIPTION, MAX_DESCRIPTION],
        },
    }


def status_health(status: int | None, redirect_hops: int) -> tuple[float | None, dict]:
    if status is None:
        return 0.0, {"reason": "no response", "status": None, "redirect_hops": redirect_hops}
    points = 15.0 if 200 <= status < 300 else 0.0
    if points and redirect_hops:
        points -= min(redirect_hops * 2.0, 6.0)
    return max(points, 0.0), {
        "status": status,
        "redirect_hops": redirect_hops,
        "penalty_per_hop": 2,
    }


def transport_security(url: str, headers: dict) -> tuple[float | None, dict]:
    https = urlsplit(url).scheme.lower() == "https"
    hsts = bool(headers.get("strict-transport-security"))
    points = (7.0 if https else 0.0) + (3.0 if https and hsts else 0.0)
    return points, {
        "https": https,
        "hsts": hsts,
        "breakdown": {"https": 7 if https else 0, "hsts": 3 if https and hsts else 0},
    }


def url_structure(url: str) -> tuple[float | None, dict]:
    parts = urlsplit(url)
    path = parts.path or "/"
    segments = [segment for segment in path.split("/") if segment]

    checks = {
        "depth_within_limit": len(segments) <= MAX_PATH_DEPTH,
        "length_within_limit": len(path) <= MAX_PATH_LENGTH,
        "lowercase": path == path.lower(),
        "no_underscores": "_" not in path,
        "no_session_id": not SESSION_PARAM.search(parts.query or ""),
    }
    points = 10 * (sum(checks.values()) / len(checks))
    return points, {
        "path": path,
        "depth": len(segments),
        "checks": checks,
        "limits": {"depth": MAX_PATH_DEPTH, "length": MAX_PATH_LENGTH},
    }


def score(page, robots) -> list[Signal]:
    """Six signals for one page. `page` is a commands.common.Page."""
    spec = data.weights()["technical"]["signals"]
    doc = page.doc
    result = page.result
    url = result.final_url if result else page.url
    headers = result.headers if result else {}
    path = urlsplit(url).path or "/"

    def build(signal_id: str, outcome: tuple[float | None, dict]) -> Signal:
        points, detail = outcome
        meta = spec[signal_id]
        return Signal(
            id=signal_id,
            cls=meta["class"],
            max=meta["max"],
            value=points,
            detail=detail,
            page=url,
            skipped_reason=detail.get("reason") if points is None else None,
        )

    if doc is None:
        # The page has no markup to inspect, so the markup signals are *not
        # measured*, not failed. Scoring them zero would count one 404 twice:
        # once in status_health, where it belongs, and again as an indexing
        # and metadata problem that nobody can act on.
        unmeasured = (None, {"reason": "the page returned no markup to inspect"})
        return [
            build("technical.crawler_access", crawler_access(robots, path)),
            build("technical.indexability", unmeasured),
            build("technical.metadata", unmeasured),
            build(
                "technical.status_health",
                status_health(result.status if result else None, len(result.chain) if result else 0),
            ),
            build("technical.transport_security", transport_security(url, headers)),
            build("technical.url_structure", url_structure(url)),
        ]

    return [
        build("technical.crawler_access", crawler_access(robots, path)),
        build("technical.indexability", indexability(doc, headers)),
        build("technical.metadata", metadata(doc)),
        build("technical.status_health", status_health(result.status, len(result.chain))),
        build("technical.transport_security", transport_security(url, headers)),
        build("technical.url_structure", url_structure(url)),
    ]
