# The practitioner eval

The scores in this tool are reproducible. Reproducible is not the same as
**useful**, and no test in the suite can tell the difference. This is the only
check that can, and it is the gate on 1.0.

## The protocol

Per minor release, on five real sites:

1. Run `python tests/evals/run_eval.py --sites tests/evals/sites.json`. It audits each
   site at the default polite crawl rate, writes both report copies for each, and
   emits a blank scoring form under `tests/evals/results/`. **Question 2 is about the
   client copy** - the one a client would receive. Rounds one and two linked only the
   operator copy, whose run ids and evidence hashes would never be sent to anyone.
2. **The maintainer** and **one practitioner who does not work on this tool** each
   answer two questions per site, independently, without seeing the other's answers.
3. Both sets of answers are committed as a single results file.

## The two questions

**1. Are these the right three?**
Look at the top three fixes. Would you have put those three at the top, in roughly
that order, having read the site yourself?

`yes` · `mostly` (right items, wrong order) · `no` (wrong items)

**2. Would you send this report unedited?**
Not "is it accurate" - would you attach it to an email to a paying client, as it is.

`yes` · `with small edits` · `no`

Both answers need one sentence of reasoning. A `yes` with no reasoning is not a data
point, and a `no` without a reason cannot be acted on.

## A round that changes the tool does not count

The gate is two **consecutive** rounds. A round that finds a defect and fixes it tested
a different tool than the one it finished with, so the counter starts again from the
next run against unchanged code.

This is not bookkeeping pedantry. Round two moved two of five scores by 24 and 10
points after a normalizer fix; counting it would have meant claiming a result for a
version that no longer exists.

## What the answers are for

The second question is the 1.0 gate: **two consecutive evals where the outside
practitioner would send at least four of five reports unedited.**

The first question is diagnostic. A run of `mostly` means the findings are right and
the ranking is wrong, which is a weights problem and is cheap to fix. A run of `no`
means the signals are measuring things that do not matter, which is not.

## Choosing the sites

**Vary the shape.** Round one ran five technical and specification sites and every
report had the same top two, which said more about the sample than the tool. Round two
ran a SaaS site, a publisher, an ecommerce catalogue, a non-profit and a reference
site, and the differences appeared immediately: schema scores went from 0 everywhere to
a range of 0 to 65.

Five sites the practitioner knows well enough to disagree with the tool about. Mixed
shapes: a documentation site, a marketing site, an ecommerce category, a publisher, a
small business. Avoid sites owned by anyone answering the questions - the point is
judgement about a report, not about a site someone is proud of.

Be a polite guest. The harness uses the default one request per second and caps the
crawl, and every site in `sites.json` should be one you would be comfortable telling
the owner you had crawled.

## Recording a result

Results are markdown, committed under `results/`, named `eval-<YYYY-MM-DD>.md`, and
they record the tool version, the scoring and data versions, both sets of answers, and
what changed as a result. An eval that changes nothing is still worth recording: it is
evidence that the last change did not break anything.
