# What each category measures, and why it is weighted as it is

Read this when asked why a category scored what it did, or why the weights are what
they are. If these numbers disagree with the envelope, the envelope is right and this
file is stale; say so.

## The weights

| Category | Weight | Why |
|---|---|---|
| Citability | 25 | The thing the tool is named after: whether one passage can be lifted and used as an answer without rewriting the context around it. |
| Brand | 20 | Whether the name resolves to an entity at all. Only in scope when `--brand` is given. |
| Technical | 15 | Gating rather than additive. It cannot make a site good; it can make everything else irrelevant. |
| Schema | 10 | Cheap, mechanical, and the only part of a page nobody has to interpret. |

Content and platform categories are declared in `data/weights.json` and are not
computed yet. They are excluded from the composite by construction, not by an
oversight, and the coverage report names exactly which categories a run used.

## How the composite is formed

```
composite = sum(weight * category_score) / sum(weight over the categories computed)
```

So `--only technical` scores out of technical alone. A category the run's inputs could
not reach is out of scope, not a zero: an audit of a URL has no brand name, so brand
does not appear in its coverage at all.

## Reading a category score against the others

- **High technical, low citability** is the common shape. The site is reachable and
  well-formed, and reads like marketing. The work is editorial.
- **Low technical, high citability** means good writing nobody can fetch. Fix access
  first; the citability score is being computed on the pages that *did* load, and the
  ones that did not may be the important ones.
- **Schema near zero with everything else healthy** is the cheapest win on the board.
  It is usually one template change.
- **Brand low and everything else high** is not a site problem, and saying so is more
  useful than a task list. See the brand skill.

## Sequencing

Order the recommendations by dependency, not by score:

1. Anything in `technical.crawler_access` or `technical.indexability`. Nothing
   downstream matters while a crawler is being turned away.
2. `citability.extractability`. Prose on a page that arrives empty recovers nothing.
3. Schema, because it is mechanical and template-wide.
4. Editorial work on citability, which is the slowest and most valuable.
