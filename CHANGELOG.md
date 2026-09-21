# Changelog

All notable changes to this project are documented here.

The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and this
project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

Nothing yet.

## [0.4.0] - 2026-09-21

No new features. The envelope contract stops being a promise in prose and becomes
something the build checks, and two rounds of practitioner eval are folded in.

### Fixed — hardening toward 1.0

- **Skill heuristics named their sources without linking them.** PRD §3.7 asks for
  primary sources with URLs. RFC 9309's robots.txt rules, schema.org and Google's
  structured-data documentation, llmstxt.org and Google's helpful-content guidance are
  now linked where each claim is made - every URL checked to resolve - and a test keeps
  them there.
- **A bot challenge served with 503 was reported as a server error.** PRD §3.2 says
  bot-blocked means 403 *or challenge*, but only the status code was checked: a
  Cloudflare interstitial answered with 503 told the client to repair a server that
  works, and one answered with 200 would have been scored as the page. A challenge is
  now recognised by the vendor's `cf-mitigated` header - no longer dropped - or by a
  known marker on a refusing status, and on a 200 only when the page is short enough to
  be nothing else, since real pages embed captcha widgets. Markers live in
  `data/bot_challenges.json`.
- **Four of the PRD's eight interaction states had no test, and two were wrong.**
  Checking every PRD claim against the code found the report's PDF-unavailable message
  naming a PyPI package that does not exist before the first release, and the no-audit
  state never used: `report` said "Run `geo audit <url>`" and `compare` said "Only 0
  audit is recorded ... run `geo audit` again". Both now print the PRD's own copy, naming
  the site and the exact command; the PDF message gives an install that works; and the
  loading, zero-mentions, no-audit and PDF states each have a test, as §3.9 requires.
- **The report never said how many signals the score was computed on.** PRD §3.4 has it
  say "computed on 31 of 36 signals"; it now does, under the score, with anything not
  measured named in plain words.
- **`--rescore` did not reproduce a run, only its number.** G1 says the record holds
  every scorer input; it held the site-level signals, so page-level findings could not
  be rebuilt, and check findings - a broken link, a blocked AI crawler - were not passed
  at all. On seomator.com a rescore returned four of six findings. The record now keeps
  a snapshot beside the envelope, on disk only: each page's ratio on each signal and the
  fetch and robots observations, about 13 KB for fifty pages. A live run and a rescore
  classify pages through one function, with the current thresholds, and a rescore of the
  fixture site - brand audit included - now matches the run finding for finding.
- **`geo doctor`'s install hints named a package PyPI does not have yet** - the browser
  extra's hint was the first thing a real install showed. Every hint now goes through
  one helper that gives the source install until `PUBLISHED_ON_PYPI` flips, and a test
  holds that flag to the README's *Not on PyPI yet* note, so one switch still rules
  every install instruction in the project.
- **A finding scored from several parts claimed all of them were missing.** Titles were
  written for the zero case, but a finding fires at up to 70% of its maximum. The first
  real run of the installed skill, on seomator.com, had a byline and Person markup on all
  fifty pages and was told *Authorship is not machine-readable*; the skill corrected it
  in chat, but the client report would have carried it. The fixture's own publisher node
  had been called *No machine-readable publisher identity* in a golden all along.
  Authorship, attribution, publisher and article findings now use a second wording
  whenever the scorer reports that some of their parts are present. Scores do not move.
Four from a dry run of round three against the five eval sites, run to find defects
before a practitioner spends time on them (`tests/evals/results/eval-2026-09-21-round3-dry-run.md`):

- **A start URL that redirects into the sitemap was crawled and scored twice.** MDN's
  root redirects to `/en-US/`, which its sitemap also lists: one page, two requests, so
  the homepage carried double weight in every average and the report said "8 pages
  scored" over seven distinct ones. Pages are now deduplicated on where they landed,
  keeping the first in frontier order. Any apex, `www` or locale redirect has this
  shape. MDN re-crawled scores 60 rather than 57.
- **A soft 404 was scored as content.** MDN serves `/en-US/404` with 200, *Page not
  found* and 58 characters; the report listed it on every finding. A short page whose
  title or first heading says it is missing is now a failed page (`soft_404`) with its
  own finding - both conditions, because an article about 404s has one in its title and
  plenty of real pages are short. The length limit is in `thresholds.json`.
- **A page with nothing to read was listed on site-wide findings.** The fixture's own 404
  had been on the llms.txt and feeds findings all along, and a bot-blocked page too. Such
  a page is now named only on findings about its response. No score moved: llms.txt has
  one value on every page, so only the list of pages to look at changed.
- **Every client report had two blank cells** in the table that explains the scores:
  *What it measures* was empty for content and platform, because only four of the six
  categories had a description. Both have one, and a test requires one for any category
  added later.
- **Two findings named their own severity** - MDN's report put *high* beside "which is
  why this is medium". Severity moves with a site kind and the page-level cap, so a test
  now rejects finding text that says which level it sits at.
- **The 1.0 gate was asking about the wrong document.** Question 2 of the practitioner
  eval is "would you send this to a paying client unedited?", and the harness linked
  only the operator copy - run ids, evidence hashes, the failed-page table, every
  signal value. A careful practitioner answers `no` to that for reasons that say
  nothing about the product. The harness now renders both copies and the form says
  which one the question is about. Rounds one and two were affected but count for
  nothing anyway, since both changed the tool.
- **The report skill could hand over a report as if it were tailored to the site.**
  The rendered report orders findings by the scorer's rules, which do not know what a
  site is for; the skill now says what kind of site it read and names any finding
  the ordering over-weights for it.
- **Installing the plugin today led a new user to a dead end.** The marketplace is
  public and installs cleanly, but every skill told a user without the CLI to run
  `uv tool install seomator-geo-audit`, which fails until the first release is on
  PyPI. Only the README knew. The skills, the quickstart and the troubleshooting page
  now offer the source install as well, and the README's *Not on PyPI yet* note is
  the one switch for all of them: the skill lint and the doc tests require the
  fallback while the note is there and reject it once the note is gone, naming every
  page and skill still carrying it. Found by installing the plugin from a clean
  config rather than from the working tree.
- **`RELEASING.md` said the `pypi` GitHub environment had to be created first.** It
  does not: GitHub creates a missing environment on the first run that references
  it. Creating it by hand is only worth doing to add a required reviewer, which is
  now what the guide says, and why.
- **A page nothing could be measured on reported `0 of 0, nothing missing`**, which
  reads as a complete run and divides by zero for anyone who takes the fraction at
  face value. Seven citability signals were in scope and a 403 reached none of them,
  so that is what the envelope says now: `0 of 7`, each one named, alongside seven
  signals with a null value and a reason. The count comes from `composite()` itself
  rather than a second copy of the rule, so it cannot drift from a scorable run.
- **Arithmetic still decided the order inside the blocking tier**, which is the one
  place it was meant not to. A page the server refused is never scored, so its
  finding carries no `impact` and no `points_lost`, and it lost every tiebreak to a
  blocker that *had* been measured. On a site whose start URL returns 403, the audit
  led with "your content needs JavaScript" and reported the refusal second. Blockers
  now sort by their declared position in `data/findings.json`, and that list is
  ordered by the chain a crawler walks: respond, allow, index, parse. Reordering
  blockers is a data edit now, not a code edit.

### Added

- **Sample reports**, [`examples/`](examples/), as PRD §3.13 asks: a client copy and an
  operator copy regenerated from the synthetic fixture site, never from a real one. They
  are built from the audit's golden envelope by `tools/gen_docs.py`, so CI fails when
  they fall behind the code, and the client copy is tested to carry no operator data.
- **Report detail on a par with the reference implementation**, from measurements
  only. Its deliverables were read as a behavioural spec and the gaps recorded in the
  PRD with a decision each. Adopted: a summary built from the numbers; each fix's gain
  on the *overall* score and the evidence behind it (parts found and missing, whether one
  template decides it, the worst passage); **the plan**, every fix grouped this week /
  this month / this quarter by effort with blockers first; weighted contributions and a
  total row in the category table, with bars; an **AI crawler access** table saying who
  runs each crawler, what it is for and what blocking it costs; **category detail** with
  every signal by plain name; **pages analysed**; a **glossary**; and a note naming any
  category outside the run, so a weight column adding up to 80 explains itself. Left out
  on purpose: the reference's per-platform scores, competitor scores and effort in hours,
  none of which it measured, and page titles, which would carry page text into the
  record the skill reads.
- ***What is already working*, in every report** - the second deliberate exception to
  "no new features", and for the same reason as the first: three rounds of maintainer
  notes found reports that list only faults read as grudging, and the gate is reports
  sent *unedited*. Up to three site-wide signals at 90% or more of their maximum, one
  per category before a second from any, each with a fixed sentence stored beside its
  finding template. A signal with any finding, page-level included, is never named, so
  the report cannot praise what it also faults; no sentence says *every* or *all*,
  because a strength is an average. On the eval sites plausible now opens with
  self-contained passages, substantial pages and crawler access rather than with nothing.
- **`geo report --site-kind`**, the one deliberate exception to "no new features" in
  this release. Both practitioner rounds found a publisher's checklist leading the
  report on a specification and then on a reference site, and the eval judges the
  report itself - which skill guidance could not reach, because the rendered order
  came from a scorer that cannot know what a site is for. A kind (`docs`, `spec`,
  `publisher`, `saas`, `ecommerce`, `local`) moves the findings it leads with up one
  severity level and the ones it defers down two, and the report says which kind it
  was ordered for. Every number is identical across kinds; blockers never move; a
  page-level finding keeps its ceiling; nothing is ever promoted to critical. It is a
  report-time input because the skill reads the kind *from* the audit. On the fixture
  site, *Authorship is not machine-readable* goes from second to out of the top five
  for `docs`, and stays second for `publisher`. Tuned on the round-three dry run: every
  kind but publisher defers authorship, which scores per-page bylines only a publisher is
  expected to carry; `docs` and `spec` lead with llms.txt; and a deferred finding falls
  two levels, because at one it kept winning its band on an impact the kind mismatch
  inflates. On the real sites, authorship now ranks fifth on plausible, twelfth on
  adafruit and thirteenth on MDN, and stays on top for the two publishers. The eval harness orders each site for
  its stated kind and shows the practitioner the same top three the report does.
- **The plugin spike, run.** Installed from a clean config with the `claude plugin`
  CLI rather than left for a person: the marketplace clones over HTTPS, installs, and
  registers nine skills at about 659 always-on tokens a session. It also found that
  `/plugin update` compares `version` and nothing else, so a skill fix reaches
  installed users only at a release; that a `github` plugin source clones over SSH
  with no HTTPS fallback; and that a `url` source can pin an exact tag or commit. The
  skill lint now rejects a `github` source and requires a pinned `ref` to be this
  version's tag, and `RELEASING.md` says to pin the marketplace after the first
  publish. Recorded in the PRD's M0 table.
- **Site-kind guidance for the audit skill** (`skills/audit/sections/site-kind.md`).
  Both eval rounds said the same thing: the tool has no notion of what a site is
  *for*, and applied a publisher's checklist to a specification and then to a
  reference site. The numbers were right; the ordering of the advice was not. The
  skill now infers the kind from evidence it already receives — declared types, URL
  shapes, whether pages are dated — states what it concluded so the reader can
  disagree, and reorders the advice. It never changes a number, and never re-ranks
  around a blocker.
- **The frozen schema is now checked against every golden**, not only against runs
  that went well. The goldens are where the awkward states live - a refused start
  URL, a PARTIAL crawl, an `ok: false` envelope - and those are what a caller hits
  on the day something is wrong.
- **Two goldens covering states nothing was watching**: a PARTIAL run (`audit-bot-block`
  — refused start URL, sitemap still yields pages, two blockers competing for the
  lead) and the `ok: false` error envelope (`error-bad-scheme`). Twelve goldens
  existed and every one of them was a successful run.

### Fixed — from the second practitioner eval

Round two ran five sites of *different shapes* — SaaS, publisher, ecommerce,
non-profit, reference — because round one's own finding was that five technical
sites tell you nothing about whether the tool generalises. It found two defects,
one of them serious.

- **The normalizer discarded most of a page whenever the page had several
  `<article>` elements.** The content root took the first one. On eff.org — no
  `<main>`, thirteen article teasers — that was fifty characters of a single card.
  The site was scored on 100 characters, discovered one link instead of
  eighty-eight, crawled two pages instead of eight, and was reported as 32/100
  *Poor*. It is 56/100 *Fair* on eight pages now, and MDN moved 47 to 57 for the
  same reason. `<article>` is the content root only when the page has exactly one.
  **`normalizer_version` is now 2**, so every affected evidence hash moves, by design.
- **A blocking finding affecting one page led the whole report.** MDN had a single
  page of eight carrying a `noindex`, worth 0.38 composite points, ranked first,
  because blocking findings were exempt from the page-level severity cap. A blocker
  on the site still leads; a blocker on one page is a page to go and look at. The
  cap and the flag now live in one method so they cannot disagree.

Neither round counts toward the 1.0 gate: both changed the tool, and a round that
changes the tool tested a different tool than the one it finished with. The protocol
now says so.

### Changed — from the first practitioner eval

The eval was run against five real sites. It found four defects that the test
suite could not, because they are about whether the advice is *right*, not whether
the code works.

- **Findings are ranked by what they are worth to the composite, not by category
  points.** Thirty points of schema (category weight 10) outranked twenty-five of
  citability (weight 25) while being worth 3.0 against 6.25 — the ranking was
  backwards across categories. Findings now carry `impact` on the 0-100 scale.
- **Site findings come from the site-level signal.** A single bad page used to
  produce a site-level finding at full severity: llmstxt.org scored 22.16/25 across
  the site on `self_containment` — healthy — and one page still made it the number
  one recommendation, marked critical. Page-level outliers are still reported, with
  their pages named, but capped at medium unless they block.
- **Blocking findings are ordered ahead of the arithmetic**, declared in
  `data/findings.json` rather than inferred from severity, because prose on a page
  no crawler can fetch recovers nothing.
- **`content.expertise` was retitled** *Authorship is not machine-readable*. It
  previously said nothing on the page identified the author, on pages that name
  their author in prose.
- **The report says what the score measures, on page one.** Previously only in the
  appendix. This is what made the sqlite.org verdict indefensible: 44/100 *Weak*,
  with twenty of the fifty-six missing points coming from absent metadata alone,
  on a site whose documentation is among the most-cited technical writing there is.

One question was deliberately **not** settled: whether a cheap medium-severity win
should outrank an expensive high-severity one. Ordering by value-per-effort was
tried and put *add a modified date* first on five sites out of five. That is a taste
call about what an audit is for, and it belongs to the practitioner rather than to
whoever last edited the sort.

### Added

- **A published envelope JSON Schema**, shipped inside the package so a consumer
  validates against the version they installed rather than against `main`.
  `additionalProperties: false` at the top level is the freeze: a new top-level key
  fails validation, which makes adding one a deliberate edit with a `schema_version`
  decision attached.
- **Every command's output validated against it in CI**, including a failing run.
  Verified by injecting an unfrozen key into `doctor` and confirming the build breaks
  with a message naming it.
- **Golden coverage for all eleven commands**, up from four. `doctor` gets shape
  coverage rather than a golden — it reports on the machine it runs on, so its values
  are not comparable between two of them — and a test asserts no command is left with
  neither.
- **Troubleshooting prose for every error code**, asserted rather than curated, and a
  quickstart that walks the whole workflow with a test that every command appears in it.

### Fixed

- **A capped crawl reached a different set of pages on a different machine.** Links
  were enqueued the moment a page returned, so a fast branch went deeper before a slow
  branch answered at all, and `--max-pages` then decided *which* pages by completion
  order. `compare` would report pages as added and removed on a site where nothing had
  changed. The crawl is now level-synchronous breadth-first: a whole level is awaited,
  its discoveries are sorted, and only then does the next level start. A crawl is
  rate-limited rather than latency-limited, so waiting out a level costs almost
  nothing, and a test forces the race with staggered response delays rather than
  hoping for it.
- `evidence.pages_failed` is sorted. The order pages happened to fail is a property of
  the race, not of the site.

### Changed

- **The agency kit (M4) is closed at its gate and deferred, not deleted.** The gate
  asked for concrete demand and there is none, because nothing is published yet. No
  Flask, `rich` or `portalocker` dependency ships. The design in the project document
  stands for whenever the first real request arrives.
- Goldens scrub absolute paths and run-dependent values, so they are stable across
  machines rather than passing by accident on one.
- The schema fixture is module-scoped: the same coverage in 1.6s instead of 14s, which
  is about twelve seconds back on each of six CI matrix cells.

### Notes

**1.0.0 is blocked on one thing, and it is not code.** The machinery for the schema
freeze is here; 1.0.0 is the promise. The gate is two consecutive practitioner evals
where an outside reviewer would send four of five reports unedited. See
[tests/evals/README.md](tests/evals/README.md).

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

[Unreleased]: https://github.com/seo-skills/geo-audit-skill/compare/v0.4.0...HEAD
[0.4.0]: https://github.com/seo-skills/geo-audit-skill/releases/tag/v0.4.0
[0.3.0]: https://github.com/seo-skills/geo-audit-skill/releases/tag/v0.3.0
[0.2.0]: https://github.com/seo-skills/geo-audit-skill/releases/tag/v0.2.0
[0.1.0]: https://github.com/seo-skills/geo-audit-skill/releases/tag/v0.1.0
