"""The envelope contract: fixed keys, golden shape, canonical ordering."""

from __future__ import annotations

import io
import json

import pytest

from geo_audit._version import NORMALIZER_VERSION, SCHEMA_VERSION, SCORING_VERSION
from geo_audit.cli import main
from geo_audit.data import data_version
from pathlib import Path

from tests.golden import assert_matches

ENVELOPE_KEYS = [
    "schema_version",
    "command",
    "ok",
    "cli_version",
    "scoring_version",
    "data_version",
    "normalizer_version",
    "run_id",
    "observed_at",
    "evidence",
    "completeness",
    "scores",
    "signals",
    "findings",
    "error",
]

COMMAND_BLOCKS = {"score": "page", "fetch": "page", "doctor": "checks"}


def run(args, geo_home=None) -> tuple[int, dict]:
    buffer = io.StringIO()
    code = main(args + ["--json", "--quiet"], out=buffer)
    return code, json.loads(buffer.getvalue())


@pytest.mark.parametrize("command", ["fetch", "score"])
def test_fixed_key_set_and_order(site, geo_home, command):
    _, envelope = run([command, f"{site.url}/ssr-rich.html", "--allow-private"])
    assert list(envelope)[: len(ENVELOPE_KEYS)] == ENVELOPE_KEYS
    extra = set(envelope) - set(ENVELOPE_KEYS)
    assert extra <= {COMMAND_BLOCKS[command], "note"}


def test_doctor_uses_the_same_envelope(geo_home):
    _, envelope = run(["doctor"])
    assert list(envelope)[: len(ENVELOPE_KEYS)] == ENVELOPE_KEYS
    assert "checks" in envelope


def test_version_fields_are_present_on_every_command(site, geo_home):
    for args in (["doctor"], ["fetch", f"{site.url}/ssr-rich.html", "--allow-private"]):
        _, envelope = run(args)
        assert envelope["schema_version"] == SCHEMA_VERSION
        assert envelope["scoring_version"] == SCORING_VERSION
        assert envelope["normalizer_version"] == NORMALIZER_VERSION
        assert envelope["data_version"] == data_version()
        assert envelope["cli_version"]


def test_failure_envelope_has_scores_null_and_a_populated_error(geo_home):
    code, envelope = run(["score", "ftp://example.com/x"])
    assert code == 2
    assert envelope["ok"] is False
    assert envelope["scores"] is None
    assert set(envelope["error"]) == {"code", "message", "hint", "docs", "log"}
    assert envelope["error"]["code"] == "GEO_E_BLOCKED_SCHEME"


def test_there_is_no_request_flag_for_schema_version(geo_home):
    from geo_audit.cli import build_parser

    text = build_parser().format_help()
    assert "--schema-version" not in text


# --- goldens ---------------------------------------------------------------


def test_golden_score_ssr_rich(site, geo_home):
    _, envelope = run(["score", f"{site.url}/ssr-rich.html", "--allow-private", "--no-render"])
    assert_matches("score-ssr-rich", envelope, site.url)


def test_golden_score_bot_blocked(site, geo_home):
    _, envelope = run(["score", f"{site.url}/bot-block", "--allow-private", "--no-render"])
    assert_matches("score-bot-block", envelope, site.url)


def test_golden_fetch_ssr_rich(site, geo_home):
    _, envelope = run(["fetch", f"{site.url}/ssr-rich.html", "--allow-private"])
    assert_matches("fetch-ssr-rich", envelope, site.url)


def test_golden_score_weak_prose(site, geo_home):
    _, envelope = run(["score", f"{site.url}/weak-prose.html", "--allow-private", "--no-render"])
    assert_matches("score-weak-prose", envelope, site.url)


def test_golden_crawl(site, geo_home):
    _, envelope = run(["crawl", f"{site.url}/hub.html", "--allow-private", "--rate", "50",
                       "--max-pages", "8"])
    assert_matches("crawl-hub", envelope, site.url)


def test_golden_audit(site, geo_home):
    _, envelope = run(["audit", f"{site.url}/hub.html", "--allow-private", "--rate", "50",
                       "--max-pages", "8"])
    assert_matches("audit-hub", envelope, site.url)


def test_golden_audit_partial(site, geo_home):
    """The start URL is refused, the sitemap still yields pages, so the run is PARTIAL.

    No other golden covers a PARTIAL stamp or a populated `pages_failed`. The
    refused page leads although it was never scored and carries no impact; the
    tiebreak that once lost it the lead is pinned in test_scoring, since the
    pages behind this start URL no longer produce a second blocker - short pages
    stopped counting as gated in scoring 3.0.
    """
    _, envelope = run(["audit", f"{site.url}/bot-block", "--allow-private", "--rate", "50",
                       "--max-pages", "8"])
    assert envelope["evidence"]["stamp"] == "PARTIAL"
    assert envelope["findings"][0]["id"] == "fetch.blocked"
    assert_matches("audit-bot-block", envelope, site.url)


def test_golden_error_envelope(geo_home):
    """What a caller gets when the request was never valid. Nothing else golds ok=false."""
    code, envelope = run(["score", "ftp://example.com/x"])
    assert code == 2 and envelope["ok"] is False
    assert_matches("error-bad-scheme", envelope, "http://unused.invalid")


def test_golden_validate(site, geo_home):
    _, envelope = run(["validate", f"{site.url}/ssr-rich.html", "--allow-private", "--suggest"])
    assert_matches("validate-ssr-rich", envelope, site.url)


def test_golden_llmstxt(site, geo_home):
    _, envelope = run(["llmstxt", f"{site.url}/hub.html", "--allow-private", "--rate", "50",
                       "--max-pages", "8", "--generate"])
    assert_matches("llmstxt-hub", envelope, site.url)


def test_golden_scan(site, geo_home, monkeypatch):
    from geo_audit.commands import scan as scan_cmd

    monkeypatch.setattr(
        scan_cmd,
        "_platforms",
        lambda: {
            "wikipedia": {
                "label": "Wikipedia",
                "url": f"{site.url}/not-html?q={{query}}",
                "docs": "https://example.test/docs",
                "needs_key": None,
            }
        },
    )
    _, envelope = run(["scan", "Acme", "--allow-private"])
    assert_matches("scan-acme", envelope, site.url)


def test_golden_compare(site, geo_home):
    crawl = ["--allow-private", "--rate", "50", "--max-pages", "8"]
    run(["audit", f"{site.url}/hub.html", *crawl])
    run(["audit", f"{site.url}/hub.html", *crawl])
    _, envelope = run(["compare", f"{site.url}/hub.html"])
    assert_matches("compare-hub", envelope, site.url)


def test_golden_report(site, geo_home):
    crawl = ["--allow-private", "--rate", "50", "--max-pages", "8"]
    run(["audit", f"{site.url}/hub.html", *crawl])
    _, envelope = run(["report", f"{site.url}/hub.html"])
    assert_matches("report-hub", envelope, site.url)


def test_golden_prune(site, geo_home):
    crawl = ["--allow-private", "--rate", "50", "--max-pages", "8"]
    run(["audit", f"{site.url}/hub.html", *crawl])
    _, envelope = run(["prune", "--dry-run", "--keep", "1"])
    assert_matches("prune-dry-run", envelope, site.url)


def test_doctor_has_a_stable_shape_rather_than_a_golden(geo_home):
    """Doctor reports on this machine, so its values are not comparable.

    The check ids and the status vocabulary are, and those are the contract a
    caller depends on.
    """
    _, envelope = run(["doctor"])
    ids = [check["id"] for check in envelope["checks"]]
    assert ids == sorted(set(ids)) or len(ids) == len(set(ids)), "check ids must be unique"
    assert {check["status"] for check in envelope["checks"]} <= {"ok", "warn", "fail"}
    assert {"python", "cli_version", "data_files", "state_writable"} <= set(ids)


def test_every_command_has_golden_or_shape_coverage():
    """A command with neither is a command whose output nobody is watching."""
    from geo_audit.cli import COMMANDS

    source = Path(__file__).read_text(encoding="utf-8")
    uncovered = [
        name
        for name in COMMANDS
        if f'"{name}' not in source and f"test_golden_{name}" not in source
    ]
    assert not uncovered, f"no envelope coverage for: {sorted(uncovered)}"


def test_two_runs_of_the_same_page_differ_only_in_volatile_fields(site, geo_home):
    from tests.golden import normalize

    _, first = run(["score", f"{site.url}/ssr-rich.html", "--allow-private", "--no-render"])
    _, second = run(["score", f"{site.url}/ssr-rich.html", "--allow-private", "--no-render"])
    assert normalize(first, site.url) == normalize(second, site.url)
    assert first["run_id"] != second["run_id"]


# --- the goldens have to be machine-independent ---------------------------


@pytest.mark.parametrize(
    "value",
    [
        "/tmp/pytest-of-runner/pytest-0/geo-home",
        "/private/var/folders/v2/abc/T/pytest-of-x/pytest-1/geo-home",
        "/var/folders/v2/abc/T/pytest-of-x/pytest-1/geo-home",
        r"C:\Users\runneradmin\AppData\Local\Temp\pytest-of-runner\pytest-0\geo-home",
        # Windows temp sits under the user's home, so a displayed path comes
        # back tilde-prefixed and matches no drive-letter pattern. That is what
        # made the prune golden fail on Windows and nowhere else.
        r"~/AppData\Local\Temp\pytest-of-runner\pytest-0\geo-home",
    ],
)
def test_machine_paths_are_scrubbed_from_goldens(value):
    from tests.golden import _scrub_paths

    payload = json.dumps({"home": value})
    assert value not in _scrub_paths(payload), f"{value} would leak into a golden"


@pytest.mark.parametrize(
    "value",
    ["https://example.com/temperature", "/docs/templates", "https://x.test/tmp-guide"],
)
def test_the_scrub_leaves_real_values_alone(value):
    from tests.golden import _scrub_paths

    payload = json.dumps({"url": value})
    assert _scrub_paths(payload) == payload
