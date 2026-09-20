"""`geo compare`: subtraction over records, and the refusal that protects it."""

from __future__ import annotations

import io
import json

import pytest

from geo_audit.commands.compare import comparable, compare_records
from geo_audit.cli import main
from tests.fixture_server import Reply

BASE = ["--allow-private", "--rate", "50", "--max-pages", "20"]


def run(args):
    buffer = io.StringIO()
    code = main(args + ["--json", "--quiet"], out=buffer)
    return code, json.loads(buffer.getvalue())


class FakeTTY(io.StringIO):
    def isatty(self) -> bool:
        return True


def audit(site):
    return run(["audit", f"{site.url}/hub.html", *BASE])


# --- the refusal -----------------------------------------------------------


def stamped(**overrides) -> dict:
    record = {"scoring_version": "1.0", "data_version": "2026.09", "normalizer_version": 1}
    record.update(overrides)
    return record


def test_matching_versions_are_comparable():
    assert comparable(stamped(), stamped()) == (True, None)


def test_a_minor_scoring_change_is_still_comparable():
    ok, _ = comparable(stamped(scoring_version="1.0"), stamped(scoring_version="1.4"))
    assert ok is True


def test_a_major_scoring_change_is_refused():
    ok, reason = comparable(stamped(scoring_version="1.0"), stamped(scoring_version="2.0"))
    assert ok is False
    assert "the formula changed" in reason


def test_a_data_version_change_is_refused():
    """Thresholds moving would show as the site moving."""
    ok, reason = comparable(stamped(data_version="2026.09"), stamped(data_version="2026.12"))
    assert ok is False
    assert "weights or thresholds changed" in reason


def test_an_unstamped_run_is_refused():
    ok, reason = comparable(stamped(data_version=None), stamped())
    assert ok is False
    assert "predates version stamping" in reason


def test_the_command_refuses_and_says_why(site, geo_home):
    from geo_audit import state

    audit(site)
    audit(site)
    path = geo_home / "projects" / "127-0-0-1" / "audits.jsonl"
    lines = path.read_text(encoding="utf-8").splitlines()
    older = json.loads(lines[0])
    older["data_version"] = "1999.01"
    lines[0] = json.dumps(older, sort_keys=True, separators=(",", ":"))
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")

    code, envelope = run(["compare", f"{site.url}/hub.html"])
    assert code == 2
    assert envelope["error"]["code"] == "GEO_E_INCOMPARABLE"
    assert "data_version" in envelope["error"]["message"]
    assert "measure the tool rather than the site" in envelope["error"]["hint"]


# --- the subtraction -------------------------------------------------------


def test_comparing_needs_two_runs(site, geo_home):
    audit(site)
    code, envelope = run(["compare", f"{site.url}/hub.html"])
    assert code == 2
    assert "Only 1 audit is recorded" in envelope["error"]["message"]


def test_an_unchanged_site_shows_no_movement(site, geo_home):
    audit(site)
    audit(site)
    _, envelope = run(["compare", f"{site.url}/hub.html"])
    block = envelope["compare"]
    assert block["composite_delta"] == 0
    assert block["tier_changed"] is False
    assert block["pages"]["changed"] == []
    assert block["findings"]["resolved"] == []
    assert block["findings"]["introduced"] == []


def test_a_fixed_page_moves_the_score_and_names_itself(serve, geo_home):
    """The end-to-end claim: change one page, see exactly that page."""
    from tests.fixture_server import site_routes

    routes = site_routes()
    server = serve(routes)
    args = ["audit", f"{server.url}/hub.html", *BASE]
    run(args)

    routes["/schema-broken.html"] = Reply(body=routes["/ssr-rich.html"].body)
    run(args)

    _, envelope = run(["compare", f"{server.url}/hub.html"])
    block = envelope["compare"]
    assert block["composite_delta"] > 0
    assert block["categories"]["schema"]["delta"] > 0
    assert [url for url in block["pages"]["changed"] if url.endswith("/schema-broken.html")]
    assert len(block["pages"]["changed"]) == 1, "only the page that changed"
    assert block["findings"]["resolved"], "fixing markup must resolve something"


def test_explicit_run_ids_select_the_ends(site, geo_home):
    _, first = audit(site)
    audit(site)
    _, third = audit(site)
    _, envelope = run(
        ["compare", f"{site.url}/hub.html", "--from", first["run_id"], "--to", third["run_id"]]
    )
    assert envelope["compare"]["from"]["run_id"] == first["run_id"]
    assert envelope["compare"]["to"]["run_id"] == third["run_id"]


def test_comparing_a_run_with_itself_is_refused(site, geo_home):
    _, only = audit(site)
    audit(site)
    code, envelope = run(
        ["compare", f"{site.url}/hub.html", "--from", only["run_id"], "--to", only["run_id"]]
    )
    assert code == 2
    assert "same run" in envelope["error"]["message"]


def test_an_unknown_run_id_is_a_usage_error(site, geo_home):
    audit(site)
    audit(site)
    code, envelope = run(["compare", f"{site.url}/hub.html", "--from", "01AAAAAAAAAAAAAAAAAAAAAAAA"])
    assert code == 2
    assert "No recorded audit" in envelope["error"]["message"]


def test_compare_makes_no_network_request(site, geo_home):
    audit(site)
    audit(site)
    site.reset_requests()
    run(["compare", f"{site.url}/hub.html"])
    assert site.requests_seen == []


def test_unchanged_signals_are_omitted_from_the_delta_list():
    before = {
        "scores": {"composite": 50, "categories": {"a": 50}},
        "signals": [{"id": "x", "value": 1, "max": 10}, {"id": "y", "value": 2, "max": 10}],
    }
    after = {
        "scores": {"composite": 55, "categories": {"a": 55}},
        "signals": [{"id": "x", "value": 1, "max": 10}, {"id": "y", "value": 7, "max": 10}],
    }
    deltas = {entry["id"]: entry for entry in compare_records(before, after)["signals"]}
    assert set(deltas) == {"y"}
    assert deltas["y"]["delta"] == 5


def test_the_suggested_next_command_is_runnable(site, geo_home):
    audit(site)
    audit(site)
    out = FakeTTY()
    main(["compare", f"{site.url}/hub.html", "--quiet"], out=out)
    last = out.getvalue().strip().splitlines()[-1]
    assert last.startswith("Next: geo audit http")


@pytest.mark.parametrize("field", ["composite_delta", "categories", "findings", "pages", "versions"])
def test_the_compare_block_has_its_documented_shape(site, geo_home, field):
    audit(site)
    audit(site)
    _, envelope = run(["compare", f"{site.url}/hub.html"])
    assert field in envelope["compare"]
