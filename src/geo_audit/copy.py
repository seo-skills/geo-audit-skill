"""Literal interaction copy.

Every user-facing sentence that a golden test asserts on lives here, so the
wording is reviewed as copy rather than discovered inside an f-string three
levels down. Numbers 1-8 are the interaction states in the PRD; the ones this
milestone cannot yet produce (PDF unavailable, stale report) arrive with the
commands that produce them.
"""

from __future__ import annotations

# 1 — loading (stderr only)
PROGRESS = "[{step}/{total}] {action}"
ASKING_ASSISTANTS = (
    "Asking {engines} about \u201c{brand}\u201d: up to {credits} credits from your "
    "scrape.do account, usually under a minute."
)
CRAWL_EXPECTATION = (
    "Running the audit. It crawls up to 50 pages at one request per second, "
    "so expect a few minutes."
)

# 2 — empty
NO_AUDITS = (
    "No audits recorded for {site} yet. Run `geo audit {url}` to create "
    "the first one."
)
NO_SCORABLE_PAGES = (
    "The crawl found no scorable pages on {site}. The start URL returned "
    "{status}. Nothing was scored."
)
NOT_SCORABLE = "the page returned no scorable content"
NO_MENTIONS = (
    "No mentions of \u201c{brand}\u201d found on {platforms} (checked {date}). "
    "This is a result, not an error."
)
NO_BLOCKS = (
    "No citable content blocks found on this page. Score 0 — reason: no "
    "extractable blocks."
)

# 3 — PDF unavailable
PDF_UNAVAILABLE = (
    "PDF skipped: {reason}. HTML report written to {path}. To enable PDF: "
    "`uv tool install {install} && playwright install chromium`"
)

# 6 — success, report
REPORT_WRITTEN = "{mode} report for {site} written to {path}."

# 4 — error
ERROR = "{message} ({code}) {hint} Details: {log}"

# 5 — partial
PARTIAL = (
    "PARTIAL audit: {ok} of {total} pages scored. {failed} could not be "
    "evaluated ({reasons}). Scores reflect the {ok} pages only."
)

# The crawl stopped at its page limit, so the number describes part of a site.
CAPPED = (
    "The crawl stopped at its {limit}-page limit after finding {found} URLs, "
    "so the score covers {scored} of them."
)

# 6 — success
SCORE_SUCCESS = (
    "GEO citability score {score}/100 ({tier}) for {site} — {pages} page, "
    "evidence {stamp}."
)
NEXT_COMMAND = "Next: {command}"

# 8 — refuse to run (built in state.check_version, repeated here for the lint)
STATE_NEWER_SUFFIX = "Nothing was changed."

# doctor
DOCTOR_OK = "{dist} {version} — {passed} of {total} checks passed."
DOCTOR_PROBLEMS = "{dist} {version} — {failed} of {total} checks need attention."
