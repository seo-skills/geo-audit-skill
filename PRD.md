# PRD: geo-audit-skill

| | |
|---|---|
| **Project** | `geo-audit-skill` — open-source GEO (Generative Engine Optimization) + SEO audit toolkit for Claude Code |
| **Repo** | `github.com/seo-skills/geo-audit-skill` (new, public; name verified free 2026-09-20) |
| **License** | MIT (default — see D4) |
| **Status** | Canonical, consolidated. Satisfies the R-E1 hard gate. |
| **Supersedes** | `PRD-geo-skill-rewrite.md` — now the *review record only* (4 gstack review passes, 63 accepted requirements). Where the two disagree, this file wins. §9 maps every one of the 63 requirements to its disposition here. |
| **Derived from** | `zubair-trabzada/geo-seo-claude` (MIT, © 2026 Zubair Trabzada), referred to below as **upstream**. Reuse of upstream's structure and prompts is covered by a direct agreement between the maintainer and upstream's author (D1). All `file:line` citations in §1 point at upstream @ `4d3da26`. |

---

## 0. Decisions for the maintainer

This PRD is written under the **recommended default** for each. Every default is cheap to reverse before M1; the cost of reversing is stated.

| # | Decision | Default used in this PRD | If you choose otherwise |
|---|---|---|---|
| **D1** | How does the new repo relate to upstream legally? | **Resolved 2026-09-20: derivative, by written agreement.** The maintainer confirmed the agreement with upstream's author (a) covers the Python scripts as well as structure and prompts, (b) waives attribution and/or permits relicensing, and (c) is in writing. Porting is unrestricted; clean-room is not needed. Standalone repo, not a GitHub fork (forks are excluded from default code search and carry a permanent "forked from" banner). | Nothing left to decide here. One check at M0: (b) was asked as a compound question, so read the written text before finalizing `LICENSE` — *waiving the notice* and *permitting a different license* are separate grants, and D4 depends on which you have. |
| **D2** | How do users install the skills? | **Claude Code plugin** (`/plugin marketplace add seo-skills/geo-audit-skill` → `/plugin install geo`). Skills are namespaced `/geo:audit`, `/geo:citability`, … The CLI installs separately from PyPI. | Keep shell installers: R-E8 (copy + hash manifest, ownership-gated) and R-X10 (non-interactive flags, Windows parity job) return exactly as written in the review record, plus a router skill. |
| **D3** | Is the agency kit (CRM, web UI, proposals) part of this project? | **Resolved 2026-09-20 at the gate: closed.** The gate asked for concrete demand - an issue from a non-maintainer, or the maintainer's own agency use - and at 0.3.0 there is neither, because nothing is published yet. §3.11 and M4 are deferred, not deleted: no Flask, `rich` or `portalocker` dependency ships, and the section stands as a design should the first real request arrive. | Reopen it when someone asks. The import mapping, the single status enum and the locking design in §3.11 are still the plan; only the decision to build now was made. |
| **D4** | License and copyright line | **Decided: MIT, `© 2026 SEOmator`** (see `LICENSE`). The upstream copyright line is no longer required (D1). The optional README credit line was not included, at the maintainer's instruction. | A different license (e.g. Apache-2.0 for its patent grant) is possible only if the agreement permits relicensing, not merely notice removal. Decide at M0: changing license is trivial before the first outside contribution and needs every contributor's consent after it. |

---

## 1. Problem statement

Upstream works as a demo but fails as infrastructure. An audit of the repo found:

1. **Prompt-driven orchestration over dead code.** Only 2 of 21 prompt files invoke an analysis script at all (`skills/geo-schema/SKILL.md:31`, `agents/geo-schema.md:19`, both `fetch_page.py`). Everything else tells Claude to WebFetch/curl and judge. `citability_scorer.py`, `brand_scanner.py` and `llmstxt_generator.py` are effectively dead, and scores are non-deterministic and unreproducible.
2. **Massive duplication.** Each of the 5 agents restates its same-named skill (~1,600 near-copied lines, already drifting: 28 vs 69 headings in geo-technical). Scoring weights appear in 3+ places. `DEFAULT_HEADERS` lives in 3 scripts; block extraction is duplicated between `fetch_page.py` and `citability_scorer.py`; CRM tier logic between `crm_dashboard.py` and `webapp/app.py`.
3. **Install-time mutation.** `install.sh:262-295` sed-patches shebangs and every markdown file after copying, so the shipped artifact differs from the tested one. `install-win.sh` skips the venv and the patching, so Windows runs a different, unpinned tool.
4. **No versioning.** No VERSION, no manifest, no changelog; `geo-update` blindly `cp -r`s over the install.
5. **Platform coupling.** PDF hard-requires macOS Chrome at a fixed path plus pandoc. Playwright is a required dependency that is only optionally installed.
6. **State sprawl.** Three state locations; no schema for `prospects.json`; the skill writes `lead/qualified/proposal/won/lost` (`skills/geo-prospect/SKILL.md:126`) while both readers expect `lead/audit/proposal/active/churned/lost` (`crm_dashboard.py:274`, `webapp/app.py:88`) — the CLI and webapp cannot render prospects the skill creates. No concurrency guard on JSON read-modify-write.
7. **Testing vacuum.** 275 lines of tests (one file, one heuristic) against ~6,800 lines of prompts and ~1,950 lines of Python. The only CI workflow updates a star-history chart.
8. **Half-integrated features.** `white-label/` is imported by nothing. `hooks/` is referenced by install.sh, geo-update and docs but does not exist. `brand_scanner.py` is mostly stub instructions. Unused deps (Pillow, validators). Docs cite a ghost `generate_pdf_report.py`, state the skill count as 13/14/15, and contradict `citability_scorer.py:304`.
9. **Marketing copy in executable prompts.** `geo/SKILL.md:46-59` and `brand_scanner.py` hardcode market statistics into prompts and output JSON, guaranteeing staleness.

### 1.1 Why a rewrite and not incremental repair

Three alternatives were weighed: (A) full rewrite, (B) three incremental PRs (wire scripts → dedupe → packaging), (C) fix four bugs (enum, ghost script, hooks path, embedded stats). **A was chosen** for one forcing reason: defect 3 means the tested artifact is not the shipped artifact, so *no partial fix can be verified* until packaging is replaced — and packaging, duplication and orchestration all touch the same files. B degenerates into A with worse sequencing; C leaves the architecture intact. A second reason arrived with the rename: a new repo under a new maintainer cannot ship as patches to someone else's tree.

### 1.2 Relationship to upstream and positioning

<!-- TODO(maintainer): 5–8 lines only you can write. See "Your turn" in the hand-off note.
     The provisional text below keeps the PRD usable until then. -->

*Provisional:* geo-audit-skill is an independent, MIT-licensed project built on geo-seo-claude's structure and prompts, **with the agreement of its author**, who continues to maintain upstream (last upstream commit 2026-09-18). It is not a GitHub fork and does not track upstream. It differs in one claim: **every number in a report is reproducible from recorded evidence.** Upstream optimizes for breadth of advice; this project optimizes for audits you can defend to a client. Upstream is credited in README and LICENSE. We do not install over, migrate in place, or uninstall upstream; the two coexist on one machine (§3.1).

---

## 2. Goals and non-goals

**Goals**

- **G1 — Scores are a pure function of recorded evidence.** `score(snapshot, data_version, scoring_version)` always returns the same bytes. The LLM narrates and prioritizes; it never produces a number that is summed into a score.
- **G2 — One source of truth per concern.** No agent/skill twins, no duplicated weights, no duplicated helpers.
- **G3 — The tested artifact is the shipped artifact.** Nothing is modified at install time.
- **G4 — macOS, Linux, Windows parity**, or an explicit documented skip per feature.
- **G5 — Audits are evidence-bound.** Every report states what it was computed from and whether that evidence is still current.
- **G6 — A real test and CI story.**
- **G7 — A credible open-source project:** license clarity, contributor path, security policy, fixtures we have the right to redistribute.

**Non-goals**

- Multi-host support (Codex, Cursor). Claude Code only.
- Telemetry, consent flows, update checks, cross-machine sync.
- A render farm. Playwright stays optional and local.
- In-place upgrade from upstream. There is no install base in this repo to upgrade.
- Live AI-citation measurement (ChatGPT/Perplexity answer share). Deferred, §8 — but see §6: it is the most likely post-1.0 direction.

---

## 3. Architecture

```
Claude Code ── plugin "geo" ── 9 skills (+2 agency, M4)
     │  thin prompts · narrate sequentially · never fan out subagents
     ▼  JSON envelope only (never raw page text)
geo CLI  (PyPI: seomator-geo-audit · import: geo_audit · console script: geo)
  fetch · crawl · audit · score · scan · llmstxt · validate · compare · report · doctor · prune
  [M4: crm · serve · import]
     │
     ├─ lib/    http, extract, robots, headers        (each helper exists once)
     ├─ data/   crawler UA lists, thresholds, weights, tiers   (package data, carries data_version)
     ├─ assets/ JSON-LD templates, report templates            (package data)
     └─ state   → $GEO_HOME (default ~/.geo, 0700)
                  projects/<slug>/audits.jsonl · projects/<slug>/reports/ · logs/last-run.log
```

### 3.0 Patterns adopted from gstack, and the failure each prevents here

We copy four patterns and nothing else (§7). **Deterministic gates in code, prose only narrates** — prevents defect 1, where scores vary run to run because a prompt did the arithmetic. **Evidence binding** — prevents handing a client a report computed from a page that has since changed, with no way to tell. **Append-only JSONL history** — prevents defect 6's read-modify-write corruption for the file written most often. **Lint-enforced skill contracts** — prevents defect 2's drift, where two copies of one document silently diverged to 28 vs 69 headings. gstack's template *generator* is not adopted: its forcing function was multi-host output, which is a non-goal.

*Amended 2026-09-21, when pages came onto disk (§3.5 Retention).* Three storage rules join them - rules, not machinery. **A rewrite never erases a concurrent append:** gstack re-checks a log's size before compacting it, and `geo prune` now does the same before rewriting `audits.jsonl`, which prevents erasing an audit that finished while prune ran. **Nothing young is collected** (git's rule for loose objects): no stored page is deleted within a day of being written or reused, which prevents deleting the pages of an audit whose record is not yet written. **Content-addressed reads verify:** a stored page is read back only if its bytes still hash to its name, which prevents scoring a damaged copy. Still not adopted, per §7: gstack's JSONL merge driver (cross-machine sync), its event-sourced stores with compaction, and lock files.

### 3.1 Repo layout and distribution

```
.claude-plugin/plugin.json        name "geo", version == VERSION
.claude-plugin/marketplace.json
skills/<name>/SKILL.md            + skills/<name>/sections/*.md loaded on demand
skills/_shared/response-contract.md
src/geo_audit/                    the CLI (pyproject.toml, src layout)
tests/  docs/  VERSION  CHANGELOG.md  LICENSE  README.md  CONTRIBUTING.md  SECURITY.md
```

- **Skills** install through the Claude Code plugin manager (D2). This deletes `install.sh`, `install-win.sh`, `uninstall.sh`, shebang patching, ownership manifests, retired-skill pruning and the Windows-installer parity problem in one move. It also deletes the router skill: `/geo:audit` *is* the routing.
- **Coexistence.** Upstream installs un-namespaced skills into `~/.claude/skills/geo*`. Plugin skills are namespaced, so both can be installed at once. We never touch upstream's files.
- **CLI** installs with `uv tool install seomator-geo-audit` (or `pipx install seomator-geo-audit`). Python ≥ 3.11. PyPI check on 2026-09-20: `seomator-geo-audit` free, `geo-cli` free, `geo-audit` **taken**. Console script is `geo`; `geo doctor` warns if `geo` resolves to more than one binary on PATH.
- **Playwright is an optional extra** (`seomator-geo-audit[browser]`), used for JS-render diffing and PDF. Without it the affected signals are null (§3.4), never silently different.
- Skills reference no file paths. Templates and schemas are package data reached through CLI commands — this is what makes G3 hold by construction.
- **Updates:** `/plugin update` and `uv tool upgrade seomator-geo-audit`. There is no `self-update` command and no `geo-update` skill. `/plugin update` compares `version` only (M0 spike), so a skill change reaches installed users when `VERSION` moves, which is at release.
- **M0 spike (gate for D2):** publish a one-skill plugin that runs `geo --version`; confirm install from a GitHub marketplace, namespace, update behavior, and Windows. If the spike fails, fall back per D2.

### 3.2 CLI contract

**Commands** (one grammar: bare verbs). Core: `fetch`, `crawl`, `audit`, `score`, `scan`, `llmstxt`, `validate`, `compare`, `report`, `doctor`, `prune`. Agency (M4): `crm`, `serve`, `import`.

**Global flags:** `--json`, `--out`, `--config`, `--no-input`, `--quiet` / `--verbose`, `--allow-private`, `--fail-on-partial`. `serve` adds `--port` (default 5050). `NO_COLOR` respected.

**Output mode:** JSON when stdout is not a TTY or `--json` is passed; human rendering otherwise. Progress and logs go to **stderr only**, always.

**Crawl defaults** — 50 pages, 30 s timeout, 1 req/s **global** (not per worker), 5 concurrent, robots respected — are part of the versioned contract and recorded in every audit record.

**Envelope** (frozen at the M1 gate, before any porting):

```json
{
  "schema_version": 1, "command": "audit", "ok": true,
  "cli_version": "0.2.0", "scoring_version": "1.0", "data_version": "2026.09", "normalizer_version": 1,
  "run_id": "01J8…", "observed_at": "2026-09-20T18:00:00Z",
  "evidence": { "stamp": "PARTIAL", "pages_ok": 41,
                "pages_failed": [ { "url": "…", "reason": "bot_blocked" } ] },
  "completeness": { "computed": 31, "total": 36, "missing": ["render.js_diff"] },
  "scores": { "composite": 62, "tier": "fair", "categories": { "citability": 58 } },
  "signals":  [ { "id": "citability.self_containment", "class": "heuristic", "value": 17, "max": 25, "page": "…" } ],
  "findings": [ { "id": "…", "severity": "critical", "effort": "low", "priority": 1,
                  "pages": ["…"], "title": "…", "remediation": "…", "excerpt": "…(≤280 chars, delimiter-escaped)" } ],
  "error": null
}
```

On failure: `"ok": false, "scores": null`, and
`"error": { "code": "GEO_E_TIMEOUT", "message": "<human sentence>", "hint": "<what to do>", "docs": "<url|null>", "log": "~/.geo/logs/last-run.log" }`.
Every `GEO_E_*` code has a hint (contract-tested). `schema_version` is an **output field only**; there is no request flag. Policy: additive changes do not bump it; removals and renames bump it and are announced two releases ahead.

**Exit codes** (the only table):

| Code | Meaning |
|---|---|
| 0 | OK — *including PARTIAL audits* |
| 1 | Internal error |
| 2 | Usage error |
| 3 | Network failure on the **start URL** |
| 4 | State error (state newer than CLI, unreadable `GEO_HOME`) |
| 5 | `--fail-on-partial` was passed and the audit is PARTIAL |

Bot-blocked (403/challenge) and robots-disallowed pages are **findings** with `severity: critical`, not failures: exiting non-zero would abort exactly the sites that most need a report. PARTIAL is read from `evidence.stamp`, never inferred from the exit code.

**Skill ↔ CLI:** each skill preflights `geo --version` against a required range and stops with the install command if missing or skewed. On `ok: false` the skill relays `error.message` + `error.hint` — never raw JSON, never an invented score.

### 3.3 Fetch and crawl safety

The core loop feeds up to 50 pages of untrusted web content toward an agent that has tool access. This is the project's top security concern.

- **Output boundary (the main defense):** CLI output contains derived signals and length-capped, delimiter-escaped excerpts. It never contains full page text. Contract test on output size and shape per command.
- **Skill boundary:** every skill states that excerpts are data, never instructions.
- **Network guards:** redirect targets and crawl-discovered links to RFC 1918, loopback, link-local, `169.254.169.254` and non-http(s) schemes are always blocked. A private **start URL** is refused unless `--allow-private` is passed — auditing `localhost:3000` or a staging host is a legitimate use. The guard validates the *connected peer address*, not only the pre-resolved name (DNS rebinding). Redirect-chain cap, response-size cap (`GEO_E_TOO_LARGE`), decompression limit, content-type allowlist.
- **Two robots jobs, kept separate:** (a) our own etiquette as the `seomator-geo-audit` UA; (b) the *product feature* that evaluates AI-crawler UAs against the versioned list in `data/`. RFC 9309 edge cases are specified and fixture-tested: 5xx on robots.txt = disallow, redirects, conflicting groups, wildcards.

### 3.4 Scoring

- **Signal inventory** (M1 pre-work, one page, `docs/concepts/signals.md`): every signal is classified **deterministic** (parsed fact), **heuristic** (code with stated weights), **live** (third-party API, carries `observed_at`), or **advisory** (LLM judgment under a fixed rubric). The envelope and the operator report label each signal's class.
- **The composite sums deterministic + heuristic + live signals only.** Advisory output is displayed in its own clearly-labeled section and never enters a number.
- **Purity (G1):** the snapshot holds every scorer input, including live signals as observed - since 2026-09-21 literally: the pages themselves, with robots.txt and llms.txt, in the page store beside `audits.jsonl` (see Retention, §3.5). `geo audit --rescore <run_id>` recomputes from the snapshot with no network. *Reproducibility is claimed for rescoring a snapshot* — not for re-crawling a live site, which can legitimately differ.
- **One pipeline, nullable signals.** A missing capability (no Playwright) nulls specific signals and lowers `completeness`; the report says "computed on 31 of 36 signals". There is no second scoring path.
- **Upstream's scorer is a specification to correct, not to reproduce.** Upstream's six categories and weights (Citability 25 / Brand 20 / Content 20 / Technical 15 / Schema 10 / Platform 10) are the starting point. "Content" and "Platform" are largely LLM-judged upstream; the inventory decides which of their sub-signals are computable (byline, dates, outbound citations, `Person` schema → heuristic) and which become advisory. Every deliberate divergence is recorded in `docs/concepts/score-divergence.md`.
- **Versions:** `scoring_version` (formula), `data_version` (thresholds, UA lists, tiers), `normalizer_version` (extraction). All three appear in every envelope, audit record and report footer. Weights, thresholds and tier boundaries live in `data/`, not in code and not in prose. **Data updates ship as a patch release on PyPI** — that channel is already versioned, checksummed and reversible. Pinning the data means pinning the package.
- `geo compare` refuses to compare runs whose `scoring_version` major or `data_version` differ, or that lack a version. Scores are **not comparable with other tools' scores**; every report says so in its comparability note. (The README does not name upstream, at the maintainer's instruction.)

### 3.5 Evidence model

- **Hash = SHA-256 over the extracted content-block sequence** (the scorer's real inputs) **+ `normalizer_version`.** Golden test: the same fixture with a changed nonce, timestamp and ad slot still hashes identically.
- **ETag / Last-Modified are *not* part of hash identity.** They change on every redeploy even when content is identical, which would flip reports to STALE for nothing — the exact noise block-hashing exists to avoid. They are stored as metadata. *They are not a revalidation shortcut either: one was built on 2026-09-21 and withdrawn the same day. A 304 vouches for a page's bytes, not its headers, and `X-Robots-Tag` and HSTS are scored from headers. A site that drops a `noindex` header from its server config serves the same bytes under the same ETag, so a re-audit that trusted the 304 went on reporting the blocker, on the run made to confirm the fix. The saving went to the audited site, never to the user.*
- **Stamps:** `CURRENT` · `PARTIAL` (failed or changed pages enumerated) · `STALE`.
- **Retention:** the record holds derived signals and capped excerpts. Page bodies are kept too - *the maintainer lifted "no raw HTML on disk" on 2026-09-21* - in a content-addressed store beside the record (`projects/<slug>/pages/<sha256>.html.gz`): never inside `audits.jsonl`, so sharing an audit shares no client's pages; never printed, so the §3.3 output boundary is unchanged; stored once per content, and deleted by `geo prune` when no kept run names them - or when they fall outside the page budget (`max_page_bytes`, 100 MB a project), oldest runs first, since a page that changes on every run is stored every run. The rule had no stated reason; its three likely ones - injection, client data, disk growth - are each met by that design rather than by a ban. robots.txt and llms.txt are kept beside the pages, so a rescore judges both by today's rules. The store is safe beside other runs by the three §3.0 storage rules - prune leaves a history that grew while it ran alone, spares pages younger than `page_grace_hours` (24), and reads a page back only if its bytes still match its name - and it carries a `.gitignore`, so a GEO_HOME inside a git repository (a dotfiles repo, say) never commits a client's pages.

### 3.6 State

- `$GEO_HOME` (default `~/.geo`, mode 0700). `projects/<slug>/audits.jsonl` is **history and evidence, not resume state**. A crashed crawl re-runs; it is bounded to minutes.
- Core state is single-writer: one `write()` per JSONL record, atomic tmp-then-rename for everything else. The reader tolerates and discards a torn trailing line. Every record carries `run_id`. `geo prune` applies the size/age rule.
- State carries a schema version. A CLI that finds **newer** state refuses to run (exit 4, state 8 in §3.9) and changes nothing.
- Reports default to `projects/<slug>/reports/<YYYY-MM-DD>-<hash8>.html`; `--out` overrides; nothing is silently overwritten.
- `geo doctor` warns when `GEO_HOME` sits on a sync drive (iCloud, Dropbox).
- Cross-process locking is **not** needed until M4 introduces a multi-writer file (§3.11).

### 3.7 Skills

Nine core skills, thin prompts over the CLI. `agents/` is not carried over.

| Skill | Calls | Absorbs from upstream |
|---|---|---|
| `geo:audit` | `geo audit` | geo (router), geo-audit, all 5 agents |
| `geo:citability` | `geo score` | geo-citability |
| `geo:technical` | `geo audit --only technical` | geo-technical, geo-crawlers |
| `geo:content` | `geo audit --only content` + advisory rubric | geo-content, geo-platform-optimizer |
| `geo:schema` | `geo validate` | geo-schema |
| `geo:llmstxt` | `geo llmstxt` | geo-llmstxt |
| `geo:brand` | `geo scan` | geo-brand-mentions |
| `geo:compare` | `geo compare` | geo-compare |
| `geo:report` | `geo report` | geo-report, geo-report-pdf |
| *M4:* `geo:crm`, `geo:proposal` | `geo crm` | geo-prospect, geo-proposal |

Not carried over: `geo-update` (the plugin manager updates), alias/forwarding skills (no install base to forward).

- **Upstream's prompts are the starting material** (permitted by the D1 agreement), not something to write around. Each upstream skill and its twin agent are merged into one document; methodology checklists move to `sections/*.md` largely intact; what gets *removed* is scoring arithmetic (now in the CLI), market statistics, hardcoded `~/.claude/skills/geo/...` paths, and subagent fan-out instructions.
- **The CLI owns all parallelism.** Skills narrate sequentially and never spawn subagents.
- **Lint, not generation.** A CI lint validates frontmatter, asserts `version:` equals `VERSION`, asserts the skill directory set matches the table above, and asserts each skill's response-contract block is byte-identical to `skills/_shared/response-contract.md` (marker-delimited).
- **Response contract** (every skill): headline result → key numbers → artifact path → one suggested next command.
- **No scoring arithmetic in prose.** Enforced by a machine-readable key manifest: every status key or signal id a skill mentions must be one the CLI emits.
- Long methodology moves to `sections/*.md`, loaded on demand.
- **Sources, not personalities.** Auditor heuristics cite primary sources with URLs (Google Search Central, RFC 9309, schema.org, llmstxt.org). No instincts attributed to named individuals unless quoted with a link — fabricated attribution is a credibility risk an open-source audit tool cannot afford.
- No market statistics in prompts or CLI output. Market context lives in docs with source and date.

### 3.8 Reports

One pipeline: Jinja (autoescape **on**, asserted with an XSS-string fixture) → HTML → optional PDF through Playwright print-to-PDF. Without Playwright: HTML plus the state-3 note.

**Information architecture.** Reader order, not audit-decomposition order.

1. **Page 1 — the answer.** Brand header · site · date · composite score as **number + tier label, always paired** (never color alone) · one sentence on what that tier means · a summary built from the numbers · what is already working · three headline findings · **Top fixes**, ordered by `priority`: fix, gain on the overall score, effort, pages affected, evidence · **the plan** by horizon.
2. Category scores (number + label + bar, weight, contribution to the composite, total row).
3. AI crawler access; category detail, every signal by name.
3a. Findings by category, each with page attribution, evidence and remediation copy.
4. **Advisory analysis** — labeled as LLM judgment, visually distinct, excluded from scores.
5. Appendix: methodology, signal classes, versions.
6. *Operator mode only:* provenance — evidence hashes, per-signal class labels, failed-page list, brand-contrast warnings.

Page 1 carries the arc *where do I stand → what is it costing → what do I do Monday*. STALE and PARTIAL are informational with an inline refresh command, never alarming.

**Two render modes, isolated by construction.** Operator data is assembled in a **separate context object** that the client template never receives — not hidden by a conditional. Golden test: client-mode HTML contains zero operator-only fields and zero data from any other project (the regression class of upstream PR #71).

**Brand tokens** (`brand.json`): default palette when absent; foreground derived from luminance and validated at 4.5:1, falling back to defaults **loudly** (stderr warning + operator-view annotation; yellow-brand test); logo max-height and aspect constraints. Attribution footer "Generated with geo-audit-skill" is on by default and removable in config.

**Reporting parity with the reference (2026-09-21).** The reference's deliverables - its
PDF and its audit report format - were read as a behavioural spec for what a client
report carries. Every detail it *measures* is adopted; details it only *asserts* are
either rebuilt from measurements or left out, because a number the tool cannot trace
to evidence breaks G1 whatever report it appears in.

| The reference shows | Decision | Why |
|---|---|---|
| Executive summary | **Adopt, deterministic** | Two or three sentences built from the scores, the strongest and weakest categories and the largest single gain. Company background stays in the skill's narration. |
| Weighted contribution per category, with a total row | **Adopt** | Shows how each category moves the composite; pure arithmetic on recorded scores. |
| Category scores as bars | **Adopt** | Beside the number and the word, never instead of them. |
| AI crawler access table | **Adopt, richer** | From the robots matrix plus `data/ai_crawlers.json`: operator, what the crawler is for, what blocking it costs, allowed or not. |
| Per-AI-platform readiness scores | **Adapt** | The reference's are model estimates. Reachability per platform is a measured fact, so it is shown through the crawler table, grouped by operator, with no score. |
| Action plan by time horizon | **Adopt, deterministic** | This week / this month / this quarter from each fix's effort, keeping the ranked order, with each fix's gain on the *overall* score from `impact`. |
| Findings with concrete detail | **Adopt, from evidence** | What the scorer measured (the signal's own detail) and the worst passage it found, quoted and escaped, under each finding. |
| Category deep dives | **Adopt, deterministic** | Every signal in the category with a plain name, its score and a bar. The narrative half belongs to the skill. |
| Pages analysed appendix | **Adopt, without titles** | URL, status and how many findings name the page. The reference adds titles; the crawl record carries no page text by design, because the skill reads it and page text is an injection channel. |
| Glossary | **Adopt** | Static terms: GEO, AI Overviews, E-E-A-T, JSON-LD, sameAs, llms.txt, SSR, robots.txt. |
| Effort in hours | **Reject** | Precision the tool does not have; effort stays low/medium/high and the horizon says when. |
| Competitor scores | **Reject** | Not measured. A real comparison means auditing the competitors, which is a separate feature. |

**Layout:** no card mosaic. Readable at 390 px with one intentional breakpoint. Print CSS: page size, margins, running header, page numbers, `break-inside: avoid` on findings. Body contrast ≥ 4.5:1.

### 3.9 Interaction states — literal copy

Eight states. (The review record lists nine; "resume prompt" died when R-E7 dropped crawl resume.)

| # | State | Copy |
|---|---|---|
| 1 | **Loading** (stderr) | `[2/4] Crawling example.com — 12/50 pages, 2 failed` · In chat, once: "Running the audit. It crawls up to 50 pages at one request per second, so expect a few minutes." |
| 2 | **Empty** | No audit: "No audits recorded for example.com yet. Run `geo audit https://example.com` to create the first one." · Zero pages: "The crawl found no scorable pages on example.com. The start URL returned 403. Nothing was scored." · Zero mentions: "No mentions of “Acme” found on Wikipedia, Wikidata, Reddit or YouTube (checked 2026-09-20). This is a result, not an error." · Zero blocks: "No citable content blocks found on this page. Score 0 — reason: no extractable blocks." |
| 3 | **PDF unavailable** | "PDF skipped: the browser component is not installed. HTML report written to <path>. To enable PDF: `uv tool install 'seomator-geo-audit[browser]' && playwright install chromium`" |
| 4 | **Error** | "Couldn't reach example.com: connection timed out after 30 s (GEO_E_TIMEOUT). Check the URL, or try again. Details: ~/.geo/logs/last-run.log" — no score is shown. |
| 5 | **Partial** | "PARTIAL audit: 41 of 50 pages scored. 9 could not be evaluated — 6 blocked by bot protection, 3 timed out (listed below). Scores reflect the 41 pages only." |
| 6 | **Success** | "GEO score 62/100 (Fair) for example.com — 50 pages, evidence CURRENT. Report: <path>. Next: `/geo:report example.com`" |
| 7 | **Stale** | "This report was computed from pages fetched on 2026-09-01. 4 of 50 pages have changed since. Refresh with `geo audit https://example.com`." |
| 8 | **Refuse to run** | "~/.geo was written by seomator-geo-audit 0.5 (state v3); this is 0.3 (state v2). Upgrade with `uv tool upgrade seomator-geo-audit`. Nothing was changed." — never a stack trace. |

*M4 adds:* lock contention — "Another geo process is updating the CRM. Waited 10 s. Try again in a moment; run `geo doctor` if this persists." — and empty CRM — "No prospects yet. Add one with `/geo:crm new <domain>`."

Golden tests assert each string exists.

### 3.10 Brand scan: real checks or nothing

Wikipedia and Wikidata: real API checks. Reddit: public search JSON. YouTube: Data API when a key is configured, otherwise reported as *not checked*. LinkedIn: no API, so it appears in a separate **manual checks** section and is never emitted as a result. Per-platform failures (429, outage) are per-platform error entries, not a command failure. All are `live`-class signals with `observed_at`.

### 3.11 Agency kit — M4, gated (D3)

`geo crm` (rich dashboard in TTY mode, JSON otherwise), `geo serve` (Flask + HTMX, kept), `geo:proposal`, and:

- **One status enum:** `lead / audit / proposal / active / churned / lost`.
- **`geo import`** reads upstream's `~/.geo-prospects/prospects.json` **read-only** and writes `$GEO_HOME/crm/prospects.json` (0600). The source is never modified, so no backup, lock-during-migration or rollback machinery is needed. Mapping is a total function over both upstream dialects: `qualified → lead` (conservative — never advances a pipeline), `won → active`, the rest pass through; `legacy_status` is recorded. `--dry-run`. Fixtures: each dialect, a mixed file, corrupt JSON (refuses with a human message). Upstream's `audits/`, `proposals/`, `reports/` are left where they are.
- **Locking arrives here**, because this is the first multi-writer file: `portalocker`, acquisition timeout, stale-lock recovery by pid + mtime, concurrent-write test on three OSes.
- **`geo serve` hardening:** binds `127.0.0.1` only; per-session token on mutating routes; Host-header allowlist; port conflict suggests an alternate port; HTMX focus-preservation rules.
- Italian strings become English. No i18n.

**Go/no-go gate before M4:** build it if there is a concrete request for it (an issue from a non-maintainer, or your own agency use). Otherwise close M4 and ship 1.0 as an audit tool.

### 3.12 Testing and CI

pytest only. **Fixtures are synthetic pages authored for this repo** and served by a local test HTTP server — checking real third-party HTML into a public MIT repo redistributes other people's copyrighted content. Ten fixture sites cover: SSR, CSR shell, rich schema, no schema, broken schema, bot-block 403, robots edge cases, redirect chains, injection text, oversize response.

Tests required: golden envelope per command (canonicalized: timestamps, `run_id`, ordering) · both TTY and JSON modes · exit code per class · every error code has a hint · SSRF matrix · robots matrix · output-shape cap · nonce-injection hash stability · rescore-twice byte identity · nullable signals + completeness · torn-line reader · prune · state-newer refusal · `GEO_HOME` override · deterministic report path · report section order · label+numeric pairing · XSS escape · **client-mode leak** · yellow-brand contrast warning · compare refusal · skill lint + key manifest · injection fixture (instruction-like page text alters neither state nor report structure). PDF smoke test is Playwright-gated with a loud skip summary.

**CI: three workflows.** `ci.yml` — jobs: test matrix (ubuntu, macos, windows), skill lint, docs freshness, quickstart smoke (runs the literal README block against the fixture server and prints elapsed time; the functional pass is the gate, the time is a reported metric). `secret-scan.yml`. `release.yml` — tag → PyPI via trusted publishing.

**Evals** (`tests/evals/`, recorded per minor release): on 5 real sites, the maintainer and one outside practitioner each answer two questions about the top-3 fixes — *are these the right three?* and *would you send this report unedited?*

### 3.13 Docs and open-source hygiene

- **Docs IA:** quickstart · commands (generated from code, CI-checked) · concepts (signals, evidence, score divergence) · troubleshooting (every exit code and `GEO_E_*` code mapped to a fix; `geo` PATH-collision note). Every command has one runnable example generated from golden fixtures. `docs/concepts/scoring-methodology.md` is hand-written rationale with a **marker region** for generated constants; the freshness check covers the marker region only.
- **README quickstart** is a literal copy-paste block. Documented first success is `geo score <url>` — one page, no crawl, no Playwright, no Claude Code, under 30 seconds.
- **M0 files:** `LICENSE` (per D4), `README.md` (the optional upstream credit line was not included, at the maintainer's instruction; comparability is stated in every report), `CONTRIBUTING.md`, `SECURITY.md` (the §3.3 threat model and a private reporting address), `CHANGELOG.md` (Keep a Changelog), `.gitattributes` for fixtures and generated regions, a fresh `CLAUDE.md`.
- **Not carried over:** upstream's `examples/` (regenerate from the fixture site — upstream's samples have a client-data-leak history, PR #71), `pr-draft-*.md`, the star-history workflow, git history.

### 3.14 Versioning and releases

`VERSION` (semver) is the single source; `plugin.json`, skill frontmatter and `pyproject.toml` must match it (lint). Releases are tagged per milestone with a changelog entry: human summary first, itemized changes second. This project starts at **0.1.0**; it is not "v2" of anything. **1.0.0** freezes envelope `schema_version` under the §3.2 policy.

---

## 4. Milestones

Each milestone ends in a tagged release. Lanes: after M1, M2's CLI work and M3's report work can overlap; skills follow the commands they call.

| | Deliverable | Gate (all must hold) |
|---|---|---|
| **M0 — Bootstrap** *(no product code)* | New repo; the §3.13 M0 files; D2–D4 answered; written agreement re-read against D4 and kept on file (privately is fine); plugin spike (§3.1); §1.2 written. | Spike result recorded in this PRD. Repo public with `LICENSE` matching the agreement's text. |
| **M1 — Walking skeleton → 0.1.0** | *Pre-work:* signal inventory; envelope + error contract frozen. *Then:* `fetch`, `score`, `doctor`; TTY/JSON modes; exit codes; fetch guards; `lib/` with each helper once; fixture server + 10 fixtures; **one skill end to end** (`geo:citability`) with preflight and response contract; README quickstart; PyPI publish; all three CI workflows. | Kill criterion (§6) evaluated. `geo score` quickstart passes in CI on 3 OSes. Divergence table exists. |
| **M2 — Audit complete → 0.2.0** | `crawl`, `audit`, `scan`, `llmstxt`, `validate`, `prune`; `data/` files; state module; evidence stamps; robots matrix; `--rescore`; skills `audit`, `technical`, `schema`, `llmstxt`, `brand`. | Rescore-twice byte identity. PARTIAL labeled end to end. Injection fixture passes. |
| **M3 — Report and polish → 0.3.0** | `report` (HTML + PDF, two modes, brand tokens, a11y, print), `compare`; skills `content`, `compare`, `report`; full docs IA with generated reference; first recorded eval. | Client-leak and XSS goldens pass. Every doc claim is CI-asserted. Eval recorded. |
| **M4 — Agency kit** *(go/no-go, §3.11)* | **Closed at the gate, 2026-09-20.** No concrete demand; deferred rather than deleted. | — |
| **0.4.0 — Freeze and prepare** | Envelope JSON Schema shipped in the package with `additionalProperties: false`; every command validated against it in CI; golden coverage for all eleven commands; docs cover every command and every error code. | Injecting an unfrozen key fails the build. Goldens stable across machines. |
| **1.0.0** | Tag the frozen schema. The machinery landed in 0.4.0; 1.0.0 is the promise, not the work. | Two consecutive evals where the outside practitioner would send ≥ 4 of 5 reports unedited. **This is the only open gate.** |

---

## 5. Risks

| Risk | L | I | Mitigation |
|---|---|---|---|
| Untrusted page content steers the agent | M | H | §3.3: no page text in CLI output; capped, escaped excerpts; skill data-only rule; injection fixture |
| Skill prose drifts back to LLM scoring | M | H | Key-manifest lint; composite excludes advisory class by construction |
| Plugin mechanics differ from assumption (D2) | M | M | M0 spike before any skill work; documented fallback |
| Scores read as authoritative when they are heuristics | M | H | Signal-class labels; divergence doc; the report's "not comparable with other tools" note; practitioner eval gates 1.0 |
| `LICENSE` claims more than the written agreement grants (notice waiver read as relicensing right) | L | H | D1 resolved with a written agreement covering code and prompts; the one M0 check is reading its text before choosing anything other than MIT (D4) |
| Users expect parity with upstream's breadth | M | M | §1.2 positioning; README states what is deliberately absent |
| `geo` binary name collides on PATH | L | M | `geo doctor` detects duplicates; troubleshooting entry |
| Playwright download flakiness in CI | M | L | Optional extra; gated PDF smoke test; HTML is the guaranteed artifact |
| Rebuilding gstack machinery we cut | M | M | §7 is binding; additions require a PRD amendment |
| Scope outruns a solo maintainer | H | H | Walking skeleton first; M4 gated; every milestone is a usable release on its own |

---

## 6. Success metrics and kill criteria

**Kill criterion (M1 gate).** The fetch/parse layer must match upstream `fetch_page.py` output on the fixtures (byte-fidelity after canonicalization), and the scorer must produce scores on all 10 fixtures that the maintainer can explain line by line from the signal inventory. If it cannot, stop and re-plan — the premise that GEO readiness is computable enough to be worth determinism is wrong.

**Engineering.** Rescoring a snapshot twice is byte-identical. Nothing is modified at install time. Every doc claim about commands, skills and scoring constants is asserted in CI. 100 % of error codes carry a hint. `--help` is complete for every command.

**Experience.** Quickstart passes from a cold container; elapsed time is reported (target < 5 min to first report, < 30 s to first `geo score`).

**Value.** The practitioner eval of §3.12. Public adoption signals, since telemetry is cut: PyPI downloads, issues and PRs from non-maintainers, plugin installs if the marketplace exposes them.

**Strategic hypothesis.** A clean, deterministic CLI is the distribution vector: the same core can later back a CI check, a GitHub Action, or live citation measurement (§8) without touching the skills. If by 1.0 nobody uses `geo` outside Claude Code, that hypothesis is weak and the CLI's public surface should shrink rather than grow.

---

## 7. Cut list (binding)

Not built: multi-host generation · cross-machine sync · dual-voice external review pipelines · question-tuning hooks · telemetry, consent flows, update checks · LLM-judge paid eval tiers · event-sourced state with compaction · skill-start status machinery · **a custom self-update or data-update channel** (PyPI is the channel) · **shell installers and ownership manifests** (the plugin manager is the installer, per D2) · **SKILL.md template generator** (lint only) · **crawl resume** · **alias and forwarding skills** · **in-place migration of upstream state**.

## 8. Deferred

Live AI-citation measurement across engines (the strongest candidate for post-1.0; needs the CLI core first) · JS-rendered crawling at scale · longitudinal trend reports beyond `compare` · i18n · hosted version of `geo serve` · scorer plugin ecosystem · a `DESIGN.md` / design-consultation pass on the report.

---

## 9. Traceability — all 63 reviewed requirements

**K** kept · **M** modified (reason given) · **C** cut (reason given) · **→M4** kept, moved behind the agency gate · **✓** satisfied by this document.

| ID | | Where / why |
|---|---|---|
| R1 | ✓ | §1.1 |
| R2 | K | §3.4 signal inventory; M1 pre-work |
| R3 | C | Alias skills forward an install base; a new repo has none |
| R4 | M | Becomes read-only `geo import` (§3.11). Source is never modified, so backup / migration-lock are unnecessary. Refuse-to-run survives for state-newer-than-CLI (§3.6) |
| R5 | M | Volatile data in versioned `data/` files: kept. Custom update channel: cut — a PyPI patch release is already versioned, checksummed and reversible |
| R6 | K | §3.3, §5 |
| R7 | M | New repo: files are written fresh in M0; `LICENSE` per D4 (upstream notice waived by agreement, D1) |
| R8 | M | No installer to prompt from; surfaced by `geo doctor`, the `GEO_E_*` hint, and state 3 |
| R9 | ✓ | §3.0 |
| R10 | M | Kill criterion, cadence, hypothesis kept (§6, §4). "Opt-in count" metric replaced with public signals — telemetry is cut |
| R11 | K | §3.2 |
| R12 | K | M1 gate |
| R13 | — | Superseded by R-D3 |
| R-D1 | ✓ | §3.8 outline |
| R-D2 | M | No generator (R-E12), so the contract is a marker block linted for byte-equality |
| R-D3 | M ✓ | §3.9. Eight states: "resume prompt" contradicted R-E7. Lock contention →M4 |
| R-D4 | K | §3.8 |
| R-D5 | K | §3.8 |
| R-D6 | K | §3.8 |
| R-D7 | K | §3.8; HTMX focus rules →M4 |
| R-D8 | K | §3.2 |
| R-D9 | K | §3.2; its exit table is superseded |
| R-D10 | K | M1 pre-work; envelope fields in §3.2 |
| R-D11 | →M4 | §3.11 |
| R-D12 | K | §3.5 |
| R-X1 | M | §3.2. `migrate`→`import` (M4); `self-update` and `--freeze-data` cut with the channel; `compare` and `prune` added (both were required elsewhere but missing from the list) |
| R-X2 | M | Envelope, hints, log path, preflight kept. Exit 6/7 rejected per R-E3 |
| R-X3 | M | Quickstart kept. Timing is a reported metric inside `ci.yml`, not its own workflow |
| R-X4 | M | `doctor` kept; installer-ownership checks dropped with the installer; plugin↔CLI skew added |
| R-X5 | M ✓ | Dist name `seomator-geo-audit` (`geo-audit` is taken) |
| R-X6 | M | `data_version` everywhere: kept. `--freeze-data`, channel checksums, offline/rollback: void — pin the package |
| R-X7 | M | `scoring_version`, compare refusal kept. "v1 vs v2" becomes the comparability note every report carries. Only prospects are importable; other upstream artifacts stay put |
| R-X8 | K | §3.6 |
| R-X9 | K | §3.13 |
| R-X10 | C | `uv tool install` and `/plugin install` are already non-interactive and native on Windows. Returns if D2 is rejected |
| R-X11 | M | Schema policy kept (§3.2). Alias-removal schedule cut with the aliases |
| R-X12 | ✓ | §1.1, §3.0, §3.8, §3.9 |
| R-X13 | K | M1; §6 |
| R-E1 | ✓ | This document |
| R-E2 | K | §3.4, restated as snapshot purity — one testable claim instead of a claim plus an exclusion |
| R-E3 | M | §3.2. Contiguous 0–5: "5 reserved, then 8" only avoided colliding with drafts that never shipped |
| R-E4 | M ✓ | §3.7: 9 core + 2 agency. No router (namespacing routes), no aliases, no update skill |
| R-E5 | K | §6 |
| R-E6 | M | **ETag/Last-Modified removed from hash identity** — they change on redeploy with identical content and would cause false STALE. Kept as metadata; a revalidation shortcut built on them was withdrawn, because a 304 does not vouch for headers (§3.5) |
| R-E7 | K | §3.6 |
| R-E8 | C | The plugin manager owns install, update, uninstall. Returns as written if D2 is rejected |
| R-E9 | M | Kept, plus `--allow-private` for the start URL (localhost/staging audits are legitimate) and peer-address validation against DNS rebinding |
| R-E10 | K | §3.4 |
| R-E11 | K | §3.3 |
| R-E12 | K | §3.7 |
| R-E13 | K | §3.8 |
| R-E14 | M →M4 | Core state is single-writer (atomic append / rename). Locking arrives with the first multi-writer file. Sync-drive warning stays in core `doctor` |
| R-E15 | →M4 | §3.11 |
| R-E16 | K / →M4 | Autoescape + XSS fixture in M3; serve token and Host allowlist in M4 |
| R-E17 | K | §3.5, §3.4 |
| R-E18 | K | §3.7 |
| R-E19 | K | §3.8 |
| R-E20 | ✓ | §3.1 |
| R-E21 | C | Nothing to roll back to in a new repo; upstream stays independently installable |
| R-E22 | K | §3.13 |
| R-E23 | M | Three workflows with enumerated jobs. The data-channel amendment is void |
| R-E24 | M | Per minor release, 5 sites, maintainer + one outside practitioner; merged with the design review's "send unedited" metric. Sized for a solo maintainer |
| R-E25 | M | Kept: 0700, golden canonicalization, fixture-refresh doc, `.gitattributes`, key manifests, gated PDF skip, timing as metric, missing version refuses compare. Void: data-channel trust model. `prospects.json` 0600 →M4 |

Totals (63): 32 kept or satisfied as written · 23 modified · 4 cut · 2 moved whole to M4 · 1 split between M3 and M4 (R-E16) · 1 superseded by a later requirement (R13).

## 10. What changed from the reviewed draft, and why

1. **New repo, new name, new owner** — so no install base. Removes alias skills, in-place migration, rollback tag, forwarding `geo-update`, the "v2" framing, and makes the upstream relationship a first-class item the draft never mentioned: reuse is by written agreement with upstream's author, covering code and prompts (D1).
2. **Plugin distribution (D2)** — the draft deferred it "until distribution demand is real"; publishing a new open-source repo *is* that moment. Removes three installer scripts, R-E8, R-X10 and the router skill.
3. **PyPI replaces the custom data channel** — the draft accepted the channel, then needed pinning, checksums, offline behavior, rollback, a trust-model doc and a cut-list amendment to make it safe. A patch release gives all of that for free.
4. **Two logic fixes:** ETag out of hash identity (R-E6); "resume prompt" state removed (R-D3 vs R-E7).
5. **Two safety fixes:** `--allow-private` + peer-address validation (R-E9); synthetic fixtures instead of captured third-party HTML (G7).
6. **G1 restated as snapshot purity** — one claim that is actually testable.
7. **Agency kit sequenced last behind a gate (D3)** — nothing is dropped; locking, serve hardening and CRM import move with it, which is where their only consumers live.
8. **Sized for one maintainer:** 6 CI workflows → 3; per-release two-practitioner eval on 10 sites → per-minor on 5; named-expert "instincts" → cited primary sources.

---

## 11. Execution record

Appended as milestones close. Each entry records the gate evidence, not the intent.

### M0 — Bootstrap · closed 2026-09-20

| Gate | Result |
|---|---|
| New repo, standalone, no upstream history | Done. `github.com/seo-skills/geo-audit-skill`. |
| §3.13 M0 files | Done: `LICENSE`, `README.md`, `CONTRIBUTING.md`, `SECURITY.md`, `CHANGELOG.md`, `.gitattributes`, `CLAUDE.md`, and this document as `PRD.md`. |
| **D2** — distribution | **Plugin.** `.claude-plugin/plugin.json` (name `geo`) and `marketplace.json` written against the observed manifest format. Shell installers cut, per §7. |
| **D3** — agency kit | **Deferred to M4 behind the go/no-go gate**, as drafted. No Flask, `rich` or `portalocker` dependency in 0.1.0. |
| **D4** — license and copyright | **MIT, © 2026 SEOmator** - renamed with the product (see *Product naming*). No upstream copyright line is carried, which the D1 agreement permits. **Confirmed by the maintainer, 2026-09-21: SEOmator holds the copyright.** Re-read the written agreement before choosing any licence other than MIT — a notice waiver and a relicensing grant are different rights. |
| §1.2 positioning | **Still `TODO(maintainer)`.** The provisional text stands. The README ships a positioning section written around it that names no other project. |
| Plugin spike | **Done except Windows and a live `/geo:` check** (2026-09-21, `claude plugin` CLI against a throwaway config dir; the real install was hash-checked untouched). `marketplace add seo-skills/geo-audit-skill` clones over HTTPS when SSH is not configured; `install geo@seomator` succeeds; `plugin details` reports nine skills at ~659 always-on tokens a session. **Update is keyed on `version`:** after a skill change pushed without a bump, `plugin update` reported "already at the latest version (0.4.0)" and left the installed copy stale while the marketplace clone had the change. A `github` plugin source clones over SSH with no HTTPS fallback; a `url` source over HTTPS honours both `ref` and `sha`. Consequences are in `RELEASING.md`: pin the marketplace to the release tag after the first publish. |

### M1 — Walking skeleton → 0.1.0 · closed 2026-09-20

| Gate | Result |
|---|---|
| Envelope and error contract frozen before porting | Done. Fixed key set, 17 `GEO_E_*` codes each with a hint, six exit codes. Golden-tested. |
| Signal inventory | Done. `docs/concepts/signals.md`, generated from `data/weights.json`. |
| `fetch`, `score`, `doctor`; TTY and JSON modes; exit codes; fetch guards | Done. |
| `lib/` with each helper once | Done: `http`, `net`, `extract`, `robots`, `evidence`, `headers`, `ids`, `slug`, `browser`. |
| Fixture server and fixtures | Done. Eight synthetic pages plus eleven routes covering bot-block, 5xx, 404, non-HTML, oversize declared and streamed, redirect chain, redirect loop, redirect-to-private, and robots edge cases. |
| One skill end to end | Done. `geo:citability` with preflight, the shared response contract and two on-demand sections. |
| README quickstart | Done, and executed by the test suite and by a CI job against a built wheel. |
| Three CI workflows | Done: `ci.yml` (test matrix on 3 OSes × 2 Pythons, skill lint, docs freshness, quickstart from a wheel, package check), `secret-scan.yml`, `release.yml` (trusted publishing, tag/VERSION/CHANGELOG gate). |
| **Kill criterion: fetch/parse parity with the reference implementation** | **Passed. 11 of 11 fixture routes agree on every comparable field** (status, redirect chain, title, full heading structure, canonical, description, JSON-LD types after `@graph` flattening, malformed-JSON-LD detection, external link set, internal link count, client-rendering verdict). Extracted text and word count are deliberately non-comparable; see divergence 5. The run found one real gap — an empty framework mount point with no noscript notice — which is now detected and tested. |
| **Kill criterion: every score explainable line by line** | **Passed.** Each signal returns a `detail` payload of the counts behind its number; the fixtures rank ssr-rich 94 → schema-none 73 → weak-prose 13 → csr-shell 0, and each step is attributable to named signals. |
| Divergence table exists | Done. Ten entries in `docs/concepts/score-divergence.md`, each with the reason. |
| Quickstart passes in CI on 3 OSes | **Passed on all three from the first run**, against a built wheel rather than the source tree, so the artifact that is tested is the artifact that ships. |
| PyPI publish | **Not done, and blocked on a human.** `release.yml` publishes on a `v*` tag through trusted publishing; its tag/VERSION and changelog gates pass locally. The PyPI project and its trusted publisher have to be configured once by hand. `seomator-geo-audit` was still unclaimed on 2026-09-20. Until then the README points at the git install, which is verified working. |

**Test suite at 0.1.0:** 263 passing, 2 skipped (both environment-gated).

### First CI, and what it cost

The suite passed on the first push locally and failed everywhere in CI. Three
rounds, worth recording because two of the three fixes were wrong.

| Round | Symptom | Diagnosis | Outcome |
|---|---|---|---|
| 1 | every job failed except Windows | `uv pip install --system` targets the runner's system Python, and the Ubuntu and macOS images mark it externally managed under PEP 668. Behind it, nothing ever installed the interpreter the matrix asked for, so two matrix cells tested one Python. | Fixed with `setup-python`, plus an in-workflow assertion that the running version is the requested one. 9 of 11 jobs green. |
| 2 | Ubuntu only, connection failures clustered around redirect tests | Guessed twice: that abandoned redirect responses closed with RST rather than FIN, and that half-read responses poisoned the connection pool. Both plausible, both shipped, neither verified against the bug. | Both reverted. Neither changed a measured connection count, and `requests.Response.close()` already closes an unconsumed body. |
| 3 | same | Spent the round trip on the error message instead of a fix: `GEO_E_CONNECT` had been collapsing six distinct failures into "refused or reset". CI then named it - *the server closed the connection before sending a response*. Python's `http.server` honours a client's `Connection: close` by closing the socket but never sends the header back, so urllib3 pools a socket the server is dropping. Whether it fires depends on whether the FIN arrived before urllib3's dropped-connection check, which is exactly why macOS and Windows passed. | Dropped `Connection: close` from the client - keep-alive is what a crawler wants anyway - added one retry for the same race against real servers, and made the fixture server echo the header. The regression test counts connections at the server: seven requests on a warm session open seven connections with the old header and none without it. |

Two rules came out of it, both now habits in this repo: **make a failure name its
own cause before guessing at a fix**, and **verify a regression test fails with
the fix removed**. Applying the second is what identified rounds 1 and 2 as
wrong.

### M2 - Audit complete -> 0.2.0 - closed 2026-09-20

| Gate | Result |
|---|---|
| `crawl`, `audit`, `scan`, `llmstxt`, `validate`, `prune` | Done. Nine commands total. |
| `data/` files, state module, evidence stamps, robots matrix | Done in M1 and extended: `schema_requirements.json`, `brand_platforms.json`, `retention.json`. |
| `--rescore` | Done. |
| Skills `audit`, `technical`, `schema`, `llmstxt`, `brand` | Done. Six skills, each carrying the shared response contract byte-identically. |
| **Rescore-twice byte identity** | **Passed.** Two rescores of one record are byte-identical after volatile fields, reproduce the recorded composite, and a test asserts the fixture server sees no requests during one. |
| **PARTIAL labelled end to end** | **Passed.** The crawl sets the stamp, the audit carries it, and the headline sentence names how many pages were scored and why the rest were not. |
| **Injection fixture passes** | **Passed, and extended.** Beyond the existing assertions that the payload changes neither score nor envelope shape, `geo llmstxt --generate` now excludes instruction-shaped pages from the file it produces and reports them as a finding - the one artifact this tool emits that a user publishes. |

**Test suite at 0.2.0:** 430 passing, 1 skipped.

**Two defects the tests found, both worth recording because neither was visible in a
passing suite:**

1. A 404 was scored zero on indexability and metadata, which pulled the site aggregate
   below a finding threshold and produced "the page tells search engines not to index
   it" for a site with no `noindex` anywhere. One failure was being counted twice.
2. The key-manifest test - which runs every command and checks that each identifier a
   skill names appears in a real envelope - found that `detail.blocked_critical` was
   being discarded by aggregation. The technical skill's advice to read it would have
   failed against every real audit. A detail identical on every page is a fact about
   the site and now survives the roll-up.

Both are recorded as divergences 12 and 13.

### M3 - Report and polish -> 0.3.0 - closed 2026-09-20

| Gate | Result |
|---|---|
| `report` (HTML + PDF, two modes, brand tokens, a11y, print) | Done. Single self-contained file, print-to-PDF through the browser so report.css decides page breaks. |
| `compare` | Done, including the refusal across a scoring or data version change. |
| Skills `content`, `compare`, `report` | Done. Nine skills. |
| Full docs IA with generated reference | Done. Command reference, signal tables per category, crawler table, schema type table and the advisory rubrics are all generated from code or data. |
| **Client-leak golden passes** | **Passed, three ways.** The operator template rendered with only the client namespace raises UndefinedError; every field of OperatorContext is asserted absent from the client file; and a client report is checked for data from a second audited site. |
| **XSS golden passes** | **Passed.** A page titled `</title><script>alert(1)</script>` produces a report with no script tag in the body, and the environment's autoescape is asserted directly. |
| Every doc claim is CI-asserted | Done. The README's category table is checked against `data/weights.json`, every documented flag against the parser, every error code against its hint, and every identifier a skill names against a real envelope. |
| **First recorded eval** | **Harness built, eval not run.** `tests/evals/` audits the sites, renders the reports and emits a blank two-person form. It cannot be run without a practitioner, which is the point. This gate is open. |

**All six categories now compute**, with weights summing to 100: citability 25, brand
20, content 20, technical 15, schema 10, platform 10.

**Test suite at 0.3.0:** 532 passing, 1 skipped.

**Three findings worth recording:**

1. The contrast fallback the plan called for was unreachable. With header text chosen
   automatically between black and white, the worst case over the entire sRGB cube is
   4.58:1 - above AA - so no brand colour can fail there. The case that does fail
   constantly is an accent on white, and nothing was checking it. Divergence 19.
2. `--out` meant two different things: the JSON envelope globally, the HTML path in
   `report`. So `geo report --out x.html` wrote the report and then overwrote it with
   JSON. It now means one thing per command.
3. Three skills shipped naming the old product in their preflight, because they were
   generated after the rename from a helper holding the old text. The lint checked
   frontmatter, contracts and identifiers but never the preflight. It does now.

### Product naming

The product is **SEOmator GEO Audit Skill**. The PyPI distribution is
`seomator-geo-audit`, the crawler identifies itself as `SeomatorGeoAudit` with a link
to the repository, and the licence is © 2026 SEOmator. Unchanged on purpose: the
command is `geo`, the plugin is `geo`, the skills are `/geo:audit` and friends, and the
import package is `geo_audit`. Those are the names people have to remember.

All four candidate distribution names were unclaimed on PyPI and nothing had been
published, so the identifiers were free to change. After the first release this needs
a deprecation instead.

### 0.4.0 - Hardening toward 1.0

At the M4 go/no-go the choice was **harden toward 1.0**: no new features, freeze the
envelope, extend golden coverage, prepare the release. M4 stays deferred.

**One exception, taken deliberately: `geo report --site-kind`.** Both practitioner
rounds found the same defect - a publisher's checklist applied to a specification,
then to a reference site - and the eval judges the report itself. Skill guidance
could not reach it: the rendered order comes from the scorer, which cannot know what
a site is for. Leaving it would have spent round three on a known defect, and a round
that changes the tool does not count.

The kind is a report-time input, not an audit-time one, because the skill infers it
*from* the audit; the audit stays a kind-neutral measurement. A kind moves what it
leads with up one severity level (never to critical) and what it defers down two;
blockers never move; page-level findings keep their ceiling; points lost, impact and
every score are identical across kinds. The table is `data/site_kinds.json`, it
mirrors `skills/audit/sections/site-kind.md`, and a test holds the two vocabularies
together.

**A second exception: *What is already working*.** Three rounds of maintainer notes
said the same thing - a report that lists only faults reads as grudging, and a 76 with
nothing named for it is the first thing a practitioner edits - and the gate is reports
sent *unedited*. It is report-time and deterministic: up to three site-wide signals at
90% or more of their maximum (`strength_at_least` in `thresholds.json`), one per
category before a second from any, each with a fixed sentence beside its finding
template. A signal with any finding, page-level included, is never a strength, so the
report cannot praise what it also faults. No score moves.

**G1 audited against the code, 2026-09-21.** Checking every PRD claim against the
implementation found G1 half-met: the record held site-level signals, not every scorer
input, so `--rescore` rebuilt the number but lost page-level and check findings. Closed
with a record-only snapshot (per-page ratios, fetch and robots observations) and one
classification function shared by a live run and a rescore. The ETag
revalidation shortcut from §3.5 was built once pages were kept on disk, then withdrawn - see
the open list.

### Open before the next milestone

1. ~~Publish to PyPI.~~ **Done 2026-09-21:** `seomator-geo-audit` 0.4.0 released through
   the trusted publisher - verified, tested on three operating systems, built and
   published by `release.yml` - and the marketplace pinned to `v0.4.0`. The first
   milestone to end in a tagged release, as §4 asks of all of them.
2. The plugin on Windows. Everything else in the spike is verified: install and update
   from a clean config, and the nine `geo:` skills registered in a live session - the
   first real `/geo:audit`, on seomator.com, 2026-09-21.
3. Write §1.2.
4. ~~Confirm the D4 copyright holder.~~ **Confirmed 2026-09-21: SEOmator.**
5. **Run the practitioner eval.** It is the only gate left before 1.0 and the only
   check in the project that needs a person: `python tests/evals/run_eval.py`, five
   sites the practitioner knows, two questions each.
6. M4, if the go/no-go in D3 says yes: `crm`, `serve`, `import`, locking.
7. ~~The ETag revalidation shortcut.~~ **Built and withdrawn 2026-09-21.** A 304 vouches
   for a page's bytes, not for the headers two signals are scored from, so a re-audit
   trusting it could not see a header-only fix (§3.5). Every page is downloaded again.
8. A design question, not a defect: authorship, attribution and article-markup
   findings apply to every page, so hub and tool pages are listed beside articles.
   Scoping them to articles needs a reliable article test and a `scoring_version` bump.
