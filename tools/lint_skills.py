#!/usr/bin/env python3
"""Skill lint: the contract enforcement that replaces a template generator.

Upstream's failure mode was two copies of one document drifting to 28 and 69
headings without anyone noticing. A generator would fix that by making the
skill files derived artifacts, but generation was only worth its cost when the
output had to target several hosts, and that is a non-goal here. Linting gets
the same guarantee and leaves the files hand-editable.

What it enforces:

1. `VERSION` is the single source. pyproject, `_version.py`, both plugin
   manifests and every skill frontmatter must agree with it.
2. The skill directory set matches the manifest below, and plugin.json lists
   exactly those skills.
3. Each skill's response-contract block is byte-identical to
   skills/_shared/response-contract.md.
4. Key manifest: every signal id, finding id, error code and envelope key a
   skill mentions is one the CLI actually emits. This is what stops prose from
   drifting back into inventing its own scoring vocabulary.
5. Skills reference no absolute install paths and carry no market statistics.

Run: python tools/lint_skills.py [--quiet]
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

from geo_audit import data, envelope  # noqa: E402
from geo_audit._version import DIST_NAME, PRODUCT_NAME, REPO_URL  # noqa: E402
from geo_audit.errors import ERRORS  # noqa: E402

# Until the first release is on PyPI the published install command fails, so every
# install instruction also offers the source install - and once the README's note
# goes, the fallback must go with it. One switch, so publishing cannot leave a skill
# pointing at a dead end, or at a workaround nobody needs any more.
SOURCE_INSTALL = f"git+{REPO_URL}"


def prepublication() -> bool:
    return "Not on PyPI yet" in (ROOT / "README.md").read_text(encoding="utf-8")


# The skill set, with the milestone each one arrives in. Adding a skill means
# adding a line here; that is the point.
EXPECTED_SKILLS = {
    "citability": "M1",
    "audit": "M2",
    "technical": "M2",
    "schema": "M2",
    "llmstxt": "M2",
    "brand": "M2",
    "content": "M3",
    "compare": "M3",
    "report": "M3",
}

CONTRACT_BEGIN = "<!-- geo:response-contract:begin -->"
CONTRACT_END = "<!-- geo:response-contract:end -->"

FRONTMATTER_REQUIRED = ("name", "description", "version")

IDENTIFIER = re.compile(r"`([A-Za-z_][A-Za-z0-9_]*(?:\.[A-Za-z0-9_]+)+|GEO_E_[A-Z_]+)`")
BANNED_PATHS = re.compile(r"~/\.claude/skills|~/\.geo-prospects|/usr/local/bin/geo")
MARKET_STATS = re.compile(
    r"\$\s?\d|\b\d+\s?(?:billion|million|trillion)\b|\bmarket share\b|\bby 20[3-9]\d\b",
    re.IGNORECASE,
)


class Report:
    def __init__(self) -> None:
        self.errors: list[str] = []
        self.checked = 0

    def fail(self, where: str, message: str) -> None:
        self.errors.append(f"{where}: {message}")

    def check(self, condition: bool, where: str, message: str) -> None:
        self.checked += 1
        if not condition:
            self.fail(where, message)


def read_version() -> str:
    return (ROOT / "VERSION").read_text(encoding="utf-8").strip()


def parse_frontmatter(text: str) -> dict[str, str]:
    if not text.startswith("---\n"):
        return {}
    _, block, _ = text.split("---\n", 2)
    fields: dict[str, str] = {}
    for line in block.splitlines():
        if ":" in line and not line.startswith(" "):
            key, _, value = line.partition(":")
            fields[key.strip()] = value.strip()
    return fields


def known_keys() -> set[str]:
    """Every identifier the CLI is allowed to teach a skill."""
    keys: set[str] = set(ERRORS)
    for category in data.weights().values():
        keys |= set(category["signals"])
        # Advisory questions are emitted as signals too, with a rubric and no value.
        keys |= set(category.get("advisory") or {})
    findings = data.load("findings")
    keys |= set(findings["signals"]) | set(findings["checks"])

    sample = envelope.build("score", ok=True, run_id="X")
    sample["page"] = {}
    sample["checks"] = []
    sample["note"] = ""
    top = set(sample)
    for parent, children in {
        "scores": ["composite", "tier", "tier_meaning", "categories"],
        "evidence": ["stamp", "content_hash", "pages_ok", "pages_failed", "normalizer_version"],
        "completeness": ["computed", "total", "missing", "categories"],
        "error": ["code", "message", "hint", "docs", "log"],
        "signals": ["id", "class", "value", "max", "page", "detail", "skipped_reason"],
        "findings": ["id", "severity", "effort", "priority", "points_lost", "pages",
                     "title", "remediation", "excerpt"],
        "page": ["status", "final_url", "requested_url", "content_chars", "content_root",
                 "blocks", "robots", "redirect_chain", "record", "cache",
                 "jsonld_types", "jsonld_errors"],
        "crawl": ["start_url", "site", "pages_crawled", "pages_ok", "discovered",
                  "seeded_from_sitemap", "disallowed_by_robots", "stopped_because",
                  "elapsed_ms", "limits", "robots", "pages", "record"],
        "limits": ["max_pages", "requests_per_second", "concurrency", "timeout",
                   "robots_respected", "sitemap_used"],
        "rescore": ["run_id", "observed_at", "recorded_versions", "current_versions",
                    "versions_match", "recorded_composite"],
        "schema": ["verdict", "valid", "blocks", "blocks_attempted", "types",
                   "unrecognised_types", "parse_errors", "nodes", "suggestion"],
        "suggestion": ["needed", "jsonld", "script", "fill_in", "note"],
        "llmstxt": ["site", "llms_txt", "llms_full_txt", "generated", "crawl"],
        "llms_txt": ["present", "valid", "status", "url", "title", "summary",
                     "sections", "links", "link_count", "problems", "bytes",
                     "has_optional_section", "error"],
        "generated": ["text", "bytes", "pages_listed", "pages_optional", "excluded",
                      "parsed", "written_to"],
        "scan": ["brand", "site", "platforms", "platforms_checked", "platforms_total",
                 "total_results", "manual_checks", "same_as"],
        "platforms": ["platform", "label", "checked", "status", "results", "examples",
                      "docs", "observed_at", "reason"],
        "prune": ["home", "applied", "limits", "projects", "runs_dropped",
                  "bytes_reclaimed"],
        "compare": ["from", "to", "composite_delta", "tier_changed", "categories",
                    "signals", "findings", "pages", "versions"],
        "checks": ["id", "status", "detail", "hint"],
        # Signal detail keys the skills are allowed to name. They are part of the
        # documented surface, and `test_skills_lint.py` checks every one of these
        # against a real envelope rather than trusting this list.
        "detail": ["blocked_critical", "blocked_training_only", "robots_status",
                   "pages_measured", "pages_total", "mean", "min", "max",
                   "worst_page", "worst_example", "worst_section", "breakdown",
                   "reason", "ratio", "checks", "present", "missing",
                   "candidate_blocks", "self_contained", "sections", "answer_first",
                   "prose_blocks", "blocks_with_facts", "external_domains",
                   "content_chars", "content_ratio", "js_required_notice",
                   "framework_root_chars", "empty_framework_root",
                   "capped_thin_or_js_gated", "static_chars", "rendered_chars",
                   "jsonld_types", "same_as_count", "linked_hosts",
                   "links_to_encyclopedic", "wikipedia_results", "wikidata_results",
                   "reddit_results", "youtube_results", "missing_required",
                   "parse_errors", "checked", "answer_types_found"],
    }.items():
        keys |= {f"{parent}.{child}" for child in children}
        keys |= {f"{parent}[].{child}" for child in children}
    keys |= top
    # Signal detail keys are part of the documented surface too.
    keys |= {
        "breakdown.single_h1", "breakdown.enough_h2", "breakdown.no_skipped_levels",
        "breakdown.section_length",
    }
    return keys


def lint_versions(report: Report, version: str) -> None:
    pyproject = (ROOT / "pyproject.toml").read_text(encoding="utf-8")
    match = re.search(r'^version = "([^"]+)"', pyproject, re.MULTILINE)
    report.check(
        match is not None and match.group(1) == version,
        "pyproject.toml",
        f"version must be {version}",
    )

    module = (ROOT / "src/geo_audit/_version.py").read_text(encoding="utf-8")
    match = re.search(r'^CLI_VERSION = "([^"]+)"', module, re.MULTILINE)
    report.check(
        match is not None and match.group(1) == version,
        "src/geo_audit/_version.py",
        f"CLI_VERSION must be {version}",
    )

    report.check(
        re.search(rf'^name = "{re.escape(DIST_NAME)}"', pyproject, re.MULTILINE) is not None,
        "pyproject.toml",
        f"distribution name must be {DIST_NAME} (see _version.DIST_NAME)",
    )
    report.check(
        PRODUCT_NAME in (ROOT / "README.md").read_text(encoding="utf-8"),
        "README.md",
        f"must name the product: {PRODUCT_NAME}",
    )

    plugin = json.loads((ROOT / ".claude-plugin/plugin.json").read_text(encoding="utf-8"))
    report.check(plugin.get("version") == version, ".claude-plugin/plugin.json", f"version must be {version}")
    report.check(plugin.get("name") == "geo", ".claude-plugin/plugin.json", "name must be 'geo'")
    report.check(
        PRODUCT_NAME in plugin.get("description", ""),
        ".claude-plugin/plugin.json",
        f"description must name the product: {PRODUCT_NAME}",
    )

    market = json.loads((ROOT / ".claude-plugin/marketplace.json").read_text(encoding="utf-8"))
    report.check(
        market["metadata"]["version"] == version,
        ".claude-plugin/marketplace.json",
        f"metadata.version must be {version}",
    )
    for entry in market["plugins"]:
        report.check(
            entry.get("version") == version,
            ".claude-plugin/marketplace.json",
            f"plugins[{entry.get('name')}].version must be {version}",
        )


def lint_skill_set(report: Report) -> list[Path]:
    skills_dir = ROOT / "skills"
    found = {
        path.name
        for path in skills_dir.iterdir()
        if path.is_dir() and not path.name.startswith("_")
    }
    report.check(
        found == set(EXPECTED_SKILLS),
        "skills/",
        f"directory set {sorted(found)} does not match the manifest {sorted(EXPECTED_SKILLS)}",
    )

    plugin = json.loads((ROOT / ".claude-plugin/plugin.json").read_text(encoding="utf-8"))
    listed = {Path(entry).name for entry in plugin.get("skills", [])}
    report.check(
        listed == set(EXPECTED_SKILLS),
        ".claude-plugin/plugin.json",
        f"skills array {sorted(listed)} does not match the manifest {sorted(EXPECTED_SKILLS)}",
    )
    return sorted(skills_dir / name for name in found)


def lint_skill(report: Report, path: Path, version: str, contract: str, allowed: set[str]) -> None:
    where = f"skills/{path.name}/SKILL.md"
    skill_file = path / "SKILL.md"
    if not skill_file.exists():
        report.fail(where, "missing")
        return
    text = skill_file.read_text(encoding="utf-8")

    fields = parse_frontmatter(text)
    for key in FRONTMATTER_REQUIRED:
        report.check(bool(fields.get(key)), where, f"frontmatter is missing {key}")
    report.check(fields.get("name") == path.name, where, f"frontmatter name must be {path.name!r}")
    report.check(fields.get("version") == version, where, f"frontmatter version must be {version}")
    description = fields.get("description", "")
    report.check(
        40 <= len(description) <= 500,
        where,
        f"description is {len(description)} characters; aim for 40-500",
    )
    report.check(
        "Use when" in description or "use when" in description,
        where,
        "description should say when to use the skill, not only what it is",
    )

    if "## Preflight" in text:
        preflight = text.split("## Preflight", 1)[1].split("\n## ", 1)[0]
        report.check(
            DIST_NAME in preflight,
            where,
            f"the preflight must name the current distribution, {DIST_NAME}",
        )
        report.check(
            version.rsplit(".", 1)[0] in preflight,
            where,
            f"the preflight must name the current version line, {version.rsplit('.', 1)[0]}.x",
        )
        report.check(
            "geo --version" in preflight,
            where,
            "the preflight must tell the model how to check the CLI",
        )
        unpublished = prepublication()
        report.check(
            (SOURCE_INSTALL in preflight) == unpublished,
            where,
            f"the preflight must offer the source install, `uv tool install {SOURCE_INSTALL}`, "
            "until the first release is on PyPI"
            if unpublished
            else "README no longer says the package is unpublished; drop the source-install "
            "fallback from the preflight",
        )
    else:
        report.fail(where, "has no Preflight section")

    if CONTRACT_BEGIN in text and CONTRACT_END in text:
        block = text.split(CONTRACT_BEGIN, 1)[1].split(CONTRACT_END, 1)[0]
        report.check(
            block.strip() == contract.strip(),
            where,
            "response-contract block differs from skills/_shared/response-contract.md",
        )
    else:
        report.fail(where, "response-contract markers are missing")

    body = text.split("---\n", 2)[-1] if text.startswith("---\n") else text
    report.check(not BANNED_PATHS.search(body), where, "references an absolute install path")
    stats = MARKET_STATS.search(body)
    report.check(
        stats is None,
        where,
        f"contains a market statistic ({stats.group(0) if stats else ''}); those belong in docs with a source and a date",
    )

    for section in re.findall(r"`?sections/([a-z0-9_-]+\.md)`?", text):
        report.check((path / "sections" / section).exists(), where, f"references missing sections/{section}")

    for match in IDENTIFIER.findall(text):
        report.check(
            match in allowed,
            where,
            f"mentions {match!r}, which the CLI does not emit",
        )

    for section_file in sorted((path / "sections").glob("*.md")) if (path / "sections").is_dir() else []:
        section_text = section_file.read_text(encoding="utf-8")
        section_where = f"skills/{path.name}/sections/{section_file.name}"
        report.check(
            not BANNED_PATHS.search(section_text),
            section_where,
            "references an absolute install path",
        )
        for match in IDENTIFIER.findall(section_text):
            report.check(
                match in allowed,
                section_where,
                f"mentions {match!r}, which the CLI does not emit",
            )


def main(argv: list[str] | None = None) -> int:
    quiet = "--quiet" in (argv or sys.argv[1:])
    report = Report()
    version = read_version()
    contract = (ROOT / "skills/_shared/response-contract.md").read_text(encoding="utf-8")
    allowed = known_keys()

    lint_versions(report, version)
    for path in lint_skill_set(report):
        lint_skill(report, path, version, contract, allowed)

    if report.errors:
        print(f"skill lint: {len(report.errors)} problem(s)", file=sys.stderr)
        for line in report.errors:
            print(f"  {line}", file=sys.stderr)
        return 1
    if not quiet:
        print(f"skill lint: {report.checked} checks passed across {len(EXPECTED_SKILLS)} skill(s)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
