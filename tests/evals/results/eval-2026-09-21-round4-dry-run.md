# Practitioner eval — 2026-09-21 — round four, dry run

Tool 0.6.0 · scoring 2.0 · data 2026.09 · normalizer 2

A dry run by the assistant building the tool, made before anyone's time is spent on a
counted round. It does not count toward the gate and answers no question in either
column - those belong to the maintainer and the practitioner the protocol names. It
reviews the reports against every complaint the earlier rounds wrote down; the review
and the one defect it found follow the five sites.

## https://plausible.io

Score **77/100 (good)** over 8 pages, evidence CURRENT.

Categories: citability 85, content 66, platform 59, schema 68, technical 95

Ordered for: saas

Top three fixes as ranked by the tool:

1. **Claims arrive without numbers, dates or sources** — high, medium effort, 6 page(s)
2. **No machine-readable publisher identity** — high, low effort, 8 page(s)
3. **The site publishes no llms.txt** — medium, low effort, 8 page(s)

| Question | Maintainer | Practitioner |
|---|---|---|
| 1. Are these the right three? | _open_ | _open_ |
| Why | | |
| 2. Would you send this unedited? | _open_ | _open_ |
| Why | | |

## https://www.smashingmagazine.com

Score **65/100 (fair)** over 8 pages, evidence CURRENT.

Categories: citability 80, content 62, platform 52, schema 0, technical 95

Ordered for: publisher

Top three fixes as ranked by the tool:

1. **Authorship is not machine-readable** — high, medium effort, 7 page(s)
2. **The page carries no structured data** — high, medium effort, 8 page(s)
3. **The site publishes no llms.txt** — medium, low effort, 8 page(s)

| Question | Maintainer | Practitioner |
|---|---|---|
| 1. Are these the right three? | _open_ | _open_ |
| Why | | |
| 2. Would you send this unedited? | _open_ | _open_ |
| Why | | |

## https://www.adafruit.com

Score **65/100 (fair)** over 8 pages, evidence CURRENT.

Categories: citability 73, content 54, platform 46, schema 53, technical 87

Ordered for: ecommerce

Top three fixes as ranked by the tool:

1. **Little usable content is present in the HTML the crawler receives** — high, high effort, 3 page(s)
2. **No machine-readable publisher identity** — high, low effort, 8 page(s)
3. **Structured data is malformed or missing required properties** — high, low effort, 8 page(s)

| Question | Maintainer | Practitioner |
|---|---|---|
| 1. Are these the right three? | _open_ | _open_ |
| Why | | |
| 2. Would you send this unedited? | _open_ | _open_ |
| Why | | |

## https://www.eff.org

Score **56/100 (fair)** over 8 pages, evidence CURRENT.

Categories: citability 65, content 58, platform 39, schema 0, technical 89

Ordered for: publisher

Top three fixes as ranked by the tool:

1. **Little usable content is present in the HTML the crawler receives** — high, high effort, 2 page(s)
2. **Authorship is not machine-readable** — high, medium effort, 7 page(s)
3. **The page carries no structured data** — high, medium effort, 8 page(s)

| Question | Maintainer | Practitioner |
|---|---|---|
| 1. Are these the right three? | _open_ | _open_ |
| Why | | |
| 2. Would you send this unedited? | _open_ | _open_ |
| Why | | |

## https://developer.mozilla.org

Score **60/100 (fair)** over 7 pages, evidence PARTIAL.

Categories: citability 75, content 48, platform 59, schema 0, technical 94

Ordered for: docs

Top three fixes as ranked by the tool:

1. **The site publishes no llms.txt** — high, low effort, 7 page(s)
2. **The page carries no structured data** — high, medium effort, 7 page(s)
3. **Pages do not say when they were last checked** — medium, low effort, 7 page(s)

| Question | Maintainer | Practitioner |
|---|---|---|
| 1. Are these the right three? | _open_ | _open_ |
| Why | | |
| 2. Would you send this unedited? | _open_ | _open_ |
| Why | | |

## The dry run's review

### The defect

Two reports led with *Little usable content is present in the HTML the crawler
receives*, and its remediation: server-render the main content. Round two and the
round-three dry run had the same lead on the same two sites; round three called it a
blocker by design that "reads large". The review looked at why.

Every page it named was capped by one rule: under 1,200 characters of content, the
signal was capped as if the page were gated. None showed any sign of gating - no
"enable JavaScript" notice, no app mount at all. Rendered in a browser with
`geo score`, not one gained a character:

| Page | Characters in the HTML | Characters after JavaScript |
|---|---|---|
| adafruit.com/ | 649 | 649 |
| adafruit.com/product/1 | 663 | 663 |
| adafruit.com/product/102 | 1,194 | 1,194 |
| eff.org/effector/38/16 | 1,180 | 1,180 |
| eff.org/about/opportunities | 274 | 274 |

The advice was wrong for all five, and `/product/102` was six characters short of
escaping the cap. The cap measured length, which is `content.depth`'s question, and
extractability being a blocker put the wrong answer first. Fixed in `617f225`
(scoring 3.0): extractability scores evidence that content needs JavaScript - an
empty app mount, or a JavaScript notice on a page serving too little to have its
content anyway - and full marks otherwise. Divergence 25 records it.

### After the fix

| Site | Score | Top three |
|---|---|---|
| plausible.io | 77 | claims without evidence · no publisher identity · no llms.txt |
| smashingmagazine.com | 65 | authorship (7 pages) · no structured data · no llms.txt |
| adafruit.com | 67 | no publisher identity · malformed structured data · no last-checked date |
| eff.org | 58 | authorship (7 pages) · no structured data · no llms.txt |
| developer.mozilla.org | 61 | no llms.txt · no structured data · no last-checked date |

### The earlier rounds' complaints

- **Authorship led a SaaS report** (round three). Fixed in 0.4.0 by the site kinds; it
  no longer appears in plausible.io's top three.
- **The home page was the first example page for authorship** (round three). Fixed in
  0.6.0: authorship is scored on articles only, and smashingmagazine.com's finding
  names seven pages, none of them the home page.
- **The reports said only what was wrong** (rounds two and three). Fixed in 0.4.0:
  every report has *What is already working*.
- **Extractability read large on two pages of eight** (round three). Fixed here.

One thing a practitioner may still raise: eff.org's authorship finding names its about
pages. Its CMS declares them `og:type` article, and an article with no machine-readable
author is what the finding reports, so it is defensible - but a reader may disagree.

## Outcome

- Reports the practitioner would send unedited: not asked - a dry run.
- Changes made as a result: extractability scores evidence that content needs
  JavaScript, not length (`617f225`, scoring 3.0).

## Next

The counted round runs on the release that carries scoring 3.0, unchanged until both
people have answered:

```bash
python tests/evals/run_eval.py --sites tests/evals/sites.json \
  --out tests/evals/results/eval-<date>-round4.md
```
