"""`geo compare` - what changed between two recorded audits.

The refusal is the interesting part. Two runs scored under different rules
cannot be subtracted: the difference would measure the tool, not the site, and
a client shown "your score fell six points" when only our thresholds moved has
been told something false. So `compare` checks the contract versions first and
declines rather than producing a number nobody should trust.

Everything else is subtraction over records that are already on disk. No
network is used.
"""

from __future__ import annotations

from geo_audit import data, envelope, state
from geo_audit.errors import GeoError
from geo_audit.lib.ids import is_run_id
from geo_audit.lib.slug import host_of, project_slug


def _records_for(slug: str) -> list[dict]:
    records, _ = state.read_audits(slug)
    return [record for record in records if record.get("command") == "audit"]


def _pick(records: list[dict], run_id: str | None, which: str) -> dict:
    if run_id:
        if not is_run_id(run_id):
            raise GeoError(
                "GEO_E_BAD_ARGS",
                f"{run_id!r} is not a run id. Run ids are 26 characters and appear "
                f"as `run_id` in any envelope.",
            )
        for record in records:
            if record.get("run_id") == run_id:
                return record
        raise GeoError("GEO_E_BAD_ARGS", f"No recorded audit has run id {run_id}.")
    if not records:
        raise GeoError(
            "GEO_E_BAD_ARGS",
            "No audits are recorded for this site yet. Run `geo audit <url>` twice "
            "before comparing.",
        )
    return records[-1] if which == "to" else records[-2]


def _versions(record: dict) -> dict:
    return {
        "scoring_version": record.get("scoring_version"),
        "data_version": record.get("data_version"),
        "normalizer_version": record.get("normalizer_version"),
    }


def comparable(before: dict, after: dict) -> tuple[bool, str | None]:
    """Whether subtracting these two measures the site rather than the tool."""
    left, right = _versions(before), _versions(after)
    if not all(left.values()) or not all(right.values()):
        return False, "one of these runs predates version stamping"

    left_major = str(left["scoring_version"]).split(".")[0]
    right_major = str(right["scoring_version"]).split(".")[0]
    if left_major != right_major:
        return False, (
            f"scoring_version {left['scoring_version']} against "
            f"{right['scoring_version']} - the formula changed"
        )
    if left["data_version"] != right["data_version"]:
        return False, (
            f"data_version {left['data_version']} against {right['data_version']} "
            f"- the weights or thresholds changed"
        )
    return True, None


def _delta(before: float | int | None, after: float | int | None) -> float | None:
    if before is None or after is None:
        return None
    return round(after - before, 2)


def _signal_map(record: dict) -> dict[str, dict]:
    return {signal["id"]: signal for signal in record.get("signals") or []}


def _finding_map(record: dict) -> dict[str, dict]:
    return {finding["id"]: finding for finding in record.get("findings") or []}


def _page_map(record: dict) -> dict[str, str | None]:
    return {
        page["url"]: page.get("content_hash")
        for page in (record.get("crawl") or {}).get("pages") or []
    }


def compare_records(before: dict, after: dict) -> dict:
    before_scores = before.get("scores") or {}
    after_scores = after.get("scores") or {}

    categories = sorted(
        set(before_scores.get("categories") or {}) | set(after_scores.get("categories") or {})
    )
    category_deltas = {
        name: {
            "before": (before_scores.get("categories") or {}).get(name),
            "after": (after_scores.get("categories") or {}).get(name),
            "delta": _delta(
                (before_scores.get("categories") or {}).get(name),
                (after_scores.get("categories") or {}).get(name),
            ),
        }
        for name in categories
    }

    before_signals, after_signals = _signal_map(before), _signal_map(after)
    signal_deltas = []
    for signal_id in sorted(set(before_signals) | set(after_signals)):
        left = before_signals.get(signal_id, {})
        right = after_signals.get(signal_id, {})
        change = _delta(left.get("value"), right.get("value"))
        if change in (None, 0.0) and signal_id in before_signals and signal_id in after_signals:
            continue
        signal_deltas.append(
            {
                "id": signal_id,
                "before": left.get("value"),
                "after": right.get("value"),
                "max": right.get("max", left.get("max")),
                "delta": change,
            }
        )

    before_findings, after_findings = _finding_map(before), _finding_map(after)
    resolved = sorted(set(before_findings) - set(after_findings))
    introduced = sorted(set(after_findings) - set(before_findings))
    persisting = sorted(set(before_findings) & set(after_findings))

    before_pages, after_pages = _page_map(before), _page_map(after)
    added = sorted(set(after_pages) - set(before_pages))
    removed = sorted(set(before_pages) - set(after_pages))
    changed = sorted(
        url
        for url in set(before_pages) & set(after_pages)
        if before_pages[url] and after_pages[url] and before_pages[url] != after_pages[url]
    )
    unchanged = len(set(before_pages) & set(after_pages)) - len(changed)

    composite_delta = _delta(before_scores.get("composite"), after_scores.get("composite"))
    return {
        "from": {
            "run_id": before.get("run_id"),
            "observed_at": before.get("observed_at"),
            "composite": before_scores.get("composite"),
            "tier": before_scores.get("tier"),
            "pages_ok": (before.get("evidence") or {}).get("pages_ok"),
        },
        "to": {
            "run_id": after.get("run_id"),
            "observed_at": after.get("observed_at"),
            "composite": after_scores.get("composite"),
            "tier": after_scores.get("tier"),
            "pages_ok": (after.get("evidence") or {}).get("pages_ok"),
        },
        "composite_delta": composite_delta,
        "tier_changed": before_scores.get("tier") != after_scores.get("tier"),
        "categories": category_deltas,
        "signals": signal_deltas,
        "findings": {
            "resolved": resolved,
            "introduced": introduced,
            "persisting": persisting,
            "resolved_titles": [before_findings[key]["title"] for key in resolved],
            "introduced_titles": [after_findings[key]["title"] for key in introduced],
        },
        "pages": {
            "added": added,
            "removed": removed,
            "changed": changed,
            "unchanged": unchanged,
        },
        "versions": {"from": _versions(before), "to": _versions(after)},
    }


def run(args, run_id: str) -> dict:
    state.init()
    slug = project_slug(args.url)
    records = _records_for(slug)

    if not args.from_run and not args.to_run and len(records) < 2:
        raise GeoError(
            "GEO_E_BAD_ARGS",
            f"Only {len(records)} audit is recorded for {host_of(args.url)}. "
            f"Run `geo audit {args.url}` again to have something to compare.",
        )

    before = _pick(records, args.from_run, "from")
    after = _pick(records, args.to_run, "to")
    if before.get("run_id") == after.get("run_id"):
        raise GeoError("GEO_E_BAD_ARGS", "Both ends of the comparison are the same run.")

    ok, reason = comparable(before, after)
    if not ok:
        raise GeoError(
            "GEO_E_INCOMPARABLE",
            f"Runs {before.get('run_id')} and {after.get('run_id')} are not "
            f"comparable: {reason}.",
        )

    report = compare_records(before, after)
    return envelope.build(
        "compare",
        ok=True,
        run_id=run_id,
        evidence={
            "stamp": (after.get("evidence") or {}).get("stamp"),
            "content_hash": (after.get("evidence") or {}).get("content_hash"),
            "normalizer_version": (after.get("evidence") or {}).get("normalizer_version"),
            "pages_ok": (after.get("evidence") or {}).get("pages_ok"),
            "pages_failed": (after.get("evidence") or {}).get("pages_failed") or [],
        },
        scores=after.get("scores"),
        extra={"compare": report, "site": host_of(args.url), "url": args.url},
    )


__all__ = ["compare_records", "comparable", "run"]
