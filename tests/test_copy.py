"""The interaction states are copy, and copy is reviewed, not improvised."""

from __future__ import annotations

import io

from geo_audit import copy as copytext
from geo_audit.cli import main


class FakeTTY(io.StringIO):
    def isatty(self) -> bool:
        return True


def render(args):
    out = FakeTTY()
    code = main(args + ["--quiet"], out=out)
    return code, out.getvalue()


def test_success_state_pairs_the_number_with_its_label(site, geo_home):
    _, output = render(["score", f"{site.url}/ssr-rich.html", "--allow-private", "--no-render"])
    assert "GEO citability score" in output
    assert "/100 (" in output, "a number without its tier label is half a verdict"
    assert "evidence CURRENT" in output


def test_success_state_ends_with_one_suggested_next_command(site, geo_home):
    _, output = render(["score", f"{site.url}/ssr-rich.html", "--allow-private", "--no-render"])
    assert output.strip().splitlines()[-1].startswith("Next: ")


def test_empty_state_says_nothing_was_scored(site, geo_home):
    _, output = render(["score", f"{site.url}/bot-block", "--allow-private"])
    assert "found no scorable pages" in output
    assert "Nothing was scored." in output
    assert "/100" not in output, "no score may be shown when nothing was scored"


def test_error_state_shows_message_code_hint_and_log_but_no_score(geo_home):
    _, output = render(["score", "example.com"])
    assert "GEO_E_BAD_URL" in output
    assert "logs/last-run.log" in output
    assert "Traceback" not in output
    assert "/100" not in output


def test_refuse_to_run_state_says_nothing_was_changed(site, geo_home):
    import json

    from geo_audit import state
    from geo_audit._version import STATE_VERSION

    state.init()
    (geo_home / state.STATE_FILE).write_text(
        json.dumps({"state_version": STATE_VERSION + 1, "cli_version": "9.9.9"}), encoding="utf-8"
    )
    code, output = render(["score", f"{site.url}/ssr-rich.html", "--allow-private"])
    assert code == 4
    assert copytext.STATE_NEWER_SUFFIX in output
    assert "Traceback" not in output


def test_partial_state_names_how_many_pages_were_scored(site, geo_home):
    text = copytext.PARTIAL.format(ok=41, total=50, failed=9, reasons="6 blocked, 3 timed out")
    assert "PARTIAL audit: 41 of 50 pages scored." in text
    assert "Scores reflect the 41 pages only." in text


def test_an_empty_page_states_the_reason_instead_of_a_bare_zero(site, geo_home):
    _, output = render(["score", f"{site.url}/no-blocks.html", "--allow-private", "--no-render"])
    assert "No citable content blocks found on this page." in output
    assert "reason: no extractable blocks" in output


def test_an_empty_page_is_not_told_to_rewrite_passages_it_does_not_have(site, geo_home):
    """Every prose signal reads zero on an empty page, but only one is a cause."""
    import io as _io
    import json as _json

    from geo_audit.cli import main as _main

    buffer = _io.StringIO()
    _main(
        ["score", f"{site.url}/no-blocks.html", "--allow-private", "--quiet", "--no-render", "--json"],
        out=buffer,
    )
    ids = {f["id"] for f in _json.loads(buffer.getvalue())["findings"]}
    assert "citability.extractability" in ids, "the cause must still be reported"
    assert "citability.self_containment" not in ids
    assert "citability.answer_first" not in ids
    assert "citability.attribution" not in ids


def test_a_page_with_content_still_gets_every_finding(site, geo_home):
    import io as _io
    import json as _json

    from geo_audit.cli import main as _main

    buffer = _io.StringIO()
    _main(
        ["score", f"{site.url}/weak-prose.html", "--allow-private", "--quiet", "--no-render", "--json"],
        out=buffer,
    )
    ids = {f["id"] for f in _json.loads(buffer.getvalue())["findings"]}
    assert "citability.self_containment" in ids
    assert "citability.answer_first" in ids


def test_a_finding_with_no_points_to_recover_does_not_advertise_zero(site, geo_home):
    """robots and fetch findings are not scored signals.

    Printing "+0 points available" beside a critical finding reads as "fixing
    this gains you nothing", which is the opposite of what it means.
    """
    _, output = render(["score", f"{site.url}/private/secret.html", "--allow-private", "--no-render"])
    assert "blocks crawlers that AI answers depend on" in output
    assert "+0 points available" not in output
    assert "critical \u00b7 low effort" in output


def test_a_scored_finding_still_shows_what_it_recovers(site, geo_home):
    _, output = render(["score", f"{site.url}/weak-prose.html", "--allow-private", "--no-render"])
    assert "points available" in output


def test_the_recorded_path_is_one_a_user_can_open(site, geo_home):
    import io as _io
    import json as _json

    from geo_audit import state
    from geo_audit.cli import main as _main

    buffer = _io.StringIO()
    _main(
        ["score", f"{site.url}/ssr-rich.html", "--allow-private", "--quiet", "--no-render", "--json"],
        out=buffer,
    )
    record = _json.loads(buffer.getvalue())["page"]["record"]
    assert record.startswith(state.display_home())
    assert record.endswith("audits.jsonl")
    from pathlib import Path

    assert Path(record.replace(state.display_home(), str(state.geo_home()), 1)).is_file()


def test_doctor_headline_counts_checks(geo_home):
    _, output = render(["doctor"])
    from geo_audit._version import DIST_NAME

    assert DIST_NAME in output
    assert "checks" in output


def test_no_market_statistics_in_user_facing_copy():
    """Marketing numbers in prompts and CLI output go stale and are unsourced."""
    import re

    source = (
        __import__("pathlib").Path(copytext.__file__).read_text(encoding="utf-8")
    )
    assert not re.search(r"\d+\s?%", source)
    assert "billion" not in source.lower()


# --- the §3.9 states that had no test ---------------------------------------
# The PRD says golden tests assert every state's copy. Four had none, and two of
# those were wrong in ways nobody saw: a dead-end install command, and
# "Only 0 audit is recorded ... run `geo audit` again".


def test_loading_state_reports_crawl_progress_on_stderr(site, geo_home, capsys):
    import re

    main(["audit", f"{site.url}/hub.html", "--allow-private", "--rate", "50", "--max-pages", "4",
          "--json"], out=io.StringIO())
    stderr = capsys.readouterr().err
    assert re.search(r"\[2/4\] Crawling \S+ [-—] \d+/\d+ pages, \d+ failed", stderr), stderr[:300]


def test_empty_state_with_no_audit_names_the_site_and_the_command(geo_home):
    """Not `<url>`, and not "Only 0 audit ... again"."""
    for command in ("report", "compare"):
        buffer = io.StringIO()
        code = main([command, "https://example.com", "--json", "--quiet"], out=buffer)
        message = __import__("json").loads(buffer.getvalue())["error"]["message"]
        assert code == 2
        assert message == copytext.NO_AUDITS.format(site="example.com", url="https://example.com"), command


def test_zero_mentions_is_a_result_not_an_error(geo_home, monkeypatch):
    from geo_audit.commands import scan as scan_cmd

    def nobody_has_heard_of_it(name, brand, spec, allow_private=False):
        return {"platform": name, "label": spec["label"], "checked": True, "status": 200,
                "results": 0, "examples": [], "docs": spec["docs"], "observed_at": "2026-09-21T00:00:00Z"}

    monkeypatch.setattr(scan_cmd, "check", nobody_has_heard_of_it)
    _, output = render(["scan", "Acme"])
    assert "No mentions of “Acme” found on" in output
    assert "This is a result, not an error." in output


def test_pdf_unavailable_offers_an_install_that_works(site, geo_home, monkeypatch):
    """The PRD's literal copy named the PyPI package, which does not exist before
    the first release: the same dead end the skills, docs and doctor had lost."""
    from geo_audit._version import install_target
    from geo_audit.report import pdf as pdf_lib

    main(["audit", f"{site.url}/hub.html", "--allow-private", "--rate", "50", "--max-pages", "4",
          "--json", "--quiet"], out=io.StringIO())
    monkeypatch.setattr(pdf_lib, "write_pdf", lambda html, target: "the browser component is not installed")
    buffer = io.StringIO()
    main(["report", f"{site.url}/hub.html", "--pdf", "--json", "--quiet"], out=buffer)
    skipped = __import__("json").loads(buffer.getvalue())["report"]["pdf_skipped"]
    assert skipped.startswith("PDF skipped: the browser component is not installed.")
    assert f"uv tool install {install_target('browser')} && playwright install chromium" in skipped
