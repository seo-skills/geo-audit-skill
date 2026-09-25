"""The lint that replaces a template generator has to actually catch drift."""

from __future__ import annotations

import re
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


BARE_PREFLIGHT = (
    "## Preflight\n\nRun `geo --version`. Expected: "
    "`seomator-geo-audit " + VERSION.rsplit(".", 1)[0] + ".x` or newer.\n"
)
SOURCE_LINE = f"Not on PyPI yet? `uv tool install {lint_skills.SOURCE_INSTALL}`.\n"
# A clean skill follows the same switch the real ones do, so this fixture does not
# break on the day the package is published.
PREFLIGHT = BARE_PREFLIGHT + (SOURCE_LINE if lint_skills.prepublication() else "")


def contract_block(text: str = CONTRACT, preflight: str = PREFLIGHT) -> str:
    return f"{preflight}\n{lint_skills.CONTRACT_BEGIN}\n{text}\n{lint_skills.CONTRACT_END}"


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
    path = make_skill(tmp_path, body=PREFLIGHT + "\n\nNo contract here.")
    assert any("markers are missing" in e for e in lint_one(path))


def test_a_missing_preflight_is_caught(tmp_path):
    path = make_skill(tmp_path, body=contract_block(preflight=""))
    assert any("no Preflight section" in e for e in lint_one(path))


def test_a_preflight_naming_the_wrong_distribution_is_caught(tmp_path):
    """The bug this check exists for: three skills shipped naming the old
    product in the one sentence a user is told to type."""
    stale = "## Preflight\n\nRun `geo --version`. Expected: `geo-audit-cli 0.2.x`.\n"
    path = make_skill(tmp_path, body=contract_block(preflight=stale))
    errors = lint_one(path)
    assert any("must name the current distribution" in e for e in errors)
    assert any("must name the current version line" in e for e in errors)


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


# --- the key manifest is checked against real envelopes --------------------


def emitted_key_paths(envelope: dict) -> set[str]:
    """Every `parent.child` path a real envelope contains."""
    paths: set[str] = set()

    def walk(node, parent: str = "") -> None:
        if isinstance(node, dict):
            for key, value in node.items():
                if parent:
                    paths.add(f"{parent}.{key}")
                paths.add(key)
                # Signal and finding identifiers are values, not keys, and they
                # are exactly what the skills name.
                if key == "id" and isinstance(value, str):
                    paths.add(value)
                walk(value, key)
        elif isinstance(node, list):
            for item in node:
                walk(item, parent)

    walk(envelope)
    return paths


def skill_identifiers() -> dict[str, set[str]]:
    """Every backticked identifier each skill mentions."""
    found: dict[str, set[str]] = {}
    for name in lint_skills.EXPECTED_SKILLS:
        directory = ROOT / "skills" / name
        text = (directory / "SKILL.md").read_text(encoding="utf-8")
        for section in sorted((directory / "sections").glob("*.md")):
            text += section.read_text(encoding="utf-8")
        found[name] = set(lint_skills.IDENTIFIER.findall(text))
    return found


def test_every_identifier_a_skill_mentions_appears_in_a_real_envelope(site, geo_home, monkeypatch, serve):
    """The lint's offline key list must not be fiction.

    The lint is a fast approximation so it can run without a network. This
    test is the ground truth: it runs every command and checks that each
    identifier the skills name is one the CLI actually emitted.
    """
    import io
    import json

    from geo_audit.cli import main
    from geo_audit.commands import scan as scan_cmd
    from geo_audit.errors import ERRORS
    from tests.fixture_server import Reply

    monkeypatch.setenv("GEO_YOUTUBE_API_KEY", "test-key")
    stub = serve_stub(site)
    monkeypatch.setattr(scan_cmd, "_platforms", lambda: stub)
    # scrape.do stubbed locally, so the brand scan that asks assistants emits
    # every key an answer carries.
    from geo_audit import assistants
    from tests.test_assistants import routes as scrapedo_routes

    monkeypatch.setattr(assistants, "BASE", serve(scrapedo_routes()).url)
    monkeypatch.setattr(assistants, "RETRY_AFTER", 0.0)
    monkeypatch.setenv(assistants.TOKEN_ENV, "test-token")

    out = ["--json", "--quiet"]
    crawl = ["--allow-private", "--rate", "50", "--max-pages", "10"]
    page = ["--allow-private"]
    invocations = [
        ["fetch", f"{site.url}/ssr-rich.html", *page],
        ["crawl", f"{site.url}/hub.html", *crawl],
        ["audit", f"{site.url}/hub.html", "--brand", "Acme", *crawl],
        ["score", f"{site.url}/ssr-rich.html", "--no-render", *page],
        ["validate", f"{site.url}/schema-none.html", "--suggest", *page],
        ["llmstxt", f"{site.url}/hub.html", "--generate", *crawl],
        ["scan", "Acme", "--allow-private"],
        ["scan", "Acme", "--allow-private", "--assistants", "all"],
        ["prune", "--dry-run"],
        ["doctor"],
    ]

    emitted: set[str] = set(ERRORS)
    for invocation in invocations:
        buffer = io.StringIO()
        code = main(invocation + out, out=buffer)
        assert code == 0, f"{invocation[0]} exited {code}: {buffer.getvalue()[:300]}"
        emitted |= emitted_key_paths(json.loads(buffer.getvalue()))

    # One failing run, so the error block is covered. Skills are told to relay
    # `error.message` and `error.hint`, which never appear on a success.
    buffer = io.StringIO()
    assert main(["score", "not-a-url"] + out, out=buffer) == 2
    emitted |= emitted_key_paths(json.loads(buffer.getvalue()))

    # A second audit, so compare and report have two records to work from, and
    # a rescore so that block is covered too. It names the same brand as the
    # first: compare refuses two runs that scored different categories.
    buffer = io.StringIO()
    main(["audit", f"{site.url}/hub.html", "--brand", "Acme", *crawl] + out, out=buffer)
    run_id = json.loads(buffer.getvalue())["run_id"]
    for follow_up in (
        ["audit", f"{site.url}/hub.html", "--rescore", run_id],
        ["compare", f"{site.url}/hub.html"],
        ["report", f"{site.url}/hub.html"],
        ["report", f"{site.url}/hub.html", "--mode", "operator"],
    ):
        buffer = io.StringIO()
        code = main(follow_up + out, out=buffer)
        assert code == 0, f"{follow_up[0]} exited {code}: {buffer.getvalue()[:300]}"
        emitted |= emitted_key_paths(json.loads(buffer.getvalue()))

    missing: dict[str, set[str]] = {}
    for skill, identifiers in skill_identifiers().items():
        unseen = {
            identifier
            for identifier in identifiers
            if identifier not in emitted and identifier.split(".")[-1] not in emitted
        }
        if unseen:
            missing[skill] = unseen
    assert not missing, f"skills name identifiers no command emitted: {missing}"


def serve_stub(site):
    """Point the brand platforms at the fixture server."""
    return {
        name: {
            "label": name.title(),
            "url": f"{site.url}/not-html?q={{query}}&key={{key}}",
            "docs": "https://example.test/docs",
            "needs_key": None,
        }
        for name in ("wikipedia", "wikidata", "reddit", "youtube")
    }


@pytest.mark.parametrize("unpublished", [True, False], ids=["before-publish", "after-publish"])
def test_the_source_install_follows_the_readme_note(tmp_path, monkeypatch, unpublished):
    """Offered while unpublished, gone once published: one switch, both directions."""
    monkeypatch.setattr(lint_skills, "prepublication", lambda: unpublished)
    with_source = BARE_PREFLIGHT + SOURCE_LINE
    right, wrong = (with_source, BARE_PREFLIGHT) if unpublished else (BARE_PREFLIGHT, with_source)

    assert lint_one(make_skill(tmp_path / "right", body=contract_block(preflight=right))) == []
    errors = lint_one(make_skill(tmp_path / "wrong", body=contract_block(preflight=wrong)))
    assert len(errors) == 1 and "source install" in errors[0].replace("-", " ")


@pytest.mark.parametrize(
    "source, problem",
    [
        ("./", None),
        ({"source": "url", "url": "https://github.com/o/r.git", "ref": f"v{VERSION}"}, None),
        ({"source": "url", "url": "https://github.com/o/r.git", "ref": "v0.0.1"}, "the tag for this version"),
        ({"source": "github", "repo": "o/r"}, "SSH only"),
    ],
    ids=["relative", "pinned-to-this-release", "pinned-to-an-old-release", "github-ssh"],
)
def test_the_plugin_source_is_one_a_user_can_install(source, problem):
    report = lint_skills.Report()
    lint_skills.check_plugin_source(report, {"name": "geo", "source": source}, VERSION)
    if problem is None:
        assert report.errors == []
    else:
        assert len(report.errors) == 1 and problem in report.errors[0]


def test_the_skills_offer_exactly_the_site_kinds_the_cli_accepts():
    """The model picks the kind and the CLI applies it: one vocabulary, two readers.

    A kind the guide names but the CLI rejects is a usage error mid-report; a kind
    the CLI has but no skill mentions is one nobody will ever pass.
    """
    from geo_audit.scoring.model import site_kinds

    kinds = set(site_kinds())
    guide = (ROOT / "skills/audit/sections/site-kind.md").read_text(encoding="utf-8")
    report = (ROOT / "skills/report/SKILL.md").read_text(encoding="utf-8")

    assert set(re.findall(r"\*\* \(`([a-z]+)`\)", guide)) == kinds
    for kind in kinds:
        assert f"`{kind}`" in report, f"the report skill does not offer {kind}"


def test_the_guide_names_every_signal_a_kind_moves():
    """The table says what the CLI does; the guide says why, to the model.

    If a kind moves a signal its paragraph never mentions, the model narrates one
    order and the report prints another.
    """
    from geo_audit.scoring.model import site_kinds

    guide = (ROOT / "skills/audit/sections/site-kind.md").read_text(encoding="utf-8")
    paragraphs: dict[str, str] = {}
    for match in re.finditer(r"\*\*[^*]+\*\* \(`([a-z]+)`\)\.[^\n]*(?:\n(?!\n)[^\n]*)*", guide):
        # Agency is read as saas, so both paragraphs speak for that kind.
        paragraphs[match.group(1)] = paragraphs.get(match.group(1), "") + match.group(0)
    for kind, spec in site_kinds().items():
        text = paragraphs.get(kind, "")
        for signal_id in spec["lead"] + spec["defer"]:
            assert f"`{signal_id}`" in text, f"the {kind} paragraph never mentions {signal_id}"


@pytest.mark.parametrize(
    "section, source",
    [
        ("technical/sections/crawlers.md", "https://www.rfc-editor.org/rfc/rfc9309"),
        ("schema/sections/types.md", "https://schema.org/"),
        ("schema/sections/types.md", "https://developers.google.com/search/docs/appearance/structured-data/"),
        ("llmstxt/SKILL.md", "https://llmstxt.org/"),
        ("content/sections/rubrics.md", "https://developers.google.com/search/docs/fundamentals/creating-helpful-content"),
    ],
)
def test_heuristics_cite_their_primary_source(section, source):
    """PRD §3.7: sources, not personalities - auditor heuristics cite primary
    sources with URLs. Each of these sections makes a claim the source backs."""
    assert source in (ROOT / "skills" / section).read_text(encoding="utf-8")
