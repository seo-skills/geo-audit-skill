"""`geo report` - turn a recorded audit into something you can send.

Reads a record from disk. It never crawls, so the report always describes a
run that happened rather than a run it just invented, and the same record
always produces the same document.

Two modes, and the client one is the default because it is the one that gets
sent. Operator mode adds provenance; it does not remove anything.
"""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

from geo_audit import copy as copytext
from geo_audit import envelope, state
from geo_audit.errors import GeoError
from geo_audit.lib.evidence import short
from geo_audit.lib.ids import is_run_id
from geo_audit.lib.slug import host_of, project_slug
from geo_audit.report import advisory as advisory_lib
from geo_audit.report import brand as brand_lib
from geo_audit.report import context as context_lib
from geo_audit.report import pdf as pdf_lib
from geo_audit.report import render as render_lib

MODES = ("client", "operator")


def _record_for(slug: str, run_id: str | None) -> dict:
    records, _ = state.read_audits(slug)
    audits = [record for record in records if record.get("command") == "audit"]
    if not audits:
        raise GeoError(
            "GEO_E_BAD_ARGS",
            "No audits are recorded for this site yet. Run `geo audit <url>` first; "
            "`geo report` renders a run that already happened.",
        )
    if run_id is None:
        return audits[-1]
    if not is_run_id(run_id):
        raise GeoError(
            "GEO_E_BAD_ARGS",
            f"{run_id!r} is not a run id. Run ids are 26 characters and appear as "
            f"`run_id` in any envelope.",
        )
    for record in reversed(audits):
        if record.get("run_id") == run_id:
            return record
    raise GeoError("GEO_E_BAD_ARGS", f"No recorded audit has run id {run_id}.")


def output_path(slug: str, record: dict, override: str | None) -> Path:
    """Deterministic by default, and never silently overwriting."""
    if override:
        return Path(override).expanduser()

    observed = record.get("observed_at") or ""
    day = observed[:10] or datetime.now(timezone.utc).strftime("%Y-%m-%d")
    digest = (record.get("evidence") or {}).get("content_hash") or record.get("run_id", "")
    base = state.project_dir(slug) / "reports" / f"{day}-{short(digest)}"

    candidate = base.with_suffix(".html")
    counter = 2
    while candidate.exists():
        candidate = base.with_name(f"{base.name}-{counter}").with_suffix(".html")
        counter += 1
    return candidate


def run(args, run_id: str) -> dict:
    if args.mode not in MODES:
        raise GeoError(
            "GEO_E_BAD_ARGS",
            f"--mode must be one of {', '.join(MODES)}, not {args.mode!r}.",
        )

    state.init()
    slug = project_slug(args.url)
    record = _record_for(slug, args.run)
    brand = brand_lib.load(args.brand_config)
    advisory_answers = advisory_lib.load(args.advisory)

    for warning in brand.warnings:
        import sys

        print(f"brand: {warning}", file=sys.stderr)

    target = output_path(slug, record, args.out)
    record_path = None
    path = state.audits_path(slug)
    try:
        record_path = f"{state.display_home()}/{path.relative_to(state.geo_home()).as_posix()}"
    except ValueError:
        record_path = str(path)

    client, operator = context_lib.build(
        record,
        brand,
        generated_on=datetime.now(timezone.utc).strftime("%Y-%m-%d"),
        record_path=record_path,
        advisory_answers=advisory_answers,
    )

    html = (
        render_lib.render_operator(client, operator)
        if args.mode == "operator"
        else render_lib.render_client(client)
    )

    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(html, encoding="utf-8")

    pdf_path: Path | None = None
    pdf_skipped: str | None = None
    if args.pdf:
        pdf_path = target.with_suffix(".pdf")
        reason = pdf_lib.write_pdf(target, pdf_path)
        if reason:
            pdf_skipped = copytext.PDF_UNAVAILABLE.format(reason=reason, path=target)
            pdf_path = None

    return envelope.build(
        "report",
        ok=True,
        run_id=run_id,
        evidence=record.get("evidence"),
        completeness=record.get("completeness"),
        scores=record.get("scores"),
        extra={
            "report": {
                "site": host_of(args.url) or client.site,
                "mode": args.mode,
                "path": str(target),
                "bytes": len(html.encode("utf-8")),
                "pdf_path": str(pdf_path) if pdf_path else None,
                "pdf_skipped": pdf_skipped,
                "advisory_answered": sorted(advisory_answers),
                "from_run": record.get("run_id"),
                "observed_at": record.get("observed_at"),
                "brand": {
                    "source": brand.source,
                    "name": brand.name,
                    "customised": brand.customised,
                    "warnings": brand.warnings,
                    "attribution": brand.attribution,
                },
            }
        },
    )
