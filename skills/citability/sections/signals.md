# Citability signals: definitions and thresholds

Read this when the user asks why a signal scored what it did, or disputes a number.
Every threshold named here lives in `data/thresholds.json` and carries `data_version`.
If the numbers below disagree with the envelope, the envelope is right and this file
is stale — say so.

## citability.self_containment — 25 points, heuristic

**Question:** does each passage name its own subject?

**Method.** Prose blocks of 12 words or more are candidates. A candidate fails if its
first word or phrase is a referential with no antecedent inside the block: `this`,
`it`, `they`, `those`, `such`, `the former`, `as mentioned`, `however`, `therefore`
and about thirty more. The score is the share of candidates that pass, ramped from
0 points at 30 percent to full marks at 85 percent.

**Why it is weighted highest.** An engine lifts one paragraph, not the page. A
paragraph beginning "This also means..." arrives at the reader pointing at nothing.

**What it does not catch.** A passage can name its subject and still be wrong or
vague. This signal measures structural independence, not quality.

## citability.answer_first — 20 points, heuristic

**Question:** does each section lead with its answer?

**Method.** For each H2 or H3, take the first prose block under it. The section passes
if that block does not open with a filler phrase (`In this article`, `Before we`,
`Nowadays`, and similar) and its first sentence is 45 words or fewer. Ramped from 20
percent to 75 percent.

**Why 45 words.** It is a run-on threshold, not a style preference. A first sentence
longer than that is rarely a direct answer.

## citability.structure — 15 points, deterministic

**Question:** do the headings segment the page into answerable parts?

Four components, each reported separately in `detail.breakdown`:

| Component | Points | Rule |
|---|---|---|
| `single_h1` | 4 | Exactly one H1. Zero or several score nothing. |
| `enough_h2` | 4 | Scaled to three H2s. |
| `no_skipped_levels` | 3 | One point deducted per skip. **A page with no headings scores zero here**, not three: it has no outline to keep intact. |
| `section_length` | 4 | Share of sections at or under 400 words. |

## citability.evidence_density — 15 points, heuristic

**Question:** do claims carry something checkable?

Ten points for the share of prose blocks containing a fact marker — a number of two
or more digits, a measured quantity with a unit, a currency amount, a four-digit year
or a month name — ramped from 5 percent to 35 percent. Five points for outbound links
to distinct external domains, scaled to three.

**Why outbound links count.** Citing a source is the behaviour engines reward and the
one most commonly missing from marketing pages.

## citability.extractability — 15 points, deterministic

**Question:** is the content in the HTML a non-rendering crawler receives?

Full marks unless the page shows that its content needs JavaScript. Without a
browser the evidence is what the page says about itself: an app mount (`#root`,
`#app`, `#__next`, `#__nuxt`) with nothing in it, or a "you need to enable
JavaScript" notice on a page serving fewer than 1,200 characters of content. App
templates carry that notice even when the server rendered everything, so on a page
that has its content it means nothing.

**A gated page** is scored on what still arrives - eight points scaled to 3,000
characters of content, four for the ratio of content to body text scaled to 0.25,
two for a list, one for a table - and capped at 3.

**A short page is not a gated one.** How much a page says is `content.depth`'s
question. A short server-rendered page has all of its content in the HTML, and
telling it to server-render is wrong advice.

## citability.attribution — 10 points, deterministic

**Question:** does the page say who wrote it and when?

Scored on articles only: on a home page, an index of the pages beneath it, a category,
tag or author archive, or a page that declares itself a product, an app or a profile, it
is `null` and not applicable. In an audit of a site that marks its articles, a page it
left unmarked is not one either.

Byline 3 · published date 3 · modified date 1 · an Organization or Person node in
JSON-LD 2 · canonical 1. The JSON-LD check walks nested nodes, so
`Article { publisher: Organization }` counts.

## citability.render_parity — 10 points, heuristic, nullable

**Question:** how much of the visible text exists only after JavaScript runs?

Requires the optional browser extra. Compares extracted characters in the raw
response against extracted characters in the rendered DOM, ramped from 0.5 to 0.9.

**When it is null,** `completeness.missing` names it and the composite is taken over
the six signals that were computed. Report it as not measured. It is not a zero.

## How the composite is formed

```
composite = round(sum(earned for computed signals) / sum(max for computed signals) * 100)
```

Signals that were not computed leave both sides of the fraction. Advisory (LLM-judged)
signals never enter it at all — there are none in this release, and when they arrive
they will be displayed in their own section and excluded by construction.
