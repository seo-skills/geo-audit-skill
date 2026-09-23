# Changelog

All notable changes to this project are documented here.

The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and this
project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Fixed

- **A comparison refuses a normalizer change, as it already refuses the other two.**
  `comparable` collected `normalizer_version` and compared `scoring_version` and
  `data_version` only. The normalizer decides what the scorer is allowed to see, so
  changing it moves a score with the formula and the weights standing still: version 3
  stopped reading a promo banner as the page and took one site from 42 to 61, and
  `geo compare` would have reported that as the site gaining nineteen points.
- **A page with no structured data is told once, not five times.** `findings.json` has
  carried a `consequences` rule since the feature shipped - a cause at its floor
  suppresses the findings that merely restate it - and `findings_for` applies it to the
  signals it is handed. The page-level pass handed it one signal at a time, so there was
  no cause to suppress from and every consequence came back. It only showed on a site
  whose pages disagree: presence averaging 28.8 over fifty pages while the posts carried
  none. Suppression is now decided per page, where the cause is measured. The window is
  narrower than it first looked: a consequence the site earns is still reported site-wide
  with its offenders listed, and that path was always right. What was wrong is the
  page-level pass, which fires for a signal the site is *not* reported for - so the fix
  shows on a site whose structured data is healthy on average and absent on a handful of
  pages, which is the case the regression test builds.
- **The missing-run error names the runs that exist.** It said "`geo audit --list` shows
  what is recorded"; there is no such flag, and the parser answers it with
  `unrecognized arguments` and exit 2 - a worse dead end than the error it explained.
  It now lists the most recent recorded run ids, or names the file that is empty.
- **A site-level finding says what is missing, not that everything is.** Four findings
  carry a second wording for the half-present case, chosen from the `present` list the
  scorer records. Rolling fifty pages into one signal kept only the details every page
  agreed on, so `present` was dropped the moment one page differed, and an audit of
  userguiding.com - Organization name, url and sameAs on 48 of 50 pages - read "No
  machine-readable publisher identity". Aggregation now carries what the typical page
  had, so authorship, attribution, publisher identity and Article markup are reported as
  incomplete when they are incomplete.
- **`--verbose` does what its help says.** It was declared once and read nowhere: every
  command accepted it, the docs promised "more progress on stderr" for all eleven, and it
  changed nothing. It now asks for the line per page that the single rewritten crawl line
  replaced, which is where a run has more to say. `--quiet` still wins.
- **A number no run could honour is a usage error.** `--timeout 0` reached the HTTP
  layer, raised ValueError and came back as `GEO_E_INTERNAL` - exit 1, "this is a bug,
  please open an issue" - for a typo; `--max-bytes -1` was reported as the page being too
  large; and a negative rate, a negative page count or `--concurrency 0` were taken as
  given. Each numeric flag now states what it accepts and refuses the rest with
  `GEO_E_BAD_ARGS`, naming the flag. `--rate 0` still removes the rate limit.
- **`--config` sets the numeric flags it names.** A config file saying
  `{"max_pages": 2}` was accepted and ignored: the crawl read fifty. argparse had
  already filled its own default, so the "only when nobody set it" test in
  `_apply_config` was never true for a numeric flag, and only the booleans came
  through. The numeric defaults are now filled after the config is read, so a config
  sets what the command line does not. `max_redirects` named no flag and reached no
  code, so it is refused by name instead of read and dropped.

- **The browser-extra install hint works.** `geo doctor` and the report's PDF-unavailable
  message said `uv tool install 'seomator-geo-audit[browser]' && playwright install
  chromium`, and the second half failed with command not found: `uv tool` puts only the
  tool's own commands on PATH. The hint now adds `--with-executables-from playwright`.
  Doctor's warning for a `playwright` package without its command now runs it through
  the interpreter that imports it (`<python> -m playwright install chromium`) instead
  of naming the command it had just found missing.
- **A fix's gain is printed on the scale of the score above it.** `geo audit` printed each
  fix's category points as "+9 points available" under "GEO score 91/100", so the fixes
  shown for one site claimed 26.7 points on a site that could gain nine. It now prints
  "up to +1.8 overall", as the HTML report does; `geo score`, which has no overall gain
  per fix, says whose points they are ("+10.3 citability points available").
- **A site's verdict is worded for its pages.** An audit's tier meaning came straight
  from the per-page wording, so a fifty-page report led with "AI engines can lift
  answers from this page". Audits of more than one page now say "from these pages";
  the data, and so `data_version`, are unchanged.
- **A capped crawl says how much of the site it read.** An audit that stopped at its
  page limit presented the number for those pages as the site's: seomator.com's sitemap
  lists 309 URLs, and neither the terminal nor the client report said that 50 were read.
  Both now say "The crawl stopped at its 50-page limit after finding 310 URLs, so the
  score covers 50 of them." The terminal adds how to raise the limit.
- **`geo scan --site` suggests a next command about that site.** It ended with
  `Next: geo scan "<brand>" --site https://example.com` whatever site was named, so the
  suggestion scanned someone else's domain. With a site it now suggests
  `geo audit <site> --brand "<brand>"`, which folds brand presence into that site's score.
- **An audit's progress is four lines, not fifty-one.** It wrote `[1/1] audit <url>`, then
  a `[2/4] Crawling` line for every page, and never a step 3 or 4 - on a terminal, in
  logs, and in the output the audit skill reads back. On a terminal the page count now
  rewrites one line in place; elsewhere only the final count is written; and the steps
  run `[1/4]` to `[4/4]` (crawling, scoring, recording). `geo crawl` numbers its own two.

## [1.0.0] - 2026-09-22

Nothing new is built for 1.0. It is the promise the work since 0.4.0 was built to keep,
released on the maintainer's approval of round four's reports after a full review of the
repository.

### The promise

- **The envelope is frozen at `schema_version` 1.** Fields are added freely; a field is
  removed or renamed only under a new schema version, announced two releases ahead.
  Every command's output validates against the shipped JSON Schema in CI.
- **Numbers carry their provenance.** `scoring_version`, `data_version` and
  `normalizer_version` travel in every envelope, record and report, and `compare`
  refuses a pair whose difference would measure the tool rather than the site. From 1.0,
  every data change bumps `data_version`.
- **Semantic versioning** for the package and the plugin together, which release on one
  version line.

### Fixed

- Documentation found stale in the pre-release review: the README listed six skills
  where nine ship and gave a plugin install form that was never verified; SECURITY.md
  and the evidence doc said no page HTML is written to disk, untrue since 0.5.0; and
  SECURITY.md undercounted the runtime dependencies.
- The changelog no longer links 0.1.0 to 0.3.0 to tags that were never made.

### Changed

- The practitioner eval is the bar reports are held to, no longer described as the 1.0
  gate; the form says so. PyPI lists the package as Production/Stable.

## [0.8.0] - 2026-09-22

### Fixed

- **Reports rendered without most of their stylesheet.** The page template
  HTML-escaped the stylesheet, and a browser decodes no entities inside `<style>`, so
  every rule holding a quote or a `>` was dropped: the font (reports showed in Times),
  the bar fills (every bar was empty), the narrow-screen table labels and the print
  rule for links among them. Every report through 0.7.0 was affected. The stylesheet
  now enters the page as trusted markup, and is refused if it could ever end its own
  `<style>` element.
- The operator copy labelled not-applicable signals "not measured".

### Changed

- **The report is redesigned.** The score sits in a card over the masthead, with the
  tier as a coloured badge and a meter; each fix is a card with a severity stripe, a
  severity badge and chips for effort, pages and gain, its evidence in a panel and its
  pages as paths rather than full URLs; the plan is a panel per horizon; bars are
  coloured by tier and line up; crawler access reads as Allowed and Blocked badges;
  not-measured and not-applicable rows are set quietly apart. In print, cards are
  never split across pages. Colour still rides with a word everywhere.

## [0.7.0] - 2026-09-21

### Changed

- **Extractability scores evidence that content needs JavaScript, not length**
  (`scoring_version` 3.0). A page under 1,200 characters was capped as if gated, and
  `citability.extractability` being a blocker put *Little usable content is present in
  the HTML the crawler receives* - with the advice to server-render - first in the
  eval's reports for Adafruit and EFF, on product and about pages that are simply
  short. Rendered in a browser, none of the five pages named gained a single
  character. The signal now scores full marks unless a page shows it is gated: an
  empty app mount, or a JavaScript notice on a page serving too little to have its
  content anyway, which also stops template notices on server-rendered pages counting.
  How much a page says stays with `content.depth`. The detail key
  `capped_thin_or_js_gated` is now `js_gated`. A major scoring bump: composites move.

## [0.6.0] - 2026-09-21

### Changed

- **Authorship, attribution and Article markup are scored on articles only**
  (`scoring_version` 2.0). A home page, an index of the pages beneath it, or a page
  that declares itself a product, an app or a profile has no byline to find, and
  scoring it at zero put home pages and calculators first in every practitioner
  eval's authorship finding. On those pages the three signals are `null` with a
  `skipped_reason` of `not applicable: articles only`, and reports say *not
  applicable*, not *not measured*; on a site where no audited page is an article they
  leave the completeness count as well as the composite. Any other page is presumed an
  article, so no article is lost: sampled on 79 pages from eight real sites, the rule
  kept all 31 articles and excluded 27 of the 48 other pages. Rescoring those eight
  sites from their stored pages moved composites by 0 to +4 points, and a shop's
  authorship finding went away. A major scoring bump, so `compare` refuses to set a new
  run against an older one and report the rule change as the site moving.
- **The README and the PyPI page point to SEOmator.** The package names SEOmator as
  its author and links seomator.com, where the product offers more features, agentic
  ones included.

## [0.5.0] - 2026-09-21

### Added

- **Audits keep the pages they read**, lifting the PRD's no-pages-on-disk rule at the
  maintainer's decision. Each page body is gzipped into `projects/<slug>/pages/`, stored
  once under the SHA-256 of its bytes - an unchanged page costs nothing on a re-audit -
  with robots.txt and llms.txt beside it. The record names them by hash; it never
  contains them, so sharing `audits.jsonl` shares no one's pages, and nothing is ever
  printed. `geo prune` deletes a page once no kept run names it and reports how many.
  Pages have their own
  budget, 100 MB a project (`max_page_bytes`): storing a page once bounds nothing for a
  site whose pages change every run, and a measured page ran to 62 KB gzipped. Past the
  budget the oldest runs lose their pages first and keep their records, which then
  rescore from the recorded ratios; a run keeps all its pages or none. The store is
  safe beside other runs: no page is deleted within a day of being written or reused
  (`page_grace_hours`), because an audit stores its pages before it appends the record
  that names them; a page is read back only if its bytes still match its hash, so a
  damaged copy counts as missing rather than crashing a rescore; and the store's
  `.gitignore` keeps a `GEO_HOME` inside a git repository from committing client pages.
- **`--rescore` recomputes from the stored pages.** It reads back the pages an audit
  read and runs extraction, every signal and every finding again with today's code, so
  a rule changed since the audit is re-applied to the exact bytes rather than replaying
  what the audit concluded - llms.txt included, which is judged again from the stored
  file. `rescore.from` says what it used: `pages`, or `ratios` when a page was pruned or
  damaged, or `record` for runs older than both.

### Changed

- **The plugin marketplace serves the `v0.4.0` tag instead of `main`.** Every plugin
  install is now exactly a release, so skills can never run ahead of the CLI on PyPI.
  It is an HTTPS `url` source; the skill lint requires its `ref` to match `VERSION`.
- **The skills expect the 0.5 CLI.** Skills and CLI release on one version line, so after
  a plugin update the skills ask a 0.4 CLI to run `uv tool upgrade seomator-geo-audit`.

### Fixed

- **`geo prune` could erase an audit that finished while it ran.** It rewrites
  `audits.jsonl` from what it read, so a record appended in between was lost. It now
  re-checks the file's size before the rewrite and leaves a file that grew alone: the
  project is reported `skipped`, and the next prune plans with that record in view.

## [0.4.0] - 2026-09-21

No new features. The envelope contract stops being a promise in prose and becomes
something the build checks, and two rounds of practitioner eval are folded in.

**The first release published to PyPI.** `uv tool install seomator-geo-audit` works, so
every install-from-source fallback - README, quickstart, troubleshooting, the nine skill
preflights and `geo doctor` - is gone, and the tests that required them now reject them.

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

## 0.3.0 - 2026-09-20

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

## 0.2.0 - 2026-09-20

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

## 0.1.0 - 2026-09-20

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

[Unreleased]: https://github.com/seo-skills/geo-audit-skill/compare/v1.0.0...HEAD
[1.0.0]: https://github.com/seo-skills/geo-audit-skill/releases/tag/v1.0.0
[0.8.0]: https://github.com/seo-skills/geo-audit-skill/releases/tag/v0.8.0
[0.7.0]: https://github.com/seo-skills/geo-audit-skill/releases/tag/v0.7.0
[0.6.0]: https://github.com/seo-skills/geo-audit-skill/releases/tag/v0.6.0
[0.5.0]: https://github.com/seo-skills/geo-audit-skill/releases/tag/v0.5.0
[0.4.0]: https://github.com/seo-skills/geo-audit-skill/releases/tag/v0.4.0
