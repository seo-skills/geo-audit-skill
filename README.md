# SEOmator GEO Audit Skill

A GEO (Generative Engine Optimization) audit toolkit for Claude Code: a deterministic
Python CLI, plus thin skills that narrate what it computes.

```
plugin   /plugin marketplace add seo-skills/geo-audit-skill  ->  /plugin install geo
CLI      uv tool install seomator-geo-audit                  ->  geo audit <url>
```

**The one claim:** every number in a report is reproducible from recorded evidence.
The CLI computes; the model explains and prioritizes. No score is ever produced by
an LLM doing arithmetic in prose.

> **Status: 0.5.0.** Eleven commands, nine skills, six scoring categories, an envelope
> schema the build enforces, and audits that keep the pages they read. What stands between
> this and 1.0 is [the practitioner eval](tests/evals/README.md) — a human gate, by
> design. See [the roadmap](#roadmap).

## Install

```bash
uv tool install seomator-geo-audit      # or: pipx install seomator-geo-audit
```

Python 3.11 or newer. No browser required.

## Quickstart

```bash
geo doctor
geo score https://example.com/pricing
geo audit https://example.com
```

`geo score` is the first success: one page, no crawl, no browser, no Claude Code,
under thirty seconds. It prints a citability score out of 100 with its tier label,
the signals behind it, and the fixes ranked by what they recover.

`geo audit` crawls the site and scores every category over it. It respects
robots.txt for the links it discovers, holds to one request per second across the
whole crawl, and records the result so you can reproduce it later:

```bash
geo audit https://example.com --rescore <run_id>   # recomputes, no network
geo report https://example.com --pdf               # a document you can send
geo report https://example.com --site-kind docs   # ordered for a documentation site
geo compare https://example.com                    # what changed since last time
```

What a report looks like: [client copy](examples/client-report.html) and
[operator copy](examples/operator-report.html), generated from the synthetic fixture site.

Output is JSON whenever stdout is not a terminal, so the second command needs no
flag in a pipeline. Progress goes to stderr, always.

### Inside Claude Code

```
/plugin marketplace add seo-skills/geo-audit-skill
/plugin install geo
/geo:audit https://example.com
```

Six skills ship with the plugin: `/geo:audit`, `/geo:citability`, `/geo:technical`,
`/geo:schema`, `/geo:llmstxt` and `/geo:brand`. They call the CLI and read its JSON.
They never guess a number, and they never see raw page text.

## What it measures today

Six categories, weighted to 100. Every signal is classified, and the class decides
what it is allowed to do to a number.

| Category | Weight | Signals | Asks |
|---|---|---|---|
| **citability** | 25 | 7 | Can a passage be lifted from the page and used as an answer? |
| **brand** | 20 | 4 | Does the name resolve to an entity an engine can look up? |
| **content** | 20 | 4 + 2 advisory | Is it deep, attributed, dated and quotable? |
| **technical** | 15 | 6 | Can a crawler reach, read and index it at all? |
| **schema** | 10 | 5 | Does the page describe itself in a form nobody has to interpret? |
| **platform** | 10 | 4 | Is the per-surface plumbing there: llms.txt, preview cards, feeds, hreflang? |

Full definitions and thresholds: [docs/concepts/signals.md](docs/concepts/signals.md).

### Three rules that shape every number

**A signal that could not be measured is never scored as a failure.** It is `null`,
`completeness` names it, and the score is taken over the signals that were computed.
The same rule applies one level up: `geo audit --only schema` scores out of schema,
not out of schema plus five zeroes. A category whose input you did not supply — brand,
without a name — is out of scope rather than missing.

**Model judgement never becomes a number.** Two content questions are marked
`advisory`: they carry a rubric and no value, a model answers them, and the composite
filters on signal class so no code path turns an answer into a score. They appear in
their own labelled section of the report.

**A fact is scored once.** No signal id appears in two categories, and a test asserts
it. Crawler access is technical; answer-shaped schema types are schema; preview cards
are platform.

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

Crawls identify themselves as `SeomatorGeoAudit/<version>` with a link back to this
repository, hold to one request per second across the whole crawl, and respect
robots.txt for every link they discover.

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

| Release | State |
|---|---|
| 0.1.0 | `fetch`, `score`, `doctor`; evidence model; safety guards |
| 0.2.0 | `crawl`, `audit` with rescoring, `scan`, `llmstxt`, `validate`, `prune`; technical, schema and brand |
| 0.3.0 | `report` in HTML and PDF with client and operator modes, `compare`; content and platform; nine skills |
| 0.4.0 | envelope JSON Schema enforced in CI; golden coverage for every command; the agency kit closed at its gate and deferred |
| 0.5.0 | audits keep the pages they read, and a rescore recomputes from them with today's code |
| 1.0.0 | the frozen schema tagged, after two consecutive practitioner evals |

The gate on 1.0 is not a feature. It is [the eval](tests/evals/README.md): two rounds
where an outside practitioner would send at least four of five reports unedited.

## Docs

* [Quickstart](docs/quickstart.md) · [Practitioner eval](tests/evals/README.md)
* [Command reference](docs/commands.md) (generated from the parser)
* [Signals](docs/concepts/signals.md) · [Evidence](docs/concepts/evidence.md) · [Scoring methodology](docs/concepts/scoring-methodology.md) · [Score divergence](docs/concepts/score-divergence.md)
* [Envelope JSON Schema](src/geo_audit/assets/envelope.schema.json) — every command's output validates against it in CI
* [Troubleshooting](docs/troubleshooting.md) — every exit code and `GEO_E_*` code mapped to a fix
* [Contributing](CONTRIBUTING.md)

## License

MIT, © 2026 SEOmator. See [LICENSE](LICENSE).
