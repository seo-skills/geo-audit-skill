# SEOmator GEO Audit Skill

A GEO (Generative Engine Optimization) audit toolkit for Claude Code: a deterministic
Python CLI, plus thin skills that narrate what it computes.

It audits how a page or a whole site reads to AI search - ChatGPT, Claude, Perplexity,
Google AI Overviews, Bing Copilot: which of their crawlers robots.txt lets in, whether a
passage can be lifted into an answer without rewriting, whether the markup says who wrote
the page and when, and whether the per-engine plumbing (llms.txt, preview cards, feeds,
hreflang) is there. The same work is sometimes called answer engine optimization (AEO) or
LLM SEO.

```
plugin   /plugin marketplace add seo-skills/geo-audit-skill  ->  /plugin install geo@seomator
CLI      uv tool install seomator-geo-audit                  ->  geo audit <url>
```

**The one claim:** every number in a report is reproducible from recorded evidence.
The CLI computes; the model explains and prioritizes. No score is ever produced by
an LLM doing arithmetic in prose.

> **Status: 1.2.0, stable.** Eleven commands, nine skills, six scoring categories, and an
> envelope schema the build enforces and 1.0 freezes: fields are added, never removed or
> renamed without a new schema version announced two releases ahead. Reports are held
> to [the practitioner eval](tests/evals/README.md). See [the roadmap](#roadmap).

**From SEOmator.** This is SEOmator's free, MIT-licensed GEO audit. For more features,
agentic ones included, sign up at [seomator.com](https://seomator.com).

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
/plugin install geo@seomator
/geo:audit https://example.com
```

Nine skills ship with the plugin: `/geo:audit`, `/geo:citability`, `/geo:technical`,
`/geo:schema`, `/geo:content`, `/geo:llmstxt`, `/geo:brand`, `/geo:compare` and
`/geo:report`. They call the CLI and read its JSON.
They never guess a number, and they never see raw page text.

## What a GEO audit checks

Six categories, weighted to 100: thirty scored checks, plus two advisory questions a
model answers and no code turns into a number. Every signal is classified, and the class
decides what it is allowed to do to a score.

| Category | Weight | Signals | Asks |
|---|---|---|---|
| **citability** | 25 | 7 | Can a passage be lifted from the page and used as an answer? |
| **brand** | 20 | 4 | Does the name resolve to an entity an engine can look up? |
| **content** | 20 | 4 + 2 advisory | Is it deep, attributed, dated and quotable? |
| **technical** | 15 | 6 | Can a crawler reach, read and index it at all? |
| **schema** | 10 | 5 | Does the page describe itself in a form nobody has to interpret? |
| **platform** | 10 | 4 | Is the per-surface plumbing there: llms.txt, preview cards, feeds, hreflang? |

Every check, by category:

<!-- generated:checks:begin -->
**citability** (25 of 100) - Self-contained passages · Answer-first sections · Heading structure · Evidence in claims · Content in the HTML · Attribution · Content without JavaScript

**technical** (15 of 100) - AI crawler access · Indexability · Titles and descriptions · Status codes · HTTPS · URL structure

**schema** (10 of 100) - Structured data present · Valid markup · Publisher markup · Article markup · Answer markup

**brand** (20 of 100) - Encyclopedic entry · Community discussion · Video presence · Profile links

**content** (20 of 100) - Depth · Authorship · Freshness · Readability

**platform** (10 of 100) - llms.txt file · Preview cards · Feeds and sitemaps · Language versions
<!-- generated:checks:end -->

Full definitions, point tables and thresholds:
[docs/concepts/signals.md](docs/concepts/signals.md).

`geo score <url>` runs the page-level checks on one URL. `geo audit <url>` crawls the
site (50 pages by default, one request per second, robots.txt respected for every link
it discovers) and scores the site-level ones too: llms.txt, feeds and sitemaps, language
versions, and crawler access from the site's own robots.txt. A capped crawl says so in
the report, so the number is never presented as the whole site.

### Which AI crawlers it checks

Blocking a search or answer crawler keeps a site out of that engine's answers; blocking a
training crawler is a separate decision, and the report separates them.

<!-- generated:crawler-summary:begin -->
| Operator | Crawlers checked |
|---|---|
| OpenAI | `GPTBot`, `OAI-SearchBot`, `ChatGPT-User` |
| Perplexity | `PerplexityBot`, `Perplexity-User` |
| Anthropic | `ClaudeBot`, `Claude-SearchBot`, `Claude-User` |
| Google | `Google-Extended`, `Googlebot` |
| Microsoft | `Bingbot` |
| Apple | `Applebot`, `Applebot-Extended` |
| Meta | `meta-externalagent` |
| Amazon | `Amazonbot` |
| Common Crawl | `CCBot` |
<!-- generated:crawler-summary:end -->

What each one gates, with the operator's documentation:
[skills/technical/sections/crawlers.md](skills/technical/sections/crawlers.md).

### Three rules that shape every number

**A signal that could not be measured is never scored as a failure.** It is `null`,
`completeness` names it, and the score is taken over the signals that were computed.
The same rule applies one level up: `geo audit --only schema` scores out of schema,
not out of schema plus five zeroes. A category whose input you did not supply — brand,
without a name — is out of scope rather than missing. A signal that does not apply is out
of scope the same way: authorship, attribution and Article markup on a home page, a
product or a tool are `null` and *not applicable*, which is not a gap.

**Model judgement never becomes a number.** Two content questions are marked
`advisory`: they carry a rubric and no value, a model answers them, and the composite
filters on signal class so no code path turns an answer into a score. They appear in
their own labelled section of the report.

**A fact is scored once.** No signal id appears in two categories, and a test asserts
it. Crawler access is technical; answer-shaped schema types are schema; preview cards
are platform.

## What an audit produces

One run gives you four things, from the same recorded evidence:

* **A terminal summary** - the score with its tier, the category scores, and the fixes in
  the order they pay, each with what it recovers on the overall score.
* **A client report** you can send: one self-contained HTML file, no scripts, no
  tracking, that opens with the score and what the tier means, then *what is already
  working*, *what stands out*, *what to do, in order* (each fix with its evidence, the
  pages it affects and the gain), a plan grouped by effort, the category scores, the AI
  crawler table, every finding, the pages analysed and a glossary. `geo report --pdf`
  writes the same document for sending or printing.
* **An operator copy** (`--mode operator`) with the run id, the evidence hash, the crawl
  limits, the pages that failed and the full signal table.
* **A JSON envelope** for anything downstream, validated against a shipped JSON Schema in
  CI, with `scoring_version`, `data_version` and `normalizer_version` on every response.

The run is recorded under `~/.geo`, with the pages it read. `--rescore <run_id>`
recomputes the score from those stored pages with no network at all, and `geo compare`
says what changed since last time, refusing any pair whose difference would measure the
tool rather than the site.

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

## Questions people ask

**What is GEO?** Optimizing for the answers AI engines write, not only for a list of blue
links. A page ranks in AI search by being reachable, quotable and attributable, which is
what this tool measures.

**How is this different from an SEO audit?** It scores what a model can lift and credit:
self-contained passages, evidence in claims, machine-readable authorship, structured data,
llms.txt, and which AI crawlers robots.txt admits. It does not measure rankings, backlinks
or traffic, and it is not a replacement for a search console.

**Does it need a browser?** No. The optional `browser` extra adds two things: a check of
what the page looks like once JavaScript has run, and PDF export.

**Do I need Claude Code?** No. The CLI stands alone and prints JSON. The plugin adds nine
skills that read that JSON and explain it; they never compute a number themselves.

**How many pages does it crawl?** 50 by default, one request per second across the whole
crawl, five in flight, robots.txt respected for every discovered link. `--max-pages`
changes it.

**Does my content leave my machine?** No. The CLI fetches the pages you point it at and
stores them under `~/.geo` so a rescore can reproduce the number. Its output carries
derived signals and short, escaped excerpts, never page text, and nothing is uploaded.

**Can I compare the score with another tool's?** No. A score is comparable with another
score from this tool at the same `scoring_version` and `data_version`. Other tools
measure different things.

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
| 0.6.0 | authorship, attribution and Article markup scored on articles only (scoring 2.0) |
| 0.7.0 | extractability scores evidence that content needs JavaScript, not length (scoring 3.0) |
| 0.8.0 | the report renders with its whole stylesheet, redesigned for screen and print |
| 1.0.0 | the envelope schema frozen and promised; released on the maintainer's approval |
| 1.1.0 | expertise reads the article's author and archives are not articles (scoring 4.0); the page's only `<article>` has to hold the page (normalizer 3); a capped crawl spreads over the site's sections; `compare` refuses a normalizer change |
| 1.2.0 | what ChatGPT, Gemini and Google AI Mode say about a brand, asked on the user's own scrape.do key, recorded and never scored; a timeout is reported as one and never sent twice |

The bar a report is held to is not a feature. It is [the eval](tests/evals/README.md):
two rounds where an outside practitioner would send at least four of five reports
unedited. 1.0 was released on the maintainer's approval before an outside round ran.

## Docs

* [Quickstart](docs/quickstart.md) · [Practitioner eval](tests/evals/README.md)
* [Command reference](docs/commands.md) (generated from the parser)
* [Signals](docs/concepts/signals.md) · [Evidence](docs/concepts/evidence.md) · [Scoring methodology](docs/concepts/scoring-methodology.md) · [Score divergence](docs/concepts/score-divergence.md)
* [Envelope JSON Schema](src/geo_audit/assets/envelope.schema.json) — every command's output validates against it in CI
* [Troubleshooting](docs/troubleshooting.md) — every exit code and `GEO_E_*` code mapped to a fix
* [Contributing](CONTRIBUTING.md)

## License

MIT, © 2026 SEOmator. See [LICENSE](LICENSE).
