"""Golden envelope helpers.

Two things are normalized before comparison: the fields that legitimately
differ between runs (run id, timestamps, timings, machine paths) and the
fixture server's ephemeral port. Everything else is expected to be byte-stable,
which is the whole point.

Regenerate with:  GEO_UPDATE_GOLDENS=1 pytest tests/test_envelope.py
"""

from __future__ import annotations

import json
import os
from pathlib import Path

from geo_audit.envelope import canonical

GOLDEN_DIR = Path(__file__).parent / "goldens"
FIXTURE_ORIGIN = "http://fixture"


def normalize(envelope: dict, base_url: str) -> dict:
    payload = json.dumps(canonical(envelope), indent=2, sort_keys=True, ensure_ascii=False)
    payload = payload.replace(base_url, FIXTURE_ORIGIN)
    return json.loads(payload)


def assert_matches(name: str, envelope: dict, base_url: str) -> None:
    actual = normalize(envelope, base_url)
    path = GOLDEN_DIR / f"{name}.json"
    if os.environ.get("GEO_UPDATE_GOLDENS") or not path.exists():
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            json.dumps(actual, indent=2, sort_keys=True, ensure_ascii=False) + "\n",
            encoding="utf-8",
        )
        if not os.environ.get("GEO_UPDATE_GOLDENS"):
            raise AssertionError(f"golden {name} did not exist; wrote it. Review and re-run.")
        return
    expected = json.loads(path.read_text(encoding="utf-8"))
    assert actual == expected, (
        f"envelope for {name} changed.\n"
        f"Re-run with GEO_UPDATE_GOLDENS=1 if the change is intended."
    )
