"""The envelope contract: fixed keys, golden shape, canonical ordering."""

from __future__ import annotations

import io
import json

import pytest

from geo_audit._version import NORMALIZER_VERSION, SCHEMA_VERSION, SCORING_VERSION
from geo_audit.cli import main
from geo_audit.data import data_version
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


def test_two_runs_of_the_same_page_differ_only_in_volatile_fields(site, geo_home):
    from tests.golden import normalize

    _, first = run(["score", f"{site.url}/ssr-rich.html", "--allow-private", "--no-render"])
    _, second = run(["score", f"{site.url}/ssr-rich.html", "--allow-private", "--no-render"])
    assert normalize(first, site.url) == normalize(second, site.url)
    assert first["run_id"] != second["run_id"]
