"""The two render contexts.

Isolation by construction, not by conditional. `ClientContext` holds what a
client may see; `OperatorContext` holds what only the agency should. The client
template is rendered with a namespace that has no operator key in it at all, so
a leak is not a missing `{% if %}` - it is a `jinja2.UndefinedError` at render
time, which is a test failure rather than an email to a client.

This is the regression class the design is aimed at: an operator-only field
appearing in a delivered report because a conditional was inverted, or because
someone added a field to a shared context and forgot which half it belonged to.
"""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass, field, fields

from geo_audit import assistants, data
from geo_audit._version import PRODUCT_NAME
from geo_audit.copy import CAPPED
from geo_audit.lib.crawl import urls_found
from geo_audit.report.advisory import merge as advisory_merge
from geo_audit.report.brand import Brand
from geo_audit.scoring.model import NOT_APPLICABLE, Finding, for_site_kind, site_kinds

# On page one, under the number. Buried in an appendix it does not travel, and
# the eval showed exactly what that costs: sqlite.org scores 44 with twenty of
# its fifty-six missing points coming from absent metadata alone, while its
# documentation is among the most-cited technical writing on the web. Both
# facts are true. A report that states only the first one will be argued with.
SCORE_CAVEAT = (
    "This measures how readable and attributable these pages are to a machine: "
    "what a crawler can fetch, quote and attribute. It is not a measure of how "
    "often the site is cited today. A well-known site with sparse metadata will "
    "score below its reputation, and the categories below show where the "
    "difference sits."
)

CATEGORY_BLURB = {
    "citability": "Whether a passage can be lifted from the page and used as an answer.",
    "technical": "Whether a crawler can reach, read and index the page at all.",
    "schema": "Whether the page describes itself in a form nobody has to interpret.",
    "brand": "Whether the name resolves to an entity an engine can look up.",
    "content": "Whether the writing says who stands behind it, when it was last checked, and enough to answer on its own.",
    "platform": "Whether the site publishes what engines read around its pages: llms.txt, feeds, social cards and language versions.",
}

SEVERITY_ORDER = ("critical", "high", "medium", "low")

# The plan groups every fix by what it costs, in the ranked order. Time words,
# because that is how a plan is read; the rule underneath, because the tool
# knows effort and not anyone's calendar.
HORIZONS = (("This week", "low"), ("This month", "medium"), ("This quarter", "high"))

GLOSSARY = (
    ("GEO", "Generative engine optimization: making pages easy for AI answer engines to find, read, quote and attribute."),
    ("AI Overviews", "The AI-written answers Google shows above its search results."),
    ("Crawler", "A program that fetches pages - for a search index, to train a model, or to answer one user's question."),
    ("robots.txt", "The file at the root of a site that tells crawlers which parts they may fetch."),
    ("llms.txt", "A markdown file at the root of a site telling AI systems what the site is and which pages matter."),
    ("Structured data", "A machine-readable description embedded in a page, usually as JSON-LD, that engines read without interpreting the prose."),
    ("sameAs", "A structured-data property linking an organization or person to their profiles elsewhere, so engines can tell which entity it is."),
    ("E-E-A-T", "Experience, expertise, authoritativeness and trust: what search engines look for in who wrote a page and why to believe it."),
    ("Server-side rendering", "Sending a page's content in the HTML itself, so a crawler that does not run JavaScript still sees it."),
)


@dataclass
class Fix:
    priority: int
    title: str
    remediation: str
    severity: str
    effort: str
    pages: list[str]
    points: float
    category: str
    # What fixing it is worth on the overall 0-100 score - the finding's
    # `impact`. `points` is on the category's own scale, which a client misreads.
    impact: float | None = None
    # What the scorer measured, in sentences built from the signal's own detail.
    evidence: list[str] = field(default_factory=list)
    excerpt: str | None = None
    blocking: bool = False

    @property
    def page_count(self) -> int:
        return len(self.pages)


@dataclass
class CategoryScore:
    name: str
    score: int
    tier: str
    weight: int | None
    blurb: str
    # This category's share of the composite: score x weight / total weight.
    contribution: float = 0.0


@dataclass
class ClientContext:
    """Everything a client may see. Nothing here is operator-only."""

    product_name: str
    brand: Brand
    site: str
    generated_on: str
    composite: int | None
    tier: str | None
    tier_meaning: str | None
    score_caveat: str
    pages_scored: int
    evidence_stamp: str
    evidence_note: str | None
    categories: list[CategoryScore] = field(default_factory=list)
    headlines: list[Fix] = field(default_factory=list)
    top_fixes: list[Fix] = field(default_factory=list)
    by_category: dict[str, list[Fix]] = field(default_factory=dict)
    advisory: list[dict] = field(default_factory=list)
    # What AI assistants answered when asked about the brand: observed, never scored.
    assistants: dict | None = None
    # Set when the findings were ordered for a kind of site. The scores never are.
    ordered_for: str | None = None
    strengths: list[dict] = field(default_factory=list)
    summary: str = ""
    plan: list[dict] = field(default_factory=list)
    crawlers: list[dict] = field(default_factory=list)
    category_detail: list[dict] = field(default_factory=list)
    pages_analysed: list[dict] = field(default_factory=list)
    # Categories this run did not reach, so the weights above add up to less
    # than 100 - said on the page rather than left for a client to work out.
    unscored: list[dict] = field(default_factory=list)
    # PRD §3.4: "the report says 'computed on 31 of 36 signals'". It qualifies
    # the number, so it sits under the number.
    completeness_note: str | None = None
    # A crawl that stopped at its page limit read part of the site, and the
    # number is about that part - said under the number for the same reason.
    coverage_note: str | None = None
    glossary: list[dict] = field(default_factory=list)
    methodology: list[dict] = field(default_factory=list)
    signal_classes: list[dict] = field(default_factory=list)
    versions: dict = field(default_factory=dict)


@dataclass
class OperatorContext:
    """Never passed to the client render. Ever."""

    run_id: str
    observed_at: str
    evidence_hash: str | None
    record_path: str | None
    crawl_limits: dict = field(default_factory=dict)
    pages_failed: list[dict] = field(default_factory=list)
    disallowed: list[str] = field(default_factory=list)
    signals: list[dict] = field(default_factory=list)
    brand_warnings: list[str] = field(default_factory=list)
    contrast: list[dict] = field(default_factory=list)
    completeness: dict = field(default_factory=dict)
    # The user's own scrape.do account: what the assistant answers cost, and why
    # none were asked. Account details, so never in the client copy.
    assistants: dict | None = None


def ordered_findings(findings: list[dict], site_kind: str | None) -> list[dict]:
    """The recorded order, or that order re-weighted for a kind of site.

    Rebuilt as `Finding`s so the one real `prioritize` does the ordering; a
    second copy of its sort key here would drift from it. Unknown keys are
    dropped because the history on disk spans versions. Public because the eval
    harness must show the practitioner the order the report shows, not its own.
    """
    if site_kind is None:
        return findings
    known = {f.name for f in fields(Finding)}
    rebuilt = [Finding(**{k: v for k, v in item.items() if k in known}) for item in findings]
    return [f.to_dict() for f in for_site_kind(rebuilt, site_kind)]


def _ordered_for(site_kind: str | None) -> str | None:
    if site_kind is None:
        return None
    spec = site_kinds()[site_kind]
    return (
        f"Ordered for {spec['label']}. {spec['note']} "
        "The scores are the same whatever the kind of site."
    )


def strengths(
    signals: list[dict], findings: list[dict], weights: dict[str, int], site_kind: str | None
) -> list[dict]:
    """What the site already does well: up to three, never contradicted.

    Three rounds of maintainer notes said it - a report that lists only what is
    wrong reads as grudging, and a 76 with nothing named for it is the first
    thing a practitioner edits before sending.

    A strength is a site-wide signal at or above `strength_at_least` of its
    maximum that has no finding anywhere in the report, page-level included, so
    "served over HTTPS" never sits beside "not served securely". Heavier
    categories come first, then the signals that carry more of their category,
    one per category before a second from any; with a site kind, what it leads
    with comes first and what it defers last.
    """
    floor = data.thresholds("findings")["strength_at_least"]
    templates = data.load("findings")["signals"]
    reported = {finding["id"] for finding in findings}
    spec = site_kinds()[site_kind] if site_kind else {"lead": [], "defer": []}
    ranked = []
    for signal in signals:
        signal_id, value, maximum = signal["id"], signal.get("value"), signal.get("max")
        if signal.get("class") == "advisory" or value is None or not maximum:
            continue
        if value / maximum < floor or signal_id in reported:
            continue
        sentence = (templates.get(signal_id) or {}).get("strength")
        if not sentence:
            continue
        kind_rank = 0 if signal_id in spec["lead"] else 2 if signal_id in spec["defer"] else 1
        category = signal_id.split(".", 1)[0]
        ranked.append(((kind_rank, -weights.get(category, 0), -maximum, signal_id), sentence))
    # One per category before a second from any: the heaviest category otherwise
    # takes every slot, and plausible's best area - technical, 95 - went unnamed.
    ordered = sorted(ranked)
    chosen, used = [], set()
    for key, sentence in ordered:
        category = key[-1].split(".", 1)[0]
        if category not in used:
            chosen.append((key, sentence))
            used.add(category)
    chosen += [pair for pair in ordered if pair not in chosen]
    return [{"id": key[-1], "text": sentence} for key, sentence in chosen[:3]]


def _num(value: float | None) -> str:
    return "-" if value is None else f"{value:g}"


def _evidence(signal: dict | None) -> list[str]:
    """What the scorer saw, from the recorded signal - never a model's reading.

    The reference writes this part by hand for each client. Here it comes from
    the detail the scorer already recorded: which parts were found, and whether
    the score is the same everywhere or carried by a few weak pages.
    """
    if not signal:
        return []
    detail, lines = signal.get("detail") or {}, []
    present, missing = detail.get("present"), detail.get("missing")
    if isinstance(present, list) and present:
        lines.append("Found: " + ", ".join(part.replace("_", " ") for part in present) + ".")
    if isinstance(missing, list) and missing:
        lines.append("Missing: " + ", ".join(part.replace("_", " ") for part in missing) + ".")
    mean, measured = detail.get("mean"), detail.get("pages_measured")
    if mean is not None and measured:
        maximum = _num(signal.get("max"))
        if detail.get("min") == detail.get("max"):
            lines.append(
                f"{_num(mean)} of {maximum} on every page measured ({measured}): "
                "one shared template decides it, so one change fixes it everywhere."
            )
        else:
            lines.append(
                f"Averages {_num(mean)} of {maximum} over {measured} pages; the lowest, "
                f"{_num(detail.get('min'))}, is {detail.get('worst_page')}."
            )
    return lines


def _fixes_from(findings: list[dict], signals: dict[str, dict] | None = None) -> list[Fix]:
    signals = signals or {}
    blocking = set((data.load("findings").get("blocking") or {}).get("ids") or [])
    out: list[Fix] = []
    for finding in findings:
        out.append(
            Fix(
                priority=finding.get("priority", 0),
                title=finding["title"],
                remediation=finding["remediation"],
                severity=finding["severity"],
                effort=finding["effort"],
                pages=finding.get("pages") or [],
                points=finding.get("points_lost", 0.0),
                category=finding["id"].split(".", 1)[0],
                impact=finding.get("impact"),
                evidence=_evidence(signals.get(finding["id"])),
                excerpt=finding.get("excerpt"),
                blocking=finding["id"] in blocking and not finding.get("page_level"),
            )
        )
    return out


def _summary(site: str, composite: int | None, tier: str | None, pages: int,
             categories: list[CategoryScore], fixes: list[Fix]) -> str:
    """Two or three sentences from the numbers: the reference's executive
    summary, minus anything the tool did not measure."""
    if composite is None:
        return ""
    parts = [f"{site} scores {composite}/100 ({tier}) over {pages} page{'' if pages == 1 else 's'}."]
    if len(categories) > 1:
        best = max(categories, key=lambda c: c.score)
        worst = min(categories, key=lambda c: c.score)
        if best.score != worst.score:
            parts.append(f"Its strongest area is {best.name} ({best.score}) and its weakest is {worst.name} ({worst.score}).")
    blocker = next((fix for fix in fixes if fix.blocking), None)
    if blocker:
        parts.append(f"One fix comes before every other: {blocker.title}.")
    else:
        gain = max((fix for fix in fixes if fix.impact), key=lambda fix: fix.impact, default=None)
        if gain:
            parts.append(f"The largest single gain is \u201c{gain.title}\u201d, worth up to {_num(gain.impact)} points on the overall score.")
    return " ".join(parts)


def _plan(fixes: list[Fix]) -> list[dict]:
    """Every fix once, in ranked order, grouped by what it costs.

    A blocker is in the first group whatever it costs: nothing else recovers
    anything while a crawler cannot read the site.
    """
    by_effort = {effort: name for name, effort in HORIZONS}
    groups: dict[str, list[Fix]] = {name: [] for name, _ in HORIZONS}
    for fix in fixes:
        name = HORIZONS[0][0] if fix.blocking else by_effort.get(fix.effort, HORIZONS[-1][0])
        groups[name].append(fix)
    return [
        {"name": name, "effort": effort, "fixes": groups[name], "gain": round(sum(f.impact or 0 for f in groups[name]), 1)}
        for name, effort in HORIZONS
        if groups[name]
    ]


def _assistants(envelope: dict) -> dict | None:
    """Each engine's two answers, in the sentences the terminal uses.

    Absent when nothing was asked: a report does not advertise a check the run
    did not make. Only what the engines said reaches the client copy; the key's
    account details are the operator's.
    """
    block = (envelope.get("scan") or {}).get("assistants")
    if not block or not block.get("asked"):
        return None
    brand = block.get("brand") or "the brand"
    engines = []
    for entry in block.get("engines") or []:
        first = entry.get("brand_question") or {}
        second = entry.get("category_question") or {}
        about, ranking = assistants.describe(entry, brand)
        engines.append({
            "label": entry.get("label"),
            "model": entry.get("model"),
            "about": about,
            "ranking": ranking,
            "said": first.get("offers") or first.get("description"),
            "competitors": first.get("competitors") or [],
            "listed": second.get("listed") or [],
            "ranked": second.get("ranked", True),
            "cited": second.get("cited") or first.get("cited") or [],
            "questions": [q for q in (first.get("question"), second.get("question")) if q],
        })
    observed = next(
        (e.get("brand_question", {}).get("observed_at") for e in block.get("engines") or []
         if (e.get("brand_question") or {}).get("observed_at")),
        None,
    )
    return {
        "brand": brand,
        "category": block.get("category"),
        "observed_on": (observed or "")[:10] or None,
        "provider": block.get("provider"),
        "engines": engines,
    }


def _assistant_account(envelope: dict) -> dict | None:
    block = (envelope.get("scan") or {}).get("assistants")
    if not block:
        return None
    return {
        "asked": bool(block.get("asked")),
        "reason": block.get("reason"),
        "requested": block.get("requested") or [],
        "credits_used": block.get("credits_used"),
        "credits_remaining": block.get("credits_remaining"),
    }


def _crawlers(envelope: dict) -> list[dict]:
    """Who can reach the site, and what each refusal costs.

    The reference prints a platform and a status. The data here also says what
    the crawler is for and what blocking it rules out, which is the part a
    client needs to decide - refusing a training crawler is a coherent choice,
    refusing a search crawler is a decision to be absent from that engine.
    """
    access = (((envelope.get("crawl") or {}).get("robots") or {}).get("access")) or []
    known = {entry["token"]: entry for entry in data.crawlers()}
    rows = []
    for entry in access:
        meta = known.get(entry["agent"], {})
        allowed, critical = bool(entry.get("allowed")), bool(meta.get("critical"))
        if allowed:
            advice = "Nothing to do."
        elif critical:
            advice = f"Allow it: blocking it rules out {meta.get('gates', 'its engine')}."
        else:
            advice = f"Your call: blocking it only affects {meta.get('gates', 'model training')}."
        rows.append({
            "token": entry["agent"], "operator": meta.get("operator", ""),
            "purpose": meta.get("purpose", ""), "gates": meta.get("gates", ""),
            "allowed": allowed, "critical": critical, "advice": advice,
        })
    return sorted(rows, key=lambda row: (row["operator"], not row["critical"], row["token"]))


def _category_detail(envelope: dict, categories: list[CategoryScore]) -> list[dict]:
    """Every signal under its category, by name: the deep dive, from the data."""
    templates = data.load("findings")["signals"]
    grouped: dict[str, list[dict]] = {}
    for signal in envelope.get("signals") or []:
        if signal.get("class") == "advisory":
            continue
        grouped.setdefault(signal["id"].split(".", 1)[0], []).append(signal)
    order = [c.name for c in categories] + sorted(set(grouped) - {c.name for c in categories})
    scores = {c.name: c.score for c in categories}
    out = []
    for name in order:
        rows = []
        for signal in grouped.get(name, []):
            value, maximum = signal.get("value"), signal.get("max")
            label = (templates.get(signal["id"]) or {}).get("name") or signal["id"].split(".", 1)[1].replace("_", " ")
            reason = signal.get("skipped_reason") if value is None else None
            # "Not measured" is a gap in the audit; "not applicable" is not.
            applies = not (reason or "").startswith(NOT_APPLICABLE)
            rows.append({
                "name": label, "value": _num(value), "max": _num(maximum),
                "percent": round(100 * value / maximum) if value is not None and maximum else None,
                "status": None if value is not None else "Not measured" if applies else "Not applicable",
                "note": reason if applies else reason.partition(": ")[2] or None,
            })
        if rows:
            out.append({"name": name, "score": scores.get(name), "signals": rows})
    return out


def _completeness_note(completeness: dict) -> str | None:
    computed, total = completeness.get("computed"), completeness.get("total")
    if not total:
        return None
    note = f"Computed on {computed} of {total} signals."
    missing = completeness.get("missing") or []
    if missing:
        templates = data.load("findings")["signals"]
        names = [
            (templates.get(signal_id) or {}).get("name") or signal_id.split(".", 1)[-1].replace("_", " ")
            for signal_id in missing
        ]
        note += " Not measured: " + ", ".join(names) + " - the score is taken over the rest."
    return note


def _coverage_note(crawl: dict, evidence: dict) -> str | None:
    if crawl.get("stopped_because") != "max_pages":
        return None
    return CAPPED.format(
        limit=(crawl.get("limits") or {}).get("max_pages"), found=urls_found(crawl), scored=evidence.get("pages_ok", 0)
    )


def _pages_analysed(envelope: dict, fixes: list[Fix]) -> list[dict]:
    """Every crawled page and how many findings name it. No titles: the crawl
    record carries no page text, because the skill reads it and page text is
    an injection channel. The URL identifies the page."""
    counts = Counter(url for fix in fixes for url in set(fix.pages))
    return [
        {"url": page["url"], "status": page.get("status"),
         "read": bool(page.get("scorable")), "findings": counts.get(page["url"], 0)}
        for page in (envelope.get("crawl") or {}).get("pages") or []
    ]


def _evidence_note(envelope: dict) -> str | None:
    evidence = envelope.get("evidence") or {}
    stamp = evidence.get("stamp")
    failed = evidence.get("pages_failed") or []
    if stamp == "PARTIAL" and failed:
        reasons: dict[str, int] = {}
        for entry in failed:
            reasons[entry["reason"]] = reasons.get(entry["reason"], 0) + 1
        summary = ", ".join(f"{count} {reason.replace('_', ' ')}" for reason, count in sorted(reasons.items()))
        return (
            f"{evidence.get('pages_ok', 0)} pages were scored. {len(failed)} could not "
            f"be evaluated ({summary}), so the scores cover the pages that were."
        )
    if stamp == "STALE":
        return "Some pages have changed since this evidence was gathered."
    return None


def build(
    envelope: dict,
    brand: Brand,
    *,
    generated_on: str,
    record_path: str | None = None,
    advisory_answers: dict[str, dict] | None = None,
    site_kind: str | None = None,
) -> tuple[ClientContext, OperatorContext]:
    scores = envelope.get("scores") or {}
    evidence = envelope.get("evidence") or {}
    crawl = envelope.get("crawl") or {}
    completeness = envelope.get("completeness") or {}
    weights = (completeness.get("categories") or {}).get("weights_used") or {}
    total_weight = sum(weights.values())

    recorded = {signal["id"]: signal for signal in envelope.get("signals") or []}
    fixes = _fixes_from(ordered_findings(envelope.get("findings") or [], site_kind), recorded)
    by_category: dict[str, list[Fix]] = {}
    for fix in fixes:
        by_category.setdefault(fix.category, []).append(fix)

    categories = [
        CategoryScore(
            name=name,
            score=value,
            tier=data.tier_for(value)["label"],
            weight=weights.get(name),
            blurb=CATEGORY_BLURB.get(name, ""),
            contribution=round(value * weights.get(name, 0) / total_weight, 1) if total_weight else 0.0,
        )
        for name, value in sorted(
            (scores.get("categories") or {}).items(), key=lambda pair: -pair[1]
        )
    ]

    client = ClientContext(
        product_name=PRODUCT_NAME,
        brand=brand,
        site=crawl.get("site") or envelope.get("site") or "",
        generated_on=generated_on,
        composite=scores.get("composite"),
        tier=(scores.get("tier") or "").capitalize() or None,
        tier_meaning=scores.get("tier_meaning"),
        score_caveat=SCORE_CAVEAT,
        pages_scored=evidence.get("pages_ok", 0),
        evidence_stamp=evidence.get("stamp", "CURRENT"),
        evidence_note=_evidence_note(envelope),
        ordered_for=_ordered_for(site_kind),
        summary=_summary(
            crawl.get("site") or envelope.get("site") or "", scores.get("composite"),
            (scores.get("tier") or "").capitalize() or None, evidence.get("pages_ok", 0),
            categories, fixes,
        ),
        plan=_plan(fixes),
        crawlers=_crawlers(envelope),
        assistants=_assistants(envelope),
        category_detail=_category_detail(envelope, categories),
        pages_analysed=_pages_analysed(envelope, fixes),
        glossary=[{"term": term, "meaning": meaning} for term, meaning in GLOSSARY],
        completeness_note=_completeness_note(completeness),
        coverage_note=_coverage_note(crawl, evidence),
        unscored=[
            {"name": name, "weight": spec["weight"]}
            for name, spec in data.weights().items()
            if weights and name not in weights
        ],
        strengths=strengths(
            envelope.get("signals") or [], envelope.get("findings") or [], weights, site_kind
        ),
        categories=categories,
        headlines=fixes[:3],
        top_fixes=fixes[:8],
        by_category=by_category,
        advisory=advisory_merge(
            [
                signal
                for signal in envelope.get("signals") or []
                if signal.get("class") == "advisory"
            ],
            advisory_answers or {},
        ),
        methodology=[
            {
                "name": name,
                "weight": weights.get(name),
                "blurb": CATEGORY_BLURB.get(name, ""),
            }
            for name in sorted(weights)
        ],
        signal_classes=[
            {"name": "deterministic", "meaning": "A parsed fact about the page. Two runs over the same bytes agree."},
            {"name": "heuristic", "meaning": "Code with stated weights and thresholds. Arguable, but not arbitrary."},
            {"name": "live", "meaning": "Observed from a third-party service, carrying the time it was observed."},
            {"name": "advisory", "meaning": "Model judgement. Displayed separately and never summed into a score."},
        ],
        versions={
            "scoring": envelope.get("scoring_version"),
            "data": envelope.get("data_version"),
            "normalizer": envelope.get("normalizer_version"),
            "tool": envelope.get("cli_version"),
        },
    )

    operator = OperatorContext(
        run_id=envelope.get("run_id", ""),
        observed_at=envelope.get("observed_at", ""),
        evidence_hash=evidence.get("content_hash"),
        record_path=record_path,
        crawl_limits=crawl.get("limits") or {},
        pages_failed=evidence.get("pages_failed") or [],
        disallowed=crawl.get("disallowed_by_robots") or [],
        signals=envelope.get("signals") or [],
        brand_warnings=brand.warnings,
        contrast=brand.contrast_report(),
        completeness=completeness,
        assistants=_assistant_account(envelope),
    )
    return client, operator
