# What the site is for, and what that changes

The scorer measures every site against the same signals, because the signals are the
same. What a *recommendation* is worth is not the same, and the scorer has no way to
know that. You do.

This came out of both rounds of the practitioner eval, in the same words each time:
the tool applied a publisher's checklist to a specification document, and then to a
reference site. The numbers were right. The ordering of the advice was not.

## Working out the kind

Nothing in the envelope names the kind of site. Infer it, and say what you inferred so
the reader can correct you:

| Evidence | Where it is |
|---|---|
| Declared entity and content types | `jsonld_types` on each crawled page |
| URL shape - `/docs/`, `/blog/`, `/products/`, `/pricing` | `crawl.pages[].url` |
| Whether pages are dated | `content.freshness` - its `detail.mean` against its `max` |
| How uniform the pages are | any signal's `detail.min` against its `detail.max` |
| Which page is the outlier | `detail.worst_page` |
| Whether there is a catalogue | `schema.breadth`, and `Product` in the types |

A signal has two ceilings and they mean different things: `max` is the scale the
value is out of, `detail.max` is the best any single page managed.

Two or three of those agreeing is enough. If they disagree, say so and ask.

## What changes

**Documentation or reference** (`docs`). Lead with `citability.answer_first` and
`citability.structure`: a reference page is read one section at a time and an engine
lifts one section. `platform.llms_txt` leads too - documentation is what llms.txt was
proposed for. Machine-readable authorship matters least here - nobody asks who wrote
the syntax reference - so report `content.expertise` and do not lead with it.

**Specification or standard** (`spec`). Everything documentation leads with -
`citability.answer_first`, `citability.structure`, `platform.llms_txt` - and more so.
Authority comes from the document being the standard, not from a byline, so
`content.expertise` is deferred here too. Also lead with `citability.evidence_density`
and `schema.breadth`.

**Publisher or blog** (`publisher`). `content.expertise` and `content.freshness` are the whole game:
an engine choosing between two accounts of the same event picks the one it can date
and attribute. If the site has bylines in prose but nothing machine-readable, that is
the single highest-value fix and it is usually one template.

**SaaS marketing** (`saas`). Lead with `citability.self_containment` and
`citability.evidence_density`: marketing prose is where unsupported claims and
paragraphs that only make sense in sequence both concentrate. `schema.organization`
with `sameAs` matters more than average, because the brand needs to resolve to an
entity. Defer `content.expertise`: it scores per-page bylines and Person markup, which
marketing and product pages do not carry and should not be told to. Round two had it
first on a SaaS site.

**Ecommerce** (`ecommerce`). `schema.breadth` and `schema.validity` first: `Product` and `Offer`
markup is what gets a catalogue into an answer at all. Then
`citability.extractability`, because product pages are the most likely to be rendered
client-side. Defer `content.expertise` - a product page has no author.

**Local business** (`local`). `schema.organization` first, and say explicitly that it should be
`LocalBusiness` with an address and opening hours. `brand.consistency` matters more
here than anywhere else. Defer `content.expertise`, for the same reason as a shop.

**Agency or portfolio** (`saas`). Treat as SaaS marketing, and expect `content.depth` to be the
real problem: case studies that say what was achieved without saying what was done.

## Carrying it into the report

The same judgement is available to the report: `geo report <url> --site-kind <kind>`,
with the kind named in brackets above. It moves the findings a kind leads with up one
severity level and the ones it defers down two, never touches a blocker, and states
in the report which kind it was ordered for. Pass it, so the document that gets sent
agrees with what you said.

## What never changes

- **Never re-rank around a blocker.** If a crawler cannot fetch or index the page, that
  comes first whatever kind of site it is.
- **Never change a number.** You are reordering advice and adding context, not
  adjusting a score. The composite, the categories and the signal values are what they
  are.
- **Say what you assumed.** "Read as a documentation site, so I have put the
  authorship item last" is a sentence the reader can disagree with. Silently reordering
  is not.
