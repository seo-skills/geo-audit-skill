# Command reference

Generated from the argument parser at version 0.1.0. Do not edit by hand; run `python tools/gen_docs.py`.

```
usage: geo [-h] [--version] COMMAND ...

Deterministic GEO audits. Every number traces to recorded evidence.

positional arguments:
  COMMAND
    fetch     report what a crawler sees on one page
    score     score the citability of one page
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
| `GEO_E_CONNECT` | 3 | The connection was refused or reset. Check the URL, the port, and any proxy or VPN on this machine. |
| `GEO_E_DNS` | 3 | The hostname did not resolve. Check for a typo, or whether the domain is reachable from this machine. |
| `GEO_E_INTERNAL` | 1 | This is a bug in geo-audit-cli. The log names the failing step; please open an issue with it. |
| `GEO_E_PARTIAL` | 5 | Some pages could not be evaluated. Drop --fail-on-partial to accept a partial result, or fix the blocked pages listed in the findings. |
| `GEO_E_PRIVATE_ADDRESS` | 2 | This host resolves to a private, loopback or link-local address. Auditing localhost or a staging host is legitimate: re-run with --allow-private to opt in. |
| `GEO_E_REDIRECT_BLOCKED` | 3 | A redirect pointed at a private, loopback or link-local address, which is never followed. Use --allow-private only if you control the whole chain. |
| `GEO_E_STATE_NEWER` | 4 | Upgrade with `uv tool upgrade geo-audit-cli`. Nothing was changed. |
| `GEO_E_STATE_UNREADABLE` | 4 | Check permissions on GEO_HOME (it should be mode 0700 and owned by you), then run `geo doctor`. |
| `GEO_E_STATE_WRITE` | 4 | GEO_HOME could not be written. Check disk space and permissions, then run `geo doctor`. |
| `GEO_E_TIMEOUT` | 3 | Check the URL, or try again. Raise the budget with --timeout if the host is simply slow. |
| `GEO_E_TLS` | 3 | The TLS handshake failed. If the certificate is genuinely expired or self-signed, fix the site rather than the audit. |
| `GEO_E_TOO_LARGE` | 3 | The response exceeded the size cap. Raise it with --max-bytes if the page really is that large. |
| `GEO_E_TOO_MANY_REDIRECTS` | 3 | The redirect chain exceeded the cap. A redirect loop is itself a crawlability defect worth fixing. |
