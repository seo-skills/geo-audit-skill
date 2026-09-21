# Quickstart

## Install

```bash
uv tool install seomator-geo-audit
```

`pipx install seomator-geo-audit` works too. Python 3.11 or newer. No browser needed.

## Check the install

```bash
geo doctor
```

`doctor` reports and never gates: it always exits 0. Warnings are facts about this
machine, not defects. The two worth acting on:

* **Two executables named geo** — PATH order decides which one runs.
* **GEO_HOME on a sync drive** — audit history is append-only and assumes one writer.

## Score one page

```bash
geo score https://example.com/pricing
```

The documented first success: one page, no crawl, no browser, under thirty seconds.
You get a citability score out of 100 with its tier label, the seven signals behind
it, and the fixes ranked by what each recovers.

## Audit a site

```bash
geo audit https://example.com
```

Crawls up to 50 pages at one request per second across the whole crawl, respects
robots.txt for every link it discovers, and scores five categories over what it found.
Add `--brand "Acme"` to bring the sixth, brand presence, into scope.

The result is recorded. That matters more than it sounds:

```bash
geo audit https://example.com --rescore <run_id>
```

recomputes the same number and the same findings from the record with no network at
all. Two rescores are byte-identical. This is what makes a score you sent three months ago defensible today.

## Send someone a report

```bash
geo report https://example.com                      # client copy
geo report https://example.com --mode operator      # adds provenance
geo report https://example.com --pdf                # and a PDF
```

Client is the default because it is the one that gets sent. Operator adds run ids,
evidence hashes, the failed-page table and every signal's class and value. The two are
separate render contexts, so operator data cannot reach a client report.

With agency branding:

```bash
cat > brand.json <<'JSON'
{ "name": "Acme Digital", "primary": "#0B5FFF", "logo": "https://acme.test/logo.png" }
JSON
geo report https://example.com --brand-config brand.json --pdf
```

If a brand colour cannot carry readable text, the default is substituted and the
substitution is announced on stderr and in the operator copy.

## Show what changed

```bash
geo audit https://example.com     # ... do the work ...
geo audit https://example.com
geo compare https://example.com
```

Score movement by category, which findings were resolved or introduced, and which
pages actually changed by content hash. It refuses to compare runs scored under
different rules, because that difference would measure the tool rather than the site.

## The single-purpose commands

```bash
geo fetch https://example.com/page       # what a crawler sees on one page
geo crawl https://example.com            # what a crawler can reach, unscored
geo validate https://example.com --suggest   # structured data, node by node
geo llmstxt https://example.com --generate   # check or build an llms.txt
geo scan "Acme" --site https://example.com   # brand presence
```

## Housekeeping

```bash
geo prune --dry-run     # what the retention rules would remove
geo prune               # remove it
```

## Auditing something private

```bash
geo score http://localhost:3000/docs --allow-private
```

Private, loopback and link-local addresses are refused by default, because a crawler
that follows a public URL into a private network is the classic SSRF shape. Auditing
your own staging host is legitimate, so it is one flag away.

## Where things are kept

```
~/.geo/                          (override with $GEO_HOME)
  state.json                     state version
  logs/last-run.log              the last failure, in detail
  projects/<slug>/audits.jsonl   append-only history, one record per run
  projects/<slug>/reports/       rendered reports
```

Mode 0700. Nothing is written outside it unless you pass `--out`.

## Next

* [Command reference](commands.md)
* [What each signal measures](concepts/signals.md)
* [How evidence works](concepts/evidence.md)
* [Where this differs from other tools, and why](concepts/score-divergence.md)
* [Troubleshooting](troubleshooting.md)
