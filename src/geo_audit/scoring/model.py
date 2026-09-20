"""Signal and finding types, plus the composite arithmetic.

One rule shapes this module: the composite is a pure function of the signals,
and a signal that could not be computed leaves *both* sides of the fraction.
A page audited without the browser extra is scored out of the signals that
were computed, never scored zero for the ones that were not. "We could not
measure it" and "you failed it" are different sentences and must be different
numbers.
"""

from __future__ import annotations

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
    priority: int = 0

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "severity": self.severity,
            "effort": self.effort,
            "priority": self.priority,
            "points_lost": round(self.points_lost, 2),
            "pages": self.pages,
            "title": self.title,
            "remediation": self.remediation,
            "excerpt": self.excerpt,
        }


def demote(severity: str) -> str:
    index = _SEVERITY_ORDER.index(severity)
    return _SEVERITY_ORDER[min(index + 1, len(_SEVERITY_ORDER) - 1)]


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


def findings_for(signals: list[Signal], page: str) -> list[Finding]:
    rules = data.thresholds("findings")
    no_finding_above = rules["no_finding_above"]
    full_below = rules["full_severity_below"]
    out: list[Finding] = []
    for signal in signals:
        ratio = signal.ratio
        if ratio is None or ratio > no_finding_above:
            continue
        template = data.load("findings")["signals"].get(signal.id)
        if template is None:
            continue
        severity = template["severity"] if ratio < full_below else demote(template["severity"])
        out.append(
            Finding(
                id=signal.id,
                severity=severity,
                effort=template["effort"],
                title=template["title"],
                remediation=template["remediation"],
                pages=[page],
                excerpt=signal.detail.get("worst_example"),
                points_lost=signal.max - (signal.value or 0.0),
            )
        )
    return out


def prioritize(findings: list[Finding]) -> list[Finding]:
    """Deterministic order: severity, then effort, then points recovered, then id.

    Sorting by id last is what makes two runs over the same snapshot produce
    byte-identical output when everything else ties.
    """
    ordered = sorted(
        findings,
        key=lambda f: (
            _SEVERITY_ORDER.index(f.severity),
            _EFFORT_ORDER.index(f.effort),
            -f.points_lost,
            f.id,
        ),
    )
    for position, finding in enumerate(ordered, start=1):
        finding.priority = position
    return ordered
