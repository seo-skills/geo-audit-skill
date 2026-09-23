"""`geo crawl` - what a crawler can reach, and what it was turned away from.

Reports the frontier as data: pages fetched, pages that failed and why, pages
robots.txt put out of reach, and pages found only in the sitemap. None of it
is scored here; `geo audit` does that. Keeping them apart means a crawl can be
inspected on its own when a score looks wrong.
"""

from __future__ import annotations

from geo_audit import copy as copytext
from geo_audit import envelope
from geo_audit.commands.common import robots_block
from geo_audit.lib import crawl as crawl_lib
from geo_audit.lib import evidence as evidence_lib
from geo_audit.lib.slug import host_of
from geo_audit.scoring.model import merge, prioritize


def crawl_reporting(args, options: crawl_lib.CrawlOptions, *, step: int, steps: int) -> crawl_lib.CrawlResult:
    """Crawl, reporting the page count on stderr as step `step` of `steps`.

    A line per page made fifty lines of one audit, on a terminal and in the
    output a skill reads alike. On a terminal the count now rewrites one line
    in place - it only grows, so a carriage return needs no clearing - and
    anywhere else only the final count is written. `--verbose` asks for the
    line per page back, which is the one thing this command has more of to say.
    """
    import sys

    stream = sys.stderr
    live = not args.quiet and stream.isatty()
    verbose = getattr(args, "verbose", False) and not args.quiet

    def line(done: int, total: int, failed: int) -> str:
        action = f"Crawling {host_of(args.url)} - {done}/{total} pages, {failed} failed"
        return copytext.PROGRESS.format(step=step, total=steps, action=action)

    last = ""

    def progress(done: int, total: int, failed: int) -> None:
        # `last` tracks what the stream has actually seen, so the final line is
        # skipped only when it would repeat one, never when nothing was written.
        nonlocal last
        text = line(done, total, failed)
        if verbose:
            print(text, file=stream)
            last = text
        elif live:
            print("\r" + text, end="", file=stream, flush=True)
            last = text

    result = crawl_lib.crawl(args.url, options, progress=progress)
    final = line(len(result.pages), options.max_pages, len(result.failures))
    # On a terminal the final line also ends the one being rewritten in place.
    if not args.quiet and (live or final != last):
        print(("\r" if live else "") + final, file=stream)
    return result


def options_from(args) -> crawl_lib.CrawlOptions:
    return crawl_lib.CrawlOptions(
        allow_private=args.allow_private,
        timeout=args.timeout,
        max_bytes=args.max_bytes,
        check_robots=not args.no_robots,
        max_pages=args.max_pages,
        requests_per_second=args.rate,
        concurrency=args.concurrency,
        use_sitemap=not args.no_sitemap,
    )


def page_summary(page) -> dict:
    result = page.result
    return {
        "url": result.final_url if result else page.url,
        "status": result.status if result else None,
        "blocks": len(page.doc.blocks) if page.doc else 0,
        "content_chars": page.doc.content_chars if page.doc else 0,
        "content_root": page.doc.content_root if page.doc else None,
        "content_hash": evidence_lib.digest(page.doc.blocks) if page.doc else None,
        "headings": len(page.doc.headings) if page.doc else 0,
        "jsonld_types": sorted(
            {
                str(entry)
                for node in (page.doc.jsonld if page.doc else [])
                for entry in (
                    node["@type"] if isinstance(node.get("@type"), list) else [node.get("@type")]
                )
                if entry
            }
        ),
        "scorable": page.scorable,
    }


def crawl_block(result: crawl_lib.CrawlResult, options: crawl_lib.CrawlOptions) -> dict:
    pages = sorted(result.pages, key=lambda page: page.url)
    return {
        "start_url": result.start_url,
        "site": host_of(result.start_url),
        "pages_crawled": len(result.pages),
        "pages_ok": len(result.ok_pages),
        "discovered": result.discovered,
        "seeded_from_sitemap": result.seeded_from_sitemap,
        "disallowed_by_robots": sorted(result.disallowed),
        "stopped_because": result.stopped_because,
        "elapsed_ms": result.elapsed_ms,
        "limits": {
            "max_pages": options.max_pages,
            "requests_per_second": options.requests_per_second,
            "concurrency": options.concurrency,
            "timeout": options.timeout,
            "robots_respected": options.check_robots,
            "sitemap_used": options.use_sitemap,
        },
        "robots": robots_block(pages[0]) if pages else None,
        "pages": [page_summary(page) for page in pages],
    }


def evidence_block(result: crawl_lib.CrawlResult) -> dict:
    digests = [evidence_lib.digest(page.doc.blocks) for page in result.ok_pages]
    return {
        "stamp": evidence_lib.stamp_for(len(result.ok_pages), result.failures),
        "content_hash": evidence_lib.site_digest(digests) if digests else None,
        "normalizer_version": evidence_lib.NORMALIZER_VERSION,
        "pages_ok": len(result.ok_pages),
        # Sorted: the order pages happened to fail is a property of the race,
        # not of the site.
        "pages_failed": sorted(result.failures, key=lambda entry: entry["url"]),
    }


def run(args, run_id: str) -> dict:
    options = options_from(args)
    result = crawl_reporting(args, options, step=2, steps=2)
    findings = prioritize(merge([f for page in result.pages for f in page.findings]))

    return envelope.build(
        "crawl",
        ok=True,
        run_id=run_id,
        evidence=evidence_block(result),
        findings=[f.to_dict() for f in findings],
        extra={"crawl": crawl_block(result, options)},
    )
