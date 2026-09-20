"""Docs are asserted, not trusted.

Every claim the docs make about commands, flags, signals, scoring constants and
error codes is checked against the code that implements it. A docs bug is a
test failure.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tools"))

import gen_docs  # noqa: E402

from geo_audit import data  # noqa: E402
from geo_audit._version import CLI_VERSION  # noqa: E402
from geo_audit.cli import build_parser  # noqa: E402
from geo_audit.errors import ERRORS  # noqa: E402

README = (ROOT / "README.md").read_text(encoding="utf-8")
TROUBLESHOOTING = (ROOT / "docs/troubleshooting.md").read_text(encoding="utf-8")
COMMANDS = (ROOT / "docs/commands.md").read_text(encoding="utf-8")


def test_generated_docs_are_current():
    assert gen_docs.main(["--check"]) == 0, "run: python tools/gen_docs.py"


def test_every_command_is_documented():
    parser = build_parser()
    subparsers = next(a for a in parser._actions if hasattr(a, "choices") and a.choices)
    for name in subparsers.choices:
        assert f"## `geo {name}`" in COMMANDS


def test_every_error_code_is_documented_with_its_hint():
    for code, spec in ERRORS.items():
        assert f"`{code}`" in COMMANDS, f"{code} missing from the generated table"
        assert spec.hint in COMMANDS


def test_the_codes_users_hit_have_a_troubleshooting_entry():
    """Not every code needs prose, but the ones with context do."""
    for code in (
        "GEO_E_PRIVATE_ADDRESS",
        "GEO_E_REDIRECT_BLOCKED",
        "GEO_E_TOO_LARGE",
        "GEO_E_BAD_CONTENT_TYPE",
        "GEO_E_TOO_MANY_REDIRECTS",
        "GEO_E_STATE_NEWER",
    ):
        assert code in TROUBLESHOOTING, f"{code} has no troubleshooting entry"


def test_readme_category_table_matches_the_data_files():
    """The README's headline claim about what it measures, asserted."""
    for name, category in data.weights().items():
        row = re.search(
            rf"\| \*\*{re.escape(name)}\*\* \| (\d+) \| (\d+)", README
        )
        assert row, f"{name} is missing from the README category table"
        assert int(row.group(1)) == category["weight"], f"{name} weight"
        assert int(row.group(2)) == len(category["signals"]), f"{name} signal count"


def test_the_category_weights_sum_to_one_hundred():
    assert sum(category["weight"] for category in data.weights().values()) == 100


def test_readme_states_the_rules_that_shape_the_numbers():
    for claim in (
        "never scored as a failure",
        "never becomes a number",
        "scored once",
    ):
        assert claim in README, f"the README no longer states: {claim}"


def test_readme_exit_code_table_matches_the_error_module():
    for code, meaning in gen_docs.EXIT_MEANINGS.items():
        assert f"| {code} |" in README, f"exit code {code} missing from the README"
    assert "--fail-on-partial" in README


def test_the_prepublication_note_disappears_once_the_package_is_published():
    """A reminder, not a rule.

    While the note is present the README must offer a command that works
    today; when the PyPI release lands, delete the note and this test.
    """
    if "Not on PyPI yet" in README:
        assert "git+https://github.com/seo-skills/geo-audit-skill" in README


def test_readme_names_the_current_version():
    assert CLI_VERSION in README


def test_every_documented_flag_exists_in_the_parser():
    """Flags described as working must work.

    The roadmap section is excluded on purpose: it names flags that arrive in
    later releases, which is the one place a not-yet-existing flag belongs.
    """
    current = README.split("## Roadmap", 1)[0]
    for flag in re.findall(r"`(--[a-z-]+)`", current):
        assert flag in COMMANDS, f"README documents {flag}, which the parser does not offer"


def test_the_roadmap_only_names_flags_that_do_not_exist_yet():
    roadmap = README.split("## Roadmap", 1)[1].split("## Docs", 1)[0]
    for flag in re.findall(r"`(--[a-z-]+)`", roadmap):
        assert flag not in COMMANDS, f"{flag} already exists; move it out of the roadmap"


def test_doc_links_resolve():
    for target in re.findall(r"\]\(([^)#][^)]*)\)", README):
        if target.startswith("http"):
            continue
        assert (ROOT / target).exists(), f"README links to missing {target}"


@pytest.mark.parametrize(
    "doc", sorted(p for p in (ROOT / "docs").rglob("*.md"))
)
def test_docs_have_no_placeholder_text(doc):
    text = doc.read_text(encoding="utf-8")
    for marker in ("TODO", "TBD", "FIXME", "XXX", "Lorem ipsum"):
        assert marker not in text, f"{doc.name} still contains {marker}"


def test_concept_docs_carry_their_generated_regions():
    for path, regions in gen_docs.REGIONS.items():
        text = path.read_text(encoding="utf-8")
        for name in regions:
            assert f"<!-- generated:{name}:begin -->" in text
            assert f"<!-- generated:{name}:end -->" in text
            body = text.split(f"generated:{name}:begin -->", 1)[1].split(
                f"<!-- generated:{name}:end", 1
            )[0]
            assert body.strip(), f"{path.name} region {name} is empty"
