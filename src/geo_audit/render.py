"""Human rendering.

The same envelope drives this and the JSON output, so the two can never
disagree about a number. Everything here is derived; nothing is computed.

Score is always rendered as number *and* tier label together. Colour is a
third channel on top of both, never the only one carrying the verdict.
"""

from __future__ import annotations

import os
import sys
from typing import TextIO

from geo_audit import assistants
from geo_audit import copy as copytext
from geo_audit._version import DIST_NAME
from geo_audit.lib.crawl import urls_found
from geo_audit.lib.slug import host_of
from geo_audit.scoring.model import NOT_APPLICABLE

_SEVERITY_MARK = {"critical": "!!", "high": "! ", "medium": "~ ", "low": ". "}


def _use_colour(stream: TextIO) -> bool:
    if os.environ.get("NO_COLOR"):
        return False
    return hasattr(stream, "isatty") and stream.isatty()


class Style:
    def __init__(self, stream: TextIO) -> None:
        self.on = _use_colour(stream)

    def bold(self, text: str) -> str:
        return f"\033[1m{text}\033[0m" if self.on else text

    def dim(self, text: str) -> str:
        return f"\033[2m{text}\033[0m" if self.on else text


def render(envelope: dict, out: TextIO | None = None) -> None:
    out = out or sys.stdout
    style = Style(out)
    if not envelope.get("ok"):
        _render_error(envelope, out)
        return
    command = envelope.get("command")
    if command == "score":
        _render_score(envelope, out, style)
    elif command == "fetch":
        _render_fetch(envelope, out, style)
    elif command == "crawl":
        _render_crawl(envelope, out, style)
    elif command == "audit":
        _render_audit(envelope, out, style)
    elif command == "compare":
        _render_compare(envelope, out, style)
    elif command == "report":
        _render_report(envelope, out, style)
    elif command == "validate":
        _render_validate(envelope, out, style)
    elif command == "llmstxt":
        _render_llmstxt(envelope, out, style)
    elif command == "prune":
        _render_prune(envelope, out, style)
    elif command == "scan":
        _render_scan(envelope, out, style)
    elif command == "doctor":
        _render_doctor(envelope, out, style)
    else:  # pragma: no cover - every command registers a renderer
        print(envelope, file=out)


def _render_error(envelope: dict, out: TextIO) -> None:
    error = envelope.get("error") or {}
    print(
        copytext.ERROR.format(
            message=error.get("message", "Something went wrong."),
            code=error.get("code", "GEO_E_INTERNAL"),
            hint=error.get("hint", ""),
            log=error.get("log", ""),
        ).strip(),
        file=out,
    )


def _render_findings(envelope: dict, out: TextIO, style: Style, limit: int = 3) -> None:
    findings = envelope.get("findings") or []
    if not findings:
        return
    print(file=out)
    print(style.bold("Top fixes"), file=out)
    for finding in findings[:limit]:
        mark = _SEVERITY_MARK.get(finding["severity"], "  ")
        print(f"  {mark} {finding['title']}", file=out)
        meta = f"{finding['severity']} · {finding['effort']} effort"
        pages = finding.get("pages") or []
        if len(pages) > 1:
            meta += f" · {len(pages)} pages"
        # `points_lost` is on the category's 0-100 scale, so printed under the
        # overall score it read as overall points: five fixes "worth" 26.7 on
        # a site at 91. `impact` is the same loss on the overall scale.
        if finding.get("impact"):
            meta += f" · up to +{finding['impact']:g} overall"
        elif finding["points_lost"] > 0:
            meta += f" · +{finding['points_lost']:g} {finding['id'].split('.', 1)[0]} points available"
        print(style.dim(f"      {meta}"), file=out)
        print(f"      {finding['remediation']}", file=out)
    if len(findings) > limit:
        print(style.dim(f"  {len(findings) - limit} more in the JSON output."), file=out)


def _render_score(envelope: dict, out: TextIO, style: Style) -> None:
    scores = envelope.get("scores") or {}
    evidence = envelope.get("evidence") or {}
    page = envelope.get("page") or {}
    site = host_of(page.get("final_url") or page.get("requested_url") or "")

    if scores.get("composite") is None:
        print(
            copytext.NO_SCORABLE_PAGES.format(site=site, status=page.get("status", "no response")),
            file=out,
        )
        _render_findings(envelope, out, style)
        return

    print(
        style.bold(
            copytext.SCORE_SUCCESS.format(
                score=scores["composite"],
                tier=scores["tier"].capitalize(),
                site=site,
                pages=evidence.get("pages_ok", 1),
                stamp=evidence.get("stamp", "CURRENT"),
            )
        ),
        file=out,
    )
    print(style.dim(f"  {scores.get('tier_meaning', '')}"), file=out)

    if envelope.get("note"):
        print(f"  {envelope['note']}", file=out)

    completeness = envelope.get("completeness") or {}
    if completeness.get("missing"):
        print(
            style.dim(
                f"  Computed on {completeness['computed']} of {completeness['total']} "
                f"signals. Not measured: {', '.join(completeness['missing'])}."
            ),
            file=out,
        )

    print(file=out)
    print(style.bold("Signals"), file=out)
    width = max((len(s["id"]) for s in envelope.get("signals", [])), default=0)
    for signal in envelope.get("signals", []):
        if signal["value"] is None:
            applies = not (signal.get("skipped_reason") or "").startswith(NOT_APPLICABLE)
            value = "not measured" if applies else "not applicable"
        else:
            value = f"{signal['value']:g}/{signal['max']:g}"
        print(
            f"  {signal['id']:<{width}}  {value:>14}  {style.dim(signal['class'])}",
            file=out,
        )

    _render_findings(envelope, out, style)

    print(file=out)
    print(style.dim(f"Evidence {evidence.get('stamp')} · hash {evidence.get('content_hash', '')[:8]} · "
                    f"scoring {envelope['scoring_version']} · data {envelope['data_version']}"), file=out)
    if page.get("record"):
        print(style.dim(f"Recorded in {page['record']}"), file=out)
    print(
        copytext.NEXT_COMMAND.format(
            command=f"geo score {page.get('final_url', '')} --json"
        ),
        file=out,
    )


def _render_fetch(envelope: dict, out: TextIO, style: Style) -> None:
    page = envelope.get("page") or {}
    evidence = envelope.get("evidence") or {}
    print(
        style.bold(
            f"{page.get('status')} {page.get('final_url')} — "
            f"{page.get('blocks', 0)} content blocks, "
            f"{page.get('content_chars', 0):,} characters"
        ),
        file=out,
    )
    if page.get("redirect_chain"):
        for hop in page["redirect_chain"]:
            print(style.dim(f"  {hop['status']} {hop['url']} -> {hop['location']}"), file=out)
    print(
        style.dim(
            f"  content-type {page.get('content_type')} · {page.get('bytes', 0):,} bytes · "
            f"{page.get('elapsed_ms', 0)} ms · root <{page.get('content_root')}>"
        ),
        file=out,
    )
    robots = page.get("robots") or {}
    if robots:
        blocked = [row["agent"] for row in robots.get("access", []) if not row["allowed"]]
        summary = "all listed AI crawlers allowed" if not blocked else f"blocked: {', '.join(blocked)}"
        print(style.dim(f"  robots.txt {robots.get('status')} — {summary}"), file=out)
    print(file=out)
    print(
        style.dim(
            f"Evidence {evidence.get('stamp')} · hash {evidence.get('content_hash', '')[:8]} · "
            f"normalizer {envelope['normalizer_version']}"
        ),
        file=out,
    )
    _render_findings(envelope, out, style)
    print(copytext.NEXT_COMMAND.format(command=f"geo score {page.get('final_url', '')}"), file=out)


def _render_audit(envelope: dict, out: TextIO, style: Style) -> None:
    """Reader order, not audit-decomposition order: where do I stand, then what do I do."""
    scores = envelope.get("scores") or {}
    evidence = envelope.get("evidence") or {}
    block = envelope.get("crawl") or {}
    rescored = envelope.get("rescore")

    print(
        style.bold(
            f"GEO score {scores.get('composite')}/100 "
            f"({scores.get('tier', '').capitalize()}) for {block.get('site')} - "
            f"{evidence.get('pages_ok', 0)} pages, evidence {evidence.get('stamp')}."
        ),
        file=out,
    )
    print(style.dim(f"  {scores.get('tier_meaning', '')}"), file=out)
    if block.get("stopped_because") == "max_pages":
        capped = copytext.CAPPED.format(
            limit=(block.get("limits") or {}).get("max_pages"), found=urls_found(block), scored=evidence.get("pages_ok", 0)
        )
        print(style.dim(f"  {capped} Raise the limit with --max-pages."), file=out)

    failed = evidence.get("pages_failed") or []
    if failed:
        reasons: dict[str, int] = {}
        for entry in failed:
            reasons[entry["reason"]] = reasons.get(entry["reason"], 0) + 1
        summary = ", ".join(f"{count} {reason}" for reason, count in sorted(reasons.items()))
        print(
            style.dim(
                f"  PARTIAL: {evidence.get('pages_ok', 0)} of "
                f"{block.get('pages_crawled', 0)} pages scored. {len(failed)} could not "
                f"be evaluated ({summary}). Scores reflect the "
                f"{evidence.get('pages_ok', 0)} pages only."
            ),
            file=out,
        )

    completeness = envelope.get("completeness") or {}
    if completeness.get("missing"):
        print(
            style.dim(
                f"  Computed on {completeness['computed']} of {completeness['total']} "
                f"signals. Not measured: {', '.join(completeness['missing'])}."
            ),
            file=out,
        )
    if rescored:
        print(
            style.dim(
                f"  Recomputed from run {rescored['run_id']} recorded "
                f"{rescored['observed_at']}. No network was used."
            ),
            file=out,
        )
        if not rescored.get("versions_match"):
            print(
                style.dim(
                    "  Versions have moved since that run, so this number is not the "
                    "one that was recorded."
                ),
                file=out,
            )

    categories = scores.get("categories") or {}
    if categories:
        print(file=out)
        print(style.bold("Category scores"), file=out)
        width = max(len(name) for name in categories)
        weights = (completeness.get("categories") or {}).get("weights_used") or {}
        for name, value in sorted(categories.items(), key=lambda pair: -pair[1]):
            weight = weights.get(name)
            label = f" (weight {weight})" if weight else ""
            print(f"  {name:<{width}}  {value:>3}/100  {style.dim(label.strip())}", file=out)

    _render_findings(envelope, out, style, limit=5)
    _render_assistants((envelope.get("scan") or {}).get("assistants"), out, style)

    print(file=out)
    print(
        style.dim(
            f"Evidence {evidence.get('stamp')} - site hash "
            f"{(evidence.get('content_hash') or '')[:8]} - scoring "
            f"{envelope['scoring_version']} - data {envelope['data_version']} - "
            f"run {envelope['run_id']}"
        ),
        file=out,
    )
    if block.get("record"):
        print(style.dim(f"Recorded in {block['record']}"), file=out)
    # A rescore is not recorded, so its own run id is not one to rescore.
    recorded = (envelope.get("rescore") or {}).get("run_id") or envelope["run_id"]
    print(
        copytext.NEXT_COMMAND.format(
            command=f"geo audit {block.get('start_url', '')} --rescore {recorded}"
        ),
        file=out,
    )


def _arrow(delta: float | None) -> str:
    if delta is None:
        return "  "
    if delta > 0:
        return "up"
    if delta < 0:
        return "dn"
    return "--"


def _render_report(envelope: dict, out: TextIO, style: Style) -> None:
    block = envelope.get("report") or {}
    scores = envelope.get("scores") or {}
    brand = block.get("brand") or {}

    print(
        style.bold(
            copytext.REPORT_WRITTEN.format(
                mode=block.get("mode", "client").capitalize(),
                site=block.get("site"),
                path=block.get("path"),
            )
        ),
        file=out,
    )
    print(
        style.dim(
            f"  GEO score {scores.get('composite')}/100 "
            f"({(scores.get('tier') or '').capitalize()}) from run {block.get('from_run')}, "
            f"recorded {block.get('observed_at')}."
        ),
        file=out,
    )
    if block.get("pdf_path"):
        print(style.dim(f"  PDF: {block['pdf_path']}"), file=out)
    if block.get("pdf_skipped"):
        print(file=out)
        print(block["pdf_skipped"], file=out)
    if brand.get("customised"):
        print(style.dim(f"  Brand: {brand.get('name') or brand.get('source')}"), file=out)
    for warning in brand.get("warnings") or []:
        print(style.dim(f"  Brand fallback: {warning}"), file=out)
    if block.get("mode") == "client":
        print(
            style.dim(
                "  Client mode: no run ids, evidence hashes, failed-page list or "
                "signal internals are in this file."
            ),
            file=out,
        )

    print(file=out)
    print(
        copytext.NEXT_COMMAND.format(
            command=f"geo report {block.get('site', '')} --mode operator"
        ),
        file=out,
    )


def _render_compare(envelope: dict, out: TextIO, style: Style) -> None:
    block = envelope.get("compare") or {}
    before, after = block.get("from") or {}, block.get("to") or {}
    delta = block.get("composite_delta")

    direction = "unchanged"
    if delta and delta > 0:
        direction = f"up {delta:g}"
    elif delta and delta < 0:
        direction = f"down {abs(delta):g}"

    print(
        style.bold(
            f"GEO score {before.get('composite')} -> {after.get('composite')} "
            f"({direction}) for {envelope.get('site')}."
        ),
        file=out,
    )
    if block.get("tier_changed"):
        print(
            style.dim(
                f"  Tier moved from {before.get('tier')} to {after.get('tier')}."
            ),
            file=out,
        )
    print(
        style.dim(
            f"  {before.get('observed_at')} ({before.get('pages_ok')} pages) -> "
            f"{after.get('observed_at')} ({after.get('pages_ok')} pages)"
        ),
        file=out,
    )

    categories = block.get("categories") or {}
    if categories:
        print(file=out)
        print(style.bold("Categories"), file=out)
        width = max(len(name) for name in categories)
        for name, entry in sorted(categories.items(), key=lambda kv: (kv[1]["delta"] or 0)):
            move = entry["delta"]
            shown = "no change" if move in (None, 0) else f"{move:+g}"
            print(
                f"  {_arrow(move)} {name:<{width}}  {entry['before']} -> {entry['after']}  "
                f"{style.dim(shown)}",
                file=out,
            )

    findings = block.get("findings") or {}
    if findings.get("resolved_titles"):
        print(file=out)
        print(style.bold(f"Resolved ({len(findings['resolved_titles'])})"), file=out)
        for title in findings["resolved_titles"][:5]:
            print(f"  + {title}", file=out)
    if findings.get("introduced_titles"):
        print(file=out)
        print(style.bold(f"New ({len(findings['introduced_titles'])})"), file=out)
        for title in findings["introduced_titles"][:5]:
            print(f"  - {title}", file=out)
    if findings.get("persisting"):
        print(
            style.dim(f"\n  {len(findings['persisting'])} finding(s) unchanged since last time."),
            file=out,
        )

    pages = block.get("pages") or {}
    print(file=out)
    print(
        style.bold(
            f"Pages: {len(pages.get('changed') or [])} changed, "
            f"{len(pages.get('added') or [])} added, "
            f"{len(pages.get('removed') or [])} gone, "
            f"{pages.get('unchanged', 0)} untouched"
        ),
        file=out,
    )
    for url in (pages.get("changed") or [])[:5]:
        print(style.dim(f"  changed  {url}"), file=out)

    print(file=out)
    versions = (block.get("versions") or {}).get("to") or {}
    print(
        style.dim(
            f"Both runs scored at scoring {versions.get('scoring_version')} - "
            f"data {versions.get('data_version')}"
        ),
        file=out,
    )
    print(
        copytext.NEXT_COMMAND.format(command=f"geo audit {envelope.get('url', '')}"),
        file=out,
    )


def _render_crawl(envelope: dict, out: TextIO, style: Style) -> None:
    block = envelope.get("crawl") or {}
    evidence = envelope.get("evidence") or {}
    failed = evidence.get("pages_failed") or []

    print(
        style.bold(
            f"{block.get('pages_ok', 0)} of {block.get('pages_crawled', 0)} pages "
            f"scorable on {block.get('site')} - evidence {evidence.get('stamp')}."
        ),
        file=out,
    )
    limits = block.get("limits") or {}
    print(
        style.dim(
            f"  {limits.get('requests_per_second')} req/s across "
            f"{limits.get('concurrency')} workers, cap {limits.get('max_pages')} pages, "
            f"{block.get('elapsed_ms', 0) / 1000:.1f}s. Stopped: {block.get('stopped_because')}."
        ),
        file=out,
    )
    if block.get("seeded_from_sitemap"):
        print(
            style.dim(
                f"  {block['seeded_from_sitemap']} page(s) came from the sitemap, not from a link."
            ),
            file=out,
        )

    if failed:
        print(file=out)
        print(style.bold(f"Could not be evaluated ({len(failed)})"), file=out)
        for entry in failed[:10]:
            status = entry.get("status")
            print(f"  {entry['reason']:<16} {status if status else '':>3} {entry['url']}", file=out)
        if len(failed) > 10:
            print(style.dim(f"  {len(failed) - 10} more in the JSON output."), file=out)

    disallowed = block.get("disallowed_by_robots") or []
    if disallowed:
        print(file=out)
        print(style.bold(f"Out of reach by robots.txt ({len(disallowed)})"), file=out)
        for url in disallowed[:5]:
            print(f"  {url}", file=out)
        if len(disallowed) > 5:
            print(style.dim(f"  {len(disallowed) - 5} more in the JSON output."), file=out)

    _render_findings(envelope, out, style)

    print(file=out)
    print(
        style.dim(
            f"Evidence {evidence.get('stamp')} - site hash "
            f"{(evidence.get('content_hash') or '')[:8]} - normalizer "
            f"{envelope['normalizer_version']}"
        ),
        file=out,
    )
    print(
        copytext.NEXT_COMMAND.format(command=f"geo audit {block.get('start_url', '')}"),
        file=out,
    )


def _render_validate(envelope: dict, out: TextIO, style: Style) -> None:
    report = envelope.get("schema")
    page = envelope.get("page") or {}
    scores = envelope.get("scores") or {}

    if report is None:
        print(
            f"Nothing to validate: {page.get('final_url')} returned {page.get('status')}.",
            file=out,
        )
        _render_findings(envelope, out, style)
        return

    headline = {
        "absent": "No structured data on",
        "valid": "Structured data valid on",
        "invalid": "Structured data has problems on",
    }[report["verdict"]]
    print(
        style.bold(
            f"{headline} {page.get('final_url')} - "
            f"{report['blocks']} parsed block(s), schema score {scores.get('composite')}/100."
        ),
        file=out,
    )
    if report["parse_errors"]:
        print(style.dim(f"  JSON errors: {'; '.join(report['parse_errors'])}"), file=out)
    if report["unrecognised_types"]:
        print(
            style.dim(f"  Types with no requirements on file: {', '.join(report['unrecognised_types'])}"),
            file=out,
        )

    if report["nodes"]:
        print(file=out)
        print(style.bold("Nodes"), file=out)
        for node in report["nodes"]:
            mark = "ok  " if node["valid"] else "FAIL"
            print(f"  [{mark}] {node['type']}", file=out)
            if node["missing_required"]:
                print(style.dim(f"         missing required: {', '.join(node['missing_required'])}"), file=out)
            if node["missing_recommended"]:
                print(
                    style.dim(f"         missing recommended: {', '.join(node['missing_recommended'])}"),
                    file=out,
                )
    else:
        print(style.dim("  No recognised schema.org types on the page."), file=out)

    suggestion = report.get("suggestion")
    if suggestion and suggestion.get("needed"):
        print(file=out)
        print(style.bold("Suggested JSON-LD"), file=out)
        for line in suggestion["script"].splitlines():
            print(f"  {line}", file=out)
        if suggestion["fill_in"]:
            print(style.dim(f"  Fill in: {', '.join(suggestion['fill_in'])}"), file=out)

    _render_findings(envelope, out, style)
    print(file=out)
    print(copytext.NEXT_COMMAND.format(command=f"geo audit {page.get('final_url', '')}"), file=out)


def _render_llmstxt(envelope: dict, out: TextIO, style: Style) -> None:
    block = envelope.get("llmstxt") or {}
    existing = block.get("llms_txt") or {}
    generated = block.get("generated")

    if existing.get("present"):
        verdict = "valid" if existing.get("valid") else "has problems"
        print(
            style.bold(
                f"{block.get('site')} publishes an llms.txt and it is {verdict} - "
                f"{existing.get('link_count', 0)} links across "
                f"{len(existing.get('sections') or [])} section(s)."
            ),
            file=out,
        )
        if existing.get("problems"):
            for problem in existing["problems"]:
                print(style.dim(f"  - {problem}"), file=out)
    else:
        print(
            style.bold(f"{block.get('site')} publishes no llms.txt ({existing.get('url')})."),
            file=out,
        )
    if (block.get("llms_full_txt") or {}).get("present"):
        print(style.dim("  An llms-full.txt is published too."), file=out)

    if generated:
        print(file=out)
        print(
            style.bold(
                f"Proposed llms.txt - {generated['pages_listed']} pages "
                f"({generated['pages_optional']} marked optional), {generated['bytes']} bytes"
            ),
            file=out,
        )
        for line in generated["text"].splitlines()[:24]:
            print(f"  {line}", file=out)
        if len(generated["text"].splitlines()) > 24:
            print(style.dim("  ... full text in the JSON output"), file=out)
        if generated.get("written_to"):
            print(style.dim(f"  Written to {generated['written_to']}"), file=out)
        for entry in generated.get("excluded") or []:
            print(
                style.dim(
                    f"  Left out: {entry['url']} - its own title or summary is "
                    f"addressed to an AI system ({', '.join(entry['patterns'])})."
                ),
                file=out,
            )

    _render_findings(envelope, out, style)
    print(file=out)
    command = (
        f"geo llmstxt {envelope.get('llmstxt', {}).get('site', '')}"
        if generated
        else "geo llmstxt <url> --generate"
    )
    print(copytext.NEXT_COMMAND.format(command=command), file=out)


def _render_scan(envelope: dict, out: TextIO, style: Style) -> None:
    block = envelope.get("scan") or {}
    scores = envelope.get("scores") or {}
    platforms = block.get("platforms") or []
    checked = [entry for entry in platforms if entry["checked"]]

    if checked and block.get("total_results", 0) == 0:
        names = ", ".join(entry["label"] for entry in checked)
        date = (checked[0].get("observed_at") or "")[:10]
        print(
            style.bold(
                copytext.NO_MENTIONS.format(brand=block.get("brand"), platforms=names, date=date)
            ),
            file=out,
        )
    else:
        print(
            style.bold(
                f"Brand presence {scores.get('composite')}/100 "
                f"({scores.get('tier', '').capitalize()}) for "
                f"\u201c{block.get('brand')}\u201d - {block.get('total_results', 0)} results "
                f"across {block.get('platforms_checked')} of "
                f"{block.get('platforms_total')} platforms."
            ),
            file=out,
        )

    print(file=out)
    print(style.bold("Platforms"), file=out)
    width = max((len(entry["label"]) for entry in platforms), default=0)
    for entry in platforms:
        if entry["checked"]:
            detail = f"{entry.get('results', 0)} result(s)"
            example = (entry.get("examples") or [None])[0]
            if example:
                detail += f"  e.g. {example}"
            print(f"  [ok  ] {entry['label']:<{width}}  {detail}", file=out)
        else:
            print(f"  [skip] {entry['label']:<{width}}  {entry.get('reason', 'not checked')}", file=out)

    manual = block.get("manual_checks") or []
    if manual:
        print(file=out)
        print(style.bold("Manual checks - not results, and not scored"), file=out)
        for entry in manual:
            print(f"  {entry['label']}: {entry['how']}", file=out)
            print(style.dim(f"     ({entry['why']})"), file=out)

    _render_assistants(block.get("assistants"), out, style)
    _render_findings(envelope, out, style)
    print(file=out)
    completeness = envelope.get("completeness") or {}
    if completeness.get("missing"):
        print(
            style.dim(
                f"Computed on {completeness['computed']} of {completeness['total']} "
                f"signals. Not measured: {', '.join(completeness['missing'])}."
            ),
            file=out,
        )
    # With a site named, the next step is folding brand presence into its audit;
    # without one, it is naming the site. example.com is only ever a placeholder.
    site = block.get("site")
    command = (
        f"geo audit {site} --brand \"{block.get('brand')}\""
        if site
        else f"geo scan \"{block.get('brand')}\" --site https://example.com"
    )
    print(copytext.NEXT_COMMAND.format(command=command), file=out)


def _render_assistants(block: dict | None, out: TextIO, style: Style) -> None:
    """What each engine said, under a heading that says it is not a score."""
    if not block:
        return
    print(file=out)
    print(style.bold("AI assistants - observed answers, never scored"), file=out)
    if not block.get("asked"):
        print(f"  [skip] not asked: {block.get('reason')}", file=out)
        return
    engines = block.get("engines") or []
    width = max((len(entry["label"]) for entry in engines), default=0)
    for entry in engines:
        about, ranking = assistants.describe(entry, block.get("brand") or "the brand")
        print(f"  {entry['label']:<{width}}  {about}", file=out)
        print(f"  {'':<{width}}  {ranking}", file=out)
    spent = block.get("credits_used")
    left = block.get("credits_remaining")
    costs = (f"; {spent} credits used" if spent is not None else "") + (
        f", {left} left" if left is not None else ""
    )
    print(
        style.dim(
            f"  Asked through {block.get('provider')} in {block.get('locale')}{costs}. "
            "One answer from each engine: it can differ when asked again."
        ),
        file=out,
    )


def _render_prune(envelope: dict, out: TextIO, style: Style) -> None:
    block = envelope.get("prune") or {}
    projects = block.get("projects") or []
    verb = "Removed" if block.get("applied") else "Would remove"

    print(
        style.bold(
            f"{verb} {block.get('runs_dropped', 0)} run(s) across {len(projects)} "
            f"project(s) in {block.get('home')}."
        ),
        file=out,
    )
    limits = block.get("limits") or {}
    print(
        style.dim(
            f"  Keeping at most {limits.get('keep_runs')} runs per project, "
            f"nothing older than {limits.get('keep_days')} days, "
            f"{limits.get('max_project_bytes', 0) // 1024} KiB per project."
        ),
        file=out,
    )
    if projects:
        print(file=out)
        width = max(len(p["project"]) for p in projects)
        for project in projects:
            if project.get("skipped"):
                print(
                    f"  {project['project']:<{width}}  skipped: an audit was recorded while this ran, "
                    f"so nothing was changed. Run geo prune again.",
                    file=out,
                )
                continue
            reasons = ", ".join(f"{count} by {why}" for why, count in sorted(project["dropped_by"].items()))
            tail = f"  ({reasons})" if reasons else ""
            if project.get("pages_deleted"):
                tail += f"  {project['pages_deleted']} stored page(s), {project['page_bytes_reclaimed'] // 1024} KiB"
            print(
                f"  {project['project']:<{width}}  {project['runs_kept']:>4} kept  "
                f"{project['runs_dropped']:>4} dropped{tail}",
                file=out,
            )
    if not block.get("applied"):
        print(file=out)
        print(style.dim("  Nothing was changed. Drop --dry-run to apply."), file=out)
    print(file=out)
    print(copytext.NEXT_COMMAND.format(command="geo doctor"), file=out)


def _render_doctor(envelope: dict, out: TextIO, style: Style) -> None:
    checks = envelope.get("checks") or []
    failed = [c for c in checks if c["status"] != "ok"]
    headline = (
        copytext.DOCTOR_PROBLEMS.format(
            dist=DIST_NAME, version=envelope["cli_version"], failed=len(failed), total=len(checks)
        )
        if failed
        else copytext.DOCTOR_OK.format(
            dist=DIST_NAME, version=envelope["cli_version"], passed=len(checks), total=len(checks)
        )
    )
    print(style.bold(headline), file=out)
    print(file=out)
    width = max((len(c["id"]) for c in checks), default=0)
    marks = {"ok": "ok  ", "warn": "warn", "fail": "FAIL"}
    for check in checks:
        print(f"  [{marks.get(check['status'], '??')}] {check['id']:<{width}}  {check['detail']}", file=out)
        if check.get("hint"):
            print(style.dim(f"         {check['hint']}"), file=out)
    print(file=out)
    print(copytext.NEXT_COMMAND.format(command="geo score https://example.com"), file=out)
