# Command reference

Generated from the argument parser at version 0.2.0. Do not edit by hand; run `python tools/gen_docs.py`.

```
usage: geo [-h] [--version] COMMAND ...

SEOmator GEO Audit Skill. Deterministic GEO audits: every number traces to
recorded evidence.

positional arguments:
  COMMAND
    fetch     report what a crawler sees on one page
    crawl     map what a crawler can reach on a site
    audit     crawl a site and score every category over it
    score     score the citability of one page
    compare   what changed between two recorded audits
    validate  check the structured data on one page
    llmstxt   check for an llms.txt, or build one from the site
    scan      check whether a brand exists as a lookupable entity
    prune     apply the retention rules to recorded history
    doctor    check this installation and its environment

options:
  -h, --help  show this help message and exit
  --version   show program's version number and exit
```

## `geo fetch`

Fetch one page and report derived facts: status, redirect chain, content blocks, evidence hash, robots access. Never returns page text.

```
usage: geo fetch [-h] [--json] [--out PATH] [--config PATH] [--no-input]
                 [--quiet] [--verbose] [--allow-private] [--fail-on-partial]
                 [--timeout SECONDS] [--max-bytes BYTES] [--no-robots]
                 url

Fetch one page and report derived facts: status, redirect chain, content
blocks, evidence hash, robots access. Never returns page text.

positional arguments:
  url                an absolute http:// or https:// URL

options:
  -h, --help         show this help message and exit
  --json             force JSON output
  --out PATH         also write the JSON envelope here
  --config PATH      JSON file of default flag values
  --no-input         never prompt (reserved: this release never prompts)
  --quiet            suppress progress on stderr
  --verbose          more progress on stderr
  --allow-private    permit a private, loopback or link-local start URL
  --fail-on-partial  exit 5 when the result is PARTIAL
  --timeout SECONDS
  --max-bytes BYTES
  --no-robots        skip the robots.txt lookup
```

## `geo crawl`

Crawl a site and report the frontier: pages fetched, pages that failed and why, pages robots.txt put out of reach, and pages found only in the sitemap. Nothing is scored; `geo audit` does that.

```
usage: geo crawl [-h] [--json] [--out PATH] [--config PATH] [--no-input]
                 [--quiet] [--verbose] [--allow-private] [--fail-on-partial]
                 [--timeout SECONDS] [--max-bytes BYTES] [--no-robots]
                 [--max-pages N] [--rate PER_SECOND] [--concurrency N]
                 [--no-sitemap]
                 url

Crawl a site and report the frontier: pages fetched, pages that failed and
why, pages robots.txt put out of reach, and pages found only in the sitemap.
Nothing is scored; `geo audit` does that.

positional arguments:
  url                an absolute http:// or https:// URL

options:
  -h, --help         show this help message and exit
  --json             force JSON output
  --out PATH         also write the JSON envelope here
  --config PATH      JSON file of default flag values
  --no-input         never prompt (reserved: this release never prompts)
  --quiet            suppress progress on stderr
  --verbose          more progress on stderr
  --allow-private    permit a private, loopback or link-local start URL
  --fail-on-partial  exit 5 when the result is PARTIAL
  --timeout SECONDS
  --max-bytes BYTES
  --no-robots        skip the robots.txt lookup
  --max-pages N      stop after N pages (default 50)
  --rate PER_SECOND  requests per second across the whole crawl, not per
                     worker (default 1)
  --concurrency N    pages in flight at once (default 5); the rate limit still
                     governs throughput
  --no-sitemap       do not seed the frontier from the sitemaps robots.txt
                     advertises
```

## `geo audit`

Crawl a site and score citability, technical and schema over every page. The composite weights the categories that were computed; one that was not leaves both sides of the fraction rather than scoring zero.

```
usage: geo audit [-h] [--json] [--out PATH] [--config PATH] [--no-input]
                 [--quiet] [--verbose] [--allow-private] [--fail-on-partial]
                 [--timeout SECONDS] [--max-bytes BYTES] [--no-robots]
                 [--max-pages N] [--rate PER_SECOND] [--concurrency N]
                 [--no-sitemap] [--only CATEGORY[,CATEGORY]] [--brand NAME]
                 [--rescore RUN_ID]
                 url

Crawl a site and score citability, technical and schema over every page. The
composite weights the categories that were computed; one that was not leaves
both sides of the fraction rather than scoring zero.

positional arguments:
  url                   an absolute http:// or https:// URL

options:
  -h, --help            show this help message and exit
  --json                force JSON output
  --out PATH            also write the JSON envelope here
  --config PATH         JSON file of default flag values
  --no-input            never prompt (reserved: this release never prompts)
  --quiet               suppress progress on stderr
  --verbose             more progress on stderr
  --allow-private       permit a private, loopback or link-local start URL
  --fail-on-partial     exit 5 when the result is PARTIAL
  --timeout SECONDS
  --max-bytes BYTES
  --no-robots           skip the robots.txt lookup
  --max-pages N         stop after N pages (default 50)
  --rate PER_SECOND     requests per second across the whole crawl, not per
                        worker (default 1)
  --concurrency N       pages in flight at once (default 5); the rate limit
                        still governs throughput
  --no-sitemap          do not seed the frontier from the sitemaps robots.txt
                        advertises
  --only CATEGORY[,CATEGORY]
                        score only these categories (citability, technical,
                        schema, brand)
  --brand NAME          also score brand presence for this name, folding it
                        into the composite
  --rescore RUN_ID      recompute from a recorded audit instead of crawling;
                        no network is used
```

## `geo score`

Score one page for citability. No crawl, no browser required.

```
usage: geo score [-h] [--json] [--out PATH] [--config PATH] [--no-input]
                 [--quiet] [--verbose] [--allow-private] [--fail-on-partial]
                 [--timeout SECONDS] [--max-bytes BYTES] [--no-robots]
                 [--no-render]
                 url

Score one page for citability. No crawl, no browser required.

positional arguments:
  url                an absolute http:// or https:// URL

options:
  -h, --help         show this help message and exit
  --json             force JSON output
  --out PATH         also write the JSON envelope here
  --config PATH      JSON file of default flag values
  --no-input         never prompt (reserved: this release never prompts)
  --quiet            suppress progress on stderr
  --verbose          more progress on stderr
  --allow-private    permit a private, loopback or link-local start URL
  --fail-on-partial  exit 5 when the result is PARTIAL
  --timeout SECONDS
  --max-bytes BYTES
  --no-robots        skip the robots.txt lookup
  --no-render        skip JavaScript rendering even when Playwright is
                     installed
```

## `geo compare`

Subtract one recorded audit from another: composite and category movement, which findings were resolved or introduced, and which pages changed. No network is used. Refuses to compare runs scored under different rules.

```
usage: geo compare [-h] [--json] [--out PATH] [--config PATH] [--no-input]
                   [--quiet] [--verbose] [--allow-private] [--fail-on-partial]
                   [--from RUN_ID] [--to RUN_ID]
                   url

Subtract one recorded audit from another: composite and category movement,
which findings were resolved or introduced, and which pages changed. No
network is used. Refuses to compare runs scored under different rules.

positional arguments:
  url                the site whose history to compare

options:
  -h, --help         show this help message and exit
  --json             force JSON output
  --out PATH         also write the JSON envelope here
  --config PATH      JSON file of default flag values
  --no-input         never prompt (reserved: this release never prompts)
  --quiet            suppress progress on stderr
  --verbose          more progress on stderr
  --allow-private    permit a private, loopback or link-local start URL
  --fail-on-partial  exit 5 when the result is PARTIAL
  --from RUN_ID      the earlier run
  --to RUN_ID        the later run
```

## `geo validate`

Report the JSON-LD on a page node by node: what types it declares, which required and recommended properties are missing, and whether it parses at all.

```
usage: geo validate [-h] [--json] [--out PATH] [--config PATH] [--no-input]
                    [--quiet] [--verbose] [--allow-private]
                    [--fail-on-partial] [--timeout SECONDS]
                    [--max-bytes BYTES] [--no-robots] [--suggest]
                    url

Report the JSON-LD on a page node by node: what types it declares, which
required and recommended properties are missing, and whether it parses at all.

positional arguments:
  url                an absolute http:// or https:// URL

options:
  -h, --help         show this help message and exit
  --json             force JSON output
  --out PATH         also write the JSON envelope here
  --config PATH      JSON file of default flag values
  --no-input         never prompt (reserved: this release never prompts)
  --quiet            suppress progress on stderr
  --verbose          more progress on stderr
  --allow-private    permit a private, loopback or link-local start URL
  --fail-on-partial  exit 5 when the result is PARTIAL
  --timeout SECONDS
  --max-bytes BYTES
  --no-robots        skip the robots.txt lookup
  --suggest          emit JSON-LD built from what the page already states
```

## `geo llmstxt`

Look for /llms.txt and /llms-full.txt and check their structure against the llmstxt.org format. With --generate, crawl the site and build one from the pages that were actually fetched.

```
usage: geo llmstxt [-h] [--json] [--out PATH] [--config PATH] [--no-input]
                   [--quiet] [--verbose] [--allow-private] [--fail-on-partial]
                   [--timeout SECONDS] [--max-bytes BYTES] [--no-robots]
                   [--max-pages N] [--rate PER_SECOND] [--concurrency N]
                   [--no-sitemap] [--generate]
                   url

Look for /llms.txt and /llms-full.txt and check their structure against the
llmstxt.org format. With --generate, crawl the site and build one from the
pages that were actually fetched.

positional arguments:
  url                an absolute http:// or https:// URL

options:
  -h, --help         show this help message and exit
  --json             force JSON output
  --out PATH         also write the JSON envelope here
  --config PATH      JSON file of default flag values
  --no-input         never prompt (reserved: this release never prompts)
  --quiet            suppress progress on stderr
  --verbose          more progress on stderr
  --allow-private    permit a private, loopback or link-local start URL
  --fail-on-partial  exit 5 when the result is PARTIAL
  --timeout SECONDS
  --max-bytes BYTES
  --no-robots        skip the robots.txt lookup
  --max-pages N      stop after N pages (default 50)
  --rate PER_SECOND  requests per second across the whole crawl, not per
                     worker (default 1)
  --concurrency N    pages in flight at once (default 5); the rate limit still
                     governs throughput
  --no-sitemap       do not seed the frontier from the sitemaps robots.txt
                     advertises
  --generate         crawl the site and propose an llms.txt
```

## `geo scan`

Query Wikipedia, Wikidata, Reddit and YouTube for a brand name through their documented public APIs. Platforms with no usable API are listed as manual checks and never reported as results.

```
usage: geo scan [-h] [--json] [--out PATH] [--config PATH] [--no-input]
                [--quiet] [--verbose] [--allow-private] [--fail-on-partial]
                [--site URL] [--timeout SECONDS]
                brand

Query Wikipedia, Wikidata, Reddit and YouTube for a brand name through their
documented public APIs. Platforms with no usable API are listed as manual
checks and never reported as results.

positional arguments:
  brand              the brand name to look for

options:
  -h, --help         show this help message and exit
  --json             force JSON output
  --out PATH         also write the JSON envelope here
  --config PATH      JSON file of default flag values
  --no-input         never prompt (reserved: this release never prompts)
  --quiet            suppress progress on stderr
  --verbose          more progress on stderr
  --allow-private    permit a private, loopback or link-local start URL
  --fail-on-partial  exit 5 when the result is PARTIAL
  --site URL         also read this site's Organization sameAs links and
                     compare them
  --timeout SECONDS
```

## `geo prune`

Trim the append-only audit history by count, age and size. Reports what it would remove before removing it.

```
usage: geo prune [-h] [--json] [--out PATH] [--config PATH] [--no-input]
                 [--quiet] [--verbose] [--allow-private] [--fail-on-partial]
                 [--project SLUG] [--keep N] [--older-than DAYS] [--dry-run]

Trim the append-only audit history by count, age and size. Reports what it
would remove before removing it.

options:
  -h, --help         show this help message and exit
  --json             force JSON output
  --out PATH         also write the JSON envelope here
  --config PATH      JSON file of default flag values
  --no-input         never prompt (reserved: this release never prompts)
  --quiet            suppress progress on stderr
  --verbose          more progress on stderr
  --allow-private    permit a private, loopback or link-local start URL
  --fail-on-partial  exit 5 when the result is PARTIAL
  --project SLUG     one project instead of all of them
  --keep N           keep at most N runs per project
  --older-than DAYS  drop runs older than DAYS
  --dry-run          report the plan and change nothing
```

## `geo doctor`

Report on the interpreter, PATH, state directory, data files and optional extras. Always exits 0: it reports, it does not gate.

```
usage: geo doctor [-h] [--json] [--out PATH] [--config PATH] [--no-input]
                  [--quiet] [--verbose] [--allow-private] [--fail-on-partial]

Report on the interpreter, PATH, state directory, data files and optional
extras. Always exits 0: it reports, it does not gate.

options:
  -h, --help         show this help message and exit
  --json             force JSON output
  --out PATH         also write the JSON envelope here
  --config PATH      JSON file of default flag values
  --no-input         never prompt (reserved: this release never prompts)
  --quiet            suppress progress on stderr
  --verbose          more progress on stderr
  --allow-private    permit a private, loopback or link-local start URL
  --fail-on-partial  exit 5 when the result is PARTIAL
```

## Exit codes

| Code | Meaning |
|---|---|
| 0 | OK, including PARTIAL results |
| 1 | internal error |
| 2 | usage error |
| 3 | network failure on the start URL |
| 4 | state error |
| 5 | `--fail-on-partial` was passed and the result is PARTIAL |

## Error codes

| Code | Exit | Hint |
|---|---|---|
| `GEO_E_BAD_ARGS` | 2 | Run the command with --help to see the accepted flags. |
| `GEO_E_BAD_CONTENT_TYPE` | 3 | Only HTML and XHTML are scored. Point the command at a page rather than at a PDF, image or feed. |
| `GEO_E_BAD_URL` | 2 | Pass an absolute http:// or https:// URL, for example `geo score https://example.com/pricing`. |
| `GEO_E_BLOCKED_SCHEME` | 2 | Only http:// and https:// are fetched. file://, data://, ftp:// and the rest are refused by design. |
| `GEO_E_CONNECT` | 3 | The message names which connection failure it was. Check the URL, the port, and any proxy or VPN on this machine. |
| `GEO_E_DNS` | 3 | The hostname did not resolve. Check for a typo, or whether the domain is reachable from this machine. |
| `GEO_E_INCOMPARABLE` | 2 | These runs were scored by different rules, so the difference between them would measure the tool rather than the site. Re-run the older URL to get a comparable pair. |
| `GEO_E_INTERNAL` | 1 | This is a bug in seomator-geo-audit. The log names the failing step; please open an issue with it. |
| `GEO_E_PARTIAL` | 5 | Some pages could not be evaluated. Drop --fail-on-partial to accept a partial result, or fix the blocked pages listed in the findings. |
| `GEO_E_PRIVATE_ADDRESS` | 2 | This host resolves to a private, loopback or link-local address. Auditing localhost or a staging host is legitimate: re-run with --allow-private to opt in. |
| `GEO_E_REDIRECT_BLOCKED` | 3 | A redirect pointed at a private, loopback or link-local address, which is never followed. Use --allow-private only if you control the whole chain. |
| `GEO_E_STATE_NEWER` | 4 | Upgrade with `uv tool upgrade seomator-geo-audit`. Nothing was changed. |
| `GEO_E_STATE_UNREADABLE` | 4 | Check permissions on GEO_HOME (it should be mode 0700 and owned by you), then run `geo doctor`. |
| `GEO_E_STATE_WRITE` | 4 | GEO_HOME could not be written. Check disk space and permissions, then run `geo doctor`. |
| `GEO_E_TIMEOUT` | 3 | Check the URL, or try again. Raise the budget with --timeout if the host is simply slow. |
| `GEO_E_TLS` | 3 | The TLS handshake failed. If the certificate is genuinely expired or self-signed, fix the site rather than the audit. |
| `GEO_E_TOO_LARGE` | 3 | The response exceeded the size cap. Raise it with --max-bytes if the page really is that large. |
| `GEO_E_TOO_MANY_REDIRECTS` | 3 | The redirect chain exceeded the cap. A redirect loop is itself a crawlability defect worth fixing. |
