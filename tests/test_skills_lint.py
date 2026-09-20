"""The lint that replaces a template generator has to actually catch drift."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tools"))

import lint_skills  # noqa: E402

CONTRACT = (ROOT / "skills/_shared/response-contract.md").read_text(encoding="utf-8")
VERSION = (ROOT / "VERSION").read_text(encoding="utf-8").strip()


def test_the_repository_passes_its_own_lint():
    assert lint_skills.main(["--quiet"]) == 0


def test_every_declared_skill_directory_exists():
    for name in lint_skills.EXPECTED_SKILLS:
        assert (ROOT / "skills" / name / "SKILL.md").exists()


def test_plugin_manifest_lists_every_declared_skill():
    import json

    plugin = json.loads((ROOT / ".claude-plugin/plugin.json").read_text(encoding="utf-8"))
    assert {Path(p).name for p in plugin["skills"]} == set(lint_skills.EXPECTED_SKILLS)


def make_skill(tmp_path: Path, *, body: str, version: str = VERSION, name: str = "citability") -> Path:
    path = tmp_path / name
    (path / "sections").mkdir(parents=True)
    (path / "SKILL.md").write_text(
        f"---\nname: {name}\n"
        f"description: Score how quotable a page is for AI search engines. "
        f"Use when asked to check citability.\n"
        f"version: {version}\n---\n\n{body}\n",
        encoding="utf-8",
    )
    return path


def contract_block(text: str = CONTRACT) -> str:
    return f"{lint_skills.CONTRACT_BEGIN}\n{text}\n{lint_skills.CONTRACT_END}"


def lint_one(path: Path) -> list[str]:
    report = lint_skills.Report()
    lint_skills.lint_skill(report, path, VERSION, CONTRACT, lint_skills.known_keys())
    return report.errors


def test_a_clean_skill_produces_no_errors(tmp_path):
    path = make_skill(tmp_path, body=contract_block())
    assert lint_one(path) == []


def test_a_drifted_response_contract_is_caught(tmp_path):
    drifted = CONTRACT.replace("Never invent a number.", "Estimate a number if needed.")
    path = make_skill(tmp_path, body=contract_block(drifted))
    assert any("differs from" in e for e in lint_one(path))


def test_missing_contract_markers_are_caught(tmp_path):
    path = make_skill(tmp_path, body="No contract here.")
    assert any("markers are missing" in e for e in lint_one(path))


def test_a_version_mismatch_is_caught(tmp_path):
    path = make_skill(tmp_path, body=contract_block(), version="9.9.9")
    assert any("frontmatter version" in e for e in lint_one(path))


def test_an_invented_signal_id_is_caught(tmp_path):
    body = contract_block() + "\n\nRead `citability.vibes` from the envelope.\n"
    path = make_skill(tmp_path, body=body)
    assert any("citability.vibes" in e for e in lint_one(path))


def test_an_invented_error_code_is_caught(tmp_path):
    body = contract_block() + "\n\nHandle `GEO_E_MADE_UP` by retrying.\n"
    path = make_skill(tmp_path, body=body)
    assert any("GEO_E_MADE_UP" in e for e in lint_one(path))


def test_a_real_signal_id_passes(tmp_path):
    body = contract_block() + "\n\nRead `citability.self_containment` and `scores.composite`.\n"
    path = make_skill(tmp_path, body=body)
    assert lint_one(path) == []


def test_a_hardcoded_install_path_is_caught(tmp_path):
    body = contract_block() + "\n\nRun ~/.claude/skills/geo/scripts/fetch_page.py\n"
    path = make_skill(tmp_path, body=body)
    assert any("absolute install path" in e for e in lint_one(path))


@pytest.mark.parametrize(
    "stat", ["$4 billion", "58% market share", "by 2030 every search"]
)
def test_market_statistics_in_a_prompt_are_caught(tmp_path, stat):
    body = contract_block() + f"\n\nContext: {stat}.\n"
    path = make_skill(tmp_path, body=body)
    assert any("market statistic" in e for e in lint_one(path))


def test_a_missing_section_reference_is_caught(tmp_path):
    body = contract_block() + "\n\nSee `sections/nowhere.md` for detail.\n"
    path = make_skill(tmp_path, body=body)
    assert any("sections/nowhere.md" in e for e in lint_one(path))


def test_known_keys_covers_every_emitted_signal_and_error():
    from geo_audit import data
    from geo_audit.errors import ERRORS

    keys = lint_skills.known_keys()
    assert set(ERRORS) <= keys
    assert set(data.weights()["citability"]["signals"]) <= keys
