"""Structured-data signals.

The check is presence and shape, not value validation: whether the page
declares an entity, whether the properties that make the entity usable are
there, and whether the JSON parses at all. Validating that a `datePublished`
is a real date is a different job from noticing there is no `datePublished`,
and only the second is worth fifteen points.

Requirements live in `data/schema_requirements.json` so correcting one is a
data change, not a code change.
"""

from __future__ import annotations

from geo_audit import data
from geo_audit.lib.extract import Document
from geo_audit.scoring.model import Signal


def _requirements() -> dict:
    return data.load("schema_requirements")


def types_in(doc: Document) -> set[str]:
    found: set[str] = set()

    def walk(node, depth: int = 0) -> None:
        if depth > 5:
            return
        if isinstance(node, list):
            for item in node:
                walk(item, depth + 1)
            return
        if not isinstance(node, dict):
            return
        value = node.get("@type")
        if isinstance(value, str):
            found.add(value)
        elif isinstance(value, list):
            found.update(str(v) for v in value)
        for key, child in node.items():
            if key != "@type":
                walk(child, depth + 1)

    for entry in doc.jsonld:
        walk(entry)
    return found


def _nodes_of(doc: Document, wanted: set[str]) -> list[dict]:
    matched: list[dict] = []

    def walk(node, depth: int = 0) -> None:
        if depth > 5:
            return
        if isinstance(node, list):
            for item in node:
                walk(item, depth + 1)
            return
        if not isinstance(node, dict):
            return
        declared = node.get("@type")
        names = (
            {declared}
            if isinstance(declared, str)
            else set(map(str, declared))
            if isinstance(declared, list)
            else set()
        )
        if names & wanted:
            matched.append(node)
        for key, child in node.items():
            if key != "@type":
                walk(child, depth + 1)

    for entry in doc.jsonld:
        walk(entry)
    return matched


def presence(doc: Document) -> tuple[float | None, dict]:
    """Did the page try to describe itself in JSON-LD?

    A block that fails to parse still counts as present. Scoring it as absent
    produced two contradictory findings on the same page - "carries no
    structured data" next to "structured data is malformed" - when only the
    second was true. Whether the attempt succeeded is `validity`'s question.
    """
    parsed = len(doc.jsonld)
    attempted = parsed + len(doc.jsonld_errors)
    points = 30.0 if attempted else 0.0
    return points, {
        "blocks": parsed,
        "blocks_attempted": attempted,
        "unparseable_blocks": len(doc.jsonld_errors),
        "types": sorted(types_in(doc)),
    }


def validity(doc: Document) -> tuple[float | None, dict]:
    """Parse errors first, then missing required properties on declared types."""
    requirements = _requirements()["types"]
    if doc.jsonld_errors and not doc.jsonld:
        return 0.0, {"parse_errors": doc.jsonld_errors, "checked": 0}
    if not doc.jsonld:
        # Nothing to validate is not a failed validation. `schema.presence`
        # already reports the absence; scoring this zero as well reported a
        # page with no structured data as having *malformed* structured data.
        return None, {"reason": "no structured data to validate", "checked": 0}

    checked = 0
    missing: list[str] = []
    for type_name, spec in requirements.items():
        for node in _nodes_of(doc, {type_name}):
            checked += 1
            for prop in spec["required"]:
                if prop not in node:
                    missing.append(f"{type_name}.{prop}")

    if not checked:
        # Types we have no requirements for still parse; give partial credit.
        points = 15.0 if not doc.jsonld_errors else 5.0
        return points, {
            "checked": 0,
            "reason": "no recognised types to validate",
            "parse_errors": doc.jsonld_errors,
        }

    ratio = 1 - min(len(missing) / checked, 1.0)
    points = 25 * ratio
    if doc.jsonld_errors:
        points = min(points, 10.0)
    return points, {
        "checked": checked,
        "missing_required": sorted(set(missing)),
        "parse_errors": doc.jsonld_errors,
    }


def organization(doc: Document) -> tuple[float | None, dict]:
    """Who publishes this, in machine-readable form.

    `sameAs` carries most of the weight: it is the property that lets an
    engine tie the site to the entity it already knows about.
    """
    requirements = _requirements()
    nodes = _nodes_of(doc, set(requirements["entity_types"]))
    if not nodes:
        return 0.0, {"reason": "no Organization, LocalBusiness or Person node", "found": []}

    node = nodes[0]
    has = {
        "name": bool(node.get("name")),
        "url": bool(node.get("url")),
        "logo": bool(node.get("logo") or node.get("image")),
        "sameAs": bool(node.get("sameAs")),
        "description": bool(node.get("description")),
    }
    weights = {"name": 5, "url": 4, "logo": 3, "sameAs": 5, "description": 3}
    points = float(sum(weights[key] for key, present in has.items() if present))
    return points, {
        "types": sorted(types_in(doc) & set(requirements["entity_types"])),
        "present": sorted(key for key, value in has.items() if value),
        "missing": sorted(key for key, value in has.items() if not value),
        "same_as_count": len(node.get("sameAs") or []) if isinstance(node.get("sameAs"), list) else (1 if node.get("sameAs") else 0),
    }


def article(doc: Document) -> tuple[float | None, dict]:
    requirements = _requirements()
    nodes = _nodes_of(doc, set(requirements["article_types"]))
    if not nodes:
        return 0.0, {"reason": "no Article-family node", "found": []}

    node = nodes[0]
    has = {
        "headline": bool(node.get("headline")),
        "author": bool(node.get("author")),
        "datePublished": bool(node.get("datePublished")),
        "dateModified": bool(node.get("dateModified")),
        "image": bool(node.get("image")),
    }
    weights = {"headline": 4, "author": 4, "datePublished": 3, "dateModified": 2, "image": 2}
    points = float(sum(weights[key] for key, present in has.items() if present))
    return points, {
        "types": sorted(types_in(doc) & set(requirements["article_types"])),
        "present": sorted(key for key, value in has.items() if value),
        "missing": sorted(key for key, value in has.items() if not value),
    }


def breadth(doc: Document) -> tuple[float | None, dict]:
    """Types that answer a question directly, rather than describing the page."""
    answer_types = set(_requirements()["answer_types"])
    found = types_in(doc) & answer_types
    points = 10 * min(len(found) / 2, 1.0)
    return points, {
        "answer_types_found": sorted(found),
        "answer_types_known": sorted(answer_types),
        "full_marks_at": 2,
    }


def score(page) -> list[Signal]:
    spec = data.weights()["schema"]["signals"]
    doc = page.doc
    url = page.result.final_url if page.result else page.url

    def build(signal_id: str, outcome: tuple[float | None, dict]) -> Signal:
        points, detail = outcome
        meta = spec[signal_id]
        return Signal(
            id=signal_id,
            cls=meta["class"],
            max=meta["max"],
            value=points,
            detail=detail,
            page=url,
            skipped_reason=detail.get("reason") if points is None else None,
        )

    if doc is None:
        # Same rule as technical: no markup means not measured, not zero.
        unmeasured = (None, {"reason": "the page returned no markup to inspect"})
        return [build(signal_id, unmeasured) for signal_id in spec]

    return [
        build("schema.presence", presence(doc)),
        build("schema.validity", validity(doc)),
        build("schema.organization", organization(doc)),
        build("schema.article", article(doc)),
        build("schema.breadth", breadth(doc)),
    ]
