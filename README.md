# geo-audit-skill

A GEO (Generative Engine Optimization) audit toolkit for Claude Code: a deterministic
Python CLI, plus thin skills that narrate what it computes.

**The one claim:** every number in a report is reproducible from recorded evidence.
The CLI computes; the model explains and prioritizes. No score is ever produced by
an LLM doing arithmetic in prose.

> **Status: 0.1.0, the walking skeleton.** `fetch`, `score` and `doctor` work end to
> end with the full safety, evidence and exit-code contract behind them. `crawl`,
> `audit`, `report` and the rest land in 0.2.0 and 0.3.0. See [the roadmap](#roadmap).

## Install

```bash
uv tool install geo-audit-cli      # or: pipx install geo-audit-cli
```

Python 3.11 or newer. No browser required.

## Quickstart

```bash
geo doctor
geo score https://example.com/pricing
geo score https://example.com/pricing --json > score.json
```

That is the whole first run: one page, no crawl, no browser, no Claude Code.
`geo score` prints a citability score out of 100 with its tier label, the signals
behind it, and the fixes ranked by what they recover.

Output is JSON whenever stdout is not a terminal, so the second command needs no
flag in a pipeline. Progress goes to stderr, always.

### Inside Claude Code

```
/plugin marketplace add seo-skills/geo-audit-skill
/plugin install geo
/geo:citability https://example.com/pricing
```

The skills call the CLI and read its JSON. They never guess a number, and they
never see raw page text.

## What it measures today

`geo score` computes seven citability signals over one page:

| Signal | Class | Max | Question |
|---|---|---|---|
| `citability.self_containment` | heuristic | 25 | Does each passage name its own subject? |
| `citability.answer_first` | heuristic | 20 | Does each section lead with the answer? |
| `citability.structure` | deterministic | 15 | Do the headings segment the page into answerable parts? |
| `citability.evidence_density` | heuristic | 15 | Do claims carry numbers, dates and sources? |
| `citability.extractability` | deterministic | 15 | Is the content in the HTML a crawler receives? |
| `citability.attribution` | deterministic | 10 | Does the page say who wrote it and when? |
| `citability.render_parity` | heuristic | 10 | How much text appears only after JavaScript? |

`render_parity` needs the optional browser extra. Without it that signal is **null**,
`completeness` reports 6 of 7 signals computed, and the score is taken over the six
that were. A signal that could not be measured is never scored as a failure.

Full definitions, thresholds and rationale: [docs/concepts/signals.md](docs/concepts/signals.md).

## Reading the output

```
GEO citability score 62/100 (Fair) for example.com — 1 page, evidence CURRENT.
```

* **Number and label always travel together.** Colour is a third channel on top of
  both, never the only one carrying the verdict.
* **`evidence`** carries a SHA-256 over the extracted content blocks plus the
  normalizer version, so a later run can tell you whether the page it scored is
  still the page you are looking at.
* **Scores compare only with themselves.** A score is comparable with another score
  from this tool at the same `scoring_version` and `data_version`. Numbers from
  other GEO tools measure different things and are not interchangeable.

## Safety

The core loop feeds untrusted web content toward an agent with tool access, so:

* CLI output contains derived signals and length-capped, delimiter-escaped excerpts.
  **It never contains page text.**
* Redirects and links to private, loopback, link-local and metadata addresses are
  refused. A private *start* URL needs `--allow-private`, because auditing
  `localhost:3000` is a legitimate thing to want.
* The address we actually connected to is validated, not only the name we resolved.

Details and the threat model: [SECURITY.md](SECURITY.md).

## Exit codes

| Code | Meaning |
|---|---|
| 0 | OK, including PARTIAL results |
| 1 | internal error |
| 2 | usage error |
| 3 | network failure on the start URL |
| 4 | state error |
| 5 | `--fail-on-partial` was passed and the result is PARTIAL |

A 403 or a 5xx from the page is a **finding**, not a failure. Exiting non-zero there
would abort exactly the sites that most need a report.

## Roadmap

| Release | Adds |
|---|---|
| 0.1.0 | `fetch`, `score`, `doctor`; evidence model; safety guards; `geo:citability` |
| 0.2.0 | `crawl`, `audit`, `scan`, `llmstxt`, `validate`, `prune`; `--rescore`; five more skills |
| 0.3.0 | `report` (HTML and PDF, client and operator modes), `compare`, full docs |
| 1.0.0 | envelope `schema_version` frozen |

## Docs

* [Quickstart](docs/quickstart.md)
* [Command reference](docs/commands.md) (generated from the parser)
* [Signals](docs/concepts/signals.md) · [Evidence](docs/concepts/evidence.md) · [Scoring methodology](docs/concepts/scoring-methodology.md) · [Score divergence](docs/concepts/score-divergence.md)
* [Troubleshooting](docs/troubleshooting.md) — every exit code and `GEO_E_*` code mapped to a fix
* [Contributing](CONTRIBUTING.md)

## License

MIT. See [LICENSE](LICENSE).
