"""`geo prune` - keep the append-only history from growing without bound.

Three rules, applied in order, newest first: keep at most N runs per project,
drop anything older than D days, and stop once the project's file would exceed
its byte cap. The defaults are deliberately generous - a year, a hundred runs -
because the history is the evidence behind numbers that were already sent to
someone.

`--dry-run` is the default posture of the command's output: it always reports
exactly what it would remove before removing it.
"""

from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone

from geo_audit import data, envelope, state
from geo_audit.errors import GeoError


def _limits(args) -> dict:
    defaults = data.load("retention")
    return {
        "keep_runs": args.keep if args.keep is not None else defaults["keep_runs"],
        "keep_days": args.older_than if args.older_than is not None else defaults["keep_days"],
        "max_project_bytes": defaults["max_project_bytes"],
    }


def _parse_time(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None


def plan_for(records: list[dict], limits: dict, now: datetime) -> tuple[list[dict], list[dict]]:
    """Return (kept, dropped), newest first in both."""
    ordered = sorted(
        records,
        key=lambda record: record.get("run_id") or record.get("observed_at") or "",
        reverse=True,
    )
    cutoff = now - timedelta(days=limits["keep_days"])

    kept: list[dict] = []
    dropped: list[dict] = []
    size = 0
    for record in ordered:
        encoded = len(json.dumps(record, sort_keys=True, separators=(",", ":")).encode("utf-8")) + 1
        observed = _parse_time(record.get("observed_at"))
        too_many = len(kept) >= limits["keep_runs"]
        too_old = observed is not None and observed < cutoff
        too_big = size + encoded > limits["max_project_bytes"]
        if too_many or too_old or too_big:
            reason = "count" if too_many else "age" if too_old else "size"
            dropped.append({"record": record, "reason": reason})
            continue
        kept.append(record)
        size += encoded
    return kept, dropped


def _project_report(slug: str, limits: dict, now: datetime, apply: bool) -> dict:
    records, damaged = state.read_audits(slug)
    path = state.audits_path(slug)
    before_bytes = path.stat().st_size if path.exists() else 0
    kept, dropped = plan_for(records, limits, now)

    reasons: dict[str, int] = {}
    for entry in dropped:
        reasons[entry["reason"]] = reasons.get(entry["reason"], 0) + 1

    after_bytes = before_bytes
    if apply and (dropped or damaged):
        payload = "".join(
            json.dumps(record, sort_keys=True, separators=(",", ":")) + "\n"
            for record in sorted(kept, key=lambda r: r.get("run_id") or "")
        )
        state.write_atomic(path, payload)
        after_bytes = path.stat().st_size

    return {
        "project": slug,
        "runs_before": len(records),
        "runs_kept": len(kept),
        "runs_dropped": len(dropped),
        "dropped_by": reasons,
        "damaged_lines_discarded": damaged if apply else 0,
        "bytes_before": before_bytes,
        "bytes_after": after_bytes,
        "oldest_kept": min((r.get("observed_at") or "" for r in kept), default=None) or None,
    }


def run(args, run_id: str) -> dict:
    state.init()
    limits = _limits(args)
    now = datetime.now(timezone.utc)

    root = state.geo_home() / "projects"
    if args.project:
        slugs = [args.project]
        if not state.audits_path(args.project).exists():
            raise GeoError(
                "GEO_E_BAD_ARGS",
                f"No history recorded for project {args.project!r}. "
                f"`geo prune` with no --project covers every project.",
            )
    else:
        slugs = sorted(path.name for path in root.iterdir() if path.is_dir()) if root.is_dir() else []

    apply = not args.dry_run
    projects = [_project_report(slug, limits, now, apply) for slug in slugs]

    return envelope.build(
        "prune",
        ok=True,
        run_id=run_id,
        extra={
            "prune": {
                "home": state.display_home(),
                "applied": apply,
                "limits": limits,
                "projects": projects,
                "runs_dropped": sum(p["runs_dropped"] for p in projects),
                "bytes_reclaimed": sum(p["bytes_before"] - p["bytes_after"] for p in projects),
            }
        },
    )
