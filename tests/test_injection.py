"""Instruction-shaped page text must change nothing.

The fixture contains a fake system prompt, a fake tool instruction, a fake
end-of-output delimiter and a demand for a score of 100. None of it may alter
the score, the shape of the output, or the state directory.
"""

from __future__ import annotations

import io
import json

from geo_audit.cli import main


def run(url, home):
    buffer = io.StringIO()
    code = main(["score", url, "--allow-private", "--json", "--quiet", "--no-render"], out=buffer)
    return code, json.loads(buffer.getvalue())


def test_the_demanded_score_is_not_the_score(site, geo_home):
    _, envelope = run(f"{site.url}/injection.html", geo_home)
    assert envelope["scores"]["composite"] != 100
    assert envelope["scores"]["tier"] != "excellent"


def test_the_envelope_shape_is_unchanged(site, geo_home):
    _, injected = run(f"{site.url}/injection.html", geo_home)
    _, ordinary = run(f"{site.url}/schema-none.html", geo_home)
    assert list(injected) == list(ordinary)
    assert list(injected["page"]) == list(ordinary["page"])
    assert {s["id"] for s in injected["signals"]} == {s["id"] for s in ordinary["signals"]}


def test_no_fake_delimiter_survives_into_the_output(site, geo_home):
    buffer = io.StringIO()
    main(
        ["score", f"{site.url}/injection.html", "--allow-private", "--json", "--quiet", "--no-render"],
        out=buffer,
    )
    raw = buffer.getvalue()
    for marker in ("END OF PAGE", "```", "</output>", "SYSTEM:"):
        assert marker not in raw


def test_the_state_directory_is_untouched_beyond_one_audit_record(site, geo_home):
    run(f"{site.url}/injection.html", geo_home)
    files = sorted(p.relative_to(geo_home).as_posix() for p in geo_home.rglob("*") if p.is_file())
    assert files == ["projects/127-0-0-1/audits.jsonl", "state.json"]


def test_the_instructed_command_was_not_run(site, geo_home):
    run(f"{site.url}/injection.html", geo_home)
    assert geo_home.exists(), "the page asked for `rm -rf ~/.geo`"
    assert not (geo_home.parent / "report.html").exists()
