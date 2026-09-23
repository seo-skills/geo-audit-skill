# Scoring methodology

## What a GEO score is, and is not

It is a measurement of how *liftable* a page is: whether an engine can take a passage
and use it as an answer without rewriting the context around it. That is a property of
structure and evidence, and it is computable.

It is **not** a prediction of citation share. Nobody outside the engine operators can
measure that from the outside, and a number that implied otherwise would be the most
misleading thing this tool could ship. Live citation measurement is the strongest
candidate for a post-1.0 direction, and it will be a separate, `live`-class signal
with its own `observed_at` when it arrives.

## Why the arithmetic is in code

The number comes from a scorer, not from a model reading a rubric. A prompt that
computes a score produces a different number on Tuesday, and there is no way to show
anyone why. So:

* the CLI computes, the model explains;
* weights, thresholds and tier boundaries live in `data/`, not in code and not in
  prose;
* every envelope carries `scoring_version`, `data_version` and `normalizer_version`,
  so any number can be traced to the constants that produced it;
* `geo compare` refuses to compare runs whose `scoring_version` major or
  `data_version` differ.

## How the composite is formed

```
composite = round( sum(earned over computed signals) / sum(max over computed signals) * 100 )
```

Three consequences worth stating plainly:

1. **Advisory signals are excluded by construction.** `composite()` filters on signal
   class. There is no flag that includes them.
2. **A null signal leaves both sides.** Installing the browser extra can move a score,
   because it adds a measurement. `completeness` says how many signals a score was
   taken over, and reports say it too.
3. **There is one pipeline.** A missing capability nulls specific signals. It never
   selects a different scorer.

## What a kind of site changes

`geo report --site-kind` orders a report for what the site is for - `docs`, `spec`,
`publisher`, `saas`, `ecommerce` or `local`. It changes the **order and severity of
findings, and nothing else**: points lost, impact, every category score and the
composite are identical for every kind, so one site has one score however it is read.

A kind moves the findings it leads with up one severity level, never as far as
critical, and the ones it defers down two; the ordinary order then applies. A deferred
signal falls further than a led one rises because its points lost are inflated by the
kind not fitting - a reference site scores near zero on bylines it was never going to
carry - and one level left it winning its new band on that number. Blocking
findings never move, and a finding about a minority of pages keeps its ceiling. The
table is `data/site_kinds.json`. It is applied when a report is rendered rather than
when the audit runs, because the kind is read *from* the audit: the audit stays a
measurement that knows nothing about intent.

## Version policy

| Version | Bumps when | Effect |
|---|---|---|
| `schema_version` | an envelope field is removed or renamed | announced two releases ahead; additive changes do not bump it |
| `scoring_version` | the formula changes; a major bump when the composite of a site that did not change would move | `compare` refuses across a major change |
| `data_version` | a weight, threshold, tier or crawler token changes | ships as a patch release; pinning data means pinning the package |
| `normalizer_version` | extraction changes | every evidence hash moves, by design |

## Current constants

<!-- generated:constants:begin -->
*Generated from `data/` at data_version 2026.09, scoring_version 4.0, normalizer_version 3, schema_version 1.*

### Tiers

| Score | Label | What it means |
|---|---|---|
| 85–100 | excellent | AI engines can lift answers from this page with almost no rewriting. |
| 70–84 | good | Most passages are quotable as-is; a few sections still need context to stand alone. |
| 55–69 | fair | An engine can find an answer here, but it has to reassemble it from several places. |
| 35–54 | weak | Answers exist on the page but are buried in context that does not travel. |
| 0–34 | poor | There is little here an engine can quote without inventing the surrounding meaning. |

### Thresholds

| Signal | Threshold | Value |
|---|---|---|
| answer_first | `filler_openers` | 18 entries |
| answer_first | `floor_ratio` | 0.2 |
| answer_first | `good_ratio` | 0.75 |
| answer_first | `max_lead_words` | 45 |
| articles | `index_min_children` | 5 |
| attribution | `points` | 5 entries |
| content | `depth` | 3 entries |
| content | `freshness` | 2 entries |
| content | `readability` | 4 entries |
| evidence_density | `floor_ratio` | 0.05 |
| evidence_density | `good_external_domains` | 3 |
| evidence_density | `good_ratio` | 0.35 |
| extractability | `empty_framework_root_chars` | 50 |
| extractability | `good_content_chars` | 3000 |
| extractability | `good_content_ratio` | 0.25 |
| extractability | `min_content_chars` | 1200 |
| extractability | `structured_bonus_lists` | 1 |
| extractability | `structured_bonus_tables` | 1 |
| fetch | `soft_404` | 1 entries |
| findings | `full_severity_below` | 0.4 |
| findings | `no_finding_above` | 0.7 |
| findings | `severity_ladder` | 4 entries |
| findings | `strength_at_least` | 0.9 |
| render_parity | `floor_ratio` | 0.5 |
| render_parity | `good_ratio` | 0.9 |
| self_containment | `dangling_openers` | 36 entries |
| self_containment | `floor_ratio` | 0.3 |
| self_containment | `good_ratio` | 0.85 |
| self_containment | `min_block_words` | 12 |
| structure | `max_section_words` | 400 |
| structure | `min_h2` | 3 |
| structure | `min_headings` | 4 |

### AI crawler tokens

`critical` marks a token whose refusal directly costs visibility in an answer surface, as opposed to refusing model training.

| Token | Operator | Purpose | Critical | Gates |
|---|---|---|---|---|
| `GPTBot` | OpenAI | model training | no | presence in future OpenAI model weights |
| `OAI-SearchBot` | OpenAI | search index | yes | appearing in ChatGPT search results |
| `ChatGPT-User` | OpenAI | user-triggered browsing | yes | ChatGPT reading the page when a user links it |
| `PerplexityBot` | Perplexity | search index | yes | being cited in Perplexity answers |
| `Perplexity-User` | Perplexity | user-triggered browsing | yes | Perplexity opening the page for a user |
| `ClaudeBot` | Anthropic | model training | no | presence in future Claude model weights |
| `Claude-SearchBot` | Anthropic | search index | yes | appearing in Claude's search results |
| `Claude-User` | Anthropic | user-triggered browsing | yes | Claude reading the page when a user links it |
| `Google-Extended` | Google | Gemini and Vertex grounding | yes | use as a grounding source for Gemini |
| `Googlebot` | Google | search index | yes | Google Search and AI Overviews, both of which source from the index |
| `Bingbot` | Microsoft | search index | yes | Bing and Copilot, which source from the Bing index |
| `Applebot` | Apple | search index | no | Siri and Spotlight suggestions |
| `Applebot-Extended` | Apple | model training | no | use in Apple foundation models |
| `meta-externalagent` | Meta | model training and indexing | no | use by Meta AI |
| `Amazonbot` | Amazon | search index | no | Alexa answers |
| `CCBot` | Common Crawl | open web corpus | no | inclusion in the corpus most open models train on |
<!-- generated:constants:end -->
