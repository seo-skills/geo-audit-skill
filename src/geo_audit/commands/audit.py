"""`geo audit` - crawl a site and score every category over it.

The composite combines category scores by weight, over the categories that
were actually computed. A category nobody measured leaves both sides of the
fraction, exactly as a null signal does: `--only schema` scores out of schema,
not out of schema plus four zeroes.

`--rescore` recomputes from a stored record with no network at all. That is
where the reproducibility claim lives: re-crawling a live site can legitimately
differ, because the site changed. Rescoring a snapshot twice cannot.
"""

from __future__ import annotations

from geo_audit import copy as copytext
from geo_audit import assistants, data, envelope, state
from geo_audit.commands import crawl as crawl_cmd
from geo_audit.commands.common import Options, Page, _check_finding, classify
from geo_audit.errors import GeoError
from geo_audit.lib import pages as pages_lib
from geo_audit.lib.ids import is_run_id
from geo_audit.lib.slug import project_slug
from geo_audit.scoring import (
    articles,
    citability,
    content as content_scorer,
    platform as platform_scorer,
    schema_org,
    technical,
)
from geo_audit.scoring.model import (
    Signal,
    aggregate,
    apply_impact,
    composite,
    findings_for,
    merge,
    prioritize,
    weighted_composite,
)

# What an audit can compute from a URL alone. `brand` needs a name, so it
# joins the run only when --brand is given: a category the inputs cannot
# reach is not "missing", it is out of scope for that run.
SITE_CATEGORIES = ("citability", "technical", "schema", "content", "platform")
CATEGORIES = SITE_CATEGORIES + ("brand",)


def candidates(args) -> tuple[str, ...]:
    """The categories this run's inputs can reach."""
    if getattr(args, "brand", None):
        return SITE_CATEGORIES + ("brand",)
    return SITE_CATEGORIES


def parse_only(value: str | None, available: tuple[str, ...] = CATEGORIES) -> tuple[str, ...]:
    if not value:
        return available
    chosen = tuple(part.strip().lower() for part in value.split(",") if part.strip())
    unknown = [name for name in chosen if name not in CATEGORIES]
    if unknown:
        raise GeoError(
            "GEO_E_BAD_ARGS",
            f"--only does not know {', '.join(unknown)}. "
            f"Available: {', '.join(CATEGORIES)}.",
        )
    out_of_scope = [name for name in chosen if name not in available]
    if out_of_scope:
        raise GeoError(
            "GEO_E_BAD_ARGS",
            f"--only {', '.join(out_of_scope)} needs an input this run does not "
            f"have. `brand` needs --brand <name>.",
        )
    return chosen


def _site_facts(result, args) -> tuple[dict, tuple[dict, str | None]]:
    """What is true of the site rather than of any one page, and the llms.txt it came from.

    Fetched once per run. Identical on every page, so `aggregate` carries it up
    to the site-level signal verbatim instead of averaging it away.
    """
    from geo_audit.commands import llmstxt as llmstxt_cmd
    from geo_audit.commands.common import Options

    options = Options(allow_private=args.allow_private, timeout=args.timeout)
    from urllib.parse import urlsplit

    parts = urlsplit(args.url)
    found, text = llmstxt_cmd._fetch_text(
        f"{parts.scheme}://{parts.netloc}{llmstxt_cmd.CANONICAL_PATH}", options
    )
    return _site_facts_from(result.robots, result.ok_pages, _llms_seen(found)), (found, text)


def _llms_seen(found: dict) -> dict:
    present = bool(found.get("present"))
    return {"llms_present": present, "llms_valid": bool(found.get("valid")) if present else None}


def _site_facts_from(robots, pages, llms: dict) -> dict:
    """Site facts from robots.txt, the pages, and what llms.txt was judged to be.

    All three are recomputed from what was read, so a rescore applies today's
    rules to each of them.
    """
    return {
        "sitemaps": list(robots.sitemaps) if robots else [],
        "languages": {page.doc.lang for page in pages if page.doc and page.doc.lang},
        "llms_present": llms.get("llms_present"),
        "llms_valid": llms.get("llms_valid"),
    }


def _replay(record: dict):
    """The pages an audit read, read back from the page store.

    None when any of them is gone - pruned, or never stored - because a partial
    replay would score a different site from the one that was audited.
    """
    snapshot = record.get("snapshot") or {}
    fetches = snapshot.get("fetches")
    if not fetches:
        return None
    slug = project_slug(record.get("crawl", {}).get("start_url", ""))
    robots = None
    entry = snapshot.get("robots")
    if entry:
        text = pages_lib.get(slug, entry["body"]) if entry.get("body") else None
        if entry.get("body") and text is None:
            return None
        robots = pages_lib.robots_from(entry, text)
    replayed = []
    for fetch in fetches:
        body = pages_lib.get(slug, fetch["body"]) if fetch.get("body") else ""
        if body is None:
            return None
        replayed.append(classify(Page(url=fetch["requested_url"], robots=robots), pages_lib.fetch_result(fetch, body)))
    seen: dict = {}
    entry = snapshot.get("llms")
    if entry:
        from geo_audit.commands import llmstxt as llmstxt_cmd

        text = pages_lib.get(slug, entry["body"]) if entry.get("body") else None
        if entry.get("body") and text is None:
            return None
        seen = _llms_seen({**llmstxt_cmd.parse(text), "present": True} if text is not None else {})
    facts = _site_facts_from(robots, [page for page in replayed if page.doc], seen)
    return replayed, robots, facts


def _forced(signal: Signal) -> Signal:
    """A copy scored at zero, so `findings_for` produces the finding's copy.

    The severity and the points are overwritten by the caller; this exists only
    to reach the template without duplicating the lookup.
    """
    return Signal(id=signal.id, cls=signal.cls, max=signal.max, value=0.0, detail=signal.detail)


def _score_page(page, robots, categories: tuple[str, ...], site_facts: dict | None = None,
                site_marks_articles: bool = False) -> dict[str, list[Signal]]:
    scored: dict[str, list[Signal]] = {}
    if "citability" in categories and page.doc is not None:
        # An audit never opens a browser: fifty pages through Chromium is a
        # different product. `geo score` renders a single page.
        scored["citability"] = citability.score(page.doc, rendered_chars=None,
                                                site_marks_articles=site_marks_articles)
    if "technical" in categories:
        scored["technical"] = technical.score(page, robots)
    if "schema" in categories and page.doc is not None:
        scored["schema"] = schema_org.score(page, site_marks_articles=site_marks_articles)
    if "content" in categories and page.doc is not None:
        scored["content"] = content_scorer.score(page, site_marks_articles=site_marks_articles)
    if "platform" in categories:
        scored["platform"] = platform_scorer.score(page, site_facts or {})
    return scored


def run(args, run_id: str) -> dict:
    if getattr(args, "rescore", None):
        if getattr(args, "assistants", None) is not None:
            raise GeoError(
                "GEO_E_BAD_ARGS",
                "--rescore uses no network, so it cannot ask assistants; the answers "
                "an audit recorded are replayed from it.",
            )
        return rescore(args, run_id)

    state.init()
    available = candidates(args)
    categories = parse_only(args.only, available)
    requested = _assistants_requested(args, categories)
    options = crawl_cmd.options_from(args)

    result = crawl_cmd.crawl_reporting(args, options, step=2, steps=4)
    _step(args, 3, f"Scoring {len(result.pages)} pages")
    site_facts, llms = _site_facts(result, args) if "platform" in categories else ({}, None)

    rules = data.thresholds("findings")
    per_category, findings, snapshot = _score_pages(result.pages, result.robots, categories, site_facts)
    offenders, severe, explained = _classify(snapshot, rules)
    # What the scorer read, not only what it computed: each page's response with
    # its body in the page store, with robots.txt and llms.txt beside them.
    slug = project_slug(args.url)
    snapshot["fetches"] = [
        pages_lib.fetch_record(page.result, pages_lib.put(slug, page.result.body) if page.result.body else None)
        for page in result.pages
        if page.result is not None
    ]
    snapshot["robots"] = pages_lib.robots_record(result.robots, slug)
    snapshot["llms"] = pages_lib.file_record(*llms, slug) if llms else None

    advisory = content_scorer.advisory_signals() if "content" in categories else []

    extra = None
    if "brand" in categories:
        from geo_audit.commands import scan as scan_cmd

        platforms = {
            name: scan_cmd.check(name, args.brand, spec, allow_private=args.allow_private)
            for name, spec in data.load("brand_platforms")["platforms"].items()
        }
        same_as = scan_cmd._same_as_for(args.url, args.allow_private, args.timeout)
        brand_signals = scan_cmd.build_signals(platforms, same_as)
        per_category["brand"] = [brand_signals]
        findings.extend(scan_cmd.brand_findings(brand_signals, args.brand))
        extra = {
            "scan": {
                "brand": args.brand,
                "site": args.url,
                "platforms": list(platforms.values()),
                "platforms_checked": sum(1 for entry in platforms.values() if entry["checked"]),
                "platforms_total": len(platforms),
                "total_results": sum(entry.get("results", 0) for entry in platforms.values() if entry["checked"]),
                "manual_checks": data.load("brand_platforms")["manual"],
                "same_as": same_as,
            }
        }
        if requested:
            extra["scan"]["assistants"] = assistants.ask(
                args.brand, args.url, requested, allow_private=args.allow_private,
                say=scan_cmd.announcer(args, args.brand),
            )

    _step(args, 4, "Recording the audit")
    return _assemble(
        run_id=run_id,
        start_url=args.url,
        categories=categories,
        per_category=per_category,
        findings=findings,
        crawl_block=crawl_cmd.crawl_block(result, options),
        evidence=crawl_cmd.evidence_block(result),
        record=True,
        available=available,
        advisory=advisory,
        offenders=offenders,
        severe=severe,
        explained=explained,
        extra=extra,
        snapshot=snapshot,
    )


def _assistants_requested(args, categories: tuple[str, ...]) -> list[str]:
    """The engines --assistants names, checked before anything is fetched."""
    value = getattr(args, "assistants", None)
    if value is None:
        return []
    if "brand" not in categories:
        raise GeoError(
            "GEO_E_BAD_ARGS",
            "--assistants asks about a brand, so it needs --brand <name> and the "
            "brand category in the run.",
        )
    return assistants.parse_engines(value)


def _step(args, step: int, action: str) -> None:
    if not args.quiet:
        import sys

        print(copytext.PROGRESS.format(step=step, total=4, action=action), file=sys.stderr)


def _score_pages(pages, robots, categories: tuple[str, ...], site_facts: dict) -> tuple[dict, list, dict]:
    """Score every page, keeping the per-page ratios and checks findings are made from.

    One function for a live audit and for a rescore that reads the stored pages
    back, so the two cannot score the same page differently.
    """
    per_category: dict[str, list[list[Signal]]] = {name: [] for name in categories}
    findings: list = []
    # G1: the record holds every scorer input. Per-page ratios and the fetch and
    # robots observations are what page-level and check findings are made from;
    # without them a rescore returned four of seomator.com's six findings.
    snapshot: dict = {"pages": [], "ratios": {}, "checks": []}
    # Read from the pages rather than passed in, so a rescore asks the same
    # question of the same pages as the audit that stored them.
    marks_articles = articles.marks_its_articles(page.doc for page in pages if page.doc is not None)
    for page in pages:
        scored = _score_page(page, robots, categories, site_facts, marks_articles)
        url = page.result.final_url if page.result else page.url
        index = len(snapshot["pages"])
        snapshot["pages"].append(url)
        for name, signals in scored.items():
            # A page with nothing to read is an example of what went wrong with
            # its response and of nothing site-wide: MDN's soft-404 page turned
            # up on the llms.txt finding. Scores are untouched - llms.txt has one
            # value on every page - only the list of pages to go and look at.
            if page.doc is None and name != "technical":
                continue
            for signal in signals:
                if signal.ratio is not None:
                    snapshot["ratios"].setdefault(signal.id, {})[index] = signal.ratio
        for name, signals in scored.items():
            per_category[name].append(signals)
        findings.extend(page.findings)
        snapshot["checks"].extend(
            {"id": check.id, "page": check.pages[0] if check.pages else url, "excerpt": check.excerpt}
            for check in page.findings
        )
    snapshot["ratios"] = {
        signal_id: [by_page.get(i) for i in range(len(snapshot["pages"]))]
        for signal_id, by_page in sorted(snapshot["ratios"].items())
    }
    return per_category, findings, snapshot


def _classify(snapshot: dict, rules: dict) -> tuple[dict[str, list[str]], dict[str, list[str]], dict[str, set[str]]]:
    """Which pages sit below the line for each signal, from the per-page ratios.

    A finding's severity and value come from the site, but its page list has to
    come from the pages, or "8 pages" and "the one bad page" look identical.

    One function for a live run and for a rescore of its snapshot, so the two
    cannot classify a page differently; the thresholds are the current ones,
    which is what makes a rescore a recomputation rather than a replay.
    """
    ceiling, floor = rules["no_finding_above"], rules["full_severity_below"]
    offenders: dict[str, list[str]] = {}
    severe: dict[str, list[str]] = {}
    for signal_id, ratios in snapshot["ratios"].items():
        for url, ratio in zip(snapshot["pages"], ratios):
            if ratio is None:
                continue
            if ratio <= ceiling:
                offenders.setdefault(signal_id, []).append(url)
            if ratio < floor:
                severe.setdefault(signal_id, []).append(url)
    return offenders, severe, _explained(snapshot)


def _explained(snapshot: dict) -> dict[str, set[str]]:
    """Per consequence, the pages where its cause already explains it.

    `findings_for` applies `consequences` to the signals it is handed, and the
    page-level pass hands it one signal at a time, so the rule had nothing to
    suppress from: a page with no structured data was told four more times that
    its structured data was incomplete. The site-level pass was never wrong,
    which is why this survived - on userguiding.com presence averaged 28.8 over
    fifty pages while the blog posts carried none.
    """
    declared = data.load("findings").get("consequences") or {}
    maxes = {
        signal_id: spec["max"]
        for category in data.weights().values()
        for signal_id, spec in category["signals"].items()
    }
    pages = snapshot["pages"]
    out: dict[str, set[str]] = {}
    for cause, rule in declared.items():
        if not isinstance(rule, dict):
            continue
        ceiling = rule.get("floor", 0) / (maxes.get(cause) or 1)
        at_floor = {
            url
            for url, ratio in zip(pages, snapshot["ratios"].get(cause) or [])
            if ratio is not None and ratio <= ceiling
        }
        if not at_floor:
            continue
        for consequence in rule.get("suppresses") or []:
            out.setdefault(consequence, set()).update(at_floor)
    return out


def _said_of_pages(meaning: str) -> str:
    """A tier's meaning, said of more than one page.

    `data/tiers.json` words each meaning for the one page `geo score` reads, so
    a fifty-page audit led with "AI engines can lift answers from this page".
    Rewording the data would move `data_version`, which `compare` treats as a
    change of yardstick, for what is a change of grammar.
    """
    return meaning.replace("from this page", "from these pages").replace("on the page", "on these pages")


def _assemble(
    *,
    run_id: str,
    start_url: str,
    categories: tuple[str, ...],
    per_category: dict[str, list[list[Signal]]],
    findings: list,
    crawl_block: dict,
    evidence: dict,
    record: bool,
    available: tuple[str, ...] | None = None,
    advisory: list[Signal] | None = None,
    offenders: dict[str, list[str]] | None = None,
    severe: dict[str, list[str]] | None = None,
    explained: dict[str, set[str]] | None = None,
    extra: dict | None = None,
    snapshot: dict | None = None,
) -> dict:
    weights = data.weights()
    available = available or categories
    severe = severe or {}
    explained = explained or {}
    category_scores: dict[str, int] = {}
    category_completeness: dict[str, dict] = {}
    all_signals: list[Signal] = []

    site = (crawl_block or {}).get("site") or start_url
    for name in categories:
        pages = per_category.get(name) or []
        if not pages:
            continue
        rolled = aggregate(pages)
        score, completeness = composite(rolled)
        category_scores[name] = score
        category_completeness[name] = completeness
        all_signals.extend(rolled)
        # Generated from the rolled-up signal: a site does not have a problem
        # because one of its forty pages does.
        if offenders is not None:
            reported = set()
            # Brand findings carry wording that depends on the signal's detail;
            # one helper words them wherever they are made.
            from geo_audit.commands import scan as scan_cmd

            produce = scan_cmd.brand_findings if name == "brand" else findings_for
            for finding in produce(rolled, site):
                finding.pages = sorted(set(offenders.get(finding.id) or []))
                reported.add(finding.id)
                findings.append(finding)

            # A site can be healthy on average and still have a handful of
            # pages that are not. Those are worth naming - "two pages return
            # almost nothing to a crawler" is the specific, actionable half of
            # a report - but they are demoted, because a minority of pages is
            # not the site's problem, and their impact comes from the site
            # signal, so they rank below the site-wide items rather than above
            # them.
            for signal in rolled:
                if signal.id in reported or signal.ratio is None:
                    continue
                pages = sorted(set(severe.get(signal.id) or []) - explained.get(signal.id, set()))
                if not pages:
                    continue
                for finding in findings_for([_forced(signal)], site):
                    # A blocker on the whole site still leads; a blocker on one
                    # page of forty is a page to go and look at.
                    finding.mark_page_level()
                    finding.pages = pages
                    finding.points_lost = signal.max - (signal.value or 0.0)
                    findings.append(finding)

    # Only the categories this run could reach: a category the inputs cannot
    # feed is out of scope, not missing.
    total, coverage = weighted_composite(
        {name: weights[name]["weight"] for name in available}, category_scores
    )
    tier = data.tier_for(total)

    signal_counts = [c["computed"] for c in category_completeness.values()]
    signal_totals = [c["total"] for c in category_completeness.values()]
    completeness = {
        "computed": sum(signal_counts),
        "total": sum(signal_totals),
        "missing": sorted(
            signal
            for detail in category_completeness.values()
            for signal in detail["missing"]
        ),
        "categories": coverage,
    }

    # Advisory signals ride along with the data so the rubric is never separated
    # from what it is about. `composite()` filters on class, so they cannot
    # reach a number by any path.
    all_signals.extend(advisory or [])

    ranked = prioritize(
        apply_impact(
            merge(findings),
            all_signals,
            {name: weights[name]["weight"] for name in weights},
        )
    )
    result = envelope.build(
        "audit",
        ok=True,
        run_id=run_id,
        evidence=evidence,
        completeness=completeness,
        scores={
            "composite": total,
            "tier": tier["label"],
            "tier_meaning": _said_of_pages(tier["meaning"]) if evidence.get("pages_ok", 0) > 1 else tier["meaning"],
            "categories": category_scores,
        },
        signals=[signal.to_dict() for signal in all_signals],
        findings=[finding.to_dict() for finding in ranked],
        extra={"crawl": crawl_block, **(extra or {})},
    )

    if record:
        # The snapshot goes to disk with the record and never to stdout: it is
        # for rescoring, and the skill that reads the envelope has no use for it.
        stored = {**result, "snapshot": snapshot} if snapshot else result
        path = state.append_audit(project_slug(start_url), stored)
        try:
            inside = path.relative_to(state.geo_home()).as_posix()
            result["crawl"]["record"] = f"{state.display_home()}/{inside}"
        except ValueError:
            result["crawl"]["record"] = str(path)
    return result


def rescore(args, run_id: str) -> dict:
    """Recompute from a stored record. No network, no crawl, no clock."""
    wanted = args.rescore
    if not is_run_id(wanted):
        raise GeoError(
            "GEO_E_BAD_ARGS",
            f"{wanted!r} is not a run id. Run ids are 26 characters and appear "
            f"as `run_id` in any envelope.",
        )

    state.init()
    slug = project_slug(args.url) if getattr(args, "url", None) else None
    record = _find_record(wanted, slug)
    if record is None:
        where = f"for {slug}" if slug else "in any project"
        raise GeoError(
            "GEO_E_BAD_ARGS",
            f"No audit with run id {wanted} was found {where}. {_what_is_recorded(slug)}",
        )

    stored_signals = [
        Signal(
            id=entry["id"],
            cls=entry["class"],
            max=entry["max"],
            value=entry["value"],
            detail=entry.get("detail") or {},
            page=entry.get("page"),
            skipped_reason=entry.get("skipped_reason"),
        )
        for entry in record.get("signals") or []
    ]

    by_category: dict[str, list[list[Signal]]] = {}
    stored_advisory = [signal for signal in stored_signals if signal.cls == "advisory"]
    for signal in stored_signals:
        if signal.cls == "advisory":
            continue
        name = signal.id.split(".", 1)[0]
        by_category.setdefault(name, [[]])[0].append(signal)

    categories = tuple(name for name in CATEGORIES if name in by_category)
    findings: list = []

    current = {
        "scoring_version": envelope.SCORING_VERSION,
        "data_version": data.data_version(),
        "normalizer_version": envelope.NORMALIZER_VERSION,
    }
    recorded = {
        "scoring_version": record.get("scoring_version"),
        "data_version": record.get("data_version"),
        "normalizer_version": record.get("normalizer_version"),
    }
    rescore_block = {
        "run_id": wanted,
        "observed_at": record.get("observed_at"),
        "recorded_versions": recorded,
        "current_versions": current,
        "versions_match": recorded == current,
        "recorded_composite": (record.get("scores") or {}).get("composite"),
    }

    snapshot = record.get("snapshot")
    per_category = {name: by_category[name] for name in categories}
    replayed = _replay(record) if snapshot else None
    if replayed:
        # The whole scoring pipeline again, on the exact pages the audit read,
        # with today's code: a changed rule is re-applied, not replayed.
        pages, robots, facts = replayed
        page_categories = tuple(name for name in categories if name != "brand")
        per_category, findings, fresh = _score_pages(pages, robots, page_categories, facts)
        offenders, severe, explained = _classify(fresh, data.thresholds("findings"))
        if "brand" in by_category:
            per_category["brand"] = by_category["brand"]
        source = "pages"
    elif snapshot:
        offenders, severe, explained = _classify(snapshot, data.thresholds("findings"))
        findings = [
            _check_finding(check["id"], check["page"], check.get("excerpt"))
            for check in snapshot.get("checks") or []
        ]
        source = "ratios"
    else:
        # Recorded before snapshots existed: page lists can only come from the
        # recorded findings, and page-level and check findings cannot be rebuilt.
        offenders = {f["id"]: f.get("pages") or [] for f in record.get("findings") or []}
        severe = {}
        explained = {}
        source = "record"
    brand = (record.get("scan") or {}).get("brand")
    if brand and "brand" in by_category:
        from geo_audit.commands import scan as scan_cmd

        findings.extend(scan_cmd.brand_findings(by_category["brand"][0], brand))
    rescore_block["snapshot"] = bool(snapshot)
    # What this rescore recomputed from: the stored pages, the stored per-page
    # ratios, or - for a record older than both - the recorded findings.
    rescore_block["from"] = source

    return _assemble(
        run_id=run_id,
        start_url=record.get("crawl", {}).get("start_url", ""),
        categories=categories,
        per_category=per_category,
        findings=findings,
        offenders=offenders,
        severe=severe,
        explained=explained,
        crawl_block=record.get("crawl", {}),
        evidence=record.get("evidence") or {},
        record=False,
        available=categories,
        advisory=stored_advisory,
        # Brand observations, assistant answers among them, are replayed as they
        # were recorded: a rescore never asks again.
        extra={"rescore": rescore_block, **({"scan": record["scan"]} if record.get("scan") else {})},
    )


def _what_is_recorded(slug: str | None) -> str:
    """Name the run ids that are there, for someone who mistyped one.

    This hint used to read "`geo audit --list` shows what is recorded", and
    there is no such flag: the parser answers it with `unrecognized arguments`
    and exit 2, which is a worse dead end than the error it was explaining.
    """
    slugs = [slug] if slug else _known_slugs()
    recent = [
        record["run_id"]
        for candidate in slugs
        for record in _audits(candidate)
        if record.get("run_id")
    ][-3:]
    if recent:
        return "Recorded here: " + ", ".join(reversed(recent)) + "."
    if slug:
        return f"Nothing is recorded yet in {state.audits_path(slug)}."
    return "No project has a recorded audit yet."


def _audits(slug: str) -> list[dict]:
    """The audits in a project's history. `geo score` records there too, and a
    score record has no crawl to rescore."""
    return [record for record in state.read_audits(slug)[0] if record.get("command") == "audit"]


def _find_record(run_id: str, slug: str | None) -> dict | None:
    slugs = [slug] if slug else _known_slugs()
    for candidate in slugs:
        for record in reversed(_audits(candidate)):
            if record.get("run_id") == run_id:
                return record
    return None


def _known_slugs() -> list[str]:
    root = state.geo_home() / "projects"
    if not root.is_dir():
        return []
    return sorted(path.name for path in root.iterdir() if path.is_dir())
