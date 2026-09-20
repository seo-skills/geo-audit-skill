"""Content signals, and the first advisory ones.

The split matters more here than anywhere else. Depth, expertise, freshness
and readability are measurable: you can count characters, look for a Person
node, read a date, measure sentence length. Whether a page shows genuine
first-hand experience is not measurable, and pretending otherwise is how an
audit tool ends up asserting a number it cannot defend.

So the advisory signals in this module carry a question and a rubric and no
value. The model answers them; the composite never sees them, because
`composite()` filters on signal class. That exclusion is structural, not a
policy someone has to remember.
"""

from __future__ import annotations

import re
from datetime import datetime, timezone

from geo_audit import data
from geo_audit.lib.extract import Document
from geo_audit.scoring.model import ADVISORY, Signal, ramp
from geo_audit.scoring.schema_org import _nodes_of, types_in

SENTENCE_END = re.compile(r"(?<=[.!?])\s+")
DATE_META = ("article:modified_time", "datemodified", "article:published_time", "datepublished")


def _config(section: str) -> dict:
    return data.thresholds("content")[section]


def depth(doc: Document) -> tuple[float | None, dict]:
    """Enough on the page to answer the question without leaving it."""
    config = _config("depth")
    chars = doc.content_chars
    sections = len({block.section for block in doc.blocks if block.section >= 0})

    volume = 15 * min(chars / config["good_chars"], 1.0)
    structure = 6 * min(sections / config["good_sections"], 1.0)
    media = 4.0 if (doc.lists or doc.tables) else 0.0

    points = volume + structure + media
    thin = chars < config["min_chars"]
    if thin:
        points = min(points, 6.0)

    return points, {
        "content_chars": chars,
        "sections": sections,
        "lists": doc.lists,
        "tables": doc.tables,
        "thin": thin,
        "min_chars": config["min_chars"],
        "breakdown": {"volume": round(volume, 2), "structure": round(structure, 2), "media": media},
    }


def expertise(doc: Document) -> tuple[float | None, dict]:
    """Who is qualified to have written this, in a form a machine can read."""
    people = _nodes_of(doc, {"Person"})
    byline = doc.meta.get("author")
    person = people[0] if people else {}

    has = {
        "byline": bool(byline) or bool(person.get("name")),
        "person_schema": bool(people),
        "credentials": bool(person.get("jobTitle") or person.get("description")),
        "author_profile": bool(person.get("url") or person.get("sameAs")),
        "organization": bool(types_in(doc) & {"Organization", "NewsMediaOrganization"}),
    }
    weights = {"byline": 7, "person_schema": 6, "credentials": 5, "author_profile": 4, "organization": 3}
    points = float(sum(weights[key] for key, present in has.items() if present))
    return points, {
        "present": sorted(key for key, value in has.items() if value),
        "missing": sorted(key for key, value in has.items() if not value),
        "byline": byline,
        "points_table": weights,
    }


def _parse_date(value: str) -> datetime | None:
    text = (value or "").strip()
    for candidate in (text, text.replace("Z", "+00:00")):
        try:
            parsed = datetime.fromisoformat(candidate)
            return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)
        except ValueError:
            continue
    match = re.match(r"(\d{4})-(\d{2})-(\d{2})", text)
    if match:
        return datetime(*(int(part) for part in match.groups()), tzinfo=timezone.utc)
    return None


def freshness(doc: Document, now: datetime | None = None) -> tuple[float | None, dict]:
    """Datable, and dated recently enough to be chosen over an alternative."""
    config = _config("freshness")
    now = now or datetime.now(timezone.utc)

    found: dict[str, str] = {}
    for key in DATE_META:
        value = doc.meta.get(key)
        if value:
            found[key] = value
    for node in _nodes_of(doc, {"Article", "BlogPosting", "NewsArticle", "WebPage"}):
        for key in ("dateModified", "datePublished"):
            if node.get(key):
                found.setdefault(key, str(node[key]))

    modified = next(
        (found[key] for key in ("article:modified_time", "dateModified", "datemodified") if key in found),
        None,
    )
    published = next(
        (found[key] for key in ("article:published_time", "datePublished", "datepublished") if key in found),
        None,
    )

    if not modified and not published:
        return 0.0, {"reason": "no date on the page", "dates_found": []}

    best = _parse_date(modified or published or "")
    if best is None:
        return 8.0, {
            "reason": "a date is present but could not be parsed",
            "dates_found": sorted(found),
        }

    age_days = max((now - best).days, 0)
    recency = 17 * (1 - ramp(age_days, config["fresh_days"], config["stale_days"]))
    has_modified = 8.0 if modified else 0.0
    return recency + has_modified, {
        "age_days": age_days,
        "modified": modified,
        "published": published,
        "dates_found": sorted(found),
        "fresh_days": config["fresh_days"],
        "stale_days": config["stale_days"],
        "breakdown": {"recency": round(recency, 2), "has_modified_date": has_modified},
    }


def readability(doc: Document) -> tuple[float | None, dict]:
    """Sentence length, because a long sentence is hard to quote cleanly."""
    config = _config("readability")
    sentences: list[int] = []
    for block in doc.prose_blocks:
        for sentence in SENTENCE_END.split(block.text):
            words = len(sentence.split())
            if words >= 3:
                sentences.append(words)

    if not sentences:
        return 0.0, {"reason": "no prose to measure", "sentences": 0}

    mean = sum(sentences) / len(sentences)
    long_sentences = [count for count in sentences if count > config["long_sentence_words"]]
    long_share = len(long_sentences) / len(sentences)

    mean_points = 15 * (1 - ramp(mean, config["good_mean_words"], config["poor_mean_words"]))
    share_points = 10 * (1 - ramp(long_share, config["good_long_share"], 0.35))
    return mean_points + share_points, {
        "sentences": len(sentences),
        "mean_words": round(mean, 1),
        "longest": max(sentences),
        "long_sentences": len(long_sentences),
        "long_share": round(long_share, 3),
        "thresholds": {
            "good_mean_words": config["good_mean_words"],
            "long_sentence_words": config["long_sentence_words"],
        },
    }


def advisory_signals() -> list[Signal]:
    """Questions for the model, carrying no value and entering no score.

    These are emitted by every audit so the rubric travels with the data.
    `composite()` filters on class, so there is no code path in which an
    answer to one of these becomes a number.
    """
    declared = data.weights()["content"].get("advisory") or {}
    return [
        Signal(
            id=signal_id,
            cls=ADVISORY,
            max=0,
            value=None,
            detail={
                "question": spec["question"],
                "rubric": spec["rubric"],
                "answered_by": "model",
                "enters_score": False,
            },
            skipped_reason="advisory: answered by the model, never scored",
        )
        for signal_id, spec in declared.items()
    ]


def score(page, now: datetime | None = None) -> list[Signal]:
    spec = data.weights()["content"]["signals"]
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
        unmeasured = (None, {"reason": "the page returned no markup to inspect"})
        return [build(signal_id, unmeasured) for signal_id in spec]

    return [
        build("content.depth", depth(doc)),
        build("content.expertise", expertise(doc)),
        build("content.freshness", freshness(doc, now)),
        build("content.readability", readability(doc)),
    ]
