"""The one place request headers are defined.

Upstream carried three copies of DEFAULT_HEADERS across three scripts and they
had already drifted. There is one copy here and everything that makes an HTTP
request imports it.
"""

from __future__ import annotations

from geo_audit._version import CLI_VERSION, REPO_URL

# The token site owners see in their logs and match in robots.txt. It names
# the product so it can be looked up, and carries the repository URL so an
# operator who has never heard of it can find out what it is in one click.
PRODUCT_TOKEN = "SeomatorGeoAudit"

USER_AGENT = f"{PRODUCT_TOKEN}/{CLI_VERSION} (+{REPO_URL})"

DEFAULT_HEADERS: dict[str, str] = {
    "User-Agent": USER_AGENT,
    "Accept": "text/html,application/xhtml+xml;q=0.9,*/*;q=0.1",
    "Accept-Language": "en-US,en;q=0.9",
    "Accept-Encoding": "gzip, deflate",
}


def headers(extra: dict[str, str] | None = None) -> dict[str, str]:
    out = dict(DEFAULT_HEADERS)
    if extra:
        out.update(extra)
    return out
