"""Project slugs: the directory name a site's history lives under."""

from __future__ import annotations

import re
from urllib.parse import urlsplit

_SAFE = re.compile(r"[^a-z0-9.-]+")


def host_of(url: str) -> str:
    host = (urlsplit(url).hostname or "").lower()
    if host.startswith("www."):
        host = host[4:]
    return host


def project_slug(url: str) -> str:
    """`https://www.Example.com/pricing` -> `example-com`.

    Ports are dropped on purpose: `localhost:3000` and `localhost:8080` are the
    same project being served twice.
    """
    host = host_of(url)
    if not host:
        return "unknown"
    slug = _SAFE.sub("-", host).replace(".", "-").strip("-")
    return slug or "unknown"
