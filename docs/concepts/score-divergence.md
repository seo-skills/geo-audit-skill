# Score divergence

Every deliberate departure from a conventional GEO scoring model, with the reason.
This file exists so that "our tool says 62 and yours says 78" has an answer better
than a shrug.

## Comparability

A score from this tool is comparable with another score from this tool at the same
`scoring_version` and `data_version`. It is **not** comparable with a score from any
other GEO tool. Different tools weight different categories, extract different text,
and disagree about what counts as content. That is not a defect in either; it means
the numbers are not on the same scale.

## Divergences in this release

| # | Divergence | Conventional approach | What we do | Why |
|---|---|---|---|---|
| 1 | **A model never produces a number.** | Ask an LLM to rate the page 0–100 against a rubric. | Every scored signal is deterministic or heuristic code. Model judgment is an `advisory` class that cannot enter the composite. | A rubric-scored page gets a different number on a different day, and the difference cannot be explained to a client. |
| 2 | **Null, not zero, for unmeasured signals.** | Score a missing capability as a failure, or silently switch to a cheaper formula. | The signal is `null`, `completeness` names it, and the composite is taken over the signals that were computed. | Scoring "we didn't look" as "you failed" is the most common way an audit tool lies. |
| 3 | **The composite is a ratio, not a fixed denominator.** | Sum points out of a constant 100. | `earned / max-of-computed * 100`. | It is what makes (2) possible without a second scoring path. |
| 4 | **Evidence hashing excludes ETag and Last-Modified.** | Use ETag as the change signal. | Hash the content blocks; keep ETag as a revalidation shortcut only. | ETag changes on every redeploy. Using it would mark reports stale for a CSS fix. |
| 5 | **Boilerplate is stripped structurally before scoring.** | Score the whole visible body. | Landmarks and known chrome patterns are removed; the content root is `<main>`, then `<article>`, then `<body>`. | A page's nav and cookie banner are not the page's content, and including them makes every site on one CMS look alike. |
| 6 | **A blocked or erroring page is a finding, not an error.** | Abort the audit on a 403. | `ok: true`, `scores: null`, `evidence.stamp: PARTIAL`, and a critical finding. | Aborting refuses to report on exactly the sites whose bot protection is the problem. |
| 7 | **Training crawlers and search crawlers are scored separately.** | Treat any `Disallow` against an AI user agent as a failure. | Only tokens marked `critical` in `data/ai_crawlers.json` — the ones gating an answer surface — raise a finding. | Refusing `GPTBot` while allowing `OAI-SearchBot` is a coherent, common position, not a mistake. |
| 8 | **Structure scores zero for a page with no headings.** | Award "no skipped heading levels" to a page with no headings. | No headings means no outline points at all. | An empty client-rendered shell was scoring above zero on an outline it did not have. |
| 9 | **A single explicitly-named URL is fetched regardless of robots.txt.** | Refuse to fetch anything robots disallows. | `fetch` and `score` fetch the URL you named, and report robots access as a finding. A future `crawl` respects robots for links it discovers. | You must be able to audit your own site, including the parts it disallows. Discovery is where etiquette applies. |

| 10 | **A category the inputs cannot reach is out of scope, not missing.** | Report every declared category, scoring the unmeasured ones zero or omitting them silently. | The coverage report names only the categories a run could reach. An audit of a URL has no brand name, so `brand` does not appear in its coverage at all; `--brand` brings it into scope. | Listing "brand: missing" on a site audit reads as a gap in the audit rather than an input nobody supplied. |
| 11 | **`schema.presence` means the page *attempted* structured data.** | Count blocks that parsed. | A block that fails to parse counts as present; whether the attempt succeeded is `schema.validity`'s question. | Counting only parsed blocks produced two contradictory findings on one page: "carries no structured data" beside "structured data is malformed". |
| 12 | **A page with no markup is not measured on markup signals.** | Score a 404 zero on every signal. | Pages that returned no markup are scored on `technical.status_health`, where the failure belongs, and left unmeasured on indexability and metadata. | Scoring them zero counted one 404 twice and dragged the site aggregate below a finding threshold, producing "the page tells search engines not to index it" for a site with no `noindex` anywhere. |
| 13 | **A detail identical on every page survives aggregation.** | Reduce per-page signals to a mean and discard their detail. | Detail entries that every page agreed on are carried up verbatim alongside the mean, spread and worst page. | Which crawler tokens are blocked is a fact about the site. Replacing it with an average deletes the only actionable part of the signal. |
| 14 | **A platform with no usable API is a manual check, never a result.** | Estimate presence from a scrape, or omit the platform silently. | LinkedIn, X and the review sites are listed with why they cannot be queried and what to do by hand, and no signal is derived from them. | An invented number is worse than an absent one, and a silently omitted platform reads as "we checked and found nothing". |
| 15 | **A generated llms.txt excludes pages that talk to the model.** | List every crawled page. | Pages whose own title or summary is instruction-shaped are left out and reported as a finding. | That file is published and read as authoritative. Copying a page's own "ignore previous instructions" into it hands the attack a better delivery mechanism than the page had. |

| 16 | **A finding that only restates a cause is suppressed.** | Report every signal that scored below threshold. | When a cause signal scores at its floor, the findings that are merely its consequences are left out. The relation is declared in `data/findings.json`. | Found by auditing a real site with no structured data: the top finding read "structured data is malformed" for a page that had none, and three more findings restated the same absence, pushing the one that mattered down the list. |

| 17 | **Model judgement is a separate class that cannot become a number.** | Have an LLM rate the page and fold that rating into the score. | Advisory signals carry a question and a rubric and no value. `composite()` filters on class, so there is no code path from an answer to a score. | A rubric-scored page gets a different number on a different day and the difference cannot be explained to a client. Keeping the judgement is useful; keeping it out of the arithmetic is what makes the arithmetic defensible. |
| 18 | **Client and operator reports are separate render contexts.** | One template with `{% if operator %}` around the sensitive parts. | `render_client` builds a namespace with no operator key, under StrictUndefined. | A conditional can be inverted, and the failure is discovered by a client. An UndefinedError is discovered by a test. |
| 19 | **A brand keeps its colour in the header and loses only the accent.** | Reject a brand palette that fails contrast, or apply it regardless. | Header text is chosen automatically between black and white, which always clears AA; the accent, used for small text on white, is validated and falls back loudly. | Computing it showed the header fallback was unreachable - the worst case over the whole sRGB cube is 4.58:1 - while the accent case fails constantly: a yellow accent on white is 1.27:1. The check was in the wrong place. |
| 20 | **hreflang is not measured on a single-language site.** | Score every page against every signal. | The signal is `null` with a stated reason when only one language is seen. | Marking a site down for a problem it cannot have is worse than saying nothing. |
| 21 | **A fact is scored once.** | Let related signals appear in several categories, as most scoring models do. | No signal id appears in two categories, and a test asserts it. Open Graph moved out of technical when platform arrived. | A fact that moves the composite twice makes the score impossible to explain and easy to game. |
| 22 | **Two runs scored under different rules are not compared.** | Subtract the composites and report the delta. | `compare` refuses on a scoring-major, data-version or normalizer-version change, or when the two runs scored different categories, with a hint saying what the number would have meant. | "Your score fell six points" when only our thresholds moved is a false statement to a paying client. |
| 23 | **The crawl is level-synchronous, not completion-driven.** | Enqueue discovered links as each page returns, which is faster. | A whole level is awaited, its discoveries sorted, then the next level starts. | Enqueueing on completion makes `--max-pages` reach a different set of pages on a slower machine, which makes `compare` report changes that did not happen. A crawl is rate-limited rather than latency-limited, so the wait costs almost nothing. |
| 24 | **Authorship is scored on articles only.** | Score byline, dates and Article markup on every page. | `content.expertise`, `citability.attribution` and `schema.article` are *not applicable* on a home page, an index of the pages beneath it, or a page declaring a product, app or profile type without an article type. On a site where no page is an article they leave the completeness count as well as the composite. Any other page is presumed an article. | A home page has no byline to find, and every practitioner eval named home pages or calculators first in the authorship finding. Nothing is dropped on a guess: sampled on 79 real pages, the rule kept all 31 articles. |
| 25 | **Length is not extractability.** | Treat a page with little text as one whose content a crawler cannot get. | `citability.extractability` scores only evidence that content needs JavaScript: an empty app mount, or a JavaScript notice on a page serving too little to have its content anyway. How much a page says is `content.depth`'s question. | The practitioner eval's round four led two reports with "server-render your content" on short product and about pages; rendered in a browser, not one of the five gained a character. |
| 26 | **The author is the article's author.** | Take the first Person on the page. | `content.expertise` reads the Person an article's `author` names (resolving an `@id` reference), then one the page's own nodes name as author, then a Person the page declares itself to be about. A Person nested in anything else - a founder, an employee, a commenter - is not the author. | seomator.com's site-wide Organization graph names its founder, a Person with a name only, before each post's author; every post read as missing the credentials and profile its author node carried, and the report's first fix was false on all 43 pages. |
| 27 | **An archive is not an article.** | Presume every page that declares nothing is an article. | A page at `.../category/<name>` (or German `kategorie`), `.../tag/<name>` or `.../author/<name>` (plurals too, optionally paged) is not an article, unless it declares an article type. | Archives list posts that sit beside them, not beneath them, so the index rule misses them: on seomator.com two findings named seven category archives and an about page, and no article. |
| 28 | **A site that marks its articles has answered for the rest.** | Presume every undeclared page is an article. | In an audit, if two or more pages carry an article type in JSON-LD or `og:type article`, a page carrying neither is not an article. `geo score` reads one page, has no site to compare it with, and presumes as before. | The presumption kept real articles but asked careers pages, plans pages and a privacy policy for a byline wherever a crawl reached them. Rescored: seomator.com 91 to 94 with three false findings gone; plausible.io 77 to 78; the other four eval sites unchanged. |
| 29 | **A capped crawl spreads over the site.** | Read the sitemap in sorted order. | The sitemap's URLs are read one section at a time in turn - a section being the first path segment, with top-level pages as one more - and in hash-of-path order within a section. Links found on pages are still read in sorted order, level by level (row 23). | Sorted, a capped crawl audited the alphabetical prefix of a site: seomator.com's 50 of 310 ran from `/` to `/blog/how-to-*`, with no tool page after "b" and no post after "h". The order still depends on nothing but the sitemap. |

## Parity with the reference implementation

The fetch and parse layer was compared field by field against the reference
implementation this project's structure derives from, over the eleven fixture routes,
on 2026-09-20.

**Result: 11 of 11 routes agree on every comparable field** — HTTP status, redirect
chain length, `<title>`, the full heading structure with levels and text, canonical,
meta description, the set of JSON-LD `@type` values after `@graph` flattening,
detection of malformed JSON-LD, the set of external link URLs, the count of internal
links, and the client-rendering verdict.

Two fields are deliberately **not** comparable:

* **Extracted text.** The reference takes the whole body minus `script`, `style`,
  `nav`, `footer` and `header`, as one string. This project extracts a typed block
  sequence from a content root and strips chrome by class and role as well
  (divergence 5). The two are different measurements, not disagreeing ones.
* **Word count**, which follows from the above.

The comparison also found one real gap and closed it: a client-rendered shell with an
empty `<div id="app">` and *no* noscript warning was detected here only through its
content volume, not through its cause. `citability.extractability` now reports
`framework_root_chars` and `empty_framework_root`, measured before anything is
stripped, and caps the signal on either.

## Category weights

The six-category model this project starts from weights Citability 25, Brand 20,
Content 20, Technical 15, Schema 10, Platform 10. Those weights are declared in
`data/weights.json`, but only Citability is computed in this release; the others are
listed under `planned_categories` and enter no arithmetic. When they land, each will
get a row here for any sub-signal that turns out to be advisory rather than
computable.
