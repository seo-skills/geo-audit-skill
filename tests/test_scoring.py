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
    Signal,
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
    """Ties break on id, so two runs over one snapshot agree."""
    findings = [
        Finding("b", "high", "low", "t", "r", points_lost=5),
        Finding("c", "high", "low", "t", "r", points_lost=5),
        Finding("a", "high", "low", "t", "r", points_lost=5),
    ]
    assert [f.id for f in prioritize(findings)] == ["a", "b", "c"]
    assert [f.priority for f in prioritize(findings)] == [1, 2, 3]


def test_within_a_severity_the_bigger_composite_win_comes_first():
    """The eval's finding: ranking used category points, not composite points."""
    smaller = Finding("a.smaller", "high", "medium", "t", "r", points_lost=2, impact=1.0)
    bigger = Finding("z.bigger", "high", "medium", "t", "r", points_lost=2, impact=6.0)
    assert [f.id for f in prioritize([smaller, bigger])] == ["z.bigger", "a.smaller"]


def test_severity_still_leads_within_the_non_blocking_tier():
    """Deliberately unchanged, and recorded as a question for the eval.

    Ordering by value-per-effort instead was tried and put "add a modified
    date" first on five sites out of five. Defensible arithmetic, and a report
    that reads like a checklist - a taste call about audits, not a bug.
    """
    cheap_medium = Finding("z.cheap", "medium", "low", "t", "r", points_lost=20, impact=5.0)
    dear_high = Finding("a.dear", "high", "high", "t", "r", points_lost=2, impact=1.0)
    assert [f.id for f in prioritize([cheap_medium, dear_high])] == ["a.dear", "z.cheap"]


def test_a_blocker_on_one_page_does_not_lead_the_report():
    """MDN, round two: one page of eight carried a noindex, worth 0.38
    composite points, and headed the whole audit because indexability is a
    blocker and blockers skipped the cap."""
    from geo_audit import data

    blocking_id = data.load("findings")["blocking"]["ids"][0]
    outlier = Finding(blocking_id, "critical", "low", "t", "r", impact=0.4).mark_page_level()
    assert outlier.severity == "medium", "marking it page-level is what caps it"
    site_wide = Finding("z.site", "high", "medium", "t", "r", impact=5.0)
    assert [f.id for f in prioritize([outlier, site_wide])] == ["z.site", blocking_id]


def test_a_blocker_comes_first_however_the_arithmetic_falls():
    """Prose on a page no crawler can fetch recovers nothing."""
    from geo_audit import data

    blocking_id = (data.load("findings")["blocking"]["ids"])[0]
    blocker = Finding(blocking_id, "critical", "high", "t", "r", points_lost=1)
    bigger = Finding("z.other", "medium", "low", "t", "r", points_lost=40)
    assert [f.id for f in prioritize([bigger, blocker])] == [blocking_id, "z.other"]


def test_every_blocking_id_is_a_real_finding():
    from geo_audit import data

    templates = data.load("findings")
    known = set(templates["signals"]) | set(templates["checks"])
    for blocking_id in templates["blocking"]["ids"]:
        assert blocking_id in known, blocking_id


def test_impact_converts_category_points_into_composite_points():
    """30 points of schema (weight 10) is a smaller win than 25 of citability (25)."""
    from geo_audit.scoring.model import Signal, apply_impact

    signals = [
        Signal(id="schema.presence", cls="deterministic", max=100, value=70),
        Signal(id="citability.self_containment", cls="heuristic", max=100, value=75),
    ]
    findings = [
        Finding("schema.presence", "high", "medium", "t", "r", points_lost=30),
        Finding("citability.self_containment", "high", "medium", "t", "r", points_lost=25),
    ]
    apply_impact(findings, signals, {"schema": 10, "citability": 25})
    by_id = {f.id: f for f in findings}
    assert by_id["schema.presence"].impact == pytest.approx(3.0)
    assert by_id["citability.self_containment"].impact == pytest.approx(6.25)
    assert [f.id for f in prioritize(findings)][0] == "citability.self_containment"


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


def test_blockers_are_ordered_by_the_gate_they_close_not_by_arithmetic():
    """A 403 on the start URL ranked below "your content needs JS".

    The blocking tier exists so arithmetic does not decide the lead, but the
    tiebreak inside it was still `impact`, and a page the server refused is
    never scored - so it carries no impact and no points_lost, and lost every
    tiebreak to a blocker that had been measured. Order is now the declared
    one, which follows the chain: respond, allow, index, parse.
    """
    refused = Finding("fetch.blocked", "critical", "medium", "t", "r")
    needs_js = Finding("citability.extractability", "critical", "high", "t", "r", impact=3.0)
    assert refused.impact is None and refused.points_lost == 0
    assert [f.id for f in prioritize([needs_js, refused])] == [
        "fetch.blocked",
        "citability.extractability",
    ]


def test_the_declared_blocking_order_is_the_dependency_chain():
    """Each gate is a precondition for the next, so the list is not arbitrary."""
    from geo_audit import data

    ids = data.load("findings")["blocking"]["ids"]
    assert ids.index("fetch.server_error") < ids.index("technical.crawler_access")
    assert ids.index("fetch.blocked") < ids.index("technical.crawler_access")
    assert ids.index("technical.crawler_access") < ids.index("technical.indexability")
    assert ids.index("technical.indexability") < ids.index("citability.extractability")


def test_an_uncomputed_category_leaves_both_sides_of_the_fraction():
    """The same rule as a null signal, one level up, and the only one untested.

    `audit` cannot currently produce a null category - every category owns at
    least one deterministic signal, so something is always computable - which
    is exactly why the rule needs its own test rather than relying on a run to
    exercise it.
    """
    from geo_audit.scoring.model import weighted_composite

    weights = {"citability": 25, "content": 20}
    total, coverage = weighted_composite(weights, {"citability": 80, "content": None})

    assert total == 80, "content must not be averaged in as a zero"
    assert coverage["computed"] == ["citability"]
    assert coverage["missing"] == ["content"]
    assert coverage["weights_used"] == {"citability": 25}


def test_no_category_computed_is_not_a_score_of_zero_anybody_should_use():
    """Guarded by the caller, which skips a category with no pages entirely."""
    from geo_audit.scoring.model import weighted_composite

    total, coverage = weighted_composite({"citability": 25}, {"citability": None})
    assert coverage["computed"] == [] and coverage["missing"] == ["citability"]
    assert total == 0, "the caller must read `computed`, not the number"


# --- site kind ----------------------------------------------------------------


def _kind_findings():
    return [
        Finding("content.expertise", "high", "medium", "t", "r", points_lost=12, impact=2.4),
        Finding("citability.answer_first", "medium", "medium", "t", "r", points_lost=6, impact=1.5),
        Finding("schema.validity", "medium", "low", "t", "r", points_lost=10, impact=1.0),
    ]


def test_a_site_kind_reorders_without_changing_a_number():
    """Both eval rounds: a publisher's checklist led a reference site's report.

    A kind moves what matters more for it up one severity level and what
    matters less down two, then the ordinary order applies. The arithmetic -
    points lost, impact - is the same for every kind of site.
    """
    from geo_audit.scoring.model import for_site_kind

    before = {f.id: (f.points_lost, f.impact) for f in _kind_findings()}
    ordered = for_site_kind(_kind_findings(), "docs")

    assert ordered[0].id == "citability.answer_first" and ordered[0].severity == "high"
    assert next(f for f in ordered if f.id == "content.expertise").severity == "low"
    assert {f.id: (f.points_lost, f.impact) for f in ordered} == before


def test_a_deferred_finding_falls_below_the_ordinary_ones():
    """Round three's dry run, MDN as `docs`: moved down one level, authorship was
    still third, because nearly everything else on the site was already medium and
    it won that band on impact. Its impact is large *because* the kind does not
    fit - the site was never going to carry per-page bylines - so a deferred
    finding goes down two levels, below the site's ordinary problems.
    """
    from geo_audit.scoring.model import for_site_kind

    deferred = Finding("content.expertise", "high", "medium", "t", "r", impact=4.0)
    ordinary = Finding("platform.feeds", "medium", "low", "t", "r", impact=0.5)
    ordered = for_site_kind([deferred, ordinary], "docs")
    assert [f.id for f in ordered] == ["platform.feeds", "content.expertise"]


@pytest.mark.parametrize("kind", ["saas", "ecommerce", "local", "docs", "spec"])
def test_authorship_only_leads_where_pages_have_authors(kind):
    """Round two: authorship was in the top three on all five sites and first on
    three - a SaaS site, a shop and a reference site among them. The signal
    scores per-page bylines and Person markup, which only a publisher is
    expected to carry, so every other kind defers it.
    """
    from geo_audit.scoring.model import site_kinds

    assert "content.expertise" in site_kinds()[kind]["defer"]
    assert "content.expertise" in site_kinds()["publisher"]["lead"]


@pytest.mark.parametrize("kind", ["docs", "spec"])
def test_llms_txt_leads_for_documentation(kind):
    """The proposal was written for documentation sites; MDN had it fourth."""
    from geo_audit.scoring.model import site_kinds

    assert "platform.llms_txt" in site_kinds()[kind]["lead"]


def test_no_kind_is_the_order_the_audit_already_produced():
    from geo_audit.scoring.model import for_site_kind

    plain = [f.id for f in prioritize(_kind_findings())]
    assert [f.id for f in for_site_kind(_kind_findings(), None)] == plain


def test_a_kind_never_moves_a_blocker():
    from geo_audit.scoring.model import for_site_kind

    blocker = Finding("citability.extractability", "critical", "high", "t", "r")
    ordered = for_site_kind([*_kind_findings(), blocker], "docs")
    assert ordered[0].id == "citability.extractability" and ordered[0].severity == "critical"


def test_a_kind_never_makes_anything_critical():
    """Mattering more for one kind of site is not an emergency."""
    from geo_audit.scoring.model import for_site_kind

    lead = Finding("citability.answer_first", "high", "medium", "t", "r")
    assert for_site_kind([lead], "docs")[0].severity == "high"


def test_a_page_level_finding_keeps_its_ceiling_under_a_kind():
    """One page is still one page, whatever the site is for."""
    from geo_audit.scoring.model import for_site_kind

    outlier = Finding("citability.answer_first", "high", "medium", "t", "r").mark_page_level()
    assert outlier.severity == "medium"
    assert for_site_kind([outlier], "docs")[0].severity == "medium"


def test_the_site_kind_table_only_names_real_non_blocking_signals():
    from geo_audit import data

    templates = data.load("findings")
    blocking = set(templates["blocking"]["ids"])
    for kind, spec in data.load("site_kinds")["kinds"].items():
        assert spec["label"] and spec["note"], kind
        lead, defer = set(spec["lead"]), set(spec["defer"])
        assert not lead & defer, f"{kind} both leads and defers {sorted(lead & defer)}"
        for signal_id in lead | defer:
            assert signal_id in templates["signals"], f"{kind}: {signal_id} is not a signal"
            assert signal_id not in blocking, f"{kind}: blockers never move, so {signal_id} cannot be listed"


def test_no_finding_text_names_its_own_severity():
    """Round three's dry run: MDN's report put "high" beside "which is why this
    is medium". Severity moves - a site kind promotes or defers, a page-level
    finding is capped - so a sentence that names it will contradict its label.
    Say why the fix is worth doing, not which level it sits at.
    """
    import re

    from geo_audit import data

    self_rating = re.compile(r"\b(?:this is|rather than)\s+(?:critical|high|medium|low)\b", re.I)
    templates = data.load("findings")
    for section in ("signals", "checks"):
        for finding_id, template in templates[section].items():
            for wording in (template, template.get("partial") or {}):
                for field_name in ("title", "remediation"):
                    text = wording.get(field_name) or ""
                    assert not self_rating.search(text), f"{finding_id}.{field_name} names its severity"


def test_every_signal_can_say_what_is_working():
    """A strength is only shown with its sentence, so a signal without one could
    be the site's best and never be named."""
    from geo_audit import data

    for signal_id, template in data.load("findings")["signals"].items():
        assert template.get("strength"), f"{signal_id} has no strength sentence"


def test_no_strength_claims_more_than_an_average_can_show():
    """A strength means the site-wide value is at or above the threshold - an
    average. "Every page" is a claim an average cannot make."""
    import re

    from geo_audit import data

    absolute = re.compile(r"\b(?:every|all|each|always|never)\b", re.I)
    for signal_id, template in data.load("findings")["signals"].items():
        text = template.get("strength") or ""
        assert not absolute.search(text), f"{signal_id}: {text!r}"


# --- partial presence ----------------------------------------------------------


def _expertise(present, value=16.0):
    missing = sorted({"byline", "person_schema", "credentials", "author_profile", "organization"} - set(present))
    return Signal(id="content.expertise", cls="deterministic", max=25, value=value,
                  detail={"present": sorted(present), "missing": missing})


def test_a_named_author_is_not_called_unreadable():
    """The first real run of the skill, on seomator.com: Person markup and a byline
    on all fifty pages, and the finding still said "Authorship is not
    machine-readable". The skill corrected it in chat; the report would not have."""
    finding = findings_for([_expertise(["byline", "organization", "person_schema"])], "https://x")[0]
    assert "not machine-readable" not in finding.title
    assert finding.title == data.load("findings")["signals"]["content.expertise"]["partial"]["title"]


def test_nothing_about_the_author_keeps_the_absent_wording():
    """An Organization alone names no author, so it is not a partial author."""
    finding = findings_for([_expertise(["organization"], value=3.0)], "https://x")[0]
    assert finding.title == "Authorship is not machine-readable"


def test_an_aggregate_without_a_shared_present_list_keeps_the_default():
    """Pages that disagree leave no `present` in the rolled-up detail."""
    signal = Signal(id="content.expertise", cls="deterministic", max=25, value=8.0, detail={"mean": 8.0})
    assert findings_for([signal], "https://x")[0].title == "Authorship is not machine-readable"


def test_every_partial_variant_triggers_on_parts_the_scorer_reports():
    """A misspelt part name would make a variant silently unreachable."""
    from geo_audit.scoring import citability as citability_scorer, content as content_scorer
    from geo_audit.scoring import schema_org

    markup = (
        '<script type="application/ld+json">{"@context": "https://schema.org", "@graph": ['
        '{"@type": "Organization", "name": "Acme"},'
        '{"@type": "Person", "name": "Ada"},'
        '{"@type": "Article", "headline": "A", "author": {"@type": "Person", "name": "Ada"}}]}</script>'
    )
    page = extract(f"<html><head>{markup}</head><body><main><p>Text.</p></main></body></html>",
                   "https://example.com/a")
    parts = {
        "content.expertise": content_scorer.expertise(page)[1],
        "citability.attribution": citability_scorer.attribution(page)[1],
        "schema.organization": schema_org.organization(page)[1],
        "schema.article": schema_org.article(page)[1],
    }
    templates = data.load("findings")["signals"]
    with_partial = {k for k, t in templates.items() if t.get("partial")}
    assert with_partial == set(parts), "a partial variant was added without a check here"
    for signal_id, detail in parts.items():
        known = set(detail.get("present") or []) | set(detail.get("missing") or [])
        unknown = set(templates[signal_id]["partial"]["when_present"]) - known
        assert not unknown, f"{signal_id}: {sorted(unknown)} is not a part the scorer reports"
