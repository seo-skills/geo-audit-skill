"""Per-surface plumbing: the parts of platform readiness nothing else scores.

This category is deliberately narrow. Crawler access is technical, answer-shaped
schema types are `schema.breadth`, and whether the writing is any good is
content. Scoring any of them again here would mean one fact moving the
composite twice, which makes a score impossible to explain and easy to game.

What is left is the plumbing each answer surface actually reads: the llms.txt
convention, the preview card an engine builds a link from, the feeds that let
a crawler find pages nothing links to, and the language annotations that stop
an engine guessing which variant answers a question.
"""

from __future__ import annotations

import re

from geo_audit import data
from geo_audit.lib.extract import Document
from geo_audit.scoring.model import Signal

FEED_TYPES = ("application/rss+xml", "application/atom+xml", "application/feed+json")
SOCIAL_KEYS = ("og:title", "og:description", "og:image")
TWITTER_KEYS = ("twitter:card", "twitter:title", "twitter:description", "twitter:image")


def llms_txt(present: bool | None, valid: bool | None) -> tuple[float | None, dict]:
    if present is None:
        return None, {"reason": "the site was not checked for an llms.txt"}
    if not present:
        return 0.0, {"present": False, "valid": None}
    return (35.0 if valid else 20.0), {
        "present": True,
        "valid": bool(valid),
        "note": None if valid else "present but not in the documented structure",
    }


def social_cards(doc: Document) -> tuple[float | None, dict]:
    """What an engine builds a link preview from."""
    open_graph = [key for key in SOCIAL_KEYS if doc.meta.get(key)]
    twitter = [key for key in TWITTER_KEYS if doc.meta.get(key)]

    core = 24 * (len(open_graph) / len(SOCIAL_KEYS))
    extra = 6.0 if twitter else 0.0
    return core + extra, {
        "open_graph_present": open_graph,
        "open_graph_missing": [key for key in SOCIAL_KEYS if key not in open_graph],
        "twitter_present": twitter,
        "breakdown": {"open_graph": round(core, 2), "twitter": extra},
    }


def feeds(html: str, sitemaps: list[str] | None) -> tuple[float | None, dict]:
    """Ways to find pages that nothing links to yet."""
    has_feed = bool(
        re.search(
            r'<link[^>]+type=["\'](?:' + "|".join(re.escape(t) for t in FEED_TYPES) + r')["\']',
            html or "",
            re.IGNORECASE,
        )
    )
    sitemap_count = len(sitemaps or [])
    sitemap_points = 14.0 if sitemap_count else 0.0
    feed_points = 6.0 if has_feed else 0.0
    return sitemap_points + feed_points, {
        "sitemaps_in_robots": sitemap_count,
        "feed_link": has_feed,
        "breakdown": {"sitemap": sitemap_points, "feed": feed_points},
    }


def hreflang(doc: Document, html: str, languages_seen: set[str] | None) -> tuple[float | None, dict]:
    """Only applicable when the site actually has more than one language.

    Scoring a single-language site zero for having no hreflang would be
    marking it down for a problem it does not have.
    """
    annotations = re.findall(
        r'<link[^>]+hreflang=["\']([^"\']+)["\']', html or "", re.IGNORECASE
    )
    languages = {lang.split("-")[0].lower() for lang in (languages_seen or set()) if lang}

    if len(languages) < 2 and not annotations:
        return None, {
            "reason": "only one language was seen on this site, so hreflang does not apply",
            "languages_seen": sorted(languages),
        }

    if not annotations:
        return 0.0, {"annotations": 0, "languages_seen": sorted(languages)}

    has_default = any(value.lower() == "x-default" for value in annotations)
    points = 10.0 + (5.0 if has_default else 0.0)
    return points, {
        "annotations": len(annotations),
        "x_default": has_default,
        "languages_declared": sorted({value.lower() for value in annotations}),
        "languages_seen": sorted(languages),
    }


def score(page, site_facts: dict) -> list[Signal]:
    """`site_facts` carries what is true of the site rather than the page."""
    spec = data.weights()["platform"]["signals"]
    doc = page.doc
    url = page.result.final_url if page.result else page.url
    html = page.result.body if page.result else ""

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
        unmeasured = (None, {"reason": "the page returned no markup to inspect"})
        return [
            build("platform.llms_txt", llms_txt(site_facts.get("llms_present"), site_facts.get("llms_valid"))),
            build("platform.social_cards", unmeasured),
            build("platform.feeds", feeds(html, site_facts.get("sitemaps"))),
            build("platform.hreflang", unmeasured),
        ]

    return [
        build("platform.llms_txt", llms_txt(site_facts.get("llms_present"), site_facts.get("llms_valid"))),
        build("platform.social_cards", social_cards(doc)),
        build("platform.feeds", feeds(html, site_facts.get("sitemaps"))),
        build("platform.hreflang", hreflang(doc, html, site_facts.get("languages"))),
    ]
