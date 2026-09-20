# Troubleshooting

Every exit code and every `GEO_E_*` code, mapped to a fix. The authoritative table is
generated into [commands.md](commands.md) from the code itself; this page adds the
context that does not fit in a hint.

## `geo: command not found`

The CLI is installed but not on PATH, or not installed.

```bash
uv tool install seomator-geo-audit        # or: pipx install seomator-geo-audit
uv tool update-shell                 # if uv says PATH needs updating
python -m geo_audit --version        # works without the console script
```

## Two executables named `geo`

`geo doctor` reports this as a warning with both paths. PATH order decides which one
runs, and the other one is often a different tool entirely — `geo` is a short name.
Either remove the one you do not want, or call this tool as `python -m geo_audit`.

## `GEO_E_PRIVATE_ADDRESS` on a URL you control

Private, loopback and link-local addresses are refused by default. Pass
`--allow-private` to audit `localhost`, a private IP or an internal staging host.

If it fires on a *public* hostname, the guard caught something worth knowing about:
the name resolved to a private address, or the connection landed on one. The message
names the address we actually reached.

## `GEO_E_REDIRECT_BLOCKED`

A redirect pointed at a private address. The chain was not followed and nothing was
scored. This is usually a misconfigured redirect to an internal hostname that only
resolves inside a VPN.

## `GEO_E_TOO_LARGE`

The response exceeded the size cap, either by declaring it in `Content-Length` or by
reaching it mid-download. Raise it if the page really is that large:

```bash
geo score https://example.com/huge --max-bytes 20000000
```

## `GEO_E_BAD_CONTENT_TYPE`

Only `text/html` and `application/xhtml+xml` are scored on a 2xx response. Point the
command at a page rather than at a PDF, image or feed. Error responses are exempt: a
403 that returns JSON is still reported as a finding.

## `GEO_E_TOO_MANY_REDIRECTS`

The chain exceeded the cap without settling. A redirect loop is itself a crawlability
defect: a crawler gives up in the same place.

## `GEO_E_STATE_NEWER`

`$GEO_HOME` was written by a newer release. Nothing was changed. Upgrade:

```bash
uv tool upgrade seomator-geo-audit
```

Downgrading is not supported. If you need the old CLI, point it at a different
`GEO_HOME`.

## `GEO_E_STATE_WRITE` / `GEO_E_STATE_UNREADABLE`

Check ownership and permissions on `$GEO_HOME` (0700, owned by you), then run
`geo doctor`. If the directory sits inside iCloud, Dropbox, OneDrive or Google Drive,
move it: audit history is append-only and assumes a single writer, and two machines
syncing one file will corrupt it.

```bash
export GEO_HOME=~/.geo
```

## Exit code 5 in CI

`--fail-on-partial` was passed and some pages could not be evaluated. The findings
name which and why. Drop the flag to accept a partial result.

## The score changed after I installed the browser extra

Expected, and visible in the output. `citability.render_parity` moves from `null` to a
measurement, so `completeness` goes from 6 of 7 to 7 of 7 and the composite is taken
over a different set. [Signals](concepts/signals.md) explains the arithmetic.

## A page scores lower than it reads

Check `citability.extractability` first. If `content_chars` is a small fraction of
what you see in a browser, the crawler is not receiving the page you are looking at,
and every prose signal is being computed on what is left.

```bash
geo fetch https://example.com/page
```

## `GEO_E_INCOMPARABLE`

`geo compare` refuses when the two runs were scored under different rules — the
formula changed (`scoring_version` major) or the constants did (`data_version`).

This is not a bug to work around. Subtracting them would measure the tool rather than
the site, and "your score fell six points" when only our thresholds moved is a false
statement to whoever reads it. Re-run the older URL to get a comparable pair:

```bash
geo audit https://example.com
geo compare https://example.com
```

## `GEO_E_TIMEOUT`, `GEO_E_DNS`, `GEO_E_CONNECT`, `GEO_E_TLS`

Four different failures, and the message says which:

| Message says | Means |
|---|---|
| the connection was refused | Nothing is listening. Check the port and any proxy. |
| the server reset the connection | Something closed it mid-flight, often bot protection. |
| closed the connection before sending a response | Usually a stale keep-alive connection; it retries once already. |
| the connection timed out | Raise `--timeout` if the host is simply slow. |
| couldn't resolve | DNS. Check for a typo and whether the domain resolves from this machine. |
| TLS handshake failed | An expired or self-signed certificate. Fix the site, not the audit. |

All four exit 3, which means no HTTP response was obtained. A response that arrived
and said 403 or 500 is a **finding**, not one of these.

## `GEO_E_BAD_URL` and `GEO_E_BLOCKED_SCHEME`

Pass an absolute `http://` or `https://` URL. `example.com` is not one, and
`file://`, `data://` and the rest are refused by design rather than by omission.

## `GEO_E_BAD_ARGS`

A flag value the command cannot use: an unknown category for `--only`, a run id that
is not 26 characters, a brand or advisory file that is missing or malformed, an answer
to an advisory question that was never asked. The message names which.

## `GEO_E_PARTIAL`

Only ever raised by `--fail-on-partial`. It means some pages could not be evaluated,
and the findings name which and why. Drop the flag to accept a partial result — a
PARTIAL audit exits 0 by default on purpose, because the sites whose bot protection
blocks a crawler are exactly the sites that most need a report.

## `GEO_E_INTERNAL`

A bug here, not in the site. The message names the exception type and the log has the
traceback. Please open an issue with both.

## Where the log is

```
$GEO_HOME/logs/last-run.log
```

Written on failure, overwritten each run. It carries the traceback that the
user-facing message deliberately does not.
