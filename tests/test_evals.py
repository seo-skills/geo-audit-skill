"""The eval harness produces the inputs to a judgement, never the judgement."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
HARNESS = ROOT / "tests" / "evals" / "run_eval.py"


def test_the_protocol_states_its_bar():
    readme = (ROOT / "tests" / "evals" / "README.md").read_text(encoding="utf-8")
    assert "two consecutive evals" in readme.lower()
    assert "four of five" in readme.lower()
    assert "does not work on this tool" in readme


def test_the_protocol_says_a_round_that_changes_the_tool_does_not_count():
    """Round two moved two scores by 24 and 10 points after a fix.

    Counting it would have claimed a result for a version that no longer
    exists.
    """
    readme = (ROOT / "tests" / "evals" / "README.md").read_text(encoding="utf-8")
    assert "does not count" in readme
    assert "counter starts again" in readme


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


def test_every_kind_in_the_site_list_is_one_the_cli_accepts():
    """A typo here is a usage error on the fifth site, an hour into a polite crawl."""
    from geo_audit.scoring.model import site_kinds

    config = json.loads((ROOT / "tests" / "evals" / "sites.json").read_text(encoding="utf-8"))
    for entry in config["sites"]:
        if entry.get("kind") is not None:
            assert entry["kind"] in site_kinds(), f"{entry['url']}: unknown kind {entry['kind']!r}"


def test_dry_run_audits_nothing(tmp_path):
    config = tmp_path / "sites.json"
    config.write_text(json.dumps({"sites": [{"url": "https://example.com", "max_pages": 3}]}), encoding="utf-8")
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
        ), encoding="utf-8"
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
    assert "the bar is 4 of 5, twice running" in form


def test_question_two_is_asked_about_the_copy_a_client_receives(site, geo_home, tmp_path):
    """"Would you send this unedited?" was being asked about the operator copy.

    That copy carries run ids, evidence hashes, the failed-page table and every
    signal value - none of which reach a client - so a careful practitioner
    answers `no` for reasons that say nothing about the product, and the bar
    measures the wrong document. The form links the client copy for the
    question and keeps the operator copy for working out why.
    """
    import re

    config = tmp_path / "sites.json"
    config.write_text(
        json.dumps({"sites": [{"url": f"{site.url}/hub.html", "max_pages": 4,
                               "args": ["--allow-private", "--rate", "50"]}]}), encoding="utf-8"
    )
    target = tmp_path / "form.md"
    subprocess.run(
        [sys.executable, str(HARNESS), "--sites", str(config), "--out", str(target)],
        capture_output=True, text=True, cwd=ROOT, check=True,
    )
    form = target.read_text(encoding="utf-8")
    client = re.search(r"Client copy[^`\n]*`([^`]+)`", form)
    operator = re.search(r"Operator copy[^`\n]*`([^`]+)`", form)
    assert client and operator, "the form must link both copies, labelled"
    assert client.group(1) != operator.group(1)

    marker = "Provenance"
    assert marker not in Path(client.group(1)).read_text(encoding="utf-8")
    assert marker in Path(operator.group(1)).read_text(encoding="utf-8")


def test_the_form_shows_the_order_the_report_shows(site, geo_home, tmp_path):
    """Question 1 asks whether the top three are right - the top three of the
    report being judged. With a kind, that is not the audit's own order, and a
    form quoting the audit would put one list in front of the practitioner and
    another in the file they open.
    """
    import html
    import re

    config = tmp_path / "sites.json"
    config.write_text(
        json.dumps({"sites": [{"url": f"{site.url}/hub.html", "max_pages": 4, "kind": "docs",
                               "args": ["--allow-private", "--rate", "50"]}]}), encoding="utf-8"
    )
    target = tmp_path / "form.md"
    subprocess.run(
        [sys.executable, str(HARNESS), "--sites", str(config), "--out", str(target)],
        capture_output=True, text=True, cwd=ROOT, check=True,
    )
    form = target.read_text(encoding="utf-8")
    assert "Ordered for: docs" in form

    in_form = re.findall(r"^\d\. \*\*(.+?)\*\*", form, re.MULTILINE)
    client = Path(re.search(r"Client copy[^`\n]*`([^`]+)`", form).group(1))
    in_report = [html.unescape(t) for t in re.findall(r"<h3>\d+\. (.+?)</h3>", client.read_text("utf-8"))]
    assert in_form == in_report[:3]


def test_the_form_never_contains_an_answer(site, geo_home, tmp_path):
    """The harness scores nothing. Every answer cell must be empty."""
    config = tmp_path / "sites.json"
    config.write_text(
        json.dumps({"sites": [{"url": f"{site.url}/hub.html", "max_pages": 4,
                               "args": ["--allow-private", "--rate", "50"]}]}), encoding="utf-8"
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


def test_no_practitioner_column_has_been_filled_in_yet():
    """The bar is the practitioner column, not the maintainer's.

    Every recorded eval so far leaves it open on purpose: the protocol asks
    for someone who does not work on the tool, and the person who wrote it
    cannot supply that. 1.0 was released on the maintainer's approval (PRD D5).
    When a practitioner fills one in, this test changes to count how many they
    would send unedited.
    """
    open_columns = sum(
        path.read_text(encoding="utf-8").count("| _open_ |") for path in recorded_evals()
    )
    assert open_columns, (
        "a practitioner column has been filled in; update this test to count it "
        "against the bar - four of five sent unedited, twice running"
    )
