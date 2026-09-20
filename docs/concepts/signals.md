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

## Citability (this release)

<!-- generated:signals:begin -->
*Generated from `data/weights.json` at data_version 2026.09.*

| Signal | Class | Max | Requires | Question |
|---|---|---|---|---|
| `citability.self_containment` | heuristic | 25 | — | Does each passage name its own subject? |
| `citability.answer_first` | heuristic | 20 | — | Does each section lead with the answer? |
| `citability.structure` | deterministic | 15 | — | Do the headings segment the page into answerable parts? |
| `citability.evidence_density` | heuristic | 15 | — | Do claims carry numbers, dates and sources? |
| `citability.extractability` | deterministic | 15 | — | Is the content in the HTML a crawler receives? |
| `citability.attribution` | deterministic | 10 | — | Does the page say who wrote it and when? |
| `citability.render_parity` | heuristic | 10 | browser | How much text appears only after JavaScript? |

Total when every signal is computed: **110**. Without the browser extra: **100**. The composite is `earned / max-of-computed * 100`, so a signal that was not measured leaves both sides of the fraction.
<!-- generated:signals:end -->

Definitions, thresholds and the reasoning behind each are in
[the skill's methodology section](../../skills/citability/sections/signals.md), which
is the same text the model reads when a user disputes a number.

## Planned

Declared in `data/weights.json` under `planned_categories` so the divergence table can
reference them before they ship. They are absent from every computation until then.

| Category | Weight | Milestone |
|---|---|---|
| technical | 15 | 0.2.0 |
| schema | 10 | 0.2.0 |
| brand | 20 | 0.2.0 |
| content | 20 | 0.3.0 |
| platform | 10 | 0.3.0 |

## Nullable signals

A signal returns `null` when it could not be computed — most often because the
optional browser extra is absent. Then:

* `completeness.computed` and `completeness.total` diverge, and
  `completeness.missing` names the signal.
* The composite is taken over the signals that *were* computed, on both sides of the
  fraction.

`null` is never rendered as `0`. "We could not measure it" and "you failed it" are
different sentences and must be different numbers.
