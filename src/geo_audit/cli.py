"""Argument parsing, output mode, and the exit-code decision.

One place decides how a run ends. Commands return an envelope and raise
`GeoError`; nothing below this module calls `sys.exit`, prints to stdout, or
decides an exit code, which is what keeps the exit-code table in errors.py
true rather than aspirational.
"""

from __future__ import annotations

import argparse
import json
import sys
import traceback
from pathlib import Path
from typing import TextIO

from geo_audit import envelope as envelope_mod
from geo_audit import render, state
from geo_audit._version import (
    CLI_VERSION,
    DIST_NAME,
    NORMALIZER_VERSION,
    PRODUCT_NAME,
    SCHEMA_VERSION,
    SCORING_VERSION,
)
from geo_audit.commands import audit as audit_cmd
from geo_audit.commands import crawl as crawl_cmd
from geo_audit.commands import doctor as doctor_cmd
from geo_audit.commands import llmstxt as llmstxt_cmd
from geo_audit.commands import prune as prune_cmd
from geo_audit.commands import scan as scan_cmd
from geo_audit.commands import validate as validate_cmd
from geo_audit.commands import fetch as fetch_cmd
from geo_audit.commands import score as score_cmd
from geo_audit.data import data_version
from geo_audit.errors import EXIT_INTERNAL, EXIT_OK, EXIT_USAGE, GeoError
from geo_audit.lib import crawl as crawl_lib
from geo_audit.lib import http
from geo_audit.lib.evidence import PARTIAL
from geo_audit.lib.ids import new_run_id

COMMANDS = {
    "fetch": fetch_cmd.run,
    "crawl": crawl_cmd.run,
    "audit": audit_cmd.run,
    "score": score_cmd.run,
    "validate": validate_cmd.run,
    "llmstxt": llmstxt_cmd.run,
    "scan": scan_cmd.run,
    "prune": prune_cmd.run,
    "doctor": doctor_cmd.run,
}

CONFIG_KEYS = (
    "timeout",
    "max_bytes",
    "max_redirects",
    "allow_private",
    "no_robots",
    "no_render",
    "max_pages",
    "rate",
    "concurrency",
    "no_sitemap",
)


def version_line() -> str:
    return (
        f"{DIST_NAME} {CLI_VERSION} "
        f"(schema {SCHEMA_VERSION}, scoring {SCORING_VERSION}, "
        f"data {data_version()}, normalizer {NORMALIZER_VERSION})"
    )


class UsageParser(argparse.ArgumentParser):
    """argparse exits 2 on bad usage, which is the code we want anyway."""

    def error(self, message: str):  # pragma: no cover - argparse internals
        self.print_usage(sys.stderr)
        print(f"{self.prog}: {message}", file=sys.stderr)
        raise SystemExit(EXIT_USAGE)


def _global_flags() -> argparse.ArgumentParser:
    parent = argparse.ArgumentParser(add_help=False)
    parent.add_argument("--json", action="store_true", help="force JSON output")
    parent.add_argument("--out", metavar="PATH", help="also write the JSON envelope here")
    parent.add_argument("--config", metavar="PATH", help="JSON file of default flag values")
    parent.add_argument(
        "--no-input",
        action="store_true",
        help="never prompt (reserved: this release never prompts)",
    )
    parent.add_argument("--quiet", action="store_true", help="suppress progress on stderr")
    parent.add_argument("--verbose", action="store_true", help="more progress on stderr")
    parent.add_argument(
        "--allow-private",
        action="store_true",
        help="permit a private, loopback or link-local start URL",
    )
    parent.add_argument(
        "--fail-on-partial",
        action="store_true",
        help="exit 5 when the result is PARTIAL",
    )
    return parent


def _page_flags(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("url", help="an absolute http:// or https:// URL")
    parser.add_argument(
        "--timeout", type=float, default=http.DEFAULT_TIMEOUT, metavar="SECONDS"
    )
    parser.add_argument(
        "--max-bytes", type=int, default=http.DEFAULT_MAX_BYTES, metavar="BYTES"
    )
    parser.add_argument("--no-robots", action="store_true", help="skip the robots.txt lookup")


def _crawl_flags(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "--max-pages",
        type=int,
        default=crawl_lib.MAX_PAGES,
        metavar="N",
        help=f"stop after N pages (default {crawl_lib.MAX_PAGES})",
    )
    parser.add_argument(
        "--rate",
        type=float,
        default=crawl_lib.REQUESTS_PER_SECOND,
        metavar="PER_SECOND",
        help=(
            f"requests per second across the whole crawl, not per worker "
            f"(default {crawl_lib.REQUESTS_PER_SECOND:g})"
        ),
    )
    parser.add_argument(
        "--concurrency",
        type=int,
        default=crawl_lib.CONCURRENCY,
        metavar="N",
        help=(
            f"pages in flight at once (default {crawl_lib.CONCURRENCY}); the rate "
            f"limit still governs throughput"
        ),
    )
    parser.add_argument(
        "--no-sitemap",
        action="store_true",
        help="do not seed the frontier from the sitemaps robots.txt advertises",
    )


def build_parser() -> argparse.ArgumentParser:
    parent = _global_flags()
    parser = UsageParser(
        prog="geo",
        description=f"{PRODUCT_NAME}. Deterministic GEO audits: every number traces to recorded evidence.",
    )
    parser.add_argument("--version", action="version", version=version_line())
    subparsers = parser.add_subparsers(dest="command", metavar="COMMAND")

    fetch = subparsers.add_parser(
        "fetch",
        parents=[parent],
        help="report what a crawler sees on one page",
        description="Fetch one page and report derived facts: status, redirect chain, "
        "content blocks, evidence hash, robots access. Never returns page text.",
    )
    _page_flags(fetch)

    crawl = subparsers.add_parser(
        "crawl",
        parents=[parent],
        help="map what a crawler can reach on a site",
        description="Crawl a site and report the frontier: pages fetched, pages "
        "that failed and why, pages robots.txt put out of reach, and pages found "
        "only in the sitemap. Nothing is scored; `geo audit` does that.",
    )
    _page_flags(crawl)
    _crawl_flags(crawl)

    audit = subparsers.add_parser(
        "audit",
        parents=[parent],
        help="crawl a site and score every category over it",
        description="Crawl a site and score citability, technical and schema over "
        "every page. The composite weights the categories that were computed; one "
        "that was not leaves both sides of the fraction rather than scoring zero.",
    )
    _page_flags(audit)
    _crawl_flags(audit)
    audit.add_argument(
        "--only",
        metavar="CATEGORY[,CATEGORY]",
        help=f"score only these categories ({', '.join(audit_cmd.CATEGORIES)})",
    )
    audit.add_argument(
        "--brand",
        metavar="NAME",
        help="also score brand presence for this name, folding it into the composite",
    )
    audit.add_argument(
        "--rescore",
        metavar="RUN_ID",
        help="recompute from a recorded audit instead of crawling; no network is used",
    )

    score = subparsers.add_parser(
        "score",
        parents=[parent],
        help="score the citability of one page",
        description="Score one page for citability. No crawl, no browser required.",
    )
    _page_flags(score)
    score.add_argument(
        "--no-render",
        action="store_true",
        help="skip JavaScript rendering even when Playwright is installed",
    )

    validate = subparsers.add_parser(
        "validate",
        parents=[parent],
        help="check the structured data on one page",
        description="Report the JSON-LD on a page node by node: what types it "
        "declares, which required and recommended properties are missing, and "
        "whether it parses at all.",
    )
    _page_flags(validate)
    validate.add_argument(
        "--suggest",
        action="store_true",
        help="emit JSON-LD built from what the page already states",
    )

    llmstxt = subparsers.add_parser(
        "llmstxt",
        parents=[parent],
        help="check for an llms.txt, or build one from the site",
        description="Look for /llms.txt and /llms-full.txt and check their "
        "structure against the llmstxt.org format. With --generate, crawl the "
        "site and build one from the pages that were actually fetched.",
    )
    _page_flags(llmstxt)
    _crawl_flags(llmstxt)
    llmstxt.add_argument(
        "--generate",
        action="store_true",
        help="crawl the site and propose an llms.txt",
    )

    scan = subparsers.add_parser(
        "scan",
        parents=[parent],
        help="check whether a brand exists as a lookupable entity",
        description="Query Wikipedia, Wikidata, Reddit and YouTube for a brand "
        "name through their documented public APIs. Platforms with no usable API "
        "are listed as manual checks and never reported as results.",
    )
    scan.add_argument("brand", help="the brand name to look for")
    scan.add_argument(
        "--site",
        metavar="URL",
        help="also read this site's Organization sameAs links and compare them",
    )
    scan.add_argument("--timeout", type=float, default=http.DEFAULT_TIMEOUT, metavar="SECONDS")

    prune = subparsers.add_parser(
        "prune",
        parents=[parent],
        help="apply the retention rules to recorded history",
        description="Trim the append-only audit history by count, age and size. "
        "Reports what it would remove before removing it.",
    )
    prune.add_argument("--project", metavar="SLUG", help="one project instead of all of them")
    prune.add_argument("--keep", type=int, metavar="N", help="keep at most N runs per project")
    prune.add_argument(
        "--older-than", type=int, metavar="DAYS", help="drop runs older than DAYS"
    )
    prune.add_argument(
        "--dry-run", action="store_true", help="report the plan and change nothing"
    )

    subparsers.add_parser(
        "doctor",
        parents=[parent],
        help="check this installation and its environment",
        description="Report on the interpreter, PATH, state directory, data files "
        "and optional extras. Always exits 0: it reports, it does not gate.",
    )
    return parser


def _apply_config(args: argparse.Namespace) -> None:
    if not args.config:
        return
    path = Path(args.config).expanduser()
    try:
        values = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise GeoError("GEO_E_BAD_ARGS", f"Couldn't read config {path}: {exc}.") from exc
    if not isinstance(values, dict):
        raise GeoError("GEO_E_BAD_ARGS", f"Config {path} must contain a JSON object.")
    for key, value in values.items():
        if key not in CONFIG_KEYS:
            raise GeoError(
                "GEO_E_BAD_ARGS",
                f"Config {path} sets unknown key {key!r}. Accepted: {', '.join(CONFIG_KEYS)}.",
            )
        if hasattr(args, key) and getattr(args, key) in (None, False):
            setattr(args, key, value)


def _validate_url(args: argparse.Namespace) -> None:
    url = getattr(args, "url", None)
    if url is None or (getattr(args, "rescore", None) and url == "-"):
        return
    if "://" not in url:
        raise GeoError(
            "GEO_E_BAD_URL",
            f"{url!r} is not an absolute URL. Include the scheme, for example "
            f"https://{url}.",
        )


def _json_mode(args: argparse.Namespace, out: TextIO) -> bool:
    if getattr(args, "json", False):
        return True
    return not (hasattr(out, "isatty") and out.isatty())


def progress(args: argparse.Namespace, message: str) -> None:
    if not getattr(args, "quiet", False):
        print(message, file=sys.stderr)


def _emit(envelope: dict, args: argparse.Namespace, out: TextIO) -> None:
    payload = envelope_mod.dumps(envelope)
    if getattr(args, "out", None):
        target = Path(args.out).expanduser()
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(payload + "\n", encoding="utf-8")
    if _json_mode(args, out):
        print(payload, file=out)
    else:
        render.render(envelope, out)


def _log_for(error: GeoError, detail: str) -> str:
    try:
        state.ensure_home()
        state.write_log([f"error: {error.code}", error.message, "", detail])
    except Exception:  # pragma: no cover - logging must never mask the error
        pass
    return f"{state.display_home()}/{state.LOG_RELATIVE}"


def main(argv: list[str] | None = None, out: TextIO | None = None) -> int:
    out = out or sys.stdout
    parser = build_parser()
    args = parser.parse_args(argv)

    if not args.command:
        parser.print_help(out)
        return EXIT_USAGE

    run_id = new_run_id()
    try:
        _apply_config(args)
        _validate_url(args)
        progress(args, f"[1/1] {args.command} {getattr(args, 'url', '')}".rstrip())
        envelope = COMMANDS[args.command](args, run_id)
    except GeoError as error:
        failure = envelope_mod.build(
            args.command,
            ok=False,
            run_id=run_id,
            scores=None,
            error=error.as_dict(_log_for(error, "".join(traceback.format_exc()))),
        )
        _emit(failure, args, out)
        return error.exit_code
    except KeyboardInterrupt:  # pragma: no cover - interactive only
        print("Interrupted. Nothing was changed.", file=sys.stderr)
        return EXIT_INTERNAL
    except Exception as exc:  # noqa: BLE001 - the last line of defence
        internal = GeoError(
            "GEO_E_INTERNAL",
            f"geo {args.command} failed in an unexpected way: {type(exc).__name__}.",
        )
        failure = envelope_mod.build(
            args.command,
            ok=False,
            run_id=run_id,
            scores=None,
            error=internal.as_dict(_log_for(internal, "".join(traceback.format_exc()))),
        )
        _emit(failure, args, out)
        return internal.exit_code

    _emit(envelope, args, out)

    evidence = envelope.get("evidence") or {}
    if args.fail_on_partial and evidence.get("stamp") == PARTIAL:
        return GeoError("GEO_E_PARTIAL", "").exit_code
    return EXIT_OK


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
