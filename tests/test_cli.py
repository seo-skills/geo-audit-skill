"""Exit codes, output mode, and the global flags."""

from __future__ import annotations

import io
import json

import pytest

from geo_audit import state
from geo_audit._version import CLI_VERSION, DIST_NAME, STATE_VERSION
from geo_audit.cli import build_parser, main


class FakeTTY(io.StringIO):
    def isatty(self) -> bool:
        return True


def run(args, out=None):
    out = out if out is not None else io.StringIO()
    code = main(args, out=out)
    return code, out.getvalue()


# --- exit codes, one per class --------------------------------------------


def test_exit_0_on_success(site, geo_home):
    code, _ = run(["score", f"{site.url}/ssr-rich.html", "--allow-private", "--quiet", "--no-render"])
    assert code == 0


def test_exit_0_when_the_page_blocks_us(site, geo_home):
    """A working bot wall is a finding. Exiting non-zero would abort the audit."""
    code, output = run(["score", f"{site.url}/bot-block", "--allow-private", "--quiet"])
    assert code == 0
    envelope = json.loads(output)
    assert envelope["ok"] is True
    assert envelope["evidence"]["stamp"] == "PARTIAL"
    assert envelope["findings"][0]["severity"] == "critical"


def test_an_unscorable_page_says_what_it_could_not_measure(site, geo_home):
    """`0 of 0, nothing missing` reads as a complete run and divides by zero.

    Seven citability signals were in scope and the block reached none of them,
    which is what the envelope now says - the same shape a scorable page
    returns, with the values absent rather than the signals.
    """
    from geo_audit import data

    _, output = run(["score", f"{site.url}/bot-block", "--allow-private", "--quiet"])
    envelope = json.loads(output)
    declared = set(data.weights()["citability"]["signals"])

    assert envelope["scores"] is None
    assert envelope["completeness"]["computed"] == 0
    assert envelope["completeness"]["total"] == len(declared)
    assert set(envelope["completeness"]["missing"]) == declared
    assert {s["id"] for s in envelope["signals"]} == declared
    assert all(s["value"] is None and s["skipped_reason"] for s in envelope["signals"])


def test_exit_2_on_a_relative_url(geo_home):
    code, output = run(["score", "example.com", "--quiet"])
    assert code == 2
    assert json.loads(output)["error"]["code"] == "GEO_E_BAD_URL"


def test_exit_2_on_a_private_start_url_without_the_flag(site, geo_home):
    code, output = run(["score", f"{site.url}/ssr-rich.html", "--quiet"])
    assert code == 2
    assert json.loads(output)["error"]["code"] == "GEO_E_PRIVATE_ADDRESS"
    assert "--allow-private" in json.loads(output)["error"]["hint"]


def test_exit_3_on_a_network_failure_at_the_start_url(geo_home):
    code, output = run(["score", "https://nothing.invalid/page", "--quiet"])
    assert code == 3
    assert json.loads(output)["error"]["code"] in {"GEO_E_DNS", "GEO_E_CONNECT"}


def test_exit_3_on_a_redirect_loop(site, geo_home):
    code, output = run(["fetch", f"{site.url}/redirect-loop", "--allow-private", "--quiet"])
    assert code == 3
    assert json.loads(output)["error"]["code"] == "GEO_E_TOO_MANY_REDIRECTS"


def test_exit_4_when_state_is_newer(site, geo_home):
    state.init()
    (geo_home / state.STATE_FILE).write_text(
        json.dumps({"state_version": STATE_VERSION + 1, "cli_version": "9.9.9"}), encoding="utf-8"
    )
    code, output = run(["score", f"{site.url}/ssr-rich.html", "--allow-private", "--quiet"])
    assert code == 4
    assert json.loads(output)["error"]["code"] == "GEO_E_STATE_NEWER"


def test_exit_5_only_when_fail_on_partial_is_requested(site, geo_home):
    args = ["score", f"{site.url}/bot-block", "--allow-private", "--quiet"]
    assert run(args)[0] == 0
    assert run(args + ["--fail-on-partial"])[0] == 5


def test_fail_on_partial_does_not_fire_on_a_clean_run(site, geo_home):
    code, _ = run(
        ["score", f"{site.url}/ssr-rich.html", "--allow-private", "--quiet",
         "--no-render", "--fail-on-partial"]
    )
    assert code == 0


def test_exit_1_on_an_unexpected_internal_failure(site, geo_home, monkeypatch):
    from geo_audit.commands import score as score_cmd

    def boom(args, run_id):
        raise RuntimeError("something nobody predicted")

    monkeypatch.setitem(__import__("geo_audit.cli", fromlist=["COMMANDS"]).COMMANDS, "score", boom)
    code, output = run(["score", "https://example.com/x", "--quiet"])
    assert code == 1
    error = json.loads(output)["error"]
    assert error["code"] == "GEO_E_INTERNAL"
    assert "Traceback" not in error["message"]
    assert "RuntimeError" in error["message"]


def test_no_command_prints_help_and_exits_2():
    code, output = run([])
    assert code == 2
    assert "COMMAND" in output


# --- output mode -----------------------------------------------------------


def test_json_when_stdout_is_not_a_terminal(site, geo_home):
    _, output = run(["score", f"{site.url}/ssr-rich.html", "--allow-private", "--quiet", "--no-render"])
    json.loads(output)


def test_human_rendering_when_stdout_is_a_terminal(site, geo_home):
    code, output = run(
        ["score", f"{site.url}/ssr-rich.html", "--allow-private", "--quiet", "--no-render"],
        out=FakeTTY(),
    )
    assert code == 0
    with pytest.raises(json.JSONDecodeError):
        json.loads(output)
    assert "GEO citability score" in output
    assert "/100" in output


def test_json_flag_overrides_a_terminal(site, geo_home):
    _, output = run(
        ["score", f"{site.url}/ssr-rich.html", "--allow-private", "--quiet", "--no-render", "--json"],
        out=FakeTTY(),
    )
    json.loads(output)


def test_progress_goes_to_stderr_not_stdout(site, geo_home, capsys):
    main(["score", f"{site.url}/ssr-rich.html", "--allow-private", "--no-render", "--json"])
    captured = capsys.readouterr()
    json.loads(captured.out)
    assert "score" in captured.err


def test_quiet_silences_stderr_progress(site, geo_home, capsys):
    main(["score", f"{site.url}/ssr-rich.html", "--allow-private", "--no-render", "--quiet", "--json"])
    assert capsys.readouterr().err == ""


def test_no_color_is_respected(site, geo_home, monkeypatch):
    monkeypatch.setenv("NO_COLOR", "1")
    _, output = run(
        ["score", f"{site.url}/ssr-rich.html", "--allow-private", "--quiet", "--no-render"],
        out=FakeTTY(),
    )
    assert "\033[" not in output


# --- global flags ----------------------------------------------------------


def test_out_writes_the_envelope_to_a_file(site, geo_home, tmp_path):
    target = tmp_path / "nested" / "envelope.json"
    run(["score", f"{site.url}/ssr-rich.html", "--allow-private", "--quiet",
         "--no-render", "--out", str(target)])
    assert json.loads(target.read_text(encoding="utf-8"))["command"] == "score"


def test_config_supplies_defaults(site, geo_home, tmp_path):
    config = tmp_path / "geo.json"
    config.write_text(json.dumps({"allow_private": True, "no_render": True}), encoding="utf-8")
    code, _ = run(["score", f"{site.url}/ssr-rich.html", "--quiet", "--config", str(config)])
    assert code == 0


def test_config_rejects_unknown_keys(site, geo_home, tmp_path):
    config = tmp_path / "geo.json"
    config.write_text(json.dumps({"nonsense": 1}), encoding="utf-8")
    code, output = run(["score", f"{site.url}/x", "--quiet", "--config", str(config)])
    assert code == 2
    assert json.loads(output)["error"]["code"] == "GEO_E_BAD_ARGS"


def test_explicit_flags_beat_the_config_file(site, geo_home, tmp_path):
    config = tmp_path / "geo.json"
    config.write_text(json.dumps({"timeout": 99}), encoding="utf-8")
    parser = build_parser()
    args = parser.parse_args(["score", "https://example.com", "--timeout", "1"])
    from geo_audit.cli import _apply_config

    args.config = str(config)
    _apply_config(args)
    assert args.timeout == 1.0


def test_version_line_is_parseable_and_names_every_contract_version(capsys):
    with pytest.raises(SystemExit) as raised:
        main(["--version"])
    assert raised.value.code == 0
    out = capsys.readouterr().out
    assert out.split()[0] == DIST_NAME
    assert out.split()[1] == CLI_VERSION
    for label in ("schema", "scoring", "data", "normalizer"):
        assert label in out


def test_every_command_has_a_description_and_help(capsys):
    parser = build_parser()
    subparsers = [a for a in parser._actions if hasattr(a, "choices") and a.choices]
    assert subparsers, "the parser must expose subcommands"
    for name, sub in subparsers[0].choices.items():
        assert sub.description, f"{name} has no description"
        text = sub.format_help()
        assert "--json" in text and "--allow-private" in text
