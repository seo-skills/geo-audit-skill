"""Signal and finding types, plus the composite arithmetic.

One rule shapes this module: the composite is a pure function of the signals,
and a signal that could not be computed leaves *both* sides of the fraction.
A page audited without the browser extra is scored out of the signals that
were computed, never scored zero for the ones that were not. "We could not
measure it" and "you failed it" are different sentences and must be different
numbers.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field

from geo_audit import data

DETERMINISTIC = "deterministic"
HEURISTIC = "heuristic"
LIVE = "live"
ADVISORY = "advisory"

SCORED_CLASSES = frozenset({DETERMINISTIC, HEURISTIC, LIVE})

_SEVERITY_ORDER = ("critical", "high", "medium", "low")
_EFFORT_ORDER = ("low", "medium", "high")


@dataclass
class Signal:
    id: str
    cls: str
    max: float
    value: float | None
    detail: dict = field(default_factory=dict)
    page: str | None = None
    skipped_reason: str | None = None

    @property
    def computed(self) -> bool:
        return self.value is not None

    @property
    def ratio(self) -> float | None:
        if self.value is None or self.max == 0:
            return None
        return self.value / self.max

    def to_dict(self) -> dict:
        out = {
            "id": self.id,
            "class": self.cls,
            "value": None if self.value is None else round(self.value, 2),
            "max": self.max,
            "page": self.page,
            "detail": self.detail,
        }
        if self.skipped_reason:
            out["skipped_reason"] = self.skipped_reason
        return out


@dataclass
class Finding:
    id: str
    severity: str
    effort: str
    title: str
    remediation: str
    pages: list[str] = field(default_factory=list)
    excerpt: str | None = None
    points_lost: float = 0.0
    # What fixing this is worth on the 0-100 composite. `points_lost` is on the
    # category's own scale, so 30 points of schema (weight 10) and 30 points of
    # citability (weight 25) are not the same size of win - and ranking by the
    # raw number puts them in the wrong order.
    impact: float | None = None
    # True when the finding describes a minority of pages rather than the site.
    # Those never lead the report, however severe they are on the page itself.
    page_level: bool = False
    priority: int = 0

    def mark_page_level(self) -> "Finding":
        """Say this describes a minority of pages, and cap it accordingly.

        Severity and ordering follow from the same fact, so they are set in
        the same place. A page-level finding never leads the report and never
        reads as critical: MDN had one page of eight with a noindex, worth
        0.38 composite points, heading a whole site audit.
        """
        self.page_level = True
        self.severity = demote(self.severity)
        if _SEVERITY_ORDER.index(self.severity) < _SEVERITY_ORDER.index(PAGE_LEVEL_CEILING):
            self.severity = PAGE_LEVEL_CEILING
        return self

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "severity": self.severity,
            "effort": self.effort,
            "priority": self.priority,
            "points_lost": round(self.points_lost, 2),
            "impact": None if self.impact is None else round(self.impact, 2),
            "page_level": self.page_level,
            "pages": self.pages,
            "title": self.title,
            "remediation": self.remediation,
            "excerpt": self.excerpt,
        }


PAGE_LEVEL_CEILING = "medium"


def demote(severity: str) -> str:
    index = _SEVERITY_ORDER.index(severity)
    return _SEVERITY_ORDER[min(index + 1, len(_SEVERITY_ORDER) - 1)]


# Mattering more for one kind of site is not an emergency, so a promotion stops
# here. Critical stays what the blocking findings and the scorer make critical.
PROMOTION_CEILING = "high"


def promote(severity: str) -> str:
    """One level more severe, never past the ceiling, never less severe than before."""
    index = _SEVERITY_ORDER.index(severity)
    ceiling = _SEVERITY_ORDER.index(PROMOTION_CEILING)
    return _SEVERITY_ORDER[min(index, max(index - 1, ceiling))]


def clamp01(value: float) -> float:
    return 0.0 if value < 0 else 1.0 if value > 1 else value


def ramp(value: float, floor: float, good: float) -> float:
    """0 at or below `floor`, 1 at or above `good`, linear between."""
    if good <= floor:
        return 1.0 if value >= good else 0.0
    return clamp01((value - floor) / (good - floor))


def composite(signals: list[Signal]) -> tuple[int, dict]:
    scored = [s for s in signals if s.cls in SCORED_CLASSES]
    computed = [s for s in scored if s.computed]
    available = sum(s.max for s in computed)
    earned = sum(s.value or 0.0 for s in computed)
    score = int(round(earned / available * 100)) if available else 0
    completeness = {
        "computed": len(computed),
        "total": len(scored),
        "missing": sorted(s.id for s in scored if not s.computed),
    }
    return score, completeness


def _suppressed_by_cause(signals: list[Signal]) -> set[str]:
    """Findings that would only restate a cause already being reported.

    A page with no structured data does not also need to be told its
    structured data is incomplete: that is the same fact four more times,
    and it pushes the finding that matters down the list.
    """
    declared = data.load("findings").get("consequences") or {}
    values = {signal.id: signal.value for signal in signals}
    suppressed: set[str] = set()
    for cause, rule in declared.items():
        if not isinstance(rule, dict):
            continue
        value = values.get(cause)
        if value is not None and value <= rule.get("floor", 0):
            suppressed.update(rule.get("suppresses", []))
    return suppressed


def findings_for(signals: list[Signal], page: str) -> list[Finding]:
    rules = data.thresholds("findings")
    no_finding_above = rules["no_finding_above"]
    full_below = rules["full_severity_below"]
    suppressed = _suppressed_by_cause(signals)
    out: list[Finding] = []
    for signal in signals:
        if signal.id in suppressed:
            continue
        ratio = signal.ratio
        if ratio is None or ratio > no_finding_above:
            continue
        template = data.load("findings")["signals"].get(signal.id)
        if template is None:
            continue
        severity = template["severity"] if ratio < full_below else demote(template["severity"])
        # A title written for the zero case, on a finding that fires at up to 70%,
        # claims total absence. seomator.com had Person markup on every page and
        # was told "Authorship is not machine-readable". Where the scorer reports
        # which parts are there, a variant says what is missing instead.
        wording = template
        partial, present = template.get("partial"), signal.detail.get("present")
        if partial and isinstance(present, list) and set(partial["when_present"]) & set(present):
            wording = partial
        out.append(
            Finding(
                id=signal.id,
                severity=severity,
                effort=template["effort"],
                title=wording["title"],
                remediation=wording["remediation"],
                pages=[page],
                excerpt=signal.detail.get("worst_example"),
                points_lost=signal.max - (signal.value or 0.0),
            )
        )
    return out


def aggregate(per_page: list[list[Signal]]) -> list[Signal]:
    """Roll per-page signals up to one site-level signal each.

    The site value is the mean over the pages where the signal was computed.
    A signal computed on no page stays `None` rather than becoming zero, and
    the detail carries the spread and the worst page, because "62 on average"
    and "62 everywhere" call for different work.
    """
    order: list[str] = []
    grouped: dict[str, list[Signal]] = {}
    for signals in per_page:
        for signal in signals:
            if signal.id not in grouped:
                grouped[signal.id] = []
                order.append(signal.id)
            grouped[signal.id].append(signal)

    out: list[Signal] = []
    for signal_id in order:
        group = grouped[signal_id]
        first = group[0]
        computed = [s for s in group if s.computed]
        if not computed:
            out.append(
                Signal(
                    id=signal_id,
                    cls=first.cls,
                    max=first.max,
                    value=None,
                    detail={"reason": first.skipped_reason or "not measured on any page"},
                    skipped_reason=first.skipped_reason or "not measured on any page",
                )
            )
            continue

        values = [s.value or 0.0 for s in computed]
        worst = min(computed, key=lambda s: s.value if s.value is not None else 0.0)
        detail = {
            "pages_measured": len(computed),
            "pages_total": len(group),
            "mean": round(sum(values) / len(values), 2),
            "min": round(min(values), 2),
            "max": round(max(values), 2),
            "worst_page": worst.page,
        }
        # A detail that is identical on every page is a fact about the site,
        # not about a page, and it survives aggregation. Without this, the
        # actionable part of a site-level signal - which crawler tokens are
        # blocked, say - is replaced by a mean and disappears.
        detail.update(_shared_detail(computed))
        if worst.detail.get("worst_example"):
            detail["worst_example"] = worst.detail["worst_example"]
        out.append(
            Signal(
                id=signal_id,
                cls=first.cls,
                max=first.max,
                value=sum(values) / len(values),
                detail=detail,
            )
        )
    return out


def _shared_detail(signals: list[Signal]) -> dict:
    """Detail entries that every page agreed on, verbatim."""
    if not signals:
        return {}
    reserved = {"pages_measured", "pages_total", "mean", "min", "max", "worst_page"}
    first = signals[0].detail
    shared: dict = {}
    for key, value in first.items():
        if key in reserved:
            continue
        try:
            encoded = json.dumps(value, sort_keys=True)
        except TypeError:
            continue
        if all(
            key in signal.detail
            and _encodes_to(signal.detail[key], encoded)
            for signal in signals[1:]
        ):
            shared[key] = value
    return shared


def _encodes_to(value, encoded: str) -> bool:
    try:
        return json.dumps(value, sort_keys=True) == encoded
    except TypeError:
        return False


def weighted_composite(categories: dict[str, int], scores: dict[str, int]) -> tuple[int, dict]:
    """Combine category scores by weight, over the categories actually computed.

    Same rule as a null signal: a category that was not computed leaves both
    sides of the fraction rather than scoring zero.
    """
    computed = {name: value for name, value in scores.items() if value is not None}
    total_weight = sum(categories[name] for name in computed if name in categories)
    if not total_weight:
        return 0, {"computed": [], "declared": sorted(categories), "missing": sorted(categories)}
    earned = sum(categories[name] * computed[name] for name in computed if name in categories)
    return int(round(earned / total_weight)), {
        "computed": sorted(computed),
        "declared": sorted(categories),
        "missing": sorted(set(categories) - set(computed)),
        "weights_used": {name: categories[name] for name in sorted(computed) if name in categories},
    }


def merge(findings: list[Finding]) -> list[Finding]:
    """Collapse the same finding seen on several pages into one.

    Twelve copies of "no byline" is not twelve findings; it is one finding
    affecting twelve pages, and the page list is what tells the reader whether
    it is a template problem or a one-off.
    """
    merged: dict[str, Finding] = {}
    for finding in findings:
        existing = merged.get(finding.id)
        if existing is None:
            merged[finding.id] = Finding(
                id=finding.id,
                severity=finding.severity,
                effort=finding.effort,
                title=finding.title,
                remediation=finding.remediation,
                pages=list(finding.pages),
                excerpt=finding.excerpt,
                points_lost=finding.points_lost,
                page_level=finding.page_level,
            )
            continue
        for page in finding.pages:
            if page not in existing.pages:
                existing.pages.append(page)
        existing.points_lost = max(existing.points_lost, finding.points_lost)
        if finding.impact is not None:
            existing.impact = max(existing.impact or 0.0, finding.impact)
        if _SEVERITY_ORDER.index(finding.severity) < _SEVERITY_ORDER.index(existing.severity):
            existing.severity = finding.severity
        existing.excerpt = existing.excerpt or finding.excerpt
    for finding in merged.values():
        finding.pages.sort()
    return list(merged.values())


def apply_impact(
    findings: list[Finding], signals: list[Signal], category_weights: dict[str, int]
) -> list[Finding]:
    """Express each finding's value on the composite scale.

    A category is scored out of the signals that were computed in it, and then
    weighted. So the composite points a fix recovers are
    `points_lost / available_in_category * category_weight`.
    """
    available: dict[str, float] = {}
    for signal in signals:
        if not signal.computed or signal.cls not in SCORED_CLASSES:
            continue
        category = signal.id.split(".", 1)[0]
        available[category] = available.get(category, 0.0) + signal.max

    for finding in findings:
        category = finding.id.split(".", 1)[0]
        weight = category_weights.get(category)
        total = available.get(category)
        if weight and total:
            finding.impact = finding.points_lost / total * weight
    return findings


# How far a deferred finding falls. Further than a led one rises, on purpose: a
# deferred signal is exactly one whose points lost are inflated by the kind not
# fitting - a reference site scores near zero on bylines it was never going to
# carry - so one level left it winning its new band on that inflated number.
# Nothing is hidden by it; the finding is still in the report, lower down.
DEFER_LEVELS = 2


def site_kinds() -> dict[str, dict]:
    return data.load("site_kinds")["kinds"]


def for_site_kind(findings: list[Finding], kind: str | None) -> list[Finding]:
    """Order findings for what the site is for, without changing a number.

    Both practitioner evals said it: a publisher's checklist led a reference
    site's report. A kind names what matters more for it and what matters less
    (`data/site_kinds.json`). What it leads with rises one severity level, what
    it defers falls `DEFER_LEVELS`, and the usual order applies to the result.
    Points lost and impact are untouched, so every kind of site shares one set
    of scores.

    Two things never move. A blocker, because nothing matters more than being
    fetchable, whatever the site is for. And a page-level finding keeps its
    ceiling, because one page of forty is still one page.
    """
    if kind is None:
        return prioritize(findings)
    spec = site_kinds()[kind]
    lead, defer = set(spec["lead"]), set(spec["defer"])
    blocking = set((data.load("findings").get("blocking") or {}).get("ids") or [])
    ceiling = _SEVERITY_ORDER.index(PAGE_LEVEL_CEILING)
    for finding in findings:
        if finding.id in blocking:
            continue
        if finding.id in lead:
            finding.severity = promote(finding.severity)
        elif finding.id in defer:
            for _ in range(DEFER_LEVELS):
                finding.severity = demote(finding.severity)
        if finding.page_level and _SEVERITY_ORDER.index(finding.severity) < ceiling:
            finding.severity = PAGE_LEVEL_CEILING
    return prioritize(findings)


def prioritize(findings: list[Finding]) -> list[Finding]:
    """Blockers, then severity, then what the fix is worth on the composite.

    Two things here were provably wrong before and are fixed; a third is a
    judgement call and is deliberately left alone.

    Fixed: ranking used `points_lost`, which is on the category's own scale.
    Thirty points of schema (weight 10) outranked twenty-five of citability
    (weight 25) while being worth less - 3.0 composite against 6.25. Ranking
    now uses `impact`, which is the same number expressed on the 0-100 scale
    the reader actually sees.

    Fixed: blocking findings come first whatever the arithmetic says, because
    prose on a page no crawler can fetch recovers nothing. Which findings block
    is declared in `data/findings.json` rather than inferred from severity.

    Fixed: arithmetic still decided the order *inside* that tier, which was the
    one place it was supposed not to. A page the server refused is never
    scored, so its finding carries no impact and no points_lost, and it lost
    every tiebreak to a blocker that had been measured - a 403 on the start URL
    ranked below "your content needs JavaScript". Blockers now sort by their
    declared position, which follows the chain: respond, allow, index, parse.

    Left alone: whether a cheap medium-severity win should outrank an expensive
    high-severity one. Ordering by value-per-effort was tried and put "add a
    modified date" first on five sites out of five - defensible arithmetic,
    and a report that reads like a checklist. That is a taste call about
    audits, not a bug, so it belongs to the practitioner eval rather than to
    whoever last edited this function.

    Sorting by id last keeps two runs over one snapshot byte-identical.
    """
    declared = (data.load("findings").get("blocking") or {}).get("ids") or []
    blocking = {finding_id: rank for rank, finding_id in enumerate(declared)}

    def value(finding: Finding) -> float:
        return finding.impact if finding.impact is not None else finding.points_lost

    def rank(finding: Finding) -> tuple:
        """Blockers sort by the gate they close; everything else by what it recovers."""
        if finding.id in blocking and not finding.page_level:
            return (0, blocking[finding.id], 0.0, finding.id)
        return (1, _SEVERITY_ORDER.index(finding.severity), -value(finding), finding.id)

    ordered = sorted(findings, key=rank)
    for position, finding in enumerate(ordered, start=1):
        finding.priority = position
    return ordered
