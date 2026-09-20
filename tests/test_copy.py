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


def test_doctor_headline_counts_checks(geo_home):
    _, output = render(["doctor"])
    assert "geo-audit-cli" in output
    assert "checks" in output


def test_no_market_statistics_in_user_facing_copy():
    """Marketing numbers in prompts and CLI output go stale and are unsourced."""
    import re

    source = (
        __import__("pathlib").Path(copytext.__file__).read_text(encoding="utf-8")
    )
    assert not re.search(r"\d+\s?%", source)
    assert "billion" not in source.lower()
