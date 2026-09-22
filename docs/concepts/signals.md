# Signal inventory

Every signal is classified, and the class decides what it may do to a number.

| Class | Definition | May enter the composite |
|---|---|---|
| **deterministic** | A parsed fact about the document. Two runs over the same bytes agree by construction. | yes |
| **heuristic** | Code with stated weights and thresholds, all of them in `data/`. Arguable, but not arbitrary. | yes |
| **live** | Observed from a third-party API, carrying its own `observed_at`. | yes |
| **advisory** | Model judgment under a fixed rubric. | **no** |

Advisory output is displayed in its own clearly-labelled section and never summed
into a score. That exclusion is structural rather than a policy: `composite()` filters
on class, so there is no code path where a judgment becomes a number. This release
ships no advisory signals; the first arrive with `geo audit`.

## The categories

<!-- generated:signals:begin -->
*Generated from `data/weights.json` at data_version 2026.09.*

### citability (category weight 25)

| Signal | Class | Max | Requires | Question |
|---|---|---|---|---|
| `citability.self_containment` | heuristic | 25 | — | Does each passage name its own subject? |
| `citability.answer_first` | heuristic | 20 | — | Does each section lead with the answer? |
| `citability.structure` | deterministic | 15 | — | Do the headings segment the page into answerable parts? |
| `citability.evidence_density` | heuristic | 15 | — | Do claims carry numbers, dates and sources? |
| `citability.extractability` | deterministic | 15 | — | Is the content in the HTML a crawler receives? |
| `citability.attribution` | deterministic | 10 | an article | Does the page say who wrote it and when? |
| `citability.render_parity` | heuristic | 10 | browser | How much text appears only after JavaScript? |

Out of **110**, or **90** when the optional inputs are absent.

### brand (category weight 20)

| Signal | Class | Max | Requires | Question |
|---|---|---|---|---|
| `brand.encyclopedic` | live | 35 | — | Is there a Wikipedia article or a Wikidata item? |
| `brand.community` | live | 25 | — | Do people discuss it anywhere public? |
| `brand.video` | live | 20 | youtube_api_key | Is there video? Null without a YouTube API key. |
| `brand.consistency` | heuristic | 20 | site | Does the site link itself to those profiles? |

Out of **100**, or **60** when the optional inputs are absent.

### content (category weight 20)

| Signal | Class | Max | Requires | Question |
|---|---|---|---|---|
| `content.depth` | heuristic | 25 | — |  |
| `content.expertise` | deterministic | 25 | an article |  |
| `content.freshness` | deterministic | 25 | — |  |
| `content.readability` | heuristic | 25 | — |  |

Out of **100**, or **75** when the optional inputs are absent.

### technical (category weight 15)

| Signal | Class | Max | Requires | Question |
|---|---|---|---|---|
| `technical.crawler_access` | deterministic | 25 | — | Can the crawlers that gate an answer surface read it? |
| `technical.indexability` | deterministic | 20 | — | Does the page ask not to be indexed? |
| `technical.metadata` | deterministic | 20 | — | Title, description, lang, one H1, Open Graph, image alt. |
| `technical.status_health` | deterministic | 15 | — | Does the URL return 200 directly, or via hops? |
| `technical.transport_security` | deterministic | 10 | — | HTTPS, and HSTS on top of it. |
| `technical.url_structure` | heuristic | 10 | — | Depth, length, case, separators, session identifiers. |

Out of **100**.

### schema (category weight 10)

| Signal | Class | Max | Requires | Question |
|---|---|---|---|---|
| `schema.presence` | deterministic | 30 | — | Did the page attempt JSON-LD at all? |
| `schema.validity` | deterministic | 25 | — | Did the attempt succeed? |
| `schema.organization` | deterministic | 20 | — | Is there a machine-readable publisher, with sameAs? |
| `schema.article` | deterministic | 15 | an article | Are content pages dated and attributed? |
| `schema.breadth` | heuristic | 10 | — | Are there types that answer a question directly? |

Out of **100**, or **85** when the optional inputs are absent.

### platform (category weight 10)

| Signal | Class | Max | Requires | Question |
|---|---|---|---|---|
| `platform.llms_txt` | deterministic | 35 | — |  |
| `platform.social_cards` | deterministic | 30 | — |  |
| `platform.feeds` | deterministic | 20 | — |  |
| `platform.hreflang` | deterministic | 15 | more than one language |  |

Out of **100**, or **85** when the optional inputs are absent.

The category composite is `earned / max-of-computed * 100`, and the site composite weights the categories that were computed. A signal or a category that was not measured leaves both sides of its fraction. A signal that requires an article is scored on the pages that are articles - not on a home page, an index of the pages beneath it, a category, tag or author archive, a page declaring itself a product, an app or a profile, or, in an audit of a site that marks its articles, a page it left unmarked - and on a site where none is, it does not apply: it leaves the fraction and the completeness count alike.
<!-- generated:signals:end -->

Definitions, thresholds and the reasoning behind each live with the skill that
explains them - [citability](../../skills/citability/sections/signals.md),
[technical](../../skills/technical/sections/crawlers.md),
[schema](../../skills/schema/sections/types.md) - which is the same text the model
reads when a user disputes a number.

## Planned

Declared in `data/weights.json` under `planned_categories` so the divergence table can
reference them before they ship. They are absent from every computation until then,
and a run's coverage report names only the categories that run could reach.

| Category | Weight | Milestone |
|---|---|---|
| content | 20 | 0.3.0 |
| platform | 10 | 0.3.0 |

`brand` is computed, but only when its input is given: `geo scan <name>`, or
`geo audit <url> --brand <name>`. An audit of a URL alone has no brand name, so brand
is out of scope for that run rather than missing from it.

## Nullable signals

A signal returns `null` when it could not be computed — most often because the
optional browser extra is absent. Then:

* `completeness.computed` and `completeness.total` diverge, and
  `completeness.missing` names the signal.
* `completeness.categories` does the same one level up, naming which categories were
  computed and the weights used.
* The composite is taken over the signals that *were* computed, on both sides of the
  fraction.

`null` is never rendered as `0`. "We could not measure it" and "you failed it" are
different sentences and must be different numbers.
