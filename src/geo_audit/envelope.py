"""The JSON envelope: the only thing a skill ever reads.

The key set is fixed and ordered. A command may add exactly one
command-specific object (`fetch` adds `page`, `doctor` adds `checks`);
everything else has the same shape everywhere, so a skill can branch on `ok`
and `error.code` without knowing which command ran.

`schema_version` is an output field. There is no request flag for it: a caller
that wanted an older shape would be asking us to lie about what we computed.
Additive changes leave it alone; removals and renames bump it and are
announced two releases ahead.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone

from geo_audit import data
from geo_audit._version import (
    CLI_VERSION,
    NORMALIZER_VERSION,
    SCHEMA_VERSION,
    SCORING_VERSION,
)

# Values that differ between two otherwise identical runs. Golden tests replace
# them rather than pretending runs are reproducible byte-for-byte end to end.
VOLATILE_FIELDS = ("run_id", "observed_at", "elapsed_ms", "log", "peer_address", "record")


def now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def build(
    command: str,
    *,
    ok: bool,
    run_id: str,
    observed_at: str | None = None,
    evidence: dict | None = None,
    completeness: dict | None = None,
    scores: dict | None = None,
    signals: list[dict] | None = None,
    findings: list[dict] | None = None,
    error: dict | None = None,
    extra: dict | None = None,
) -> dict:
    envelope = {
        "schema_version": SCHEMA_VERSION,
        "command": command,
        "ok": ok,
        "cli_version": CLI_VERSION,
        "scoring_version": SCORING_VERSION,
        "data_version": data.data_version(),
        "normalizer_version": NORMALIZER_VERSION,
        "run_id": run_id,
        "observed_at": observed_at or now_iso(),
        "evidence": evidence,
        "completeness": completeness,
        "scores": scores,
        "signals": signals or [],
        "findings": findings or [],
        "error": error,
    }
    if extra:
        envelope.update(extra)
    return envelope


def dumps(envelope: dict) -> str:
    return json.dumps(envelope, indent=2, ensure_ascii=False)


def canonical(envelope: dict) -> dict:
    """A copy with volatile values replaced, for golden comparison."""

    def scrub(node):
        if isinstance(node, dict):
            return {
                key: ("<volatile>" if key in VOLATILE_FIELDS and value is not None else scrub(value))
                for key, value in node.items()
            }
        if isinstance(node, list):
            return [scrub(item) for item in node]
        return node

    return scrub(envelope)
