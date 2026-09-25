"""Two runs that scored different categories are two different yardsticks.

The composite is a weighted mean over the categories a run computed, so `--only
technical` after a full audit took the same unchanged site from 81 to 88 and a
tier up, and `compare` listed eight findings as resolved - every one outside
technical, none of them fixed, all of them simply not measured. `--brand` moves
the denominator the same way. The version gates exist to stop the tool's
movement reading as the site's; this is the same refusal for scope.
"""

from __future__ import annotations

import io
import json

from geo_audit.commands.compare import comparable
from geo_audit.cli import main

VERSIONS = {"scoring_version": "4.0", "data_version": "2026.09", "normalizer_version": 3}
BASE = ["--allow-private", "--rate", "50", "--max-pages", "20"]


def _run_of(*categories: str) -> dict:
    return {**VERSIONS, "scores": {"categories": {name: 50 for name in categories}}}


def run(args):
    buffer = io.StringIO()
    code = main(args + ["--json", "--quiet"], out=buffer)
    return code, json.loads(buffer.getvalue())


def test_runs_over_different_categories_are_not_compared():
    ok, reason = comparable(_run_of("citability", "technical"), _run_of("technical"))
    assert ok is False
    assert "categor" in reason and "--only" in reason


def test_adding_brand_is_a_change_of_scope_too():
    ok, _ = comparable(_run_of("technical", "schema"), _run_of("technical", "schema", "brand"))
    assert ok is False


def test_the_same_categories_in_any_order_compare():
    assert comparable(_run_of("technical", "schema"), _run_of("schema", "technical")) == (True, None)


def test_a_narrowed_run_is_refused_end_to_end_and_a_matching_pair_is_not(site, geo_home):
    _, first = run(["audit", f"{site.url}/hub.html", *BASE])
    _, second = run(["audit", f"{site.url}/hub.html", *BASE])
    run(["audit", f"{site.url}/hub.html", *BASE, "--only", "technical"])

    code, envelope = run(["compare", f"{site.url}/hub.html", "--allow-private"])
    assert code == 2
    assert envelope["error"]["code"] == "GEO_E_INCOMPARABLE"

    code, envelope = run(["compare", f"{site.url}/hub.html", "--allow-private",
                          "--from", first["run_id"], "--to", second["run_id"]])
    assert code == 0, envelope["error"]
    assert envelope["compare"]["findings"]["resolved"] == []
