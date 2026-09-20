"""Open-source hygiene: the checks that stop a repo embarrassing itself."""

from __future__ import annotations

import json
import re
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tools"))

import scan_secrets  # noqa: E402

from geo_audit._version import CLI_VERSION  # noqa: E402


def test_the_repository_has_no_secrets():
    assert scan_secrets.main() == 0


@pytest.mark.parametrize(
    "planted",
    [
        "AKIA" + "IOSFODNN7EXAMPLE",  # geo-secret-scan-allow
        "-----BEGIN RSA PRIVATE" + " KEY-----",  # geo-secret-scan-allow
        "ghp_" + "a" * 36,
        'api_key = "' + "b" * 32 + '"',
    ],
)
def test_the_scanner_catches_a_planted_secret(tmp_path, monkeypatch, planted):
    target = tmp_path / "leaky.py"
    target.write_text(f"value = 1\n{planted}\n", encoding="utf-8")
    monkeypatch.setattr(scan_secrets, "ROOT", tmp_path)
    monkeypatch.setattr(scan_secrets, "tracked_files", lambda: [target])
    assert scan_secrets.main() == 1


def test_the_scanner_rejects_committed_credential_files(tmp_path, monkeypatch):
    target = tmp_path / ".env"
    target.write_text("NOTHING=1\n", encoding="utf-8")
    monkeypatch.setattr(scan_secrets, "ROOT", tmp_path)
    monkeypatch.setattr(scan_secrets, "tracked_files", lambda: [target])
    assert scan_secrets.main() == 1


# --- required files --------------------------------------------------------


@pytest.mark.parametrize(
    "name",
    [
        "LICENSE",
        "README.md",
        "CONTRIBUTING.md",
        "SECURITY.md",
        "CHANGELOG.md",
        "CLAUDE.md",
        "VERSION",
        ".gitattributes",
        ".gitignore",
        "pyproject.toml",
    ],
)
def test_required_file_exists(name):
    assert (ROOT / name).is_file()


def test_license_is_mit_with_a_copyright_holder():
    text = (ROOT / "LICENSE").read_text(encoding="utf-8")
    assert "MIT License" in text
    match = re.search(r"Copyright \(c\) (\d{4}) (.+)", text)
    assert match, "LICENSE has no copyright line"
    assert match.group(2).strip(), "LICENSE has no copyright holder"
    assert "<" not in match.group(2), "LICENSE still has a placeholder holder"


def test_changelog_has_an_entry_for_the_current_version():
    text = (ROOT / "CHANGELOG.md").read_text(encoding="utf-8")
    assert "## [Unreleased]" in text
    assert f"## [{CLI_VERSION}]" in text


def test_version_agreement_across_every_manifest():
    version = (ROOT / "VERSION").read_text(encoding="utf-8").strip()
    assert version == CLI_VERSION
    assert f'version = "{version}"' in (ROOT / "pyproject.toml").read_text(encoding="utf-8")
    plugin = json.loads((ROOT / ".claude-plugin/plugin.json").read_text(encoding="utf-8"))
    assert plugin["version"] == version


# --- CI --------------------------------------------------------------------


@pytest.mark.parametrize("workflow", ["ci.yml", "secret-scan.yml", "release.yml"])
def test_workflow_exists(workflow):
    assert (ROOT / ".github/workflows" / workflow).is_file()


def test_ci_runs_every_gate_this_project_claims():
    text = (ROOT / ".github/workflows/ci.yml").read_text(encoding="utf-8")
    for gate in ("pytest", "tools/lint_skills.py", "tools/gen_docs.py --check"):
        assert gate in text, f"ci.yml does not run {gate}"
    for platform in ("ubuntu-latest", "macos-latest", "windows-latest"):
        assert platform in text


def test_release_is_gated_on_the_tag_matching_version():
    text = (ROOT / ".github/workflows/release.yml").read_text(encoding="utf-8")
    assert "VERSION" in text
    assert "CHANGELOG.md" in text
    assert "id-token: write" in text, "trusted publishing needs an OIDC token"
    assert "password:" not in text, "a release token must not live in the workflow"


# --- fixtures we have the right to redistribute ----------------------------


def test_every_fixture_is_authored_here():
    """No captured third-party HTML. Synthetic pages only."""
    for fixture in (ROOT / "tests/fixtures/site").glob("*.html"):
        text = fixture.read_text(encoding="utf-8")
        assert "<!-- saved from" not in text
        assert "wp-content" not in text
        assert not re.search(r"(?:gtag|googletagmanager|facebook\.net|hotjar)", text)


def test_no_generated_or_vendored_directories_are_tracked():
    tracked = subprocess.run(
        ["git", "ls-files"], cwd=ROOT, capture_output=True, text=True
    ).stdout.splitlines()
    if not tracked:
        pytest.skip("not a git repository yet")
    for path in tracked:
        assert not path.startswith(".venv/")
        assert "__pycache__" not in path
        assert not path.startswith("dist/")
