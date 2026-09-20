"""RFC 9309 robots.txt.

Two jobs live here and they are kept apart on purpose:

(a) our own etiquette, as the `SeomatorGeoAudit` product token, when crawling;
(b) the product feature, which answers "can GPTBot read this page?" by
    evaluating the AI crawler tokens in data/ai_crawlers.json against the
    same parsed file.

Status handling follows RFC 9309 section 2.3.1 exactly, because the edge cases
are where robots parsers quietly disagree:

    2xx  parse and apply
    3xx  follow up to five hops, then treat as unavailable
    4xx  unavailable -> everything is allowed
    5xx  unreachable -> everything is disallowed
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from urllib.parse import unquote, urljoin, urlsplit

import requests

from geo_audit.errors import GeoError
from geo_audit.lib import http
from geo_audit.lib.headers import PRODUCT_TOKEN

MAX_ROBOTS_BYTES = 512_000


@dataclass(frozen=True)
class Rule:
    allow: bool
    path: str
    pattern: re.Pattern


@dataclass
class Group:
    agents: list[str] = field(default_factory=list)
    rules: list[Rule] = field(default_factory=list)
    crawl_delay: float | None = None


def _compile(path: str) -> re.Pattern:
    """Translate a robots path into a regex.

    `*` matches any run of characters, a trailing `$` anchors the end, and
    everything else is literal.
    """
    anchored = path.endswith("$")
    body = path[:-1] if anchored else path
    parts = [re.escape(segment) for segment in body.split("*")]
    expression = "^" + ".*".join(parts) + ("$" if anchored else "")
    return re.compile(expression)


def _rule(allow: bool, raw: str) -> Rule | None:
    path = raw.strip()
    if not path:
        # "Disallow:" with an empty value allows everything; it is not a rule.
        return None
    if not path.startswith("/") and not path.startswith("*"):
        path = "/" + path
    return Rule(allow=allow, path=path, pattern=_compile(path))


@dataclass
class RobotsFile:
    source_url: str
    status: int | None
    groups: list[Group] = field(default_factory=list)
    sitemaps: list[str] = field(default_factory=list)
    unreachable: bool = False
    unavailable: bool = False
    error: str | None = None

    def group_for(self, agent: str) -> Group | None:
        token = agent.split("/")[0].strip().lower()
        best: Group | None = None
        best_len = -1
        wildcard: Group | None = None
        for group in self.groups:
            for candidate in group.agents:
                lowered = candidate.lower()
                if lowered == "*":
                    wildcard = wildcard or group
                    continue
                if token.startswith(lowered) and len(lowered) > best_len:
                    best, best_len = group, len(lowered)
        return best or wildcard

    def allows(self, agent: str, path: str) -> bool:
        if self.unreachable:
            return False
        if self.unavailable or not self.groups:
            return True
        group = self.group_for(agent)
        if group is None or not group.rules:
            return True
        target = unquote(path) or "/"
        winner: Rule | None = None
        for rule in group.rules:
            if not rule.pattern.match(target):
                continue
            if winner is None:
                winner = rule
                continue
            if len(rule.path) > len(winner.path):
                winner = rule
            elif len(rule.path) == len(winner.path) and rule.allow:
                # RFC 9309 section 2.2.2: the least restrictive rule wins a tie.
                winner = rule
        return True if winner is None else winner.allow

    def crawl_delay_for(self, agent: str) -> float | None:
        group = self.group_for(agent)
        return group.crawl_delay if group else None


def parse(text: str, source_url: str = "", status: int | None = 200) -> RobotsFile:
    robots = RobotsFile(source_url=source_url, status=status)
    group: Group | None = None
    accepting_agents = False

    for raw_line in text.splitlines():
        line = raw_line.split("#", 1)[0].strip()
        if not line or ":" not in line:
            continue
        field_name, _, value = line.partition(":")
        key = field_name.strip().lower()
        value = value.strip()

        if key in ("user-agent", "useragent"):
            if group is None or not accepting_agents:
                group = Group()
                robots.groups.append(group)
                accepting_agents = True
            if value:
                group.agents.append(value)
            continue

        if key == "sitemap":
            if value:
                # The spec wants an absolute URL here; plenty of real files
                # write a path instead.
                robots.sitemaps.append(urljoin(source_url, value) if source_url else value)
            continue

        if group is None:
            continue
        accepting_agents = False

        if key == "disallow":
            rule = _rule(False, value)
            if rule:
                group.rules.append(rule)
        elif key == "allow":
            rule = _rule(True, value)
            if rule:
                group.rules.append(rule)
        elif key == "crawl-delay":
            try:
                group.crawl_delay = float(value)
            except ValueError:
                pass

    robots.groups = [g for g in robots.groups if g.agents]
    return robots


def robots_url_for(url: str) -> str:
    parts = urlsplit(url)
    return urljoin(f"{parts.scheme}://{parts.netloc}", "/robots.txt")


def load(
    url: str,
    *,
    session: requests.Session | None = None,
    allow_private: bool = False,
    timeout: float = 10.0,
) -> RobotsFile:
    target = robots_url_for(url)
    try:
        result = http.fetch(
            target,
            allow_private=allow_private,
            timeout=timeout,
            max_bytes=MAX_ROBOTS_BYTES,
            max_redirects=5,
            accept_types=None,
            session=session,
        )
    except GeoError as exc:
        if exc.code == "GEO_E_TOO_MANY_REDIRECTS":
            return RobotsFile(source_url=target, status=None, unavailable=True, error=exc.code)
        return RobotsFile(source_url=target, status=None, unreachable=True, error=exc.code)

    if 200 <= result.status < 300:
        return parse(result.body, source_url=target, status=result.status)
    if 400 <= result.status < 500:
        return RobotsFile(source_url=target, status=result.status, unavailable=True)
    if result.status >= 500:
        return RobotsFile(source_url=target, status=result.status, unreachable=True)
    return RobotsFile(source_url=target, status=result.status, unavailable=True)


def access_matrix(robots: RobotsFile, agents: list[str], path: str) -> list[dict]:
    """Per-crawler access, deterministically ordered by the input list."""
    rows = []
    for agent in agents:
        rows.append(
            {
                "agent": agent,
                "allowed": robots.allows(agent, path),
                "crawl_delay": robots.crawl_delay_for(agent),
            }
        )
    return rows


def self_allows(robots: RobotsFile, path: str) -> bool:
    return robots.allows(PRODUCT_TOKEN, path)
