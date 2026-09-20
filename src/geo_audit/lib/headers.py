"""The one place request headers are defined.

Upstream carried three copies of DEFAULT_HEADERS across three scripts and they
had already drifted. There is one copy here and everything that makes an HTTP
request imports it.
"""

from __future__ import annotations

from geo_audit._version import CLI_VERSION

PRODUCT_TOKEN = "geo-audit-cli"

USER_AGENT = (
    f"{PRODUCT_TOKEN}/{CLI_VERSION} "
    "(+https://github.com/seo-skills/geo-audit-skill)"
)

DEFAULT_HEADERS: dict[str, str] = {
    "User-Agent": USER_AGENT,
    "Accept": "text/html,application/xhtml+xml;q=0.9,*/*;q=0.1",
    "Accept-Language": "en-US,en;q=0.9",
    "Accept-Encoding": "gzip, deflate",
    "Connection": "close",
}


def headers(extra: dict[str, str] | None = None) -> dict[str, str]:
    out = dict(DEFAULT_HEADERS)
    if extra:
        out.update(extra)
    return out
