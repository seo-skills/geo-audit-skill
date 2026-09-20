"""Error codes, their hints, and the exit-code mapping.

Two rules hold for this module, both contract-tested:

1. Every `GEO_E_*` code carries a non-empty hint. A code without a next action
   is a stack trace with better manners.
2. The exit code is a property of the error class, never of the call site, so
   the table in docs/troubleshooting.md can be generated from here.

Exit codes (the only table):

    0  OK, including PARTIAL audits
    1  internal error
    2  usage error
    3  network failure on the start URL (no HTTP response was obtained)
    4  state error
    5  --fail-on-partial was passed and the result is PARTIAL

An HTTP response is not a network failure. A 403 challenge or a 5xx from the
start URL is a *finding* with critical severity and exit 0, because exiting
non-zero there would abort exactly the sites that most need a report.
"""

from __future__ import annotations

from dataclasses import dataclass

EXIT_OK = 0
EXIT_INTERNAL = 1
EXIT_USAGE = 2
EXIT_NETWORK = 3
EXIT_STATE = 4
EXIT_PARTIAL = 5

_DOCS = "https://github.com/seo-skills/geo-audit-skill/blob/main/docs/troubleshooting.md"


@dataclass(frozen=True)
class ErrorSpec:
    code: str
    exit_code: int
    hint: str

    @property
    def docs(self) -> str:
        return f"{_DOCS}#{self.code.lower().replace('_', '-')}"


def _spec(code: str, exit_code: int, hint: str) -> ErrorSpec:
    return ErrorSpec(code=code, exit_code=exit_code, hint=hint)


ERRORS: dict[str, ErrorSpec] = {
    s.code: s
    for s in [
        # --- usage (2) -------------------------------------------------
        _spec(
            "GEO_E_BAD_URL",
            EXIT_USAGE,
            "Pass an absolute http:// or https:// URL, for example "
            "`geo score https://example.com/pricing`.",
        ),
        _spec(
            "GEO_E_BAD_ARGS",
            EXIT_USAGE,
            "Run the command with --help to see the accepted flags.",
        ),
        _spec(
            "GEO_E_BLOCKED_SCHEME",
            EXIT_USAGE,
            "Only http:// and https:// are fetched. file://, data://, ftp:// and "
            "the rest are refused by design.",
        ),
        _spec(
            "GEO_E_PRIVATE_ADDRESS",
            EXIT_USAGE,
            "This host resolves to a private, loopback or link-local address. "
            "Auditing localhost or a staging host is legitimate: re-run with "
            "--allow-private to opt in.",
        ),
        # --- network on the start URL (3) ------------------------------
        _spec(
            "GEO_E_TIMEOUT",
            EXIT_NETWORK,
            "Check the URL, or try again. Raise the budget with --timeout if the "
            "host is simply slow.",
        ),
        _spec(
            "GEO_E_DNS",
            EXIT_NETWORK,
            "The hostname did not resolve. Check for a typo, or whether the "
            "domain is reachable from this machine.",
        ),
        _spec(
            "GEO_E_CONNECT",
            EXIT_NETWORK,
            "The connection was refused or reset. Check the URL, the port, and "
            "any proxy or VPN on this machine.",
        ),
        _spec(
            "GEO_E_TLS",
            EXIT_NETWORK,
            "The TLS handshake failed. If the certificate is genuinely expired "
            "or self-signed, fix the site rather than the audit.",
        ),
        _spec(
            "GEO_E_TOO_MANY_REDIRECTS",
            EXIT_NETWORK,
            "The redirect chain exceeded the cap. A redirect loop is itself a "
            "crawlability defect worth fixing.",
        ),
        _spec(
            "GEO_E_REDIRECT_BLOCKED",
            EXIT_NETWORK,
            "A redirect pointed at a private, loopback or link-local address, "
            "which is never followed. Use --allow-private only if you control "
            "the whole chain.",
        ),
        _spec(
            "GEO_E_TOO_LARGE",
            EXIT_NETWORK,
            "The response exceeded the size cap. Raise it with --max-bytes if "
            "the page really is that large.",
        ),
        _spec(
            "GEO_E_BAD_CONTENT_TYPE",
            EXIT_NETWORK,
            "Only HTML and XHTML are scored. Point the command at a page rather "
            "than at a PDF, image or feed.",
        ),
        # --- state (4) --------------------------------------------------
        _spec(
            "GEO_E_STATE_NEWER",
            EXIT_STATE,
            "Upgrade with `uv tool upgrade geo-audit-cli`. Nothing was changed.",
        ),
        _spec(
            "GEO_E_STATE_UNREADABLE",
            EXIT_STATE,
            "Check permissions on GEO_HOME (it should be mode 0700 and owned by "
            "you), then run `geo doctor`.",
        ),
        _spec(
            "GEO_E_STATE_WRITE",
            EXIT_STATE,
            "GEO_HOME could not be written. Check disk space and permissions, "
            "then run `geo doctor`.",
        ),
        # --- partial (5) ------------------------------------------------
        _spec(
            "GEO_E_PARTIAL",
            EXIT_PARTIAL,
            "Some pages could not be evaluated. Drop --fail-on-partial to accept "
            "a partial result, or fix the blocked pages listed in the findings.",
        ),
        # --- internal (1) -----------------------------------------------
        _spec(
            "GEO_E_INTERNAL",
            EXIT_INTERNAL,
            "This is a bug in geo-audit-cli. The log names the failing step; "
            "please open an issue with it.",
        ),
    ]
}


class GeoError(Exception):
    """An error that is safe to show a user verbatim.

    `message` is one human sentence with no stack trace and no raw exception
    repr. Anything a developer needs goes to the log file instead.
    """

    def __init__(self, code: str, message: str) -> None:
        if code not in ERRORS:
            raise KeyError(f"unknown error code: {code}")
        super().__init__(message)
        self.code = code
        self.message = message

    @property
    def spec(self) -> ErrorSpec:
        return ERRORS[self.code]

    @property
    def exit_code(self) -> int:
        return self.spec.exit_code

    def as_dict(self, log_path: str) -> dict:
        return {
            "code": self.code,
            "message": self.message,
            "hint": self.spec.hint,
            "docs": self.spec.docs,
            "log": log_path,
        }
