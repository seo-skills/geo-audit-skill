# Changelog

All notable changes to this project are documented here.

The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and this
project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

## [0.3.0] - 2026-09-20

Reports, comparison, and the last two scoring categories. All six categories now
compute and their weights sum to 100.

### Added

- **`geo report`** — a recorded audit rendered as a single self-contained HTML file,
  optionally printed to PDF through the browser so the print stylesheet decides the
  page breaks. Two modes: client, and operator with a provenance section.
- **Client and operator isolation by construction.** `render_client` builds a
  namespace with no `operator` key in it, under `StrictUndefined`, so a leak is a
  render error rather than a field in a document already sent. Tests prove the
  mechanism, walk every operator field, and check a report for data from a second
  audited site.
- **Brand tokens** with a real contrast rule. The header keeps the brand colour with
  automatically chosen text; the accent, which is where palettes actually fail on
  white, falls back loudly with a stderr warning and an operator-view annotation.
- **`geo compare`** — what moved between two recorded audits, by category, finding and
  page, with no network. It refuses across a scoring or data version change, because
  that difference would measure the tool rather than the site.
- **Content category** (weight 20): depth, expertise, freshness, readability.
- **The advisory mechanism.** Two content questions carry a rubric and no value, a
  model answers them, and `composite()` filters on signal class so no code path turns
  an answer into a number. `geo report --advisory` folds answers into a labelled
  section; answers to questions nobody asked, and verdicts outside the fixed set, are
  refused.
- **Platform category** (weight 10): llms.txt, preview cards, feeds, hreflang.
  Deliberately narrow — anything already scored elsewhere is left out.
- **Three more skills**: `geo:content`, `geo:compare`, `geo:report`. Nine in total.
- **The practitioner eval harness** (`tests/evals/`): audits the sites, renders the
  reports, and emits a blank two-person scoring form. It produces the inputs to a
  judgement and never the judgement; a test asserts it never pre-fills an answer.

### Changed

- `hreflang` is not measured on a single-language site rather than scored zero.
- Open Graph moved from `technical.metadata` to `platform.social_cards`, so one tag
  counts once. A test asserts no signal id appears in two categories.
- `--out` means one thing per command: this command's primary artifact. For `report`
  that is the HTML file.
- The skill lint checks each preflight names the current distribution and version.

### Fixed

- `geo report --out x.html` wrote the HTML and then overwrote it with the JSON
  envelope.
- Three skills shipped naming the old product in their preflight. The lint now
  catches that class.

## [0.2.0] - 2026-09-20

The audit itself: a crawler, four scored categories, and five more skills.

### Added

- **`geo crawl`** - maps what a crawler can reach. The rate limit is global rather
  than per worker, because five workers at one request per second each is five
  requests per second at the site. robots.txt governs discovery, not the URL you
  typed: a disallowed page is never requested, and the fixture server's request log
  proves it rather than proving only that no result came back. Sitemaps seed the
  frontier; tracking-parameter variants and fragments collapse to one page.
- **`geo audit`** - crawls, scores every category over every page, and weights them
  into one number. Per-page signals roll up as a mean over the pages where they were
  measured, carrying the spread and the worst page. A detail that is identical on
  every page survives aggregation, so a site-level fact like which crawler tokens are
  blocked is not replaced by an average.
- **`geo audit --rescore <run_id>`** - recomputes from a stored record with no network
  at all. Rescoring twice is byte-identical, and a test asserts the server sees no
  requests during one. It reports the recorded versions against the current ones, so a
  rescore after a data update says plainly that the number is not the one recorded.
- **`geo audit --only`** and **`--brand`** - a category the run's inputs cannot reach
  is out of scope rather than missing, and `--only schema` scores out of schema alone.
- **Technical category** (weight 15): crawler access against the AI crawler tokens,
  indexability, metadata, status health, transport security, URL structure. Training
  tokens and search tokens are scored separately.
- **Schema category** (weight 10): presence, validity against schema.org-derived
  requirements, publisher identity, article properties, and types that answer a
  question directly.
- **Brand category** (weight 20): Wikipedia, Wikidata, Reddit and YouTube through
  their documented public APIs, plus whether the site links itself to those profiles.
- **`geo validate`** - reports JSON-LD node by node, with `--suggest` building a block
  from what the page already states rather than a template to fill in.
- **`geo llmstxt`** - checks /llms.txt against the llmstxt.org structure, and with
  `--generate` builds one from pages that were actually fetched.
- **`geo scan`** - brand presence. Platforms with no usable API are listed as manual
  checks and never emitted as results.
- **`geo prune`** - count, age and size limits over the append-only history.
- **Five skills**: `geo:audit`, `geo:technical`, `geo:schema`, `geo:llmstxt`,
  `geo:brand`, each carrying the shared response contract byte-identically.
- **Instruction-shaped text detection.** Pages whose own title or summary is addressed
  to an AI system are excluded from a generated llms.txt and reported as a finding.
  That file gets published and read as authoritative; copying a page's own "ignore
  previous instructions" into it would hand the attack a better delivery mechanism
  than the page had.

### Changed

- **The product is SEOmator GEO Audit Skill.** The PyPI distribution is
  `seomator-geo-audit`, the crawler identifies itself as `SeomatorGeoAudit` with a
  link back to this repository, and the licence is © 2026 SEOmator. Nothing a user
  types changed: the command is still `geo`, the plugin is still `geo`, and the skills
  are still `/geo:audit` and friends. The names live in `_version.py` and the lint
  asserts every manifest agrees with them.
- Connections are kept alive rather than closed per request. A crawl of fifty pages
  costs one connection, not fifty handshakes.
- A 404 reached by following a link is its own finding. It is a broken link, not a
  server error, and the fix is different.
- A page that returned no markup is *not measured* on markup signals rather than
  scored zero, so one 404 is not counted twice.
- `schema.presence` means "did the page attempt JSON-LD", which stops a page with
  broken markup receiving two contradictory findings at once.
- Findings repeated across pages merge into one finding carrying every page it
  affects.

### Fixed

- Structured data that is absent is no longer reported as valid.
- A finding with no points to recover no longer advertises `+0 points available`.
- An empty page reports the one finding that explains the absence instead of six that
  presuppose content it does not have.

## [0.1.0] - 2026-09-20

The walking skeleton: three commands with the full safety, evidence and exit-code
contract behind them, and one skill end to end.

### Added

- **`geo score`** — citability of a single page over seven signals
  (`self_containment`, `answer_first`, `structure`, `evidence_density`,
  `extractability`, `attribution`, `render_parity`). Prints a number and its tier
  label together, the signals behind it, and findings ranked by points recovered.
- **`geo fetch`** — what a non-rendering crawler receives: status, redirect chain,
  content-block count, evidence hash, JSON-LD types, and per-crawler robots access.
- **`geo doctor`** — interpreter, PATH collisions, `$GEO_HOME` permissions, sync-drive
  detection, state version, package data, and the optional browser extra. Reports;
  never gates.
- **JSON envelope** with a fixed key set and `schema_version`, `scoring_version`,
  `data_version` and `normalizer_version` on every response. JSON whenever stdout is
  not a terminal; progress on stderr, always.
- **Evidence model.** SHA-256 over the extracted content-block sequence plus
  `normalizer_version`. ETag and Last-Modified are metadata and a revalidation
  shortcut, deliberately not part of hash identity. Stamps: `CURRENT`, `PARTIAL`,
  `STALE`.
- **Fetch safety.** Private, loopback, link-local, multicast and reserved addresses
  refused, including IPv4-mapped IPv6 forms; the connected peer address validated as
  well as the resolved name, which closes DNS rebinding; per-hop redirect validation;
  declared and streaming size caps; content-type allowlist; `--allow-private` to opt
  in to auditing a private start URL.
- **RFC 9309 robots.txt** parser with the full status matrix (4xx allows, 5xx
  disallows, redirects followed), longest-match and least-restrictive-tie rules,
  wildcards and end anchors. Sixteen AI crawler tokens in versioned data, each with
  its operator's documentation URL.
- **Append-only state** under `$GEO_HOME` (default `~/.geo`, mode 0700). One record
  per run; a torn trailing line is discarded silently; state carries a version and a
  newer state is refused without changing anything.
- **Seventeen `GEO_E_*` error codes**, every one carrying a hint and a docs anchor,
  mapped to six exit codes. A 403 or 5xx from an audited page is a finding, not a
  failure.
- **`geo:citability` skill** with preflight, the shared response contract, and
  methodology sections loaded on demand.
- **Claude Code plugin** manifests for `/plugin marketplace add` installation.
- **Test suite** covering the envelope goldens, the SSRF matrix, the robots matrix,
  hash stability under nonce and timestamp rotation, the output boundary, the
  injection fixture, state handling, skill contracts, and the README quickstart.
- **Generated docs** for the command reference and scoring constants, with a CI
  freshness check.

### Notes

- Scores are comparable only with other scores from this tool at the same
  `scoring_version` and `data_version`.
- `citability.render_parity` is `null` without the optional browser extra. The
  composite is taken over the signals that were computed; a signal that was not
  measured is never scored as a failure.

[Unreleased]: https://github.com/seo-skills/geo-audit-skill/compare/v0.3.0...HEAD
[0.3.0]: https://github.com/seo-skills/geo-audit-skill/releases/tag/v0.3.0
[0.2.0]: https://github.com/seo-skills/geo-audit-skill/releases/tag/v0.2.0
[0.1.0]: https://github.com/seo-skills/geo-audit-skill/releases/tag/v0.1.0
