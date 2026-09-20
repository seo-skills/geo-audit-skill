# Quickstart

## Install

```bash
uv tool install geo-audit-cli
```

`pipx install geo-audit-cli` works too. Python 3.11 or newer. No browser needed.

## Check the install

```bash
geo doctor
```

`doctor` reports and never gates: it always exits 0. Warnings are facts about this
machine, not defects. The two worth acting on:

* **Two executables named geo** — PATH order decides which one runs.
* **GEO_HOME on a sync drive** — audit history is append-only and assumes one writer.

## Score a page

```bash
geo score https://example.com/pricing
```

You get a number out of 100 with its tier label, the seven signals behind it, and the
fixes ranked by what each recovers. One page, no crawl, under thirty seconds.

## Get JSON

```bash
geo score https://example.com/pricing --json > score.json
```

The `--json` flag is optional in a pipeline: output is JSON whenever stdout is not a
terminal. Progress goes to stderr, always, so redirecting stdout never loses it.

## Audit something private

```bash
geo score http://localhost:3000/docs --allow-private
```

Private, loopback and link-local addresses are refused by default, because a crawler
that follows a public URL into a private network is the classic SSRF shape. Auditing
your own staging host is a legitimate thing to want, so it is one flag away.

## Where things are kept

```
~/.geo/                        (override with $GEO_HOME)
  state.json                   state version
  logs/last-run.log            the last failure, in detail
  projects/<slug>/audits.jsonl append-only history, one record per run
```

Mode 0700. Nothing is written outside it unless you pass `--out`.

## What is in a record

Every run appends its whole envelope: the signals with their inputs, the score, the
findings, and the evidence hash. That is what makes a score defensible three months
later, when the page has changed and the client asks where the number came from.

```bash
tail -1 ~/.geo/projects/example-com/audits.jsonl | python -m json.tool | head -30
```

## Next

* [Command reference](commands.md)
* [What each signal measures](concepts/signals.md)
* [How evidence works](concepts/evidence.md)
* [Troubleshooting](troubleshooting.md)
