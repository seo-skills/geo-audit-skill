# Writing a progress report from a comparison

## Lead with the label

Tiers are what people remember and numbers are what they check. "Fair, up from Weak"
carries the whole result; "55 to 60" invites an argument about five points.

If the tier did not move, say that first too. A six-point rise inside one band is
progress that has not yet arrived, and framing it as a band change is the fastest way
to lose someone's trust on the next report.

## Separate the work from the drift

The comparison gives you both the findings that resolved and the pages that changed.
Read them together:

| Resolved | Pages changed | What it usually means |
|---|---|---|
| several | few | The work landed. Attribute it. |
| few | many | The site changed for other reasons and the score followed. Say so. |
| several | many | A release included the fixes. Credit the release, not the audit. |
| none | none | Nothing shipped. The report is one sentence long. |

The third row is the one people get wrong. If a redesign shipped in the same window,
the score moved for reasons nobody can separate, and claiming the GEO work did it is
a claim that will not survive the next quarter.

## Score movement that is not improvement

A composite can rise because:

- fewer pages were scored, so a weak section fell out of the crawl;
- a page that was returning 404 now returns 200 and nothing else changed;
- the crawl found the sitemap this time and picked up better pages.

Always report how many pages each run covered. A rise with fewer pages is a different
event from a rise with the same pages, and only one of them is progress.

## What to put in front of a client

1. The tier, then the number.
2. Two or three fixes that landed, named as the work, not as finding titles.
3. What is next, taken from the persisting findings ranked by the newer audit.
4. One sentence on coverage: how many pages, and whether that changed.

Leave the signal deltas out unless someone asks. They are for the operator.
