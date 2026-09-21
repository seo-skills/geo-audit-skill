"""Citability signals: can an engine quote one passage of this page as-is?

Every function here returns `(points, detail)`. `detail` is the explainability
payload — the counts and the worst example behind the number — because a score
nobody can talk through is a score nobody should send to a client.

Returning `None` for points means the signal could not be computed on this
page. It is never a way to say zero.
"""

from __future__ import annotations

import re
from urllib.parse import urlsplit

from geo_audit import data
from geo_audit.lib.extract import Block, Document, excerpt
from geo_audit.scoring import articles
from geo_audit.scoring.model import DETERMINISTIC, HEURISTIC, Signal, ramp

_MONTHS = (
    "january|february|march|april|may|june|july|august|september|october|"
    "november|december|jan|feb|mar|apr|jun|jul|aug|sep|oct|nov|dec"
)

FACT_MARKER = re.compile(
    r"\b\d{2,}\b"
    r"|\b\d+(?:\.\d+)?\s?(?:%|percent|ms|s|kb|mb|gb|tb|km|kg|lb|hours?|minutes?|days?|weeks?|months?|years?|x)\b"
    r"|[$€£]\s?\d"
    r"|\b(?:19|20)\d{2}\b"
    rf"|\b(?:{_MONTHS})\b",
    re.IGNORECASE,
)

_SENTENCE_END = re.compile(r"(?<=[.!?])\s+")


def first_sentence(text: str) -> str:
    parts = _SENTENCE_END.split(text.strip(), maxsplit=1)
    return parts[0] if parts else text


def _opener_patterns(openers: list[str]) -> re.Pattern:
    alternatives = "|".join(re.escape(o) for o in sorted(openers, key=len, reverse=True))
    return re.compile(rf"^(?:{alternatives})\b", re.IGNORECASE)


def _starts_with(pattern: re.Pattern, text: str) -> bool:
    return bool(pattern.match(text.lstrip("\"'“‘ ")))


# --------------------------------------------------------------------------
# 1. self containment
# --------------------------------------------------------------------------
def self_containment(doc: Document) -> tuple[float | None, dict]:
    config = data.thresholds("self_containment")
    pattern = _opener_patterns(config["dangling_openers"])
    candidates = [b for b in doc.prose_blocks if b.words >= config["min_block_words"]]

    if not candidates:
        return 0.0, {
            "reason": "no extractable blocks",
            "candidate_blocks": 0,
            "self_contained": 0,
            "ratio": 0.0,
        }

    dangling = [b for b in candidates if _starts_with(pattern, b.text)]
    contained = len(candidates) - len(dangling)
    ratio = contained / len(candidates)
    points = 25 * ramp(ratio, config["floor_ratio"], config["good_ratio"])
    detail = {
        "candidate_blocks": len(candidates),
        "self_contained": contained,
        "ratio": round(ratio, 3),
        "floor_ratio": config["floor_ratio"],
        "good_ratio": config["good_ratio"],
    }
    if dangling:
        detail["worst_example"] = excerpt(dangling[0].text)
        detail["dangling_blocks"] = len(dangling)
    return points, detail


# --------------------------------------------------------------------------
# 2. answer first
# --------------------------------------------------------------------------
def _sections(doc: Document) -> list[tuple[str, Block | None]]:
    out: list[tuple[str, Block | None]] = []
    heading: str | None = None
    lead: Block | None = None
    for block in doc.blocks:
        if block.kind in ("h2", "h3"):
            if heading is not None:
                out.append((heading, lead))
            heading, lead = block.text, None
        elif heading is not None and lead is None and block.kind in ("p", "li", "blockquote"):
            lead = block
    if heading is not None:
        out.append((heading, lead))
    return out


def answer_first(doc: Document) -> tuple[float | None, dict]:
    config = data.thresholds("answer_first")
    pattern = _opener_patterns(config["filler_openers"])
    sections = [(h, lead) for h, lead in _sections(doc) if lead is not None]

    if not sections:
        return 0.0, {
            "reason": "no headed sections with body text",
            "sections": 0,
            "answer_first": 0,
            "ratio": 0.0,
        }

    passing = []
    failing = []
    for heading, lead in sections:
        lead_sentence = first_sentence(lead.text)
        ok = (
            not _starts_with(pattern, lead.text)
            and len(lead_sentence.split()) <= config["max_lead_words"]
        )
        (passing if ok else failing).append((heading, lead))

    ratio = len(passing) / len(sections)
    points = 20 * ramp(ratio, config["floor_ratio"], config["good_ratio"])
    detail = {
        "sections": len(sections),
        "answer_first": len(passing),
        "ratio": round(ratio, 3),
        "max_lead_words": config["max_lead_words"],
    }
    if failing:
        detail["worst_example"] = excerpt(failing[0][1].text)
        detail["worst_section"] = excerpt(failing[0][0], 80)
    return points, detail


# --------------------------------------------------------------------------
# 3. structure
# --------------------------------------------------------------------------
def structure(doc: Document) -> tuple[float | None, dict]:
    config = data.thresholds("structure")
    levels = [level for level, _ in doc.headings]
    h1 = levels.count(1)
    h2 = levels.count(2)

    h1_points = 4.0 if h1 == 1 else 0.0
    h2_points = 4.0 * min(h2 / config["min_h2"], 1.0) if config["min_h2"] else 4.0

    skipped = 0
    previous = 0
    for level in levels:
        if previous and level > previous + 1:
            skipped += 1
        previous = level
    # A page with no headings has not "avoided skipping levels"; it has no
    # outline at all. Awarding the points for an absent structure was the bug
    # that made an empty client-rendered shell score above zero here.
    if not levels:
        skip_points = 0.0
    else:
        skip_points = 3.0 if skipped == 0 else max(0.0, 3.0 - skipped)

    section_words: dict[int, int] = {}
    for block in doc.blocks:
        if block.section >= 0 and block.kind in ("p", "li", "blockquote", "dd"):
            section_words[block.section] = section_words.get(block.section, 0) + block.words
    oversized = [s for s, words in section_words.items() if words > config["max_section_words"]]
    if section_words:
        length_points = 4.0 * (1 - len(oversized) / len(section_words))
    else:
        length_points = 0.0

    points = h1_points + h2_points + skip_points + length_points
    return points, {
        "h1": h1,
        "h2": h2,
        "headings": len(levels),
        "skipped_levels": skipped,
        "sections": len(section_words),
        "oversized_sections": len(oversized),
        "max_section_words": config["max_section_words"],
        "breakdown": {
            "single_h1": round(h1_points, 2),
            "enough_h2": round(h2_points, 2),
            "no_skipped_levels": round(skip_points, 2),
            "section_length": round(length_points, 2),
        },
    }


# --------------------------------------------------------------------------
# 4. evidence density
# --------------------------------------------------------------------------
def evidence_density(doc: Document) -> tuple[float | None, dict]:
    config = data.thresholds("evidence_density")
    blocks = doc.prose_blocks
    if not blocks:
        return 0.0, {"reason": "no extractable blocks", "ratio": 0.0, "external_domains": 0}

    with_facts = [b for b in blocks if FACT_MARKER.search(b.text)]
    ratio = len(with_facts) / len(blocks)
    domains = sorted({(urlsplit(u).hostname or "").lower().removeprefix("www.") for u in doc.external_links})
    domains = [d for d in domains if d]

    fact_points = 10 * ramp(ratio, config["floor_ratio"], config["good_ratio"])
    link_points = 5 * min(len(domains) / config["good_external_domains"], 1.0)

    detail = {
        "prose_blocks": len(blocks),
        "blocks_with_facts": len(with_facts),
        "ratio": round(ratio, 3),
        "external_domains": len(domains),
        "breakdown": {
            "facts": round(fact_points, 2),
            "outbound_citations": round(link_points, 2),
        },
    }
    barren = [b for b in blocks if not FACT_MARKER.search(b.text) and b.words >= 25]
    if barren:
        detail["worst_example"] = excerpt(barren[0].text)
    return fact_points + link_points, detail


# --------------------------------------------------------------------------
# 5. extractability
# --------------------------------------------------------------------------
def extractability(doc: Document) -> tuple[float | None, dict]:
    config = data.thresholds("extractability")
    chars = doc.content_chars
    volume_points = 8 * min(chars / config["good_content_chars"], 1.0)

    ratio = chars / doc.body_chars if doc.body_chars else 0.0
    ratio_points = 4 * min(ratio / config["good_content_ratio"], 1.0)

    structured = 0.0
    if doc.lists >= config["structured_bonus_lists"]:
        structured += 2
    if doc.tables >= config["structured_bonus_tables"]:
        structured += 1

    empty_mount = (
        doc.framework_root_chars is not None
        and doc.framework_root_chars < config["empty_framework_root_chars"]
    )

    points = volume_points + ratio_points + structured
    capped = False
    if doc.js_required_notice or empty_mount or chars < config["min_content_chars"]:
        points = min(points, 3.0)
        capped = True

    return points, {
        "content_chars": chars,
        "body_chars": doc.body_chars,
        "content_ratio": round(ratio, 3),
        "content_root": doc.content_root,
        "lists": doc.lists,
        "tables": doc.tables,
        "js_required_notice": doc.js_required_notice,
        "framework_root_chars": doc.framework_root_chars,
        "empty_framework_root": empty_mount,
        "capped_thin_or_js_gated": capped,
        "min_content_chars": config["min_content_chars"],
    }


# --------------------------------------------------------------------------
# 6. attribution
# --------------------------------------------------------------------------
def _jsonld_types(doc: Document) -> set[str]:
    """Every @type in the graph, including nested author and publisher nodes.

    A page that declares `Article { publisher: Organization }` has said who
    published it just as clearly as one with a top-level Organization node.
    Only reading the outermost @type marked the common case as missing.
    """
    types: set[str] = set()

    def walk(node, depth: int = 0) -> None:
        if depth > 4:
            return
        if isinstance(node, list):
            for item in node:
                walk(item, depth + 1)
            return
        if not isinstance(node, dict):
            return
        value = node.get("@type")
        if isinstance(value, str):
            types.add(value)
        elif isinstance(value, list):
            types.update(str(v) for v in value)
        for key, child in node.items():
            if key != "@type":
                walk(child, depth + 1)

    for entry in doc.jsonld:
        walk(entry)
    return types


def _jsonld_has(doc: Document, key: str) -> bool:
    return any(key in node for node in doc.jsonld)


def attribution(doc: Document) -> tuple[float | None, dict]:
    exempt = articles.exempt(doc)
    if exempt:
        return exempt
    points_table = data.thresholds("attribution")["points"]
    types = _jsonld_types(doc)

    found = {
        "byline": bool(doc.meta.get("author")) or _jsonld_has(doc, "author"),
        "published_date": bool(
            doc.meta.get("article:published_time") or doc.meta.get("datepublished")
        )
        or _jsonld_has(doc, "datePublished"),
        "modified_date": bool(
            doc.meta.get("article:modified_time") or doc.meta.get("datemodified")
        )
        or _jsonld_has(doc, "dateModified"),
        "organization_schema": bool(types & {"Organization", "Person", "NewsMediaOrganization"}),
        "canonical": bool(doc.meta.get("canonical")),
    }
    points = sum(points_table[key] for key, present in found.items() if present)
    return float(points), {
        "present": sorted(k for k, v in found.items() if v),
        "missing": sorted(k for k, v in found.items() if not v),
        "jsonld_types": sorted(types),
        "points_table": points_table,
    }


# --------------------------------------------------------------------------
# 7. render parity (nullable: needs the browser extra)
# --------------------------------------------------------------------------
def render_parity(doc: Document, rendered_chars: int | None) -> tuple[float | None, dict]:
    if rendered_chars is None:
        return None, {"reason": "browser extra not installed"}
    if rendered_chars <= 0:
        return 0.0, {"rendered_chars": 0, "static_chars": doc.content_chars, "ratio": 0.0}
    config = data.thresholds("render_parity")
    ratio = min(doc.content_chars / rendered_chars, 1.0)
    points = 10 * ramp(ratio, config["floor_ratio"], config["good_ratio"])
    return points, {
        "static_chars": doc.content_chars,
        "rendered_chars": rendered_chars,
        "ratio": round(ratio, 3),
        "floor_ratio": config["floor_ratio"],
        "good_ratio": config["good_ratio"],
    }


# --------------------------------------------------------------------------
def score(doc: Document, *, rendered_chars: int | None = None) -> list[Signal]:
    spec = data.weights()["citability"]["signals"]
    page = doc.url

    def build(signal_id: str, result: tuple[float | None, dict]) -> Signal:
        points, detail = result
        meta = spec[signal_id]
        return Signal(
            id=signal_id,
            cls=meta["class"],
            max=meta["max"],
            value=points,
            detail=detail,
            page=page,
            skipped_reason=detail.get("reason") if points is None else None,
        )

    return [
        build("citability.self_containment", self_containment(doc)),
        build("citability.answer_first", answer_first(doc)),
        build("citability.structure", structure(doc)),
        build("citability.evidence_density", evidence_density(doc)),
        build("citability.extractability", extractability(doc)),
        build("citability.attribution", attribution(doc)),
        build("citability.render_parity", render_parity(doc, rendered_chars)),
    ]


__all__ = [
    "DETERMINISTIC",
    "HEURISTIC",
    "score",
    "self_containment",
    "answer_first",
    "structure",
    "evidence_density",
    "extractability",
    "attribution",
    "render_parity",
]
