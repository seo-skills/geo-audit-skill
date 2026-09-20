# The advisory rubrics, and how to apply them

Two questions, each with three tests. Apply the tests to what is on the page, not to
how the page feels. The difference shows in what you can quote back.

<!-- generated:rubrics:begin -->
## `content.advisory.experience`

**Does the page show first-hand experience of the thing it describes?**

1. Names specific situations, tools, versions or constraints the author met.
2. Reports what happened, including what did not work.
3. Could not have been written by summarising other pages on the topic.

## `content.advisory.helpfulness`

**Would a reader with this question leave satisfied, or keep searching?**

1. Answers the question the title asks, rather than the adjacent easier one.
2. States limits and cases where the advice does not apply.
3. Does not require reading another page to be actionable.

*Generated from `data/weights.json` at data_version 2026.09. These are the questions the CLI emits; answering a different one is refused.*
<!-- generated:rubrics:end -->

## Verdicts

| Verdict | Means |
|---|---|
| `yes` | Every test in the rubric is met, and you can point at where. |
| `partial` | Some tests met, others not. The usual answer for competent content. |
| `no` | The page does not meet the rubric. |
| `unclear` | You could not tell from the page. Not a polite `no`: it means the evidence is absent either way. |

`partial` is the honest default for most pages and you should expect to use it most
often. A run of `yes` verdicts across a site usually means the rubric was not applied.

## How to write the note

Two or three sentences, and at least one of them quoting or naming something specific
on the page. Compare:

> **Weak:** The content shows reasonable expertise and covers the topic well.
>
> **Useful:** Names the exact Postgres version and the lock it hit, and says the first
> fix made throughput worse. Nothing about what they would do differently, so a reader
> in the same position still has to guess at the order of operations.

The second one can be checked by anyone with the page open. That is the bar.

## What not to do

- **Do not score.** No number, no grade, no percentage. The verdict vocabulary is
  fixed at four words for exactly this reason.
- **Do not infer experience from confidence.** Fluent writing about a topic is not
  evidence of having done it; specific friction is.
- **Do not penalise a page for being short** if it answers the question. Depth is
  measured separately, and by the CLI.
- **Do not answer from the URL, the title or the meta description.** If you have not
  read the content, the verdict is `unclear`.
