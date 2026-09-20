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
from geo_audit.scoring import citability, schema_org, technical
from geo_audit.scoring.model import (
    Signal,
    aggregate,
    composite,
    findings_for,
    merge,
    prioritize,
    weighted_composite,
)

CATEGORIES = ("citability", "technical", "schema")


def parse_only(value: str | None) -> tuple[str, ...]:
    if not value:
        return CATEGORIES
    chosen = tuple(part.strip().lower() for part in value.split(",") if part.strip())
    unknown = [name for name in chosen if name not in CATEGORIES]
    if unknown:
        raise GeoError(
            "GEO_E_BAD_ARGS",
            f"--only does not know {', '.join(unknown)}. "
            f"Available: {', '.join(CATEGORIES)}.",
        )
    return chosen


def _score_page(page, robots, categories: tuple[str, ...]) -> dict[str, list[Signal]]:
    scored: dict[str, list[Signal]] = {}
    if "citability" in categories and page.doc is not None:
        # An audit never opens a browser: fifty pages through Chromium is a
        # different product. `geo score` renders a single page.
        scored["citability"] = citability.score(page.doc, rendered_chars=None)
    if "technical" in categories:
        scored["technical"] = technical.score(page, robots)
    if "schema" in categories and page.doc is not None:
        scored["schema"] = schema_org.score(page)
    return scored


def run(args, run_id: str) -> dict:
    if getattr(args, "rescore", None):
        return rescore(args, run_id)

    state.init()
    categories = parse_only(args.only)
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

    per_category: dict[str, list[list[Signal]]] = {name: [] for name in categories}
    findings = []
    for page in result.pages:
        scored = _score_page(page, result.robots, categories)
        for name, signals in scored.items():
            per_category[name].append(signals)
            findings.extend(findings_for(signals, page.result.final_url if page.result else page.url))
        findings.extend(page.findings)

    return _assemble(
        run_id=run_id,
        start_url=args.url,
        categories=categories,
        per_category=per_category,
        findings=findings,
        crawl_block=crawl_cmd.crawl_block(result, options),
        evidence=crawl_cmd.evidence_block(result),
        record=True,
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
    extra: dict | None = None,
) -> dict:
    weights = data.weights()
    category_scores: dict[str, int] = {}
    category_completeness: dict[str, dict] = {}
    all_signals: list[Signal] = []

    for name in categories:
        pages = per_category.get(name) or []
        if not pages:
            continue
        rolled = aggregate(pages)
        score, completeness = composite(rolled)
        category_scores[name] = score
        category_completeness[name] = completeness
        all_signals.extend(rolled)

    total, coverage = weighted_composite(
        {name: weights[name]["weight"] for name in weights}, category_scores
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

    ranked = prioritize(merge(findings))
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
    for signal in stored_signals:
        name = signal.id.split(".", 1)[0]
        by_category.setdefault(name, [[]])[0].append(signal)

    categories = tuple(name for name in CATEGORIES if name in by_category)
    findings = []
    for name in categories:
        findings.extend(findings_for(by_category[name][0], record.get("crawl", {}).get("start_url", "")))

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
        crawl_block=record.get("crawl", {}),
        evidence=record.get("evidence") or {},
        record=False,
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
