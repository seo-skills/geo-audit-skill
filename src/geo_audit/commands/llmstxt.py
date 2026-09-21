"""`geo llmstxt` - check for an llms.txt, or build one from the site.

The format is small and specified at llmstxt.org: one H1, an optional
blockquote summary, then H2 sections of markdown links. Validation here is
structural. Whether the descriptions are any good is a judgement, and
judgement is the model's job, not the scorer's.

Generation reads the crawl rather than guessing: every entry is a page that
was actually fetched, titled with its own `<title>` and described with its own
meta description. An llms.txt full of invented summaries is worse than none,
because it is confidently wrong at the exact moment an engine is trusting it.
"""

from __future__ import annotations

import re
from urllib.parse import urlsplit

from geo_audit import data, envelope
from geo_audit.commands import crawl as crawl_cmd
from geo_audit.commands.common import Options, load_page
from geo_audit.errors import GeoError
from geo_audit.lib import crawl as crawl_lib
from geo_audit.lib import http, safety
from geo_audit.lib.extract import excerpt, normalize_text
from geo_audit.lib.slug import host_of
from geo_audit.scoring.model import Finding, prioritize

CANONICAL_PATH = "/llms.txt"
FULL_PATH = "/llms-full.txt"
MAX_LINKS_PER_SECTION = 100
MAX_DESCRIPTION = 160
MAX_TITLE = 100

H1 = re.compile(r"^#\s+(.+?)\s*$", re.MULTILINE)
H2 = re.compile(r"^##\s+(.+?)\s*$", re.MULTILINE)
QUOTE = re.compile(r"^>\s*(.+?)\s*$", re.MULTILINE)
LINK = re.compile(r"^\s*[-*]\s*\[([^\]]+)\]\(([^)]+)\)\s*(?::\s*(.*))?$", re.MULTILINE)


def parse(text: str) -> dict:
    """Structure only: what the file declares, and what it is missing."""
    headings = H1.findall(text)
    sections = H2.findall(text)
    quotes = QUOTE.findall(text)
    links = [
        {"title": title.strip(), "url": url.strip(), "description": (note or "").strip() or None}
        for title, url, note in LINK.findall(text)
    ]

    problems: list[str] = []
    if not headings:
        problems.append("no H1 title")
    elif len(headings) > 1:
        problems.append(f"{len(headings)} H1 headings; the format allows one")
    if not quotes:
        problems.append("no blockquote summary")
    if not sections:
        problems.append("no H2 sections")
    if not links:
        problems.append("no links")

    return {
        "title": headings[0] if headings else None,
        "summary": quotes[0] if quotes else None,
        "sections": sections,
        "links": links,
        "link_count": len(links),
        "has_optional_section": any(name.strip().lower() == "optional" for name in sections),
        "problems": problems,
        "valid": not problems,
        "bytes": len(text.encode("utf-8")),
    }


def _fetch_optional(url: str, options: Options) -> dict:
    return _fetch_text(url, options)[0]


def _fetch_text(url: str, options: Options) -> tuple[dict, str | None]:
    """The report on an optional file, and its text for the page store.

    Kept apart because the report is printed and the text never is.
    """
    try:
        result = http.fetch(
            url,
            allow_private=options.allow_private,
            timeout=options.timeout,
            max_bytes=options.max_bytes,
            accept_types=None,
        )
    except GeoError as error:
        return {"url": url, "present": False, "status": None, "error": error.code}, None
    if not result.ok:
        return {"url": url, "present": False, "status": result.status, "error": None}, None
    report = parse(result.body)
    report.update({"url": url, "present": True, "status": result.status, "error": None})
    return report, result.body


def _markdown_safe(text: str, limit: int) -> str:
    """Cap, escape prompt delimiters, then neutralise markdown link syntax.

    Everything here comes from a crawled page, and the file being built is one
    the user publishes. A page that titles itself "Ignore previous
    instructions" must not have that text copied verbatim into a document an
    engine is about to read as authoritative, and a page whose title contains
    a bracket must not be able to break out of the link that wraps it.
    """
    clean = excerpt(normalize_text(text), limit)
    for character, replacement in (("[", "("), ("]", ")"), ("(", "\N{MATHEMATICAL LEFT WHITE TORTOISE SHELL BRACKET}"), (")", "\N{MATHEMATICAL RIGHT WHITE TORTOISE SHELL BRACKET}")):
        clean = clean.replace(character, replacement)
    return clean


def _describe(doc) -> str | None:
    description = doc.meta.get("description")
    if not description:
        description = next((block.text for block in doc.prose_blocks if block.words >= 8), None)
    if not description:
        return None
    return _markdown_safe(description, MAX_DESCRIPTION)


def generate(result: crawl_lib.CrawlResult, start_url: str) -> dict:
    """Build an llms.txt from pages that were actually fetched."""
    pages = [page for page in result.ok_pages if page.doc is not None]
    if not pages:
        raise GeoError(
            "GEO_E_BAD_ARGS",
            "No scorable pages were crawled, so there is nothing to list in an llms.txt.",
        )

    start = next(
        (page for page in pages if page.result and page.result.final_url.rstrip("/") == start_url.rstrip("/")),
        pages[0],
    )
    site = host_of(start_url)
    title = _markdown_safe(start.doc.title or site, MAX_TITLE)
    summary = _describe(start.doc) or f"Documentation and articles published on {site}."

    primary: list[str] = []
    optional: list[str] = []
    excluded: list[dict] = []
    for page in sorted(pages, key=lambda p: p.result.final_url if p.result else p.url):
        url = page.result.final_url if page.result else page.url
        raw_title = page.doc.title or urlsplit(url).path
        entry_title = _markdown_safe(raw_title, MAX_TITLE)
        description = _describe(page.doc)

        # This file gets published and read as authoritative. A page whose own
        # title or summary is addressed to a model does not go in it.
        matched = safety.instruction_like(raw_title) + safety.instruction_like(description or "")
        if matched:
            excluded.append({"url": url, "reason": "instruction_like", "patterns": sorted(set(matched))})
            continue

        line = f"- [{entry_title}]({url})"
        if description:
            line += f": {description}"
        # Thin pages go in Optional, which the format defines as skippable.
        target = optional if page.doc.content_chars < 600 else primary
        if len(target) < MAX_LINKS_PER_SECTION:
            target.append(line)

    lines = [f"# {title}", "", f"> {summary}", ""]
    if primary:
        lines += ["## Pages", "", *primary, ""]
    if optional:
        lines += ["## Optional", "", *optional, ""]

    text = "\n".join(lines).rstrip() + "\n"
    return {
        "text": text,
        "bytes": len(text.encode("utf-8")),
        "pages_listed": len(primary) + len(optional),
        "pages_optional": len(optional),
        "excluded": excluded,
        "parsed": parse(text),
    }


def run(args, run_id: str) -> dict:
    options = Options(
        allow_private=args.allow_private,
        timeout=args.timeout,
        max_bytes=args.max_bytes,
        check_robots=not args.no_robots,
    )
    parts = urlsplit(args.url)
    origin = f"{parts.scheme}://{parts.netloc}"

    existing = _fetch_optional(origin + CANONICAL_PATH, options)
    full = _fetch_optional(origin + FULL_PATH, options)

    findings: list[Finding] = []
    templates = data.load("findings")["checks"]
    if not existing["present"]:
        findings.append(_finding("llmstxt.missing", origin + CANONICAL_PATH, templates))
    elif not existing["valid"]:
        findings.append(
            _finding(
                "llmstxt.invalid",
                origin + CANONICAL_PATH,
                templates,
                "; ".join(existing["problems"]),
            )
        )

    block: dict = {
        "site": host_of(args.url),
        "llms_txt": existing,
        "llms_full_txt": {"url": full["url"], "present": full["present"], "status": full["status"]},
    }

    if getattr(args, "generate", False):
        crawl_options = crawl_cmd.options_from(args)
        result = crawl_lib.crawl(args.url, crawl_options)
        block["generated"] = generate(result, args.url)
        for entry in block["generated"]["excluded"]:
            findings.append(
                _finding(
                    "content.instruction_like",
                    entry["url"],
                    templates,
                    ", ".join(entry["patterns"]),
                )
            )
        block["crawl"] = {
            "pages_crawled": len(result.pages),
            "pages_ok": len(result.ok_pages),
            "stopped_because": result.stopped_because,
        }
        if args.out:
            block["generated"]["written_to"] = args.out

    return envelope.build(
        "llmstxt",
        ok=True,
        run_id=run_id,
        findings=[finding.to_dict() for finding in prioritize(findings)],
        extra={"llmstxt": block},
    )


def _finding(key: str, url: str, templates: dict, detail: str | None = None) -> Finding:
    template = templates[key]
    return Finding(
        id=key,
        severity=template["severity"],
        effort=template["effort"],
        title=template["title"],
        remediation=template["remediation"],
        pages=[url],
        excerpt=detail,
    )
