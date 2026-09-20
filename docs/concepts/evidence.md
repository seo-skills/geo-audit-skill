# Evidence

A score means nothing without knowing what it was computed from. Every envelope
carries an `evidence` block, and every report footer carries the four versions that
produced it.

## The hash

```
SHA-256( normalizer_version + the extracted content-block sequence )
```

The blocks are the scorer's actual inputs: title, headings, paragraphs, list items,
table cells, in document order, each paired with its kind. Not the raw HTML, and not
the visible text — the normalized sequence.

### What deliberately does not change it

A page that is rebuilt without being rewritten must hash the same, or every report
goes stale for nothing and the stamp stops meaning anything. So the normalizer strips,
structurally:

* `<script>`, `<style>`, `<noscript>`, `<template>`, `<iframe>`, `<form>` and friends
* HTML comments
* `<nav>` and `<aside>` inside the content root
* site `<header>` and `<footer>` when there is no `<main>` or `<article>` to scope to
* elements whose class, id or role matches known chrome: ads, promos, cookie banners,
  share widgets, related-posts rails, breadcrumbs, pagination

The regression test for this is `ssr-rich.html` against `ssr-rich-variant.html`: the
two differ in CSP nonce, a "generated at" footer timestamp and the entire body of an
ad slot, and they hash identically.

### What does change it

Any change to the content blocks themselves — text, order, or the kind of element a
block came from — and any change to `normalizer_version`. The version is inside the
hash input rather than beside it, so a normalizer change can never be mistaken for a
content change.

## ETag and Last-Modified

Stored as metadata, used only as a revalidation shortcut (`If-None-Match` → 304 means
"skip the download"). **Not part of hash identity.** They change on every redeploy
even when the content is identical, and flipping a client's report to STALE because
someone pushed a CSS fix is exactly the noise block-hashing exists to remove.

## Stamps

| Stamp | Meaning |
|---|---|
| `CURRENT` | Every page in scope was fetched and scored in this run. |
| `PARTIAL` | Some pages could not be evaluated. They are enumerated in `evidence.pages_failed` with a reason. |
| `STALE` | The evidence predates changes to the pages it covers. |

`PARTIAL` is read from `evidence.stamp`, never inferred from the exit code. A partial
audit exits 0 unless you asked for `--fail-on-partial`.

## Retention

Derived signals, counts, and length-capped excerpts. **No raw HTML is written to
disk.** An audit record is roughly the size of the envelope you saw, which is a few
kilobytes, not a page.

## Validating an envelope

The envelope shape is published as a JSON Schema and shipped inside the package, so a
consumer validates against the version they installed rather than against `main`:

```python
import json
from importlib import resources
from jsonschema import Draft202012Validator

schema = json.loads(
    resources.files("geo_audit.assets").joinpath("envelope.schema.json").read_text()
)
Draft202012Validator(schema).validate(envelope)
```

`additionalProperties: false` at the top level is what makes `schema_version` a
promise rather than a label: a new top-level key fails validation, so adding one is a
deliberate edit to the schema with a version decision attached. Additive changes
*inside* the nested objects do not bump `schema_version`; removing or renaming a
top-level key does, and is announced two releases ahead.

Every command's output is validated against it in CI, including a failing run.

## Purity

`score(snapshot, scoring_version, data_version)` is a pure function. Reproducibility
is claimed for rescoring a recorded snapshot, not for re-crawling a live site, which
can legitimately differ — the site changed. `geo audit --rescore` arrives in 0.2.0 and
recomputes from the stored record with no network access.
