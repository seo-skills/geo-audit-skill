# Practitioner eval — 2026-09-21 — round three, dry run

Tool 0.4.0 · scoring 1.0 · data 2026.09 · normalizer 2

Two people answer independently: the maintainer, and one practitioner who does not work on this tool. Fill in both columns before reading the other one.

Answers: question 1 is `yes` / `mostly` / `no`. Question 2 is `yes` / `with small edits` / `no`. Both need one sentence of reasoning.

## https://plausible.io

Score **76/100 (good)** over 8 pages, evidence CURRENT.

Categories: citability 83, content 65, platform 59, schema 65, technical 95

Ordered for: saas

Top three fixes as ranked by the tool:

1. **Authorship is not machine-readable** — high, medium effort, 8 page(s)
2. **Claims arrive without numbers, dates or sources** — high, medium effort, 6 page(s)
3. **No machine-readable publisher identity** — high, low effort, 8 page(s)

| Question | Maintainer | Practitioner |
|---|---|---|
| 1. Are these the right three? | **no** | _open_ |
| Why | Authorship leads a SaaS site, and its remediation asks for author bylines with Person markup on pages that include a calculator. The saas table did not defer it. | |
| 2. Would you send this unedited? | **no** | _open_ |
| Why | The first fix is wrong for this kind of site, so the rest of the report is not read charitably. | |

## https://www.smashingmagazine.com

Score **65/100 (fair)** over 8 pages, evidence CURRENT.

Categories: citability 80, content 62, platform 52, schema 0, technical 95

Ordered for: publisher

Top three fixes as ranked by the tool:

1. **Authorship is not machine-readable** — high, medium effort, 8 page(s)
2. **The page carries no structured data** — high, medium effort, 8 page(s)
3. **The site publishes no llms.txt** — medium, low effort, 8 page(s)

| Question | Maintainer | Practitioner |
|---|---|---|
| 1. Are these the right three? | **yes** | _open_ |
| Why | Right for a publisher: the bylines are in prose and nowhere machine-readable, which is one template, and the site carries no structured data at all. | |
| 2. Would you send this unedited? | **with small edits** | _open_ |
| Why | Round two's note still stands - a site this solid gets a report that lists only what is wrong. And the homepage is the first example page for authorship, where no byline belongs. | |

## https://www.adafruit.com

Score **61/100 (fair)** over 8 pages, evidence CURRENT.

Categories: citability 68, content 47, platform 46, schema 45, technical 87

Ordered for: ecommerce

Top three fixes as ranked by the tool:

1. **Little usable content is present in the HTML the crawler receives** — high, high effort, 3 page(s)
2. **Authorship is not machine-readable** — high, medium effort, 8 page(s)
3. **No machine-readable publisher identity** — high, low effort, 8 page(s)

| Question | Maintainer | Practitioner |
|---|---|---|
| 1. Are these the right three? | **no** | _open_ |
| Why | Server-rendering the product pages is the right lead, but authorship is second on a shop and asks for bylines on /product/1. | |
| 2. Would you send this unedited? | **no** | _open_ |
| Why | Same defect as plausible: a publisher's item in a catalogue's top three. | |

## https://www.eff.org

Score **56/100 (fair)** over 8 pages, evidence CURRENT.

Categories: citability 65, content 58, platform 39, schema 0, technical 89

Ordered for: publisher

Top three fixes as ranked by the tool:

1. **Little usable content is present in the HTML the crawler receives** — high, high effort, 2 page(s)
2. **Authorship is not machine-readable** — high, medium effort, 8 page(s)
3. **The page carries no structured data** — high, medium effort, 8 page(s)

| Question | Maintainer | Practitioner |
|---|---|---|
| 1. Are these the right three? | **mostly** | _open_ |
| Why | Authorship and structured data are right for a publisher. Extractability leads by design because it is a blocker, but on two pages of eight it reads large. | |
| 2. Would you send this unedited? | **with small edits** | _open_ |
| Why | Framing only: nothing names what the site does well. | |

## https://developer.mozilla.org

Score **57/100 (fair)** over 8 pages, evidence CURRENT.

Categories: citability 69, content 45, platform 59, schema 0, technical 92

Ordered for: docs

Top three fixes as ranked by the tool:

1. **The page carries no structured data** — high, medium effort, 7 page(s)
2. **Authorship is not machine-readable** — medium, medium effort, 7 page(s)
3. **Pages do not say when they were last checked** — medium, low effort, 7 page(s)

| Question | Maintainer | Practitioner |
|---|---|---|
| 1. Are these the right three? | **no** | _open_ |
| Why | Authorship first on a reference site. One level down was not enough - nearly everything else on MDN was already medium, and authorship won that band on an impact the kind mismatch inflates. | |
| 2. Would you send this unedited? | **no** | _open_ |
| Why | Its own 404 page was scored and listed on every finding, and the homepage was crawled twice - fetched once through the redirect and once from the sitemap. | |

## Outcome

**This dry run does not count toward the 1.0 gate, and was not meant to.** It was run to
find defects before a practitioner spends time on them, and it found seven; fixing them
changed the tool. The counted round three runs the harness again, on unchanged code,
with the practitioner.

- Reports the **maintainer** would send unedited: **0 of 5** as run - two close, three
  not, all three for reasons below.
- Reports the **practitioner** would send unedited: _open_. Still the gate.

The site sample stayed the same as round two on purpose, so the first run with site
kinds could be read against the last run without them. Each site now carries a `kind`.

### Changes made as a result

1. **The saas, ecommerce and local tables did not defer authorship.** Round two had
   *Authorship is not machine-readable* in the top three on all five sites and first on
   three. The signal scores per-page bylines and Person markup, which only a publisher is
   expected to carry. Every kind but publisher now defers it.
2. **A deferred finding fell one level, which was not enough.** On MDN it dropped to
   medium and stayed third, because nearly everything else was already medium and it won
   that band on an impact the kind mismatch inflates. It now falls two.
3. **Documentation did not lead with llms.txt**, which was proposed for documentation
   sites. `docs` and `spec` now lead it.
4. **A start URL that redirects into the sitemap was crawled twice.** MDN's root redirects
   to `/en-US/`, which the sitemap lists: one page, two requests, scored twice, so the
   homepage carried double weight in every average and the report said "8 pages scored"
   over seven. Pages are now deduplicated on where they landed. The shape is any apex,
   `www` or locale redirect - most sites.
5. **A soft 404 was scored as content.** MDN serves `/en-US/404` with 200, *Page not found*
   and 58 characters. It is now recorded as a failed page with its own finding, and a
   short page only counts as one when its title or first heading says it is missing.
6. **Pages with nothing to read were listed on site-wide findings.** The soft 404 turned up
   on the llms.txt finding, and the fixture's own 404 had been listed on llms.txt and feeds
   all along. Such a page is now named only on findings about its response. No score moved.
7. **Two findings named their own severity.** MDN's report put *high* beside "which is why
   this is medium". Severity moves with a site kind and the page-level cap; the text no
   longer says which level it sits at.

With the changes, from the same crawl data: authorship moves from first to fifth on
plausible, second to twelfth on adafruit and first to thirteenth on MDN, and stays first
and second on the two publishers. MDN re-crawled scores 60 rather than 57, over seven
distinct readable pages.

### Still open, and now said three times

**The reports say only what is wrong.** Round two's note - a 76 with no acknowledgement
of why reads as grudging - applies to every report here. Nothing in the document names
what a site already does well, which is the first thing a practitioner adds by hand. It
is a new report section, not a fix, so it is listed rather than built: it is the next
thing to ask the practitioner about.

*Resolved since:* built the same day as the second deliberate exception to the 0.4.0
feature freeze - *What is already working*, in every report (`eefcd64`, and the PRD's
0.4.0 section).
