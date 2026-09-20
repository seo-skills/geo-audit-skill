"""`geo fetch` — what a crawler sees, and nothing more.

The output boundary is the point of this command. It reports derived facts and
capped, escaped excerpts. It never returns page text, because its output is
read by an agent with tool access and a crawled page is untrusted input.
"""

from __future__ import annotations

from geo_audit import envelope
from geo_audit.commands.common import Options, evidence_block, load_page, page_block
from geo_audit.scoring.model import prioritize


def run(args, run_id: str) -> dict:
    options = Options(
        allow_private=args.allow_private,
        timeout=args.timeout,
        max_bytes=args.max_bytes,
        check_robots=not args.no_robots,
    )
    page = load_page(args.url, options)
    findings = prioritize(page.findings)
    return envelope.build(
        "fetch",
        ok=True,
        run_id=run_id,
        evidence=evidence_block(page),
        findings=[f.to_dict() for f in findings],
        extra={"page": page_block(page)},
    )
