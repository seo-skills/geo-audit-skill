"""Page bodies on disk, each stored once under the hash of its bytes.

The audit record holds what the scorer computed; this holds what it read, so a
rescore can read it again and a re-audit can ask a server whether anything
changed. The PRD kept no pages on disk; the maintainer lifted that on
2026-09-21, and what the rule protected is kept by how pages are stored:

- apart from `audits.jsonl`, so sharing an audit shares no client's pages;
- never printed, so the CLI's output boundary is exactly what it was;
- gzipped and content-addressed, so an unchanged page costs nothing on a
  re-audit, and `geo prune` deletes a page once no kept run names it.
"""

from __future__ import annotations

import gzip
import hashlib
from pathlib import Path

from geo_audit import state
from geo_audit.lib import http
from geo_audit.lib import robots as robots_lib

SUFFIX = ".html.gz"


def store_dir(slug: str) -> Path:
    return state.project_dir(slug) / "pages"


def put(slug: str, body: str) -> str:
    data = body.encode("utf-8")
    digest = hashlib.sha256(data).hexdigest()
    path = store_dir(slug) / f"{digest}{SUFFIX}"
    if not path.exists():
        # mtime=0 keeps the compressed bytes a function of the page alone.
        state.write_atomic_bytes(path, gzip.compress(data, mtime=0))
    return digest


def get(slug: str, digest: str) -> str | None:
    path = store_dir(slug) / f"{digest}{SUFFIX}"
    if not path.exists():
        return None
    return gzip.decompress(path.read_bytes()).decode("utf-8")


def stored(slug: str) -> list[str]:
    folder = store_dir(slug)
    if not folder.is_dir():
        return []
    return sorted(path.name[: -len(SUFFIX)] for path in folder.glob(f"*{SUFFIX}"))


def referenced(records: list[dict]) -> set[str]:
    names: set[str] = set()
    for record in records:
        snapshot = record.get("snapshot") or {}
        names.update(f["body"] for f in snapshot.get("fetches") or [] if f.get("body"))
        robots = snapshot.get("robots") or {}
        if robots.get("body"):
            names.add(robots["body"])
    return names


def _size(slug: str, digest: str) -> int:
    path = store_dir(slug) / f"{digest}{SUFFIX}"
    return path.stat().st_size if path.exists() else 0


def plan_keep(slug: str, newest_first: list[dict], budget: int) -> set[str]:
    """Which stored pages to keep: the newest runs' pages, as far as the budget goes.

    Storing a page once bounds growth only for pages that do not change, and a
    measured page ran to 62 KB gzipped. So the store has a budget. A run keeps
    all of its pages or none - a partial replay would score a different site -
    and past the budget the older runs lose theirs; their records stay, and a
    rescore of them falls back to the recorded ratios.
    """
    keep: set[str] = set()
    used = 0
    for record in newest_first:
        names = referenced([record]) - keep
        cost = sum(_size(slug, name) for name in names)
        if used + cost > budget:
            break
        keep |= names
        used += cost
    return keep


def collect(slug: str, keep: set[str], apply: bool) -> tuple[int, int]:
    """Pages no kept run names: how many, how many bytes, deleted if `apply`."""
    count = size = 0
    for digest in stored(slug):
        if digest in keep:
            continue
        path = store_dir(slug) / f"{digest}{SUFFIX}"
        count += 1
        size += path.stat().st_size
        if apply:
            path.unlink(missing_ok=True)
    return count, size


def fetch_record(result: http.FetchResult, digest: str | None) -> dict:
    return {
        "requested_url": result.requested_url, "final_url": result.final_url,
        "status": result.status, "headers": result.headers, "body": digest,
        "body_bytes": result.body_bytes, "encoding": result.encoding,
        "elapsed_ms": result.elapsed_ms, "peer_address": result.peer_address,
        "peer_verified": result.peer_verified,
        "chain": [{"url": hop.url, "status": hop.status, "location": hop.location} for hop in result.chain],
    }


def fetch_result(record: dict, body: str) -> http.FetchResult:
    return http.FetchResult(
        requested_url=record["requested_url"], final_url=record["final_url"],
        status=record["status"], headers=dict(record.get("headers") or {}), body=body,
        body_bytes=record.get("body_bytes", len(body.encode("utf-8"))),
        encoding=record.get("encoding") or "utf-8", elapsed_ms=record.get("elapsed_ms", 0),
        peer_address=record.get("peer_address"), peer_verified=bool(record.get("peer_verified")),
        chain=[http.Hop(**hop) for hop in record.get("chain") or []],
    )


def robots_record(robots: robots_lib.RobotsFile | None, slug: str) -> dict | None:
    if robots is None:
        return None
    return {
        "source_url": robots.source_url, "status": robots.status,
        "unreachable": robots.unreachable, "unavailable": robots.unavailable, "error": robots.error,
        "body": put(slug, robots.text) if robots.text is not None else None,
    }


def robots_from(record: dict, body: str | None) -> robots_lib.RobotsFile:
    if body is not None:
        return robots_lib.parse(body, source_url=record["source_url"], status=record["status"])
    return robots_lib.RobotsFile(
        source_url=record["source_url"], status=record["status"],
        unreachable=bool(record.get("unreachable")), unavailable=bool(record.get("unavailable")),
        error=record.get("error"),
    )
