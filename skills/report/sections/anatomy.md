# What is in the report, and how it behaves

## Section order

The document runs in reader order rather than audit order: where do I stand, what is
it costing me, what do I do on Monday.

1. **The answer.** Brand header, site, date, the score as a number and a tier label
   together, one sentence on what that tier means, which kind of site it was ordered
   for if one was given, then what is already working, what stands out and what to do
   in order. *What is already working* names up to three strong signals from different
   categories, and never one the report has a finding about; a site with none gets no
   section rather than an empty one.
2. **Category scores.** Number and rating together, with the weight each carried.
3. **Everything found**, grouped by category, each with its pages and its remediation.
4. **Advisory analysis**, visually distinct, stated as judgement, excluded from every
   number above it.
5. **How this was measured.** Categories, weights, signal classes, comparability.
6. **Provenance** - operator copy only.

## Rules the layout follows

- **A score never appears without its label.** Colour is a third channel on top of the
  number and the word, never the only one carrying the verdict. Severity-coloured
  blocks also say the severity in text.
- **One column, no card mosaic.** The document is read top to bottom and printed.
- **One breakpoint**, at 390 pixels. Tables become stacked rows with their labels.
- **Single self-contained file.** The stylesheet is inlined and there is no script
  tag. It survives being emailed, opened offline and forwarded.
- **Print rules are real.** A4 with margins, page numbers in the footer, findings and
  table rows set not to break across pages, and the provenance section starting on a
  new page. Links print their URLs.

## Contrast

Body text, muted text, header text and accent text are each measured against their
background, and the ratios are in the operator copy. The accent is the one that fails
in practice: a bright brand colour used for small text on white is frequently below
the 4.5:1 AA minimum, and when it is, the default is substituted and the substitution
is announced.

The header keeps the brand colour. Text on it is chosen automatically between black
and white, and that choice always clears AA, so a brand is never rejected outright for
being bright.

## PDF

Rendered by printing the HTML through the browser, so the print stylesheet is what
decides page breaks. Without the browser extra the HTML is still written and the
command says the PDF was skipped and how to enable it. The HTML is the guaranteed
artifact; the PDF is the convenience.

## The output path

`~/.geo/projects/<slug>/reports/<date>-<hash8>.html`, where the hash is the evidence
hash of the run being rendered. Two reports of the same run on the same day do not
overwrite each other; the second gets a suffix. `--out` overrides the path entirely.
