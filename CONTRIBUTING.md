# Contributing

## The one rule

**No number reaches a user that did not come from the scorer.** If a change makes a
score depend on model output, on the time of day, or on anything not recorded in the
audit record, it is the wrong change regardless of how much better the number looks.

Everything below follows from that.

## Setup

```bash
uv venv --python 3.12
uv pip install -e ".[dev]"
.venv/bin/python -m pytest
```

Optional, for the render signals and PDF later:

```bash
uv pip install -e ".[dev,browser]"
.venv/bin/python -m playwright install chromium
```

## Before you open a PR

```bash
python -m pytest                  # the suite
python tools/lint_skills.py       # skill contracts and the key manifest
python tools/gen_docs.py --check  # generated docs are current
```

CI runs exactly these on Linux, macOS and Windows, against Python 3.11 and 3.13.

**3.11 is the declared minimum and it is not the version you are probably running.**
Syntax that 3.12 accepts can fail there: a backslash inside an f-string expression is
the one that has already caught us, since PEP 701 only lifted that restriction in
3.12. If your interpreter is newer, check before pushing:

```bash
uv venv --python 3.11 /tmp/min && uv pip install --python /tmp/min/bin/python -e ".[dev]"
/tmp/min/bin/python -m pytest -q
```

## Where things live

| Change | Where it goes |
|---|---|
| A weight, threshold, tier boundary or crawler token | `src/geo_audit/data/*.json`, and bump `data_version` |
| Finding copy or remediation advice | `src/geo_audit/data/findings.json` |
| A new signal | `src/geo_audit/scoring/`, plus its entry in `weights.json` and `findings.json` |
| Anything a user reads in the terminal | `src/geo_audit/copy.py` |
| A shared helper | `src/geo_audit/lib/`, and only once |

Constants do not live in code, and they never live in prose.

## Adding a signal

1. Add it to `data/weights.json` with its `max` and its class.
2. Add a finding template to `data/findings.json`. The lint fails without one.
3. Write the function in `scoring/citability.py` (or a new category module). It returns
   `(points, detail)`. `detail` carries the counts behind the number and, where useful,
   a `worst_example` built with `extract.excerpt`.
4. Return `None` for points when the signal could not be computed. Never zero.
5. Add tests: one that it fires, one that it does not fire on a healthy page, and one
   for the boundary you chose.
6. Run `python tools/gen_docs.py`. The signal tables regenerate themselves.
7. Add a row to `docs/concepts/score-divergence.md` if the choice is arguable. Most
   are.

## Adding a skill

1. Add the directory name to `EXPECTED_SKILLS` in `tools/lint_skills.py`.
2. Add it to the `skills` array in `.claude-plugin/plugin.json`.
3. Copy the response-contract block from `skills/_shared/response-contract.md`
   verbatim, between the markers. The lint compares it byte for byte.
4. Every identifier the skill mentions in backticks must be one the CLI emits. That is
   the key manifest, and it is what keeps prose from inventing vocabulary.
5. Long methodology goes in `sections/*.md`, loaded on demand.

## Fixtures

Fixtures are **authored for this repository**, never captured from the web. Checking
real third-party HTML into a public MIT repo redistributes someone else's copyrighted
content. If you need a fixture that behaves like a real site, write one that behaves
like a real site.

## Tests that are not optional

A PR touching any of these needs the matching test updated in the same commit:

* the envelope shape → the goldens in `tests/goldens/`
* the normalizer → `test_evidence.py`, including the nonce-variant golden
* the fetch layer → `test_net_guards.py`, `test_fetch_caps.py`
* error codes → `test_errors.py` (every code needs a hint)
* user-facing copy → `test_copy.py`
* anything a doc claims → `test_docs.py`

## Commits

Imperative present tense, first line 72 characters or fewer, body explaining why
rather than what. One logical change per commit: the history should bisect.

## Versioning

`VERSION` at the repo root is the single source. `pyproject.toml`, `_version.py`, both
plugin manifests and every skill frontmatter must agree with it, and the lint checks
that they do. The four contract versions (`schema`, `scoring`, `data`, `normalizer`)
move independently and are documented in
[scoring-methodology.md](docs/concepts/scoring-methodology.md).

## Scope

The cut list is binding. Not built, and not accepted without a change to the project
document first: multi-host output generation, cross-machine sync, telemetry, consent
flows, update checks, a self-update or data-update channel separate from PyPI, shell
installers, a skill template generator, crawl resume, and alias or forwarding skills.
