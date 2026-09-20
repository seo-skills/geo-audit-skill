"""Folding model judgement into a report without letting it become a score.

The audit emits advisory questions with a rubric and no value. A model answers
them. This module reads those answers back in for the report.

The one rule: an advisory answer is rendered in its own labelled section and
never reaches `scores`. That is enforced by where the data goes - the answers
join the client context's advisory list and nothing else - rather than by a
flag someone could set.
"""

from __future__ import annotations

import json
from pathlib import Path

from geo_audit import data
from geo_audit.errors import GeoError
from geo_audit.lib.extract import excerpt

VERDICTS = ("yes", "partial", "no", "unclear")
MAX_NOTE = 600


def declared_ids() -> set[str]:
    out: set[str] = set()
    for category in data.weights().values():
        out.update((category.get("advisory") or {}).keys())
    return out


def load(path: str | Path | None) -> dict[str, dict]:
    """Read answers, rejecting anything that is not an answer to a real question."""
    if path is None:
        return {}
    target = Path(path).expanduser()
    if not target.exists():
        raise GeoError(
            "GEO_E_BAD_ARGS",
            f"No advisory file at {target}. The audit envelope lists the questions "
            f"under `signals` with class `advisory`.",
        )
    try:
        payload = json.loads(target.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise GeoError("GEO_E_BAD_ARGS", f"{target} is not valid JSON: {exc.msg}.") from exc
    if not isinstance(payload, dict):
        raise GeoError("GEO_E_BAD_ARGS", f"{target} must contain a JSON object keyed by signal id.")

    known = declared_ids()
    answers: dict[str, dict] = {}
    for signal_id, answer in payload.items():
        if signal_id not in known:
            raise GeoError(
                "GEO_E_BAD_ARGS",
                f"{signal_id!r} is not an advisory question. Known questions: "
                f"{', '.join(sorted(known))}.",
            )
        if not isinstance(answer, dict):
            raise GeoError(
                "GEO_E_BAD_ARGS",
                f"The answer to {signal_id} must be an object with `verdict` and `note`.",
            )
        verdict = str(answer.get("verdict", "")).strip().lower()
        if verdict not in VERDICTS:
            raise GeoError(
                "GEO_E_BAD_ARGS",
                f"{signal_id} has verdict {answer.get('verdict')!r}; it must be one "
                f"of {', '.join(VERDICTS)}.",
            )
        # The note is model-written prose about a crawled page, so it is capped
        # and escaped like any other text that did not originate here.
        answers[signal_id] = {
            "verdict": verdict,
            "note": excerpt(str(answer.get("note", "")), MAX_NOTE),
        }
    return answers


def merge(advisory_signals: list[dict], answers: dict[str, dict]) -> list[dict]:
    """Attach answers to the questions they answer. Values stay absent."""
    merged = []
    for signal in advisory_signals:
        answer = answers.get(signal["id"], {})
        merged.append(
            {
                "id": signal["id"],
                "question": (signal.get("detail") or {}).get("question", ""),
                "rubric": (signal.get("detail") or {}).get("rubric", []),
                "verdict": answer.get("verdict"),
                "note": answer.get("note"),
                "answered": bool(answer),
            }
        )
    return merged
