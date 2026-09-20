# CLAUDE.md

Guidance for Claude Code when working in this repository.

## What this is

A GEO (Generative Engine Optimization) audit toolkit: a deterministic Python CLI
(`geo`, PyPI `geo-audit-cli`) plus thin Claude Code skills that call it. The skills
narrate; the CLI computes.

**The invariant everything else serves:** no number reaches a user that did not come
from the scorer. If a change makes a score depend on model output, it is the wrong
change.

## Layout

| Path | Contents |
|---|---|
| `src/geo_audit/cli.py` | Argument parsing, output mode, the exit-code decision. The only place that decides how a run ends. |
| `src/geo_audit/commands/` | One module per command. Each returns an envelope and raises `GeoError`; none calls `sys.exit` or prints to stdout. |
| `src/geo_audit/lib/` | Shared helpers, each existing exactly once: `http`, `net`, `extract`, `robots`, `evidence`, `headers`, `ids`, `slug`, `browser`. |
| `src/geo_audit/scoring/` | `model.py` holds the signal types and the composite arithmetic; category modules hold the signals. |
| `src/geo_audit/data/` | Weights, thresholds, tiers, crawler tokens, finding copy. Constants live here, not in code and not in prose. |
| `src/geo_audit/copy.py` | Literal user-facing sentences. Golden tests assert them. |
| `skills/<name>/SKILL.md` | One skill per directory, with `sections/*.md` loaded on demand. |
| `skills/_shared/response-contract.md` | The block every skill embeds byte-identically. |
| `tools/lint_skills.py` | Skill contract enforcement, including the key manifest. |
| `tools/gen_docs.py` | Generates `docs/commands.md` and the marker regions in concept docs. |
| `tests/fixtures/site/` | Synthetic fixture pages, authored here. Never captured from the web. |

## Before claiming anything works

```bash
.venv/bin/python -m pytest
.venv/bin/python tools/lint_skills.py
.venv/bin/python tools/gen_docs.py --check
```

All three, every time. CI runs exactly these on three operating systems.

## Rules that are easy to break by accident

- **Constants go in `data/`.** A threshold hardcoded in a scorer is a bug even when
  the number is right, because `data_version` stops describing the score.
- **A signal that could not be computed returns `None`, never `0`.** The composite
  divides by the max of the *computed* signals so that a missing capability lowers
  `completeness` rather than the score.
- **CLI output never contains page text.** Derived signals, counts, and excerpts
  capped at 280 characters with backticks and angle brackets escaped. `tests/
  test_output_boundary.py` enforces the rule; do not weaken it to make a report
  richer.
- **One helper, one home.** Upstream's duplicated `DEFAULT_HEADERS` and duplicated
  block extraction are the failure mode this layout exists to prevent.
- **Skills reference no file paths.** Templates and data are reached through CLI
  commands, which is what makes the shipped artifact equal the tested one.
- **Nothing is modified at install time.** No shebang rewriting, no generated files
  in the install step.
- **No market statistics in prompts or CLI output.** The skill lint rejects them.
  Market context belongs in docs, with a source and a date.

## When editing a skill

The response-contract block between `<!-- geo:response-contract:begin -->` and
`<!-- geo:response-contract:end -->` must stay byte-identical to
`skills/_shared/response-contract.md`. Every backticked identifier must be one the CLI
emits. Both are enforced by `tools/lint_skills.py`, which fails the build.

## Versioning

`VERSION` is the single source; `pyproject.toml`, `_version.py`, both plugin manifests
and every skill frontmatter must match it. The four contract versions (`schema`,
`scoring`, `data`, `normalizer`) move independently and appear in every envelope.

## Cut list (binding)

Not built without amending the project document first: multi-host generation,
cross-machine sync, telemetry, consent flows, update checks, a self-update or
data-update channel separate from PyPI, shell installers and ownership manifests, a
SKILL.md template generator, crawl resume, alias and forwarding skills.
