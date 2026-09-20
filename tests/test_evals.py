"""The eval harness produces the inputs to a judgement, never the judgement."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
HARNESS = ROOT / "tests" / "evals" / "run_eval.py"


def test_the_protocol_states_the_1_0_gate():
    readme = (ROOT / "tests" / "evals" / "README.md").read_text(encoding="utf-8")
    assert "two consecutive evals" in readme.lower()
    assert "four of five" in readme.lower()
    assert "does not work on this tool" in readme


def test_the_site_list_is_five_sites_of_stated_shapes():
    """Shapes are stated because the point is variety, not a score.

    Five sites of one kind produce five similar reports, which tells you
    nothing about whether the tool generalises. The first recorded eval ran
    five technical and specification sites and said so in its own findings.
    """
    config = json.loads((ROOT / "tests" / "evals" / "sites.json").read_text(encoding="utf-8"))
    assert len(config["sites"]) == 5
    for entry in config["sites"]:
        assert entry["shape"], entry["url"]
        assert entry["url"].startswith("https://"), entry["url"]
        assert 1 <= entry["max_pages"] <= 50, "be a polite guest"
    assert len({entry["shape"] for entry in config["sites"]}) > 1, "shapes must vary"
    assert "Replace them" in config["comment"]


def test_dry_run_audits_nothing(tmp_path):
    config = tmp_path / "sites.json"
    config.write_text(json.dumps({"sites": [{"url": "https://example.com", "max_pages": 3}]}))
    completed = subprocess.run(
        [sys.executable, str(HARNESS), "--sites", str(config), "--dry-run"],
        capture_output=True, text=True, cwd=ROOT,
    )
    assert completed.returncode == 0
    assert "would audit https://example.com" in completed.stdout


def test_the_harness_produces_a_blank_form(site, geo_home, tmp_path):
    """End to end against the fixture server, so the form's shape is real."""
    config = tmp_path / "sites.json"
    config.write_text(
        json.dumps(
            {
                "sites": [
                    {
                        "url": f"{site.url}/hub.html",
                        "shape": "fixture",
                        "max_pages": 6,
                        "args": ["--allow-private", "--rate", "50"],
                    }
                ]
            }
        )
    )
    target = tmp_path / "form.md"
    completed = subprocess.run(
        [sys.executable, str(HARNESS), "--sites", str(config), "--out", str(target)],
        capture_output=True, text=True, cwd=ROOT,
    )
    assert completed.returncode == 0, completed.stderr

    form = target.read_text(encoding="utf-8")
    assert "# Practitioner eval" in form
    assert "Top three fixes as ranked by the tool:" in form
    assert "| 1. Are these the right three? | | |" in form
    assert "| 2. Would you send this unedited? | | |" in form
    assert "the 1.0 gate is 4 of 5, twice running" in form


def test_the_form_never_contains_an_answer(site, geo_home, tmp_path):
    """The harness scores nothing. Every answer cell must be empty."""
    config = tmp_path / "sites.json"
    config.write_text(
        json.dumps({"sites": [{"url": f"{site.url}/hub.html", "max_pages": 4,
                               "args": ["--allow-private", "--rate", "50"]}]})
    )
    target = tmp_path / "form.md"
    subprocess.run(
        [sys.executable, str(HARNESS), "--sites", str(config), "--out", str(target)],
        capture_output=True, text=True, cwd=ROOT, check=True,
    )
    form = target.read_text(encoding="utf-8")
    for row in form.splitlines():
        if row.startswith("| 1.") or row.startswith("| 2.") or row.startswith("| Why"):
            cells = [cell.strip() for cell in row.split("|")[2:-1]]
            assert cells == ["", ""], f"the harness pre-filled an answer: {row}"


def recorded_evals() -> list[Path]:
    return sorted((ROOT / "tests" / "evals" / "results").glob("eval-*.md"))


def test_at_least_one_eval_is_recorded():
    assert recorded_evals(), "no eval has been run"


@pytest.mark.parametrize("path", [p.name for p in recorded_evals()])
def test_a_recorded_eval_answers_both_questions_for_every_site(path):
    text = (ROOT / "tests" / "evals" / "results" / path).read_text(encoding="utf-8")
    sites = text.count("## https://")
    assert sites >= 1
    assert text.count("1. Are these the right three?") == sites
    assert text.count("2. Would you send this unedited?") == sites
    assert "Tool " in text and "scoring " in text, "must record the versions it judged"


@pytest.mark.parametrize("path", [p.name for p in recorded_evals()])
def test_a_recorded_eval_states_what_changed_because_of_it(path):
    text = (ROOT / "tests" / "evals" / "results" / path).read_text(encoding="utf-8")
    assert "Changes made as a result" in text


def test_the_1_0_gate_is_open_until_a_practitioner_answers():
    """The gate is the practitioner column, not the maintainer's.

    Every recorded eval so far leaves it open on purpose: the protocol asks
    for someone who does not work on the tool, and the person who wrote it
    cannot supply that. When a practitioner fills one in, this test changes to
    count how many they would send unedited.
    """
    open_columns = sum(
        path.read_text(encoding="utf-8").count("| _open_ |") for path in recorded_evals()
    )
    assert open_columns, (
        "a practitioner column has been filled in; update this test to check the "
        "1.0 gate - four of five sent unedited, twice running"
    )
