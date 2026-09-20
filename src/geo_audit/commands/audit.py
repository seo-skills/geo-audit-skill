"""`geo audit` - crawl a site and score every category over it.

The composite combines category scores by weight, over the categories that
were actually computed. A category nobody measured leaves both sides of the
fraction, exactly as a null signal does: `--only schema` scores out of schema,
not out of schema plus four zeroes.

`--rescore` recomputes from a stored record with no network at all. That is
where the reproducibility claim lives: re-crawling a live site can legitimately
differ, because the site changed. Rescoring a snapshot twice cannot.
"""

from __future__ import annotations

from geo_audit import copy as copytext
from geo_audit import data, envelope, state
from geo_audit.commands import crawl as crawl_cmd
from geo_audit.commands.common import Options
from geo_audit.errors import GeoError
from geo_audit.lib import crawl as crawl_lib
from geo_audit.lib.ids import is_run_id
from geo_audit.lib.slug import host_of, project_slug
from geo_audit.scoring import (
    citability,
    content as content_scorer,
    platform as platform_scorer,
    schema_org,
    technical,
)
from geo_audit.scoring.model import (
    Signal,
    aggregate,
    apply_impact,
    composite,
    findings_for,
    merge,
    prioritize,
    weighted_composite,
)

# What an audit can compute from a URL alone. `brand` needs a name, so it
# joins the run only when --brand is given: a category the inputs cannot
# reach is not "missing", it is out of scope for that run.
SITE_CATEGORIES = ("citability", "technical", "schema", "content", "platform")
CATEGORIES = SITE_CATEGORIES + ("brand",)


def candidates(args) -> tuple[str, ...]:
    """The categories this run's inputs can reach."""
    if getattr(args, "brand", None):
        return SITE_CATEGORIES + ("brand",)
    return SITE_CATEGORIES


def parse_only(value: str | None, available: tuple[str, ...] = CATEGORIES) -> tuple[str, ...]:
    if not value:
        return available
    chosen = tuple(part.strip().lower() for part in value.split(",") if part.strip())
    unknown = [name for name in chosen if name not in CATEGORIES]
    if unknown:
        raise GeoError(
            "GEO_E_BAD_ARGS",
            f"--only does not know {', '.join(unknown)}. "
            f"Available: {', '.join(CATEGORIES)}.",
        )
    out_of_scope = [name for name in chosen if name not in available]
    if out_of_scope:
        raise GeoError(
            "GEO_E_BAD_ARGS",
            f"--only {', '.join(out_of_scope)} needs an input this run does not "
            f"have. `brand` needs --brand <name>.",
        )
    return chosen


def _site_facts(result, args) -> dict:
    """What is true of the site rather than of any one page.

    Fetched once per run. Identical on every page, so `aggregate` carries it up
    to the site-level signal verbatim instead of averaging it away.
    """
    from geo_audit.commands import llmstxt as llmstxt_cmd
    from geo_audit.commands.common import Options

    facts: dict = {
        "sitemaps": list(result.robots.sitemaps) if result.robots else [],
        "languages": {page.doc.lang for page in result.ok_pages if page.doc and page.doc.lang},
        "llms_present": None,
        "llms_valid": None,
    }
    options = Options(allow_private=args.allow_private, timeout=args.timeout)
    from urllib.parse import urlsplit

    parts = urlsplit(args.url)
    found = llmstxt_cmd._fetch_optional(
        f"{parts.scheme}://{parts.netloc}{llmstxt_cmd.CANONICAL_PATH}", options
    )
    facts["llms_present"] = bool(found.get("present"))
    facts["llms_valid"] = bool(found.get("valid")) if found.get("present") else None
    return facts


def _forced(signal: Signal) -> Signal:
    """A copy scored at zero, so `findings_for` produces the finding's copy.

    The severity and the points are overwritten by the caller; this exists only
    to reach the template without duplicating the lookup.
    """
    return Signal(id=signal.id, cls=signal.cls, max=signal.max, value=0.0, detail=signal.detail)


def _score_page(page, robots, categories: tuple[str, ...], site_facts: dict | None = None) -> dict[str, list[Signal]]:
    scored: dict[str, list[Signal]] = {}
    if "citability" in categories and page.doc is not None:
        # An audit never opens a browser: fifty pages through Chromium is a
        # different product. `geo score` renders a single page.
        scored["citability"] = citability.score(page.doc, rendered_chars=None)
    if "technical" in categories:
        scored["technical"] = technical.score(page, robots)
    if "schema" in categories and page.doc is not None:
        scored["schema"] = schema_org.score(page)
    if "content" in categories and page.doc is not None:
        scored["content"] = content_scorer.score(page)
    if "platform" in categories:
        scored["platform"] = platform_scorer.score(page, site_facts or {})
    return scored


def run(args, run_id: str) -> dict:
    if getattr(args, "rescore", None):
        return rescore(args, run_id)

    state.init()
    available = candidates(args)
    categories = parse_only(args.only, available)
    options = crawl_cmd.options_from(args)

    def progress(done: int, total: int, failed: int) -> None:
        if not args.quiet:
            import sys

            print(
                copytext.PROGRESS.format(
                    step=2,
                    total=4,
                    action=f"Crawling {host_of(args.url)} - {done}/{total} pages, {failed} failed",
                ),
                file=sys.stderr,
            )

    result = crawl_lib.crawl(args.url, options, progress=progress)
    site_facts = _site_facts(result, args) if "platform" in categories else {}

    per_category: dict[str, list[list[Signal]]] = {name: [] for name in categories}
    findings = []
    # Which pages are actually below the line for each signal. The finding's
    # severity and value come from the site, but the page list has to come from
    # the pages, or "8 pages" and "the one bad page" look identical.
    offenders: dict[str, list[str]] = {}
    severe: dict[str, list[str]] = {}
    rules = data.thresholds("findings")
    ceiling = rules["no_finding_above"]
    floor = rules["full_severity_below"]

    for page in result.pages:
        scored = _score_page(page, result.robots, categories, site_facts)
        url = page.result.final_url if page.result else page.url
        for signals in scored.values():
            for signal in signals:
                ratio = signal.ratio
                if ratio is None:
                    continue
                if ratio <= ceiling:
                    offenders.setdefault(signal.id, []).append(url)
                if ratio < floor:
                    severe.setdefault(signal.id, []).append(url)
        for name, signals in scored.items():
            per_category[name].append(signals)
        findings.extend(page.findings)

    advisory = content_scorer.advisory_signals() if "content" in categories else []

    extra = None
    if "brand" in categories:
        from geo_audit.commands import scan as scan_cmd

        platforms = {
            name: scan_cmd.check(name, args.brand, spec, allow_private=args.allow_private)
            for name, spec in data.load("brand_platforms")["platforms"].items()
        }
        same_as = scan_cmd._same_as_for(args.url, args.allow_private, args.timeout)
        brand_signals = scan_cmd.build_signals(platforms, same_as)
        per_category["brand"] = [brand_signals]
        findings.extend(findings_for(brand_signals, args.brand))
        extra = {
            "scan": {
                "brand": args.brand,
                "site": args.url,
                "platforms": list(platforms.values()),
                "platforms_checked": sum(1 for entry in platforms.values() if entry["checked"]),
                "platforms_total": len(platforms),
                "total_results": sum(entry.get("results", 0) for entry in platforms.values() if entry["checked"]),
                "manual_checks": data.load("brand_platforms")["manual"],
                "same_as": same_as,
            }
        }

    return _assemble(
        run_id=run_id,
        start_url=args.url,
        categories=categories,
        per_category=per_category,
        findings=findings,
        crawl_block=crawl_cmd.crawl_block(result, options),
        evidence=crawl_cmd.evidence_block(result),
        record=True,
        available=available,
        advisory=advisory,
        offenders=offenders,
        severe=severe,
        extra=extra,
    )


def _assemble(
    *,
    run_id: str,
    start_url: str,
    categories: tuple[str, ...],
    per_category: dict[str, list[list[Signal]]],
    findings: list,
    crawl_block: dict,
    evidence: dict,
    record: bool,
    available: tuple[str, ...] | None = None,
    advisory: list[Signal] | None = None,
    offenders: dict[str, list[str]] | None = None,
    severe: dict[str, list[str]] | None = None,
    extra: dict | None = None,
) -> dict:
    weights = data.weights()
    available = available or categories
    severe = severe or {}
    category_scores: dict[str, int] = {}
    category_completeness: dict[str, dict] = {}
    all_signals: list[Signal] = []

    site = (crawl_block or {}).get("site") or start_url
    for name in categories:
        pages = per_category.get(name) or []
        if not pages:
            continue
        rolled = aggregate(pages)
        score, completeness = composite(rolled)
        category_scores[name] = score
        category_completeness[name] = completeness
        all_signals.extend(rolled)
        # Generated from the rolled-up signal: a site does not have a problem
        # because one of its forty pages does.
        if offenders is not None:
            reported = set()
            for finding in findings_for(rolled, site):
                finding.pages = sorted(set(offenders.get(finding.id) or []))
                reported.add(finding.id)
                findings.append(finding)

            # A site can be healthy on average and still have a handful of
            # pages that are not. Those are worth naming - "two pages return
            # almost nothing to a crawler" is the specific, actionable half of
            # a report - but they are demoted, because a minority of pages is
            # not the site's problem, and their impact comes from the site
            # signal, so they rank below the site-wide items rather than above
            # them.
            for signal in rolled:
                if signal.id in reported or signal.ratio is None:
                    continue
                pages = sorted(set(severe.get(signal.id) or []))
                if not pages:
                    continue
                for finding in findings_for([_forced(signal)], site):
                    # A blocker on the whole site still leads; a blocker on one
                    # page of forty is a page to go and look at.
                    finding.mark_page_level()
                    finding.pages = pages
                    finding.points_lost = signal.max - (signal.value or 0.0)
                    findings.append(finding)

    # Only the categories this run could reach: a category the inputs cannot
    # feed is out of scope, not missing.
    total, coverage = weighted_composite(
        {name: weights[name]["weight"] for name in available}, category_scores
    )
    tier = data.tier_for(total)

    signal_counts = [c["computed"] for c in category_completeness.values()]
    signal_totals = [c["total"] for c in category_completeness.values()]
    completeness = {
        "computed": sum(signal_counts),
        "total": sum(signal_totals),
        "missing": sorted(
            signal
            for detail in category_completeness.values()
            for signal in detail["missing"]
        ),
        "categories": coverage,
    }

    # Advisory signals ride along with the data so the rubric is never separated
    # from what it is about. `composite()` filters on class, so they cannot
    # reach a number by any path.
    all_signals.extend(advisory or [])

    ranked = prioritize(
        apply_impact(
            merge(findings),
            all_signals,
            {name: weights[name]["weight"] for name in weights},
        )
    )
    result = envelope.build(
        "audit",
        ok=True,
        run_id=run_id,
        evidence=evidence,
        completeness=completeness,
        scores={
            "composite": total,
            "tier": tier["label"],
            "tier_meaning": tier["meaning"],
            "categories": category_scores,
        },
        signals=[signal.to_dict() for signal in all_signals],
        findings=[finding.to_dict() for finding in ranked],
        extra={"crawl": crawl_block, **(extra or {})},
    )

    if record:
        path = state.append_audit(project_slug(start_url), result)
        try:
            inside = path.relative_to(state.geo_home()).as_posix()
            result["crawl"]["record"] = f"{state.display_home()}/{inside}"
        except ValueError:
            result["crawl"]["record"] = str(path)
    return result


def rescore(args, run_id: str) -> dict:
    """Recompute from a stored record. No network, no crawl, no clock."""
    wanted = args.rescore
    if not is_run_id(wanted):
        raise GeoError(
            "GEO_E_BAD_ARGS",
            f"{wanted!r} is not a run id. Run ids are 26 characters and appear "
            f"as `run_id` in any envelope.",
        )

    state.init()
    slug = project_slug(args.url) if getattr(args, "url", None) else None
    record = _find_record(wanted, slug)
    if record is None:
        where = f"for {slug}" if slug else "in any project"
        raise GeoError(
            "GEO_E_BAD_ARGS",
            f"No audit with run id {wanted} was found {where}. "
            f"`geo audit --list` shows what is recorded.",
        )

    stored_signals = [
        Signal(
            id=entry["id"],
            cls=entry["class"],
            max=entry["max"],
            value=entry["value"],
            detail=entry.get("detail") or {},
            page=entry.get("page"),
            skipped_reason=entry.get("skipped_reason"),
        )
        for entry in record.get("signals") or []
    ]

    by_category: dict[str, list[list[Signal]]] = {}
    stored_advisory = [signal for signal in stored_signals if signal.cls == "advisory"]
    for signal in stored_signals:
        if signal.cls == "advisory":
            continue
        name = signal.id.split(".", 1)[0]
        by_category.setdefault(name, [[]])[0].append(signal)

    categories = tuple(name for name in CATEGORIES if name in by_category)
    findings: list = []

    current = {
        "scoring_version": envelope.SCORING_VERSION,
        "data_version": data.data_version(),
        "normalizer_version": envelope.NORMALIZER_VERSION,
    }
    recorded = {
        "scoring_version": record.get("scoring_version"),
        "data_version": record.get("data_version"),
        "normalizer_version": record.get("normalizer_version"),
    }
    rescore_block = {
        "run_id": wanted,
        "observed_at": record.get("observed_at"),
        "recorded_versions": recorded,
        "current_versions": current,
        "versions_match": recorded == current,
        "recorded_composite": (record.get("scores") or {}).get("composite"),
    }

    return _assemble(
        run_id=run_id,
        start_url=record.get("crawl", {}).get("start_url", ""),
        categories=categories,
        per_category={name: by_category[name] for name in categories},
        findings=findings,
        offenders={
            finding["id"]: finding.get("pages") or []
            for finding in record.get("findings") or []
        },
        crawl_block=record.get("crawl", {}),
        evidence=record.get("evidence") or {},
        record=False,
        available=categories,
        advisory=stored_advisory,
        extra={"rescore": rescore_block},
    )


def _find_record(run_id: str, slug: str | None) -> dict | None:
    slugs = [slug] if slug else _known_slugs()
    for candidate in slugs:
        records, _ = state.read_audits(candidate)
        for record in reversed(records):
            if record.get("run_id") == run_id:
                return record
    return None


def _known_slugs() -> list[str]:
    root = state.geo_home() / "projects"
    if not root.is_dir():
        return []
    return sorted(path.name for path in root.iterdir() if path.is_dir())
