"""Golden envelope helpers.

Three things are normalized before comparison: the fields that legitimately
differ between runs (run id, timestamps, timings), the fixture server's
ephemeral port, and absolute paths, which differ per machine and per temp
directory. Everything else is expected to be byte-stable, which is the point.

Regenerate with:  GEO_UPDATE_GOLDENS=1 pytest tests/test_envelope.py
"""

from __future__ import annotations

import json
import os
import re
from pathlib import Path

from geo_audit.envelope import canonical

GOLDEN_DIR = Path(__file__).parent / "goldens"
FIXTURE_ORIGIN = "http://fixture"

# Temp directories, and anything under them, differ per run and per platform.
TEMP_PATH = re.compile(
    r"(?:/private)?(?:/var/folders/[^\"\s]*|/tmp/[^\"\s]*)"
    r"|[A-Za-z]:\\\\[^\"\s]*?Temp\\\\[^\"\s]*"
)


def _scrub_paths(payload: str) -> str:
    home = os.environ.get("GEO_HOME")
    if home:
        payload = payload.replace(str(Path(home).resolve()), "<home>")
        payload = payload.replace(home, "<home>")
    return TEMP_PATH.sub("<path>", payload)


def normalize(envelope: dict, base_url: str) -> dict:
    payload = json.dumps(canonical(envelope), indent=2, sort_keys=True, ensure_ascii=False)
    payload = payload.replace(base_url, FIXTURE_ORIGIN)
    payload = _scrub_paths(payload)
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
