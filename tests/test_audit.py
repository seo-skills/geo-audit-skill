"""`geo audit`: category weighting, PARTIAL end to end, and rescore purity."""

from __future__ import annotations

import io
import json

import pytest

from geo_audit import data
from geo_audit.cli import main
from geo_audit.commands.audit import CATEGORIES, SITE_CATEGORIES, parse_only
from geo_audit.errors import GeoError
from geo_audit.scoring.model import weighted_composite
from tests.golden import normalize

BASE = ["--allow-private", "--rate", "50", "--max-pages", "20"]


def run(args):
    buffer = io.StringIO()
    code = main(args + ["--json", "--quiet"], out=buffer)
    return code, json.loads(buffer.getvalue())


def audit(site, *extra):
    return run(["audit", f"{site.url}/hub.html", *BASE, *extra])


class FakeTTY(io.StringIO):
    def isatty(self) -> bool:
        return True


# --- the composite ---------------------------------------------------------


def test_an_audit_scores_every_category_its_inputs_can_reach(site, geo_home):
    """`brand` needs a name, so a URL-only audit does not claim to have missed it."""
    code, envelope = audit(site)
    assert code == 0
    assert set(envelope["scores"]["categories"]) == set(SITE_CATEGORIES)
    assert "brand" not in envelope["completeness"]["categories"]["missing"]
    assert "brand" not in envelope["completeness"]["categories"]["declared"]
    assert 0 <= envelope["scores"]["composite"] <= 100
    assert envelope["scores"]["tier"] in {t["label"] for t in data.tiers()}


def test_the_composite_is_the_weighted_mean_of_the_categories(site, geo_home):
    _, envelope = audit(site)
    weights = {name: data.weights()[name]["weight"] for name in SITE_CATEGORIES}
    expected, _ = weighted_composite(weights, envelope["scores"]["categories"])
    assert envelope["scores"]["composite"] == expected


def test_a_category_nobody_computed_leaves_both_sides_of_the_fraction(site, geo_home):
    """`--only schema` scores out of schema, not schema plus two zeroes."""
    _, full = audit(site)
    _, narrow = audit(site, "--only", "schema")
    assert narrow["scores"]["categories"] == {"schema": full["scores"]["categories"]["schema"]}
    assert narrow["scores"]["composite"] == full["scores"]["categories"]["schema"]
    coverage = narrow["completeness"]["categories"]
    assert coverage["computed"] == ["schema"]
    assert sorted(coverage["missing"]) == ["citability", "technical"]


def test_only_accepts_several_categories(site, geo_home):
    _, envelope = audit(site, "--only", "technical,schema")
    assert set(envelope["scores"]["categories"]) == {"technical", "schema"}


def test_an_unknown_category_is_a_usage_error(site, geo_home):
    code, envelope = audit(site, "--only", "vibes")
    assert code == 2
    assert envelope["error"]["code"] == "GEO_E_BAD_ARGS"
    assert "citability" in envelope["error"]["message"]


def test_parse_only_defaults_to_what_is_available():
    assert parse_only(None) == CATEGORIES
    assert parse_only(None, SITE_CATEGORIES) == SITE_CATEGORIES
    assert parse_only("  schema , technical ") == ("schema", "technical")
    with pytest.raises(GeoError):
        parse_only("nope")


def test_only_brand_without_a_brand_name_says_what_is_missing():
    with pytest.raises(GeoError) as raised:
        parse_only("brand", SITE_CATEGORIES)
    assert "--brand" in raised.value.message


# --- PARTIAL, end to end ---------------------------------------------------


def test_partial_is_carried_from_the_crawl_to_the_headline(site, geo_home):
    _, envelope = audit(site)
    assert envelope["evidence"]["stamp"] == "PARTIAL"
    assert envelope["evidence"]["pages_failed"]

    out = FakeTTY()
    main(["audit", f"{site.url}/hub.html", *BASE, "--quiet"], out=out)
    rendered = out.getvalue()
    assert "PARTIAL:" in rendered
    assert "could not be evaluated" in rendered
    assert "Scores reflect the" in rendered


def test_a_partial_audit_exits_zero_unless_asked_otherwise(site, geo_home):
    assert audit(site)[0] == 0
    buffer = io.StringIO()
    code = main(
        ["audit", f"{site.url}/hub.html", *BASE, "--json", "--quiet", "--fail-on-partial"],
        out=buffer,
    )
    assert code == 5


def test_a_failed_page_is_not_scored_as_a_failure(site, geo_home):
    """A 404 belongs in status_health and pages_failed, not in indexability."""
    _, envelope = audit(site)
    by_id = {signal["id"]: signal for signal in envelope["signals"]}
    indexability = by_id["technical.indexability"]
    status = by_id["technical.status_health"]
    assert indexability["detail"]["pages_measured"] < indexability["detail"]["pages_total"]
    assert status["detail"]["pages_measured"] == status["detail"]["pages_total"]
    assert indexability["value"] > 0, "pages with markup must not be dragged to zero by a 404"


# --- rescore ---------------------------------------------------------------


def test_rescoring_twice_is_byte_identical(site, geo_home):
    """The reproducibility claim, and the gate for this milestone."""
    _, recorded = audit(site)
    run_id = recorded["run_id"]

    _, first = run(["audit", f"{site.url}/hub.html", "--rescore", run_id])
    _, second = run(["audit", f"{site.url}/hub.html", "--rescore", run_id])

    left = json.dumps(normalize(first, site.url), sort_keys=True)
    right = json.dumps(normalize(second, site.url), sort_keys=True)
    assert left == right


def test_a_rescore_reproduces_the_recorded_composite(site, geo_home):
    _, recorded = audit(site)
    _, again = run(["audit", f"{site.url}/hub.html", "--rescore", recorded["run_id"]])
    assert again["scores"]["composite"] == recorded["scores"]["composite"]
    assert again["scores"]["categories"] == recorded["scores"]["categories"]


def test_a_rescore_makes_no_network_request(site, geo_home):
    _, recorded = audit(site)
    site.reset_requests()
    run(["audit", f"{site.url}/hub.html", "--rescore", recorded["run_id"]])
    assert site.requests_seen == [], "a rescore must not touch the network"


def test_a_rescore_reports_both_version_sets(site, geo_home):
    _, recorded = audit(site)
    _, again = run(["audit", f"{site.url}/hub.html", "--rescore", recorded["run_id"]])
    block = again["rescore"]
    assert block["run_id"] == recorded["run_id"]
    assert block["versions_match"] is True
    assert block["recorded_versions"]["data_version"] == data.data_version()
    assert block["recorded_composite"] == recorded["scores"]["composite"]


def test_a_rescore_notices_when_the_constants_have_moved(site, geo_home, monkeypatch):
    _, recorded = audit(site)
    path = geo_home / "projects" / "127-0-0-1" / "audits.jsonl"
    lines = path.read_text(encoding="utf-8").splitlines()
    stored = json.loads(lines[-1])
    stored["data_version"] = "1999.01"
    lines[-1] = json.dumps(stored, sort_keys=True, separators=(",", ":"))
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")

    _, again = run(["audit", f"{site.url}/hub.html", "--rescore", recorded["run_id"]])
    assert again["rescore"]["versions_match"] is False
    assert again["rescore"]["recorded_versions"]["data_version"] == "1999.01"


def test_an_unknown_run_id_is_a_usage_error(site, geo_home):
    code, envelope = run(["audit", f"{site.url}/hub.html", "--rescore", "01AAAAAAAAAAAAAAAAAAAAAAAA"])
    assert code == 2
    assert "was found" in envelope["error"]["message"]


def test_a_malformed_run_id_says_what_a_run_id_looks_like(site, geo_home):
    code, envelope = run(["audit", f"{site.url}/hub.html", "--rescore", "yesterday"])
    assert code == 2
    assert "26 characters" in envelope["error"]["message"]


# --- the record ------------------------------------------------------------


def test_every_audit_appends_one_record(site, geo_home):
    from geo_audit import state

    audit(site)
    audit(site)
    records, damaged = state.read_audits("127-0-0-1")
    assert len(records) == 2
    assert damaged == 0
    assert all(record["command"] == "audit" for record in records)


def test_the_record_holds_the_signals_a_rescore_needs(site, geo_home):
    from geo_audit import state

    audit(site)
    record = state.read_audits("127-0-0-1")[0][-1]
    assert record["signals"]
    assert all("value" in signal and "max" in signal for signal in record["signals"])
    assert record["evidence"]["content_hash"]


def test_audit_output_carries_no_page_text(site, geo_home):
    buffer = io.StringIO()
    main(["audit", f"{site.url}/hub.html", *BASE, "--json", "--quiet"], out=buffer)
    raw = buffer.getvalue()
    assert "Server-side rendering puts the full text" not in raw
    assert "Fixture Press publishes four articles" not in raw
