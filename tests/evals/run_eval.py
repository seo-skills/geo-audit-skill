#!/usr/bin/env python3
"""Run the practitioner eval and emit a blank scoring form.

This script produces the inputs to a judgement, not the judgement. It audits
each site, renders both report copies, and writes a form with the top three
fixes already filled in and the two questions left empty. Nothing here scores
the answers, because the whole point is that the answers come from people.

    python tests/evals/run_eval.py --sites tests/evals/sites.json
    python tests/evals/run_eval.py --sites tests/evals/sites.json --dry-run
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
RESULTS = Path(__file__).resolve().parent / "results"


def geo(*args: str) -> dict:
    """Run the CLI as a user would, and parse its envelope."""
    completed = subprocess.run(
        [sys.executable, "-m", "geo_audit", *args, "--json", "--quiet"],
        capture_output=True,
        text=True,
        cwd=ROOT,
    )
    if not completed.stdout.strip():
        raise SystemExit(f"geo {' '.join(args)} produced no output:\n{completed.stderr}")
    return json.loads(completed.stdout)


def audit_site(entry: dict) -> dict:
    url = entry["url"]
    # `args` lets an entry add flags - a staging host needs --allow-private,
    # and the harness's own test needs to point at a local fixture server.
    extra = list(entry.get("args") or [])
    print(f"  auditing {url} (up to {entry.get('max_pages', 10)} pages, 1 req/s)...", flush=True)
    envelope = geo("audit", url, "--max-pages", str(entry.get("max_pages", 10)), *extra)
    if not envelope.get("ok"):
        return {"url": url, "error": (envelope.get("error") or {}).get("message")}

    # `report` reads from disk and never crawls, so it takes none of the
    # network flags an entry might carry. Both copies: question 2 asks whether
    # the report could go to a client, and a client gets the client copy - the
    # operator copy's provenance would earn a `no` that says nothing about the
    # product. The operator copy is for working out why an answer went wrong.
    brand = ["--brand-config", entry["brand"]] if entry.get("brand") else []
    client = geo("report", url, *brand)
    operator = geo("report", url, "--mode", "operator", *brand)

    scores = envelope.get("scores") or {}
    return {
        "url": url,
        "shape": entry.get("shape"),
        "run_id": envelope["run_id"],
        "composite": scores.get("composite"),
        "tier": scores.get("tier"),
        "categories": scores.get("categories"),
        "pages_ok": (envelope.get("evidence") or {}).get("pages_ok"),
        "stamp": (envelope.get("evidence") or {}).get("stamp"),
        "top_three": [
            {
                "title": finding["title"],
                "severity": finding["severity"],
                "effort": finding["effort"],
                "pages": len(finding.get("pages") or []),
            }
            for finding in (envelope.get("findings") or [])[:3]
        ],
        "client_report": (client.get("report") or {}).get("path"),
        "operator_report": (operator.get("report") or {}).get("path"),
    }


def form(results: list[dict], versions: dict) -> str:
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    lines = [
        f"# Practitioner eval — {today}",
        "",
        f"Tool {versions['cli']} · scoring {versions['scoring']} · data {versions['data']} · "
        f"normalizer {versions['normalizer']}",
        "",
        "Two people answer independently: the maintainer, and one practitioner who does "
        "not work on this tool. Fill in both columns before reading the other one.",
        "",
        "Answers: question 1 is `yes` / `mostly` / `no`. Question 2 is `yes` / "
        "`with small edits` / `no`. Both need one sentence of reasoning.",
        "",
    ]
    for result in results:
        lines += [f"## {result['url']}", ""]
        if result.get("error"):
            lines += [f"**The audit failed:** {result['error']}", ""]
            continue
        lines += [
            f"Score **{result['composite']}/100 ({result['tier']})** over "
            f"{result['pages_ok']} pages, evidence {result['stamp']}.",
            "",
            f"Categories: " + ", ".join(f"{k} {v}" for k, v in sorted((result["categories"] or {}).items())),
            "",
            f"Client copy, the one question 2 is about: `{result['client_report']}`",
            "",
            f"Operator copy, for working out why: `{result['operator_report']}`  ·  "
            f"run `{result['run_id']}`",
            "",
            "Top three fixes as ranked by the tool:",
            "",
        ]
        for index, fix in enumerate(result["top_three"], start=1):
            lines.append(
                f"{index}. **{fix['title']}** — {fix['severity']}, {fix['effort']} effort, "
                f"{fix['pages']} page(s)"
            )
        lines += [
            "",
            "| Question | Maintainer | Practitioner |",
            "|---|---|---|",
            "| 1. Are these the right three? | | |",
            "| Why | | |",
            "| 2. Would you send this unedited? | | |",
            "| Why | | |",
            "",
        ]

    lines += [
        "## Outcome",
        "",
        "- Reports the practitioner would send unedited: __ of 5 "
        "(the 1.0 gate is 4 of 5, twice running)",
        "- Changes made as a result:",
        "",
    ]
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--sites", required=True, help="a JSON file of sites to audit")
    parser.add_argument("--out", help="where to write the form (default: results/eval-<date>.md)")
    parser.add_argument("--dry-run", action="store_true", help="list what would be audited")
    args = parser.parse_args(argv)

    config = json.loads(Path(args.sites).read_text(encoding="utf-8"))
    sites = config["sites"]

    if args.dry_run:
        for entry in sites:
            print(f"  would audit {entry['url']} (up to {entry.get('max_pages', 10)} pages)")
        return 0

    version = geo("doctor")
    versions = {
        "cli": version["cli_version"],
        "scoring": version["scoring_version"],
        "data": version["data_version"],
        "normalizer": version["normalizer_version"],
    }

    print(f"Running the eval over {len(sites)} site(s) at one request per second.")
    results = [audit_site(entry) for entry in sites]

    RESULTS.mkdir(parents=True, exist_ok=True)
    target = Path(args.out) if args.out else RESULTS / (
        f"eval-{datetime.now(timezone.utc).strftime('%Y-%m-%d')}.md"
    )
    target.write_text(form(results, versions), encoding="utf-8")
    print(f"\nForm written to {target}")
    print("Both people fill it in independently, then commit it.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
