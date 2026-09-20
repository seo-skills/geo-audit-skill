"""The plugin manifests, checked against how real plugins are actually written.

There is no machine-readable schema published for these files - the documented
URL serves a web page - so the next best evidence is the installed corpus. The
vocabularies below were taken from 163 installed `plugin.json` files and 10
`marketplace.json` files on a real machine. A key outside them is not
necessarily wrong, but it is unattested, and an unattested key in a manifest
the plugin manager parses is worth noticing before a user does.

This is half of the D2 spike. The other half - `/plugin marketplace add` and
`/plugin install geo` - has to be run by a person inside Claude Code.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from geo_audit._version import CLI_VERSION, PRODUCT_NAME

ROOT = Path(__file__).resolve().parent.parent

ATTESTED_PLUGIN_KEYS = {
    "$schema", "agents", "author", "commands", "description", "homepage",
    "keywords", "license", "name", "repository", "skills", "version",
}
ATTESTED_MARKETPLACE_KEYS = {
    "$schema", "description", "id", "metadata", "name", "owner", "plugins",
}


def plugin() -> dict:
    return json.loads((ROOT / ".claude-plugin/plugin.json").read_text(encoding="utf-8"))


def marketplace() -> dict:
    return json.loads((ROOT / ".claude-plugin/marketplace.json").read_text(encoding="utf-8"))


def test_both_manifests_parse():
    assert plugin()["name"] == "geo"
    assert marketplace()["plugins"]


def test_the_plugin_manifest_uses_only_attested_keys():
    unattested = set(plugin()) - ATTESTED_PLUGIN_KEYS
    assert not unattested, f"no installed plugin uses: {sorted(unattested)}"


def test_the_marketplace_manifest_uses_only_attested_keys():
    unattested = set(marketplace()) - ATTESTED_MARKETPLACE_KEYS
    assert not unattested, f"no installed marketplace uses: {sorted(unattested)}"


def test_the_marketplace_entry_uses_only_attested_keys():
    attested = {"name", "source", "description", "version", "author", "keywords", "category"}
    for entry in marketplace()["plugins"]:
        unattested = set(entry) - attested
        assert not unattested, f"unattested plugin entry key(s): {sorted(unattested)}"


def test_every_declared_skill_directory_exists_and_has_a_skill_file():
    for declared in plugin()["skills"]:
        path = ROOT / declared.lstrip("./")
        assert path.is_dir(), f"{declared} is not a directory"
        assert (path / "SKILL.md").is_file(), f"{declared} has no SKILL.md"


def test_the_skills_array_matches_the_directories_on_disk():
    declared = {Path(entry).name for entry in plugin()["skills"]}
    on_disk = {p.parent.name for p in (ROOT / "skills").glob("*/SKILL.md")}
    assert declared == on_disk


def test_both_manifests_carry_the_current_version():
    assert plugin()["version"] == CLI_VERSION
    assert marketplace()["metadata"]["version"] == CLI_VERSION
    for entry in marketplace()["plugins"]:
        assert entry["version"] == CLI_VERSION


def test_the_product_is_named_where_a_user_will_see_it():
    assert PRODUCT_NAME in plugin()["description"]
    assert any(PRODUCT_NAME in entry["description"] for entry in marketplace()["plugins"])


@pytest.mark.parametrize("field", ["description", "author", "license", "homepage", "repository"])
def test_the_plugin_manifest_is_complete(field):
    assert plugin().get(field), f"plugin.json has no {field}"


def test_the_marketplace_points_at_this_repository():
    for entry in marketplace()["plugins"]:
        assert entry["source"] == "./", "the plugin lives in this repo, not elsewhere"


def test_the_skill_namespace_is_stable():
    """Skills are addressed as /geo:<name>, so the plugin name is user-facing."""
    assert plugin()["name"] == "geo", (
        "renaming the plugin renames every skill a user types"
    )
