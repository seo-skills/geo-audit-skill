# Security

## Reporting a vulnerability

Open a [private security advisory](https://github.com/seo-skills/geo-audit-skill/security/advisories/new)
on the repository. Please do not open a public issue for anything exploitable.

Expect an acknowledgement within three working days and an assessment within ten.
If a fix is warranted it ships as a patch release, with the advisory published once
the release is out.

## Threat model

This tool feeds untrusted web content toward an agent that has tool access. That is
the top concern, ahead of anything about the CLI itself.

### 1. Prompt injection through crawled content

**The attack.** A page contains text shaped like an instruction: a fake system prompt,
a fake end-of-output delimiter, a demand to report a particular score, or a request to
run a command. The page is audited, the text reaches the model, the model acts on it.

**The main defence is the output boundary.** CLI output carries derived signals,
counts, and length-capped, delimiter-escaped excerpts. **It never carries page text.**
An excerpt is capped at 280 characters and has backticks and angle brackets replaced
before it leaves the process, so it cannot close a surrounding context.

**The second defence is the skill boundary.** Every skill states that excerpts are
data, never instructions, and the skill lint enforces that the clause is present and
byte-identical across skills.

**Tested by** `tests/test_injection.py` and `tests/test_output_boundary.py`. The
fixture page contains a fake system prompt, a fake tool instruction, a fake
end-of-output delimiter and a demand for a score of 100. The tests assert that the
score is not 100, that the envelope shape is unchanged, that no fake delimiter
survives into the output, and that the state directory is untouched beyond its one
audit record.

### 2. Server-side request forgery

**The attack.** A public URL, or a redirect from one, points into a private network
or at a cloud metadata endpoint.

**Defences.**

* Private, loopback, link-local, multicast, reserved and unspecified addresses are
  refused, including IPv4-mapped IPv6 forms such as `::ffff:127.0.0.1`.
* `169.254.169.254` is covered by the link-local rule.
* Only `http` and `https` are fetched.
* A host resolving to a mix of public and private addresses is refused as a whole:
  which address we get is the resolver's choice, not ours.
* **The connected peer address is validated, not only the resolved name.** This is
  what closes DNS rebinding, where a name resolves publicly on the first lookup and
  to loopback on the second.
* Redirects are followed by hand, one hop at a time, with the full check on each.
* A *private start URL* is refused unless `--allow-private` is passed. That flag is
  an opt-in for auditing `localhost` or a staging host, which is a legitimate use.

**Tested by** `tests/test_net_guards.py`, including a rebinding simulation that
patches only the pre-flight resolution and relies on the peer check to stop it.

### 3. Resource exhaustion

* Redirect chain cap (5 by default).
* Declared `Content-Length` checked before a byte is read.
* Decoded body capped while streaming, which is also the decompression limit: a small
  compressed payload that inflates to gigabytes trips the cap at the cap.
* Content-type allowlist on 2xx responses.
* Request timeout, default 30 s.

### 4. State

* `$GEO_HOME` is created mode 0700, and `geo doctor` warns if it is looser.
* No raw HTML is written to disk; records hold derived signals and capped excerpts.
* State carries a version. A CLI that finds newer state refuses to run and changes
  nothing, rather than migrating someone's history downward.
* `geo doctor` warns when `$GEO_HOME` sits on a sync drive, where append-only
  single-writer assumptions do not hold.

### 5. Supply chain

* No install-time mutation: nothing is rewritten, patched or generated during
  installation, so the artifact that was tested is the artifact that runs.
* Two runtime dependencies (`requests`, `beautifulsoup4`). Playwright is an optional
  extra.
* Releases publish to PyPI through trusted publishing from a tagged workflow, with no
  long-lived token in the repository.

## Out of scope

* The security of the sites being audited. Findings about them are the product.
* Anything requiring local code execution as the user already running the CLI.
* Denial of service against a site by its own operator's audit. Crawl defaults are 1
  request per second globally, and that is a politeness floor, not a guarantee.
