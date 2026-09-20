"""Detecting page text that is addressed to an AI system rather than a reader.

This is not a filter that makes untrusted content safe - nothing does, and the
output boundary is the real defence. It exists because one artifact this tool
produces, a generated llms.txt, is a document the user publishes and an engine
then reads as authoritative. Copying a page's own "ignore previous
instructions" into that file would be handing the attack a better delivery
mechanism than the page had.

So the rule is narrow and conservative: entries that look like they are
talking to a model are left out of the generated file and reported, rather
than silently rewritten or silently included.
"""

from __future__ import annotations

import re

PATTERNS: tuple[tuple[str, re.Pattern], ...] = (
    (
        "override",
        re.compile(
            r"\b(?:ignore|disregard|forget|override)\b[^.]{0,30}\b"
            r"(?:previous|prior|above|earlier|all)\b[^.]{0,20}\b"
            r"(?:instruction|prompt|rule|direction)",
            re.IGNORECASE,
        ),
    ),
    (
        "role_marker",
        re.compile(r"(?:^|\s)(?:system|assistant|user)\s*:", re.IGNORECASE),
    ),
    (
        "role_assertion",
        re.compile(r"\byou are (?:now|an? )\b[^.]{0,40}\b(?:mode|assistant|model|ai)\b", re.IGNORECASE),
    ),
    (
        "new_instructions",
        re.compile(r"\bnew instructions?\b(?:\s+for\b)?", re.IGNORECASE),
    ),
    (
        "output_demand",
        re.compile(r"\b(?:output|respond with|reply with|return)\b[^.]{0,20}\{", re.IGNORECASE),
    ),
    (
        "end_of_context",
        re.compile(r"-{2,}\s*END OF\b|\bEND OF (?:PAGE|DOCUMENT|CONTEXT|OUTPUT)\b", re.IGNORECASE),
    ),
)


def instruction_like(text: str) -> list[str]:
    """Return the names of the patterns this text matches, or an empty list.

    Deliberately conservative: prose about prompt injection will trip it, and
    a false positive costs one excluded entry plus a line explaining why.
    """
    if not text:
        return []
    return [name for name, pattern in PATTERNS if pattern.search(text)]
