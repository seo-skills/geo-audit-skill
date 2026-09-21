"""`geo score` — citability of a single page.

The documented first success: one URL, no crawl, no browser, no Claude Code.
Everything the scorer used is written to the project's append-only history, so
the number in the terminal can be traced to the evidence that produced it
after the page has changed.
"""

from __future__ import annotations

from geo_audit import copy as copytext
from geo_audit import data, envelope, state
from geo_audit.commands.common import Options, evidence_block, load_page, page_block
from geo_audit.lib import browser
from geo_audit.lib.slug import host_of, project_slug
from geo_audit.scoring import citability
from geo_audit.scoring.model import Signal, composite, findings_for, prioritize


def run(args, run_id: str) -> dict:
    state.init()
    options = Options(
        allow_private=args.allow_private,
        timeout=args.timeout,
        max_bytes=args.max_bytes,
        check_robots=not args.no_robots,
    )
    page = load_page(args.url, options)
    block = page_block(page)
    evidence = evidence_block(page)

    if not page.scorable:
        # Nothing was measured, so say what was in scope and that none of it
        # was reached - `0 of 0, nothing missing` reads as a complete run, and
        # divides by zero for anyone who takes it at face value. Running the
        # unmeasured signals through `composite` keeps that count agreeing with
        # a scorable run forever, instead of a second copy of the same rule.
        unmeasured = [
            Signal(
                id=signal_id,
                cls=meta["class"],
                max=meta["max"],
                value=None,
                page=block["final_url"],
                skipped_reason=copytext.NOT_SCORABLE,
            )
            for signal_id, meta in data.weights()["citability"]["signals"].items()
        ]
        _, completeness = composite(unmeasured)
        result = envelope.build(
            "score",
            ok=True,
            run_id=run_id,
            evidence=evidence,
            completeness=completeness,
            scores=None,
            signals=[s.to_dict() for s in unmeasured],
            findings=[f.to_dict() for f in prioritize(page.findings)],
            extra={
                "page": block,
                "note": copytext.NO_SCORABLE_PAGES.format(
                    site=host_of(block["final_url"]),
                    status=block["status"] or "no response",
                ),
            },
        )
        _record(page, result)
        return result

    rendered_chars = None
    if not args.no_render and browser.available():
        rendered_chars = browser.rendered_content_chars(block["final_url"], timeout=args.timeout)

    signals = citability.score(page.doc, rendered_chars=rendered_chars)
    score, completeness = composite(signals)
    tier = data.tier_for(score)
    findings = findings_for(signals, block["final_url"]) + page.findings

    extra = {"page": block}
    if not page.doc.blocks:
        # Every prose signal reads zero on an empty page, but only one of them
        # is a cause; the rest are consequences. Telling someone to rewrite the
        # opening sentence of each passage, on a page with no passages, is
        # worse than saying nothing. Report what explains the absence.
        extra["note"] = copytext.NO_BLOCKS
        findings = [f for f in findings if not f.id.startswith("citability.")
                    or f.id == "citability.extractability"]

    findings = prioritize(findings)

    result = envelope.build(
        "score",
        ok=True,
        run_id=run_id,
        evidence=evidence,
        completeness=completeness,
        scores={
            "composite": score,
            "tier": tier["label"],
            "tier_meaning": tier["meaning"],
            "categories": {"citability": score},
        },
        signals=[s.to_dict() for s in signals],
        findings=[f.to_dict() for f in findings],
        extra=extra,
    )
    _record(page, result)
    return result


def _record(page, result: dict) -> None:
    slug = project_slug(result["page"]["final_url"])
    path = state.append_audit(slug, result)
    try:
        inside = path.relative_to(state.geo_home()).as_posix()
        result["page"]["record"] = f"{state.display_home()}/{inside}"
    except ValueError:
        result["page"]["record"] = str(path)
