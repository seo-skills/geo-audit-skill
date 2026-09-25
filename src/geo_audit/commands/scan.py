"""`geo scan` - does this brand exist as an entity anyone can look up?

Real checks or nothing. Every platform here is queried through its documented
public API and reports a count with the time it was observed. Platforms with
no usable API are listed separately as manual checks and are never emitted as
a result: a check nobody performed is not a finding, and inventing one is the
fastest way to make an audit untrustworthy.

Per-platform failure is per-platform. A rate limit at Reddit is an error entry
against Reddit, not a failed command, because the Wikipedia answer is still
worth having.
"""

from __future__ import annotations

import json
import os
from urllib.parse import quote_plus

from geo_audit import assistants, data, envelope
from geo_audit import copy as copytext
from geo_audit.errors import GeoError
from geo_audit.lib import http
from geo_audit.lib.extract import excerpt
from geo_audit.lib.slug import host_of
from geo_audit.scoring.model import LIVE, Signal, composite, findings_for, prioritize

TIMEOUT = 15.0
MAX_BYTES = 2_000_000
MAX_TITLES = 5


def _platforms() -> dict:
    return data.load("brand_platforms")["platforms"]


def _query(brand: str, spec: dict, key: str | None) -> str:
    return spec["url"].format(query=quote_plus(brand), key=quote_plus(key or ""))


def _count_results(name: str, payload: dict) -> tuple[int, list[str]]:
    """Each API answers in its own shape; this is the only place that knows."""
    if name == "wikipedia":
        hits = (payload.get("query") or {}).get("search") or []
        return len(hits), [hit.get("title", "") for hit in hits[:MAX_TITLES]]
    if name == "wikidata":
        hits = payload.get("search") or []
        return len(hits), [
            f"{hit.get('id', '')} {hit.get('label', '')}".strip() for hit in hits[:MAX_TITLES]
        ]
    if name == "reddit":
        children = ((payload.get("data") or {}).get("children")) or []
        return len(children), [
            ((child.get("data") or {}).get("title") or "") for child in children[:MAX_TITLES]
        ]
    if name == "youtube":
        items = payload.get("items") or []
        return len(items), [
            ((item.get("snippet") or {}).get("title") or "") for item in items[:MAX_TITLES]
        ]
    return 0, []


def check(name: str, brand: str, spec: dict, allow_private: bool = False) -> dict:
    observed = envelope.now_iso()
    key_name = spec.get("needs_key")
    key = os.environ.get(key_name) if key_name else None
    if key_name and not key:
        return {
            "platform": name,
            "label": spec["label"],
            "checked": False,
            "reason": f"no API key: set {key_name} to enable this check",
            "docs": spec["docs"],
            "observed_at": observed,
        }

    url = _query(brand, spec, key)
    try:
        result = http.fetch(
            url,
            allow_private=allow_private,
            timeout=TIMEOUT,
            max_bytes=MAX_BYTES,
            accept_types=None,
        )
    except GeoError as error:
        return {
            "platform": name,
            "label": spec["label"],
            "checked": False,
            "reason": f"{error.code}: {error.message}",
            "docs": spec["docs"],
            "observed_at": observed,
        }

    if not result.ok:
        return {
            "platform": name,
            "label": spec["label"],
            "checked": False,
            "status": result.status,
            "reason": (
                f"{spec['label']} returned {result.status}"
                + (" - it rate-limits unauthenticated clients" if result.status == 429 else "")
            ),
            "docs": spec["docs"],
            "observed_at": observed,
        }

    try:
        payload = json.loads(result.body)
    except json.JSONDecodeError:
        return {
            "platform": name,
            "label": spec["label"],
            "checked": False,
            "status": result.status,
            "reason": f"{spec['label']} did not return JSON",
            "docs": spec["docs"],
            "observed_at": observed,
        }

    count, titles = _count_results(name, payload)
    return {
        "platform": name,
        "label": spec["label"],
        "checked": True,
        "status": result.status,
        "results": count,
        # Third-party text: capped and delimiter-escaped like any other.
        "examples": [excerpt(title, 120) for title in titles if title],
        "docs": spec["docs"],
        "observed_at": observed,
    }


def _signal(signal_id: str, value: float | None, detail: dict, spec: dict) -> Signal:
    meta = spec[signal_id]
    return Signal(
        id=signal_id,
        cls=meta["class"],
        max=meta["max"],
        value=value,
        detail=detail,
        skipped_reason=detail.get("reason") if value is None else None,
    )


def build_signals(results: dict[str, dict], same_as: list[str] | None) -> list[Signal]:
    spec = data.weights()["brand"]["signals"]
    signals: list[Signal] = []

    wikipedia, wikidata = results.get("wikipedia", {}), results.get("wikidata", {})
    if not wikipedia.get("checked") and not wikidata.get("checked"):
        signals.append(
            _signal(
                "brand.encyclopedic",
                None,
                {"reason": "neither Wikipedia nor Wikidata could be checked",
                 "wikipedia": wikipedia.get("reason"), "wikidata": wikidata.get("reason")},
                spec,
            )
        )
    else:
        points = 0.0
        if wikipedia.get("checked") and wikipedia.get("results"):
            points += 20
        if wikidata.get("checked") and wikidata.get("results"):
            points += 15
        signals.append(
            _signal(
                "brand.encyclopedic",
                points,
                {
                    "wikipedia_results": wikipedia.get("results"),
                    "wikidata_results": wikidata.get("results"),
                    "breakdown": {"wikipedia": 20, "wikidata": 15},
                },
                spec,
            )
        )

    reddit = results.get("reddit", {})
    if not reddit.get("checked"):
        signals.append(_signal("brand.community", None, {"reason": reddit.get("reason", "not checked")}, spec))
    else:
        count = reddit.get("results", 0)
        signals.append(
            _signal(
                "brand.community",
                25 * min(count / 10, 1.0),
                {"reddit_results": count, "full_marks_at": 10},
                spec,
            )
        )

    youtube = results.get("youtube", {})
    if not youtube.get("checked"):
        signals.append(_signal("brand.video", None, {"reason": youtube.get("reason", "not checked")}, spec))
    else:
        count = youtube.get("results", 0)
        signals.append(
            _signal(
                "brand.video",
                20 * min(count / 5, 1.0),
                {"youtube_results": count, "full_marks_at": 5},
                spec,
            )
        )

    if same_as is None:
        signals.append(
            _signal("brand.consistency", None, {"reason": "no --site was given, so nothing to compare"}, spec)
        )
    else:
        hosts = {host_of(url) for url in same_as}
        expected = {"wikipedia.org", "en.wikipedia.org", "wikidata.org"}
        linked = sorted(host for host in hosts if host)
        matched = [host for host in linked if any(host.endswith(name) for name in expected)]
        points = 0.0
        if linked:
            points += 10
        if matched:
            points += 10
        signals.append(
            _signal(
                "brand.consistency",
                points,
                {
                    "same_as_count": len(same_as),
                    "linked_hosts": linked,
                    "links_to_encyclopedic": matched,
                    "breakdown": {"any_same_as": 10, "encyclopedic_same_as": 10},
                },
                spec,
            )
        )
    return signals


def _same_as_for(url: str, allow_private: bool, timeout: float) -> list[str] | None:
    from geo_audit.commands.common import Options, load_page
    from geo_audit.scoring import schema_org

    page = load_page(url, Options(allow_private=allow_private, timeout=timeout))
    if page.doc is None:
        return None
    for node in schema_org._nodes_of(page.doc, set(data.load("schema_requirements")["entity_types"])):
        same_as = node.get("sameAs")
        if isinstance(same_as, str):
            return [same_as]
        if isinstance(same_as, list):
            return [str(entry) for entry in same_as]
    return []


def announcer(args, brand: str):
    """The progress line an ask prints on stderr, or None under --quiet."""
    if getattr(args, "quiet", False):
        return None

    def say(engines: str, credits: int) -> None:
        import sys

        print(copytext.ASKING_ASSISTANTS.format(engines=engines, brand=brand, credits=credits), file=sys.stderr)

    return say


def run(args, run_id: str) -> dict:
    brand = args.brand.strip()
    if not brand:
        raise GeoError("GEO_E_BAD_ARGS", "Give a brand name to scan, for example `geo scan Acme`.")
    requested = assistants.parse_engines(args.assistants) if getattr(args, "assistants", None) else []

    results = {
        name: check(name, brand, spec, allow_private=args.allow_private)
        for name, spec in _platforms().items()
    }

    same_as = None
    if getattr(args, "site", None):
        same_as = _same_as_for(args.site, args.allow_private, args.timeout)

    signals = build_signals(results, same_as)
    score, completeness = composite(signals)
    tier = data.tier_for(score)
    findings = prioritize(findings_for(signals, args.site or brand))

    checked = [entry for entry in results.values() if entry["checked"]]
    total_results = sum(entry.get("results", 0) for entry in checked)
    # Observed, never scored: nothing below feeds `signals`.
    asked = (
        {"assistants": assistants.ask(brand, getattr(args, "site", None), requested,
                                      allow_private=args.allow_private, say=announcer(args, brand))}
        if requested
        else {}
    )

    return envelope.build(
        "scan",
        ok=True,
        run_id=run_id,
        completeness=completeness,
        scores={
            "composite": score,
            "tier": tier["label"],
            "tier_meaning": tier["meaning"],
            "categories": {"brand": score},
        },
        signals=[signal.to_dict() for signal in signals],
        findings=[finding.to_dict() for finding in findings],
        extra={
            "scan": {
                "brand": brand,
                "site": getattr(args, "site", None),
                "platforms": list(results.values()),
                "platforms_checked": len(checked),
                "platforms_total": len(results),
                "total_results": total_results,
                "manual_checks": data.load("brand_platforms")["manual"],
                "same_as": same_as,
                **asked,
            }
        },
    )


__all__ = ["LIVE", "build_signals", "check", "run"]
