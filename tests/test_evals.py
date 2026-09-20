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


def test_the_shipped_site_list_is_a_placeholder_not_a_recommendation():
    config = json.loads((ROOT / "tests" / "evals" / "sites.json").read_text(encoding="utf-8"))
    assert len(config["sites"]) == 5
    assert all(entry["shape"] == "placeholder" for entry in config["sites"])
    assert "Replace these" in config["comment"]


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


def test_no_eval_result_is_recorded_yet():
    """A reminder, not a rule.

    When the first eval is recorded this test changes to assert its shape.
    Until then it states plainly that the 1.0 gate is unmet.
    """
    recorded = sorted((ROOT / "tests" / "evals" / "results").glob("eval-*.md"))
    if recorded:
        pytest.skip(f"{len(recorded)} eval(s) recorded; update this test to check their shape")
    assert True, "the practitioner eval has not been run; the 1.0 gate is open"
