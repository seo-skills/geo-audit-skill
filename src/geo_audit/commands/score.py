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
from geo_audit.scoring.model import composite, findings_for, prioritize


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
        result = envelope.build(
            "score",
            ok=True,
            run_id=run_id,
            evidence=evidence,
            completeness={"computed": 0, "total": 0, "missing": []},
            scores=None,
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
    findings = prioritize(findings_for(signals, block["final_url"]) + page.findings)

    extra = {"page": block}
    if page.doc is not None and not page.doc.blocks:
        extra["note"] = copytext.NO_BLOCKS

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
        result["page"]["record"] = str(path.relative_to(state.geo_home().parent))
    except ValueError:
        result["page"]["record"] = str(path)
