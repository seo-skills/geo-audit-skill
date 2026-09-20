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

from geo_audit import copy as copytext
from geo_audit.lib.slug import host_of

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
        if finding["points_lost"] > 0:
            meta += f" · +{finding['points_lost']:g} points available"
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
            value = "not measured"
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


def _render_doctor(envelope: dict, out: TextIO, style: Style) -> None:
    checks = envelope.get("checks") or []
    failed = [c for c in checks if c["status"] != "ok"]
    headline = (
        copytext.DOCTOR_PROBLEMS.format(
            version=envelope["cli_version"], failed=len(failed), total=len(checks)
        )
        if failed
        else copytext.DOCTOR_OK.format(
            version=envelope["cli_version"], passed=len(checks), total=len(checks)
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
