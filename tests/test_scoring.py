"""The scorer: determinism, nullable signals, and finding order."""

from __future__ import annotations

from pathlib import Path

import pytest

from geo_audit import data
from geo_audit.lib.extract import extract
from geo_audit.scoring import citability
from geo_audit.scoring.model import (
    SCORED_CLASSES,
    Finding,
    composite,
    findings_for,
    prioritize,
    ramp,
)

FIXTURES = Path(__file__).parent / "fixtures" / "site"
URL = "https://example.com/page"


def doc_for(name: str):
    return extract((FIXTURES / name).read_text(encoding="utf-8"), URL)


def score_of(name: str, rendered_chars=None) -> int:
    signals = citability.score(doc_for(name), rendered_chars=rendered_chars)
    return composite(signals)[0]


# --- the arithmetic --------------------------------------------------------


def test_ramp_is_clamped_at_both_ends():
    assert ramp(0.0, 0.3, 0.8) == 0.0
    assert ramp(0.3, 0.3, 0.8) == 0.0
    assert ramp(0.8, 0.3, 0.8) == 1.0
    assert ramp(1.0, 0.3, 0.8) == 1.0
    assert ramp(0.55, 0.3, 0.8) == pytest.approx(0.5)


def test_a_null_signal_leaves_both_sides_of_the_fraction():
    """Not measured is not the same number as failed."""
    doc = doc_for("ssr-rich.html")
    without = composite(citability.score(doc, rendered_chars=None))[0]
    perfect = composite(citability.score(doc, rendered_chars=doc.content_chars))[0]
    zeroed = composite(citability.score(doc, rendered_chars=10_000_000))[0]
    assert without > zeroed, "a missing browser must not score like a failed render"
    assert perfect >= without


def test_completeness_names_the_signal_it_could_not_compute():
    _, completeness = composite(citability.score(doc_for("ssr-rich.html")))
    assert completeness["computed"] == 6
    assert completeness["total"] == 7
    assert completeness["missing"] == ["citability.render_parity"]


def test_completeness_is_full_when_the_browser_is_available():
    doc = doc_for("ssr-rich.html")
    _, completeness = composite(citability.score(doc, rendered_chars=doc.content_chars))
    assert completeness == {"computed": 7, "total": 7, "missing": []}


def test_every_declared_signal_is_produced_exactly_once():
    declared = set(data.weights()["citability"]["signals"])
    produced = [s.id for s in citability.score(doc_for("ssr-rich.html"))]
    assert sorted(produced) == sorted(declared)
    assert len(produced) == len(set(produced))


def test_every_signal_declares_a_scored_class():
    for signal in citability.score(doc_for("ssr-rich.html")):
        assert signal.cls in SCORED_CLASSES


def test_scoring_the_same_document_twice_is_identical():
    doc = doc_for("ssr-rich.html")
    first = [s.to_dict() for s in citability.score(doc)]
    second = [s.to_dict() for s in citability.score(doc)]
    assert first == second


# --- discrimination --------------------------------------------------------


def test_fixtures_rank_the_way_the_signal_table_says_they_should():
    rich = score_of("ssr-rich.html")
    plain = score_of("schema-none.html")
    weak = score_of("weak-prose.html")
    shell = score_of("csr-shell.html")
    assert rich > plain > weak > shell
    assert rich >= 85 and shell <= 5


def test_an_empty_shell_scores_zero_not_a_participation_score():
    assert score_of("no-blocks.html") == 0


def test_no_extractable_blocks_is_stated_as_the_reason():
    points, detail = citability.self_containment(doc_for("no-blocks.html"))
    assert points == 0.0
    assert detail["reason"] == "no extractable blocks"


# --- individual signals ----------------------------------------------------


def test_self_containment_flags_a_dangling_opener():
    doc = extract(
        "<main><p>This also means the migration has to run first, which "
        "affects everyone on the team and the release schedule.</p></main>",
        URL,
    )
    points, detail = citability.self_containment(doc)
    assert detail["self_contained"] == 0
    assert points == 0.0
    assert detail["worst_example"].startswith("This also means")


def test_self_containment_accepts_a_named_subject():
    doc = extract(
        "<main><p>The migration runs before the deploy, so every service "
        "restarts once during the release window.</p></main>",
        URL,
    )
    points, detail = citability.self_containment(doc)
    assert detail["self_contained"] == 1
    assert points == 25.0


def test_answer_first_rejects_a_filler_opener():
    doc = extract(
        "<main><h2>What is it?</h2><p>In this article we will explore the "
        "history of the subject before arriving at an answer.</p></main>",
        URL,
    )
    points, detail = citability.answer_first(doc)
    assert detail["answer_first"] == 0
    assert points == 0.0


def test_answer_first_rejects_a_run_on_lead_sentence():
    long_sentence = " ".join(["word"] * 60) + "."
    doc = extract(f"<main><h2>Q?</h2><p>{long_sentence}</p></main>", URL)
    _, detail = citability.answer_first(doc)
    assert detail["answer_first"] == 0


def test_structure_requires_an_outline_to_award_the_outline_points():
    empty, detail = citability.structure(extract("<main><p>Text.</p></main>", URL))
    assert detail["breakdown"]["no_skipped_levels"] == 0.0
    assert empty == 0.0


def test_structure_penalises_a_skipped_level():
    doc = extract("<main><h1>A</h1><h4>B</h4><p>Text.</p></main>", URL)
    _, detail = citability.structure(doc)
    assert detail["skipped_levels"] == 1


def test_evidence_density_counts_facts_not_words():
    with_facts = extract(
        "<main><p>Latency fell to 240 ms in March 2026 across 12 regions.</p></main>", URL
    )
    without = extract(
        "<main><p>Latency fell noticeably over the last while in many places.</p></main>", URL
    )
    assert citability.evidence_density(with_facts)[0] > citability.evidence_density(without)[0]


def test_extractability_caps_a_javascript_gated_page():
    points, detail = citability.extractability(doc_for("csr-shell.html"))
    assert detail["js_required_notice"] is True
    assert detail["capped_thin_or_js_gated"] is True
    assert points <= 3.0


def test_extractability_catches_an_empty_mount_point_with_no_noscript_notice():
    """A shell that does not announce itself is still a shell.

    Found by comparing the fetch layer against the reference implementation on
    the fixture set: no-blocks.html has an empty `<div id="app">` and no
    noscript warning, so notice-detection alone missed the reason for the page
    being empty.
    """
    detail = citability.extractability(doc_for("no-blocks.html"))[1]
    assert detail["js_required_notice"] is False
    assert detail["framework_root_chars"] == 0
    assert detail["empty_framework_root"] is True
    assert detail["capped_thin_or_js_gated"] is True


def test_a_server_rendered_page_has_no_empty_mount_point():
    detail = citability.extractability(doc_for("ssr-rich.html"))[1]
    assert detail["framework_root_chars"] is None
    assert detail["empty_framework_root"] is False


def test_attribution_reads_a_nested_publisher():
    doc = extract(
        '<html><head><script type="application/ld+json">'
        '{"@type":"Article","publisher":{"@type":"Organization","name":"X"}}'
        "</script></head><body><main><p>Body.</p></main></body></html>",
        URL,
    )
    _, detail = citability.attribution(doc)
    assert "organization_schema" in detail["present"]


def test_render_parity_is_null_without_a_rendered_measurement():
    points, detail = citability.render_parity(doc_for("ssr-rich.html"), None)
    assert points is None
    assert detail["reason"] == "browser extra not installed"


def test_render_parity_scores_a_gap_between_static_and_rendered():
    doc = doc_for("ssr-rich.html")
    full, _ = citability.render_parity(doc, doc.content_chars)
    half, _ = citability.render_parity(doc, doc.content_chars * 4)
    assert full == 10.0
    assert half == 0.0


# --- findings --------------------------------------------------------------


def test_a_healthy_signal_produces_no_finding():
    doc = doc_for("ssr-rich.html")
    signals = citability.score(doc, rendered_chars=doc.content_chars)
    ids = {f.id for f in findings_for(signals, URL)}
    assert "citability.self_containment" not in ids


def test_a_failing_signal_produces_its_full_severity():
    signals = citability.score(doc_for("weak-prose.html"))
    findings = {f.id: f for f in findings_for(signals, URL)}
    assert findings["citability.self_containment"].severity == "critical"


def test_a_middling_signal_is_demoted_one_step():
    from geo_audit.scoring.model import Signal

    signal = Signal(
        id="citability.self_containment", cls="heuristic", max=25, value=25 * 0.6
    )
    finding = findings_for([signal], URL)[0]
    assert finding.severity == "high", "critical demoted one step"


def test_priority_is_a_deterministic_total_order():
    findings = [
        Finding("b", "high", "low", "t", "r", points_lost=5),
        Finding("a", "critical", "high", "t", "r", points_lost=1),
        Finding("c", "high", "low", "t", "r", points_lost=5),
        Finding("d", "medium", "low", "t", "r", points_lost=20),
    ]
    order = [f.id for f in prioritize(findings)]
    assert order == ["a", "b", "c", "d"]
    assert [f.priority for f in prioritize(findings)] == [1, 2, 3, 4]


def test_every_finding_template_has_remediation_copy():
    templates = data.load("findings")
    for kind in ("signals", "checks"):
        for key, template in templates[kind].items():
            assert template["title"].strip(), key
            assert len(template["remediation"]) > 40, key
            assert template["severity"] in ("critical", "high", "medium", "low"), key
            assert template["effort"] in ("low", "medium", "high"), key


def test_every_scored_signal_has_a_finding_template():
    declared = set(data.weights()["citability"]["signals"])
    templates = set(data.load("findings")["signals"])
    assert declared <= templates


def test_tier_boundaries_are_contiguous_and_descending():
    tiers = data.tiers()
    mins = [t["min"] for t in tiers]
    assert mins == sorted(mins, reverse=True)
    assert mins[-1] == 0
    for tier in tiers:
        assert tier["meaning"].strip()
    assert data.tier_for(62)["label"] == "fair"
    assert data.tier_for(100)["label"] == "excellent"
    assert data.tier_for(0)["label"] == "poor"
