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

from dataclasses import dataclass, field, fields

from geo_audit import data
from geo_audit._version import PRODUCT_NAME
from geo_audit.report.advisory import merge as advisory_merge
from geo_audit.report.brand import Brand
from geo_audit.scoring.model import Finding, for_site_kind, site_kinds

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
    # Set when the findings were ordered for a kind of site. The scores never are.
    ordered_for: str | None = None
    strengths: list[dict] = field(default_factory=list)
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


def _fixes_from(findings: list[dict]) -> list[Fix]:
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
            )
        )
    return out


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

    fixes = _fixes_from(ordered_findings(envelope.get("findings") or [], site_kind))
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
    )
    return client, operator
