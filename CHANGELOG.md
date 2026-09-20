# Changelog

All notable changes to this project are documented here.

The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and this
project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

## [0.1.0] - 2026-09-20

The walking skeleton: three commands with the full safety, evidence and exit-code
contract behind them, and one skill end to end.

### Added

- **`geo score`** — citability of a single page over seven signals
  (`self_containment`, `answer_first`, `structure`, `evidence_density`,
  `extractability`, `attribution`, `render_parity`). Prints a number and its tier
  label together, the signals behind it, and findings ranked by points recovered.
- **`geo fetch`** — what a non-rendering crawler receives: status, redirect chain,
  content-block count, evidence hash, JSON-LD types, and per-crawler robots access.
- **`geo doctor`** — interpreter, PATH collisions, `$GEO_HOME` permissions, sync-drive
  detection, state version, package data, and the optional browser extra. Reports;
  never gates.
- **JSON envelope** with a fixed key set and `schema_version`, `scoring_version`,
  `data_version` and `normalizer_version` on every response. JSON whenever stdout is
  not a terminal; progress on stderr, always.
- **Evidence model.** SHA-256 over the extracted content-block sequence plus
  `normalizer_version`. ETag and Last-Modified are metadata and a revalidation
  shortcut, deliberately not part of hash identity. Stamps: `CURRENT`, `PARTIAL`,
  `STALE`.
- **Fetch safety.** Private, loopback, link-local, multicast and reserved addresses
  refused, including IPv4-mapped IPv6 forms; the connected peer address validated as
  well as the resolved name, which closes DNS rebinding; per-hop redirect validation;
  declared and streaming size caps; content-type allowlist; `--allow-private` to opt
  in to auditing a private start URL.
- **RFC 9309 robots.txt** parser with the full status matrix (4xx allows, 5xx
  disallows, redirects followed), longest-match and least-restrictive-tie rules,
  wildcards and end anchors. Sixteen AI crawler tokens in versioned data, each with
  its operator's documentation URL.
- **Append-only state** under `$GEO_HOME` (default `~/.geo`, mode 0700). One record
  per run; a torn trailing line is discarded silently; state carries a version and a
  newer state is refused without changing anything.
- **Seventeen `GEO_E_*` error codes**, every one carrying a hint and a docs anchor,
  mapped to six exit codes. A 403 or 5xx from an audited page is a finding, not a
  failure.
- **`geo:citability` skill** with preflight, the shared response contract, and
  methodology sections loaded on demand.
- **Claude Code plugin** manifests for `/plugin marketplace add` installation.
- **Test suite** covering the envelope goldens, the SSRF matrix, the robots matrix,
  hash stability under nonce and timestamp rotation, the output boundary, the
  injection fixture, state handling, skill contracts, and the README quickstart.
- **Generated docs** for the command reference and scoring constants, with a CI
  freshness check.

### Notes

- Scores are comparable only with other scores from this tool at the same
  `scoring_version` and `data_version`.
- `citability.render_parity` is `null` without the optional browser extra. The
  composite is taken over the signals that were computed; a signal that was not
  measured is never scored as a failure.

[Unreleased]: https://github.com/seo-skills/geo-audit-skill/compare/v0.1.0...HEAD
[0.1.0]: https://github.com/seo-skills/geo-audit-skill/releases/tag/v0.1.0
