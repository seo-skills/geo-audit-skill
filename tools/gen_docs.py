#!/usr/bin/env python3
"""Generate the parts of the docs that are derived from code and data.

Two kinds of output:

* `docs/commands.md` is generated whole from the argument parser, so a flag
  cannot exist without being documented or be documented without existing.
* Marker regions inside hand-written docs (`<!-- generated:<name>:begin -->` …
  `<!-- generated:<name>:end -->`) hold constants pulled from data/. The
  surrounding rationale stays hand-written, and the freshness check covers the
  marker region only.

    python tools/gen_docs.py            rewrite
    python tools/gen_docs.py --check    fail if anything is out of date (CI)
"""

from __future__ import annotations

import argparse
import io
import sys
from contextlib import redirect_stdout
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

from geo_audit import data  # noqa: E402
from geo_audit._version import (  # noqa: E402
    CLI_VERSION,
    NORMALIZER_VERSION,
    SCHEMA_VERSION,
    SCORING_VERSION,
)
from geo_audit.cli import build_parser  # noqa: E402
from geo_audit.errors import ERRORS  # noqa: E402

EXIT_MEANINGS = {
    0: "OK, including PARTIAL results",
    1: "internal error",
    2: "usage error",
    3: "network failure on the start URL",
    4: "state error",
    5: "`--fail-on-partial` was passed and the result is PARTIAL",
}


def _help_of(parser: argparse.ArgumentParser) -> str:
    buffer = io.StringIO()
    with redirect_stdout(buffer):
        parser.print_help()
    return buffer.getvalue().rstrip()


def commands_doc() -> str:
    parser = build_parser()
    subparsers = next(a for a in parser._actions if hasattr(a, "choices") and a.choices)
    lines = [
        "# Command reference",
        "",
        f"Generated from the argument parser at version {CLI_VERSION}. "
        "Do not edit by hand; run `python tools/gen_docs.py`.",
        "",
        "```",
        _help_of(parser),
        "```",
        "",
    ]
    for name, sub in subparsers.choices.items():
        lines += [
            f"## `geo {name}`",
            "",
            sub.description or "",
            "",
            "```",
            _help_of(sub),
            "```",
            "",
        ]
    lines += [
        "## Exit codes",
        "",
        "| Code | Meaning |",
        "|---|---|",
    ]
    for code, meaning in EXIT_MEANINGS.items():
        lines.append(f"| {code} | {meaning} |")
    lines += [
        "",
        "## Error codes",
        "",
        "| Code | Exit | Hint |",
        "|---|---|---|",
    ]
    for code in sorted(ERRORS):
        spec = ERRORS[code]
        lines.append(f"| `{code}` | {spec.exit_code} | {spec.hint} |")
    lines.append("")
    return "\n".join(lines)


def signals_region() -> str:
    spec = data.weights()["citability"]["signals"]
    questions = {
        "citability.self_containment": "Does each passage name its own subject?",
        "citability.answer_first": "Does each section lead with the answer?",
        "citability.structure": "Do the headings segment the page into answerable parts?",
        "citability.evidence_density": "Do claims carry numbers, dates and sources?",
        "citability.extractability": "Is the content in the HTML a crawler receives?",
        "citability.attribution": "Does the page say who wrote it and when?",
        "citability.render_parity": "How much text appears only after JavaScript?",
    }
    lines = [
        f"*Generated from `data/weights.json` at data_version {data.data_version()}.*",
        "",
        "| Signal | Class | Max | Requires | Question |",
        "|---|---|---|---|---|",
    ]
    for signal_id, meta in spec.items():
        requires = meta.get("requires", "—")
        lines.append(
            f"| `{signal_id}` | {meta['class']} | {meta['max']:g} | {requires} | "
            f"{questions.get(signal_id, '')} |"
        )
    total = sum(m["max"] for m in spec.values())
    always = sum(m["max"] for m in spec.values() if "requires" not in m)
    lines += [
        "",
        f"Total when every signal is computed: **{total:g}**. "
        f"Without the browser extra: **{always:g}**. "
        "The composite is `earned / max-of-computed * 100`, so a signal that was not "
        "measured leaves both sides of the fraction.",
    ]
    return "\n".join(lines)


def constants_region() -> str:
    tiers = data.tiers()
    lines = [
        f"*Generated from `data/` at data_version {data.data_version()}, "
        f"scoring_version {SCORING_VERSION}, normalizer_version {NORMALIZER_VERSION}, "
        f"schema_version {SCHEMA_VERSION}.*",
        "",
        "### Tiers",
        "",
        "| Score | Label | What it means |",
        "|---|---|---|",
    ]
    for index, tier in enumerate(tiers):
        upper = 100 if index == 0 else tiers[index - 1]["min"] - 1
        lines.append(f"| {tier['min']}–{upper} | {tier['label']} | {tier['meaning']} |")

    thresholds = data.load("thresholds")
    lines += ["", "### Thresholds", "", "| Signal | Threshold | Value |", "|---|---|---|"]
    for section in sorted(thresholds):
        for key in sorted(thresholds[section]):
            value = thresholds[section][key]
            if isinstance(value, (list, dict)):
                value = f"{len(value)} entries"
            lines.append(f"| {section} | `{key}` | {value} |")

    crawlers = data.crawlers()
    lines += [
        "",
        "### AI crawler tokens",
        "",
        "`critical` marks a token whose refusal directly costs visibility in an "
        "answer surface, as opposed to refusing model training.",
        "",
        "| Token | Operator | Purpose | Critical | Gates |",
        "|---|---|---|---|---|",
    ]
    for entry in crawlers:
        lines.append(
            f"| `{entry['token']}` | {entry['operator']} | {entry['purpose']} | "
            f"{'yes' if entry['critical'] else 'no'} | {entry['gates']} |"
        )
    return "\n".join(lines)


def crawlers_region() -> str:
    lines = [
        "| Token | Operator | Purpose | Critical | Gates |",
        "|---|---|---|---|---|",
    ]
    for entry in data.crawlers():
        lines.append(
            f"| `{entry['token']}` | [{entry['operator']}]({entry['docs']}) | "
            f"{entry['purpose']} | {'**yes**' if entry['critical'] else 'no'} | "
            f"{entry['gates']} |"
        )
    lines.append("")
    lines.append(f"*Generated from `data/ai_crawlers.json` at data_version {data.data_version()}.*")
    return "\n".join(lines)


def schema_types_region() -> str:
    requirements = data.load("schema_requirements")["types"]
    lines = ["| Type | Required | Recommended |", "|---|---|---|"]
    for name in sorted(requirements):
        spec = requirements[name]
        required = ", ".join(f"`{p}`" for p in spec["required"]) or "-"
        recommended = ", ".join(f"`{p}`" for p in spec["recommended"]) or "-"
        lines.append(f"| `{name}` | {required} | {recommended} |")
    lines.append("")
    lines.append(
        f"*Generated from `data/schema_requirements.json` at data_version "
        f"{data.data_version()}.*"
    )
    return "\n".join(lines)


REGIONS = {
    ROOT / "skills/technical/sections/crawlers.md": {"crawlers": crawlers_region},
    ROOT / "skills/schema/sections/types.md": {"schema-types": schema_types_region},
    ROOT / "docs/concepts/signals.md": {"signals": signals_region},
    ROOT / "docs/concepts/scoring-methodology.md": {"constants": constants_region},
}

WHOLE_FILES = {ROOT / "docs/commands.md": commands_doc}


def replace_region(text: str, name: str, body: str) -> str:
    begin = f"<!-- generated:{name}:begin -->"
    end = f"<!-- generated:{name}:end -->"
    if begin not in text or end not in text:
        raise SystemExit(f"marker region {name!r} is missing")
    head, rest = text.split(begin, 1)
    _, tail = rest.split(end, 1)
    return f"{head}{begin}\n{body}\n{end}{tail}"


def render_all() -> dict[Path, str]:
    out: dict[Path, str] = {}
    for path, builder in WHOLE_FILES.items():
        out[path] = builder().rstrip() + "\n"
    for path, regions in REGIONS.items():
        text = path.read_text(encoding="utf-8")
        for name, builder in regions.items():
            text = replace_region(text, name, builder().rstrip())
        out[path] = text
    return out


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true", help="fail instead of writing")
    args = parser.parse_args(argv)

    stale: list[str] = []
    for path, content in render_all().items():
        current = path.read_text(encoding="utf-8") if path.exists() else None
        if current == content:
            continue
        if args.check:
            stale.append(str(path.relative_to(ROOT)))
        else:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(content, encoding="utf-8")
            print(f"wrote {path.relative_to(ROOT)}")

    if stale:
        print("docs are out of date:", file=sys.stderr)
        for name in stale:
            print(f"  {name}", file=sys.stderr)
        print("run: python tools/gen_docs.py", file=sys.stderr)
        return 1
    if args.check:
        print("docs are current")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
