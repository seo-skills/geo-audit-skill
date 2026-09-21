"""`geo report`: mode isolation, escaping, contrast, and print rules.

The leak test is the reason this file exists. An operator-only field appearing
in a delivered client report is the failure mode the two-context design is
aimed at, and it is the kind of bug that is discovered by a client rather than
by a developer.
"""

from __future__ import annotations

import io
import json
import re
from dataclasses import fields
from pathlib import Path

import pytest
from jinja2 import UndefinedError

from geo_audit.commands.report import output_path
from geo_audit.cli import main
from geo_audit.report import brand as brand_lib
from geo_audit.report import context as context_lib
from geo_audit.report import render as render_lib
from tests.fixture_server import Reply

BASE = ["--allow-private", "--rate", "50", "--max-pages", "20"]


def run(args):
    buffer = io.StringIO()
    code = main(args + ["--json", "--quiet"], out=buffer)
    return code, json.loads(buffer.getvalue())


class FakeTTY(io.StringIO):
    def isatty(self) -> bool:
        return True


@pytest.fixture
def audited(site, geo_home):
    """One recorded audit, and the envelope it produced."""
    _, envelope = run(["audit", f"{site.url}/hub.html", *BASE])
    return envelope


def report(site, *extra) -> dict:
    _, envelope = run(["report", f"{site.url}/hub.html", *extra])
    return envelope["report"]


def html_of(site, *extra) -> str:
    return Path(report(site, *extra)["path"]).read_text(encoding="utf-8")


# --- mode isolation --------------------------------------------------------


def test_the_client_namespace_has_no_operator_key(audited, site):
    """Structural proof, not a conditional.

    Rendering the operator template with only the client namespace must raise,
    which is what makes a leak a test failure rather than a delivered field.
    """
    template = render_lib._environment().get_template(render_lib.OPERATOR_TEMPLATE)
    client, _ = context_lib.build(
        audited, brand_lib.Brand(), generated_on="2026-09-20"
    )
    with pytest.raises(UndefinedError):
        template.render(client=client, stylesheet="")


def test_client_mode_omits_every_operator_only_value(audited, site):
    """The real definition: nothing whose home is OperatorContext.

    Page URLs are excluded from this check on purpose. A broken link on the
    client's own site belongs in their report; what does not belong is the
    failure table, the reasons, the hashes and the signal internals.
    """
    client_html = html_of(site)
    operator_html = html_of(site, "--mode", "operator")

    forbidden = {
        "run id": audited["run_id"],
        "evidence hash": audited["evidence"]["content_hash"],
        "observed timestamp": audited["observed_at"],
        "signal id": audited["signals"][0]["id"],
        "provenance heading": "Provenance",
        "operator-copy marker": "operator copy only",
    }
    for reason in {entry["reason"] for entry in audited["evidence"]["pages_failed"]}:
        forbidden[f"failure reason {reason}"] = reason

    leaked = {label: value for label, value in forbidden.items() if value and value in client_html}
    assert not leaked, f"client report leaked: {sorted(leaked)}"

    # Each of them must be in the operator copy, or the test is vacuous.
    missing = {label: value for label, value in forbidden.items() if value and value not in operator_html}
    assert not missing, f"operator report is missing: {sorted(missing)}"


def test_every_operator_context_field_is_absent_from_the_client_report(audited, site):
    """Walk the dataclass, so a new operator field cannot be forgotten."""
    client_html = html_of(site)
    brand = brand_lib.Brand()
    _, operator = context_lib.build(audited, brand, generated_on="2026-09-20")

    # Fields whose values legitimately also appear in client-facing findings.
    shared_by_design = {"pages_failed", "signals", "contrast", "brand_warnings", "completeness"}
    for field in fields(operator):
        if field.name in shared_by_design:
            continue
        value = getattr(operator, field.name)
        if isinstance(value, str) and len(value) > 8:
            assert value not in client_html, f"operator.{field.name} leaked"
        if isinstance(value, dict):
            for item in value.values():
                if isinstance(item, str) and len(item) > 8:
                    assert item not in client_html, f"operator.{field.name} leaked"


def test_a_report_contains_no_data_from_another_project(site, serve, geo_home):
    """Upstream's leak class: one client's report carrying another's data."""
    other = serve(
        {
            "/index.html": Reply(
                body="<html><head><title>Rival Industries confidential</title></head>"
                "<body><main><h1>Rival Industries confidential</h1>"
                "<p>" + ("secret " * 120) + "</p></main></body></html>"
            ),
            "/robots.txt": Reply(body="User-agent: *\nAllow: /\n", content_type="text/plain"),
        }
    )
    run(["audit", f"{other.url}/index.html", *BASE])
    run(["audit", f"{site.url}/hub.html", *BASE])

    for mode in ("client", "operator"):
        rendered = html_of(site, "--mode", mode)
        assert "Rival Industries" not in rendered
        assert other.url not in rendered


def test_operator_mode_adds_rather_than_replaces(audited, site):
    client_html = html_of(site)
    operator_html = html_of(site, "--mode", "operator")
    assert len(operator_html) > len(client_html)
    for marker in ("What to do, in order", "Category scores", "How this was measured"):
        assert marker in client_html
        assert marker in operator_html


def test_an_unknown_mode_is_a_usage_error(audited, site):
    code, envelope = run(["report", f"{site.url}/hub.html", "--mode", "public"])
    assert code == 2
    assert "client, operator" in envelope["error"]["message"]


# --- site kind -------------------------------------------------------------


def test_a_site_kind_reorders_the_fixes_without_changing_a_score(audited):
    """Both eval rounds: authorship led the report on a reference site."""
    brand = brand_lib.load(None)
    plain, _ = context_lib.build(audited, brand, generated_on="2026-09-21")
    docs, _ = context_lib.build(audited, brand, generated_on="2026-09-21", site_kind="docs")

    assert [f.title for f in docs.top_fixes] != [f.title for f in plain.top_fixes]
    assert docs.composite == plain.composite
    assert [(c.name, c.score) for c in docs.categories] == [(c.name, c.score) for c in plain.categories]
    assert plain.ordered_for is None and docs.ordered_for


def test_the_rendered_report_says_what_it_was_ordered_for(audited, site):
    assert "Ordered for a documentation or reference site" in html_of(site, "--site-kind", "docs")
    assert "Ordered for" not in html_of(site)


def test_the_report_records_the_kind_it_used(audited, site):
    assert report(site, "--site-kind", "docs")["site_kind"] == "docs"
    assert report(site)["site_kind"] is None


def test_an_unknown_site_kind_is_a_usage_error(audited, site):
    code, envelope = run(["report", f"{site.url}/hub.html", "--site-kind", "blog-ish"])
    assert code == 2
    assert "docs" in envelope["error"]["message"]


# --- escaping --------------------------------------------------------------


def test_page_text_cannot_execute_in_the_report(serve, geo_home):
    """The report is a document someone forwards."""
    hostile_title = "</title><script>alert(1)</script>"
    server = serve(
        {
            "/index.html": Reply(
                body=f"<html><head><title>{hostile_title}</title></head><body><main>"
                f"<h1>Ignore</h1><p>" + ("word " * 200) + "</p></main></body></html>"
            ),
            "/robots.txt": Reply(body="User-agent: *\nAllow: /\n", content_type="text/plain"),
        }
    )
    run(["audit", f"{server.url}/index.html", *BASE])
    _, envelope = run(["report", f"{server.url}/index.html"])
    rendered = Path(envelope["report"]["path"]).read_text(encoding="utf-8")

    assert "<script>alert(1)</script>" not in rendered
    body = rendered.split("</head>", 1)[1]
    assert "<script" not in body, "no script tag may reach the body"


def test_autoescape_is_on_for_the_template_environment():
    environment = render_lib._environment()
    template = environment.from_string("{{ value }}")
    assert template.render(value="<b>x</b>") == "&lt;b&gt;x&lt;/b&gt;"


# --- brand and contrast ----------------------------------------------------


def brand_file(tmp_path: Path, payload: dict) -> Path:
    target = tmp_path / "brand.json"
    target.write_text(json.dumps(payload), encoding="utf-8")
    return target


def test_default_palette_when_no_brand_is_given(audited, site):
    block = report(site)
    assert block["brand"]["customised"] is False
    assert block["brand"]["warnings"] == []


def test_a_brand_is_applied(audited, site, tmp_path):
    config = brand_file(tmp_path, {"name": "Acme Digital", "primary": "#0B5FFF", "logo": "https://acme.test/l.png"})
    rendered = html_of(site, "--brand-config", str(config))
    assert "Acme Digital" in rendered
    assert "#0B5FFF" in rendered
    assert "https://acme.test/l.png" in rendered


def test_an_unreadable_accent_falls_back_loudly(audited, site, tmp_path, capsys):
    """Yellow on white is 1.27:1. It looks deliberate and nobody notices."""
    config = brand_file(tmp_path, {"name": "Acme", "primary": "#FFE600", "accent": "#FFE600"})
    buffer = io.StringIO()
    main(["report", f"{site.url}/hub.html", "--brand-config", str(config), "--json", "--quiet"], out=buffer)
    envelope = json.loads(buffer.getvalue())

    warnings = envelope["report"]["brand"]["warnings"]
    assert any("accent" in warning and "4.5:1" in warning for warning in warnings)
    assert "brand:" in capsys.readouterr().err, "the fallback must be loud on stderr"

    rendered = Path(envelope["report"]["path"]).read_text(encoding="utf-8")
    assert f"--accent: {brand_lib.DEFAULT_ACCENT}" in rendered
    assert "--primary: #FFE600" in rendered, "the header can keep the brand colour"


def test_the_brand_fallback_is_annotated_in_the_operator_view(audited, site, tmp_path):
    config = brand_file(tmp_path, {"primary": "#FFE600", "accent": "#FFE600"})
    rendered = html_of(site, "--mode", "operator", "--brand-config", str(config))
    assert "below the 4.5:1 AA minimum" in rendered
    assert "accent text on paper" in rendered


def test_every_contrast_pair_the_default_palette_uses_passes_aa():
    for entry in brand_lib.Brand().contrast_report():
        assert entry["passes_aa"], f"{entry['pair']} is {entry['ratio']}:1"


def test_a_malformed_brand_file_is_a_usage_error(audited, site, tmp_path):
    target = tmp_path / "brand.json"
    target.write_text("{not json", encoding="utf-8")
    code, envelope = run(["report", f"{site.url}/hub.html", "--brand-config", str(target)])
    assert code == 2
    assert "not valid JSON" in envelope["error"]["message"]


def test_attribution_is_on_by_default_and_removable(audited, site, tmp_path):
    assert "Generated with SEOmator GEO Audit Skill" in html_of(site)
    config = brand_file(tmp_path, {"attribution": False})
    assert "Generated with SEOmator GEO Audit Skill" not in html_of(site, "--brand-config", str(config))


# --- structure and accessibility -------------------------------------------


def test_the_sections_appear_in_reader_order(audited, site):
    rendered = html_of(site)
    order = ["GEO audit:", "out of 100", "What stands out", "What to do, in order",
             "Category scores", "Everything found", "How this was measured"]
    positions = [rendered.index(marker) for marker in order]
    assert positions == sorted(positions), "sections must run in reader order"


def test_the_score_never_appears_without_its_label(audited, site):
    rendered = html_of(site)
    verdict = rendered.split('class="verdict"', 1)[1].split("</div>", 1)[0]
    assert 'class="score"' in verdict
    assert 'class="tier"' in verdict


def test_colour_is_never_the_only_channel(audited, site):
    """Every severity-coloured block also carries the word."""
    rendered = html_of(site)
    for block in re.findall(r'<div class="fix (\w+)">(.*?)</div>', rendered, re.DOTALL):
        severity, body = block
        assert severity in body, f"a {severity} block does not say so in text"


def test_print_rules_are_present(audited, site):
    rendered = html_of(site)
    assert "@page" in rendered
    assert "size: A4" in rendered
    assert "break-inside: avoid" in rendered
    assert "@media print" in rendered


def test_one_intentional_breakpoint(audited, site):
    rendered = html_of(site)
    breakpoints = re.findall(r"@media \(max-width: ([^)]+)\)", rendered)
    assert breakpoints == ["30rem"], f"expected one breakpoint, found {breakpoints}"


def test_the_report_is_a_single_self_contained_file(audited, site):
    """It gets emailed. It cannot depend on anything being fetched."""
    rendered = html_of(site)
    assert "<style>" in rendered
    assert not re.search(r'<link[^>]+rel="stylesheet"', rendered)
    assert "<script" not in rendered


# --- paths and records -----------------------------------------------------


def test_the_default_path_is_deterministic_and_dated(audited, site, geo_home):
    block = report(site)
    name = Path(block["path"]).name
    assert re.fullmatch(r"\d{4}-\d{2}-\d{2}-[0-9a-f]{8}\.html", name), name
    assert Path(block["path"]).parent == geo_home / "projects" / "127-0-0-1" / "reports"


def test_nothing_is_silently_overwritten(audited, site):
    first = report(site)["path"]
    second = report(site)["path"]
    assert first != second
    assert Path(first).exists() and Path(second).exists()


def test_out_overrides_the_path(audited, site, tmp_path):
    target = tmp_path / "nested" / "audit.html"
    block = report(site, "--out", str(target))
    assert Path(block["path"]) == target
    assert target.read_text(encoding="utf-8").startswith("<!DOCTYPE html>")


def test_reporting_without_an_audit_says_what_to_run(site, geo_home):
    code, envelope = run(["report", f"{site.url}/hub.html"])
    assert code == 2
    assert "geo audit" in envelope["error"]["message"]


def test_a_specific_run_can_be_rendered(site, geo_home):
    _, first = run(["audit", f"{site.url}/hub.html", *BASE])
    run(["audit", f"{site.url}/hub.html", *BASE])
    block = report(site, "--run", first["run_id"])
    assert block["from_run"] == first["run_id"]


def test_report_makes_no_network_request(audited, site):
    site.reset_requests()
    report(site)
    assert site.requests_seen == []


def test_the_same_record_renders_the_same_document(audited, site, tmp_path):
    first = tmp_path / "a.html"
    second = tmp_path / "b.html"
    report(site, "--out", str(first))
    report(site, "--out", str(second))
    strip_date = lambda text: re.sub(r"\d{4}-\d{2}-\d{2}", "DATE", text)  # noqa: E731
    assert strip_date(first.read_text(encoding="utf-8")) == strip_date(second.read_text(encoding="utf-8"))


# --- PDF -------------------------------------------------------------------


def test_pdf_absence_is_reported_not_fatal(audited, site, monkeypatch):
    from geo_audit.report import pdf as pdf_lib

    monkeypatch.setattr(pdf_lib, "write_pdf", lambda *a, **k: "the browser extra is not installed")
    code, envelope = run(["report", f"{site.url}/hub.html", "--pdf"])
    assert code == 0
    block = envelope["report"]
    assert block["pdf_path"] is None
    assert "playwright install chromium" in block["pdf_skipped"]
    assert Path(block["path"]).exists(), "the HTML is the guaranteed artifact"


def test_output_path_falls_back_to_the_run_id_without_a_hash(tmp_path, monkeypatch, geo_home):
    record = {"observed_at": "2026-05-05T00:00:00Z", "run_id": "01ABCDEFGHJKMNPQRSTVWXYZ00", "evidence": {}}
    path = output_path("example-com", record, None)
    assert path.name.startswith("2026-05-05-")


@pytest.mark.browser
@pytest.mark.skipif(
    not __import__("geo_audit.report.pdf", fromlist=["available"]).available(),
    reason="the optional browser extra is not installed; PDF rendering is not exercised",
)
def test_a_real_pdf_renders_through_the_print_pipeline(audited, site, tmp_path):
    """Print-to-PDF, so report.css decides the page breaks rather than a second renderer."""
    target = tmp_path / "audit.html"
    _, envelope = run(["report", f"{site.url}/hub.html", "--pdf", "--out", str(target)])
    block = envelope["report"]

    assert block["pdf_skipped"] is None
    pdf = Path(block["pdf_path"])
    assert pdf.exists() and pdf.suffix == ".pdf"

    raw = pdf.read_bytes()
    assert raw.startswith(b"%PDF-"), "not a PDF"
    assert len(raw) > 10_000, "a one-page stub means the print stylesheet did not apply"
    assert b"/Type /Page" in raw or b"/Type/Page" in raw


def test_every_category_says_what_it_measures():
    """Round three's dry run: the client report's category table had blank
    "What it measures" cells for content and platform - in every report sent.
    """
    from geo_audit import data

    for category in data.weights():
        assert context_lib.CATEGORY_BLURB.get(category), f"{category} has no description"


# --- strengths -------------------------------------------------------------


def _signal(signal_id, value, maximum=10, cls="deterministic"):
    return {"id": signal_id, "class": cls, "value": value, "max": maximum, "page": None, "detail": {}}


WEIGHTS = {"technical": 15, "platform": 10, "schema": 10}


def test_a_strength_is_a_strong_signal_with_no_finding_of_its_own():
    """Three rounds of maintainer notes: a report that lists only faults reads
    as grudging, and a 76 with nothing named for it is the first thing edited.
    """
    signals = [
        _signal("technical.transport_security", 10),   # strong, no finding
        _signal("technical.status_health", 10),        # strong, but reported below
        _signal("schema.presence", 5),                 # not strong
        _signal("schema.validity", None),              # not measured
        _signal("content.expertise", None, cls="advisory"),
    ]
    findings = [{"id": "technical.status_health"}]
    shown = context_lib.strengths(signals, findings, WEIGHTS, None)
    assert [s["id"] for s in shown] == ["technical.transport_security"]
    assert shown[0]["text"]


def test_a_strength_never_sits_beside_a_finding_about_it():
    """95% HTTPS and one page on http: "served over HTTPS" beside "not served
    securely" is the contradiction this rule exists to prevent."""
    signals = [_signal("technical.transport_security", 9.5)]
    page_level = [{"id": "technical.transport_security", "page_level": True}]
    assert context_lib.strengths(signals, page_level, WEIGHTS, None) == []


def test_heavier_categories_first_and_the_kind_first_of_all():
    signals = [_signal("platform.llms_txt", 10), _signal("technical.transport_security", 10)]
    plain = [s["id"] for s in context_lib.strengths(signals, [], WEIGHTS, None)]
    docs = [s["id"] for s in context_lib.strengths(signals, [], WEIGHTS, "docs")]
    assert plain == ["technical.transport_security", "platform.llms_txt"]
    assert docs == ["platform.llms_txt", "technical.transport_security"]


def test_at_most_three_strengths():
    signals = [_signal(f"technical.{name}", 10) for name in
               ("transport_security", "status_health", "indexability", "metadata", "url_structure")]
    assert len(context_lib.strengths(signals, [], WEIGHTS, None)) == 3


def test_a_report_with_strengths_says_what_is_working(audited, site):
    html = html_of(site)
    shown = report(site)["strengths"]
    assert shown, "the fixture site must have at least one strength"
    assert "What is already working" in html


def test_a_site_with_no_strengths_gets_no_empty_section():
    brand = brand_lib.load(None)
    envelope = {"signals": [_signal("schema.presence", 1)], "findings": [], "scores": {}}
    client, _ = context_lib.build(envelope, brand, generated_on="2026-09-21")
    assert client.strengths == []
    assert "What is already working" not in render_lib.render_client(client)


def test_strengths_are_spread_across_categories_before_repeating_one():
    """Round three's dry run: plausible's three strengths were all citability, and
    its best category - technical, 95 - went unmentioned. A practitioner names
    what works across areas before naming a second thing in one."""
    signals = [
        _signal("citability.self_containment", 25, 25), _signal("citability.answer_first", 20, 20),
        _signal("citability.extractability", 15, 15), _signal("technical.transport_security", 10),
    ]
    weights = {"citability": 25, "technical": 15}
    shown = [s["id"] for s in context_lib.strengths(signals, [], weights, None)]
    assert shown[:2] == ["citability.self_containment", "technical.transport_security"]
    assert len(shown) == 3


# --- reporting parity with the reference --------------------------------------


def _client(audited, **kwargs):
    client, _ = context_lib.build(audited, brand_lib.load(None), generated_on="2026-09-21", **kwargs)
    return client


def test_the_summary_is_built_from_the_numbers(audited):
    client = _client(audited)
    scores = audited["scores"]["categories"]
    best, worst = max(scores, key=scores.get), min(scores, key=scores.get)
    assert f"{audited['scores']['composite']}/100" in client.summary
    assert best in client.summary and worst in client.summary


def test_the_summary_leads_with_a_blocker_when_there_is_one(site, geo_home):
    """A start URL the server refuses blocks the whole site. The hub fixture has
    none: its one client-rendered page is one page of several, which is a
    page-level finding, not a site-wide blocker."""
    _, refused = run(["audit", f"{site.url}/bot-block", "--allow-private", "--rate", "50", "--max-pages", "8"])
    client = _client(refused)
    blocker = next(f for f in client.top_fixes if f.blocking)
    assert blocker.title in client.summary


def test_category_contributions_add_up_to_the_score(audited):
    client = _client(audited)
    total = sum(category.contribution for category in client.categories)
    # Each share is rounded to 0.1 and the composite to a whole number.
    assert abs(total - audited["scores"]["composite"]) < 1.0


def test_each_fix_carries_its_gain_on_the_overall_score_and_its_evidence(audited):
    client = _client(audited)
    signal_fixes = [f for f in client.top_fixes if f.impact is not None]
    assert signal_fixes, "the fixture must have findings tied to signals"
    for fix in signal_fixes:
        assert fix.impact > 0
        assert fix.evidence, f"{fix.title} says nothing about what was measured"


def test_the_plan_places_every_fix_once_with_blockers_first(audited):
    client = _client(audited)
    planned = [fix.title for group in client.plan for fix in group["fixes"]]
    everything = [fix.title for fixes in client.by_category.values() for fix in fixes]
    assert sorted(planned) == sorted(everything)
    first = client.plan[0]["fixes"]
    blockers = [fix.title for fix in client.top_fixes if fix.blocking]
    assert set(blockers) <= {fix.title for fix in first}, "a blocker must be in the first group"


def test_the_crawler_table_covers_every_token_the_robots_matrix_checked(audited):
    client = _client(audited)
    checked = {entry["agent"] for entry in audited["crawl"]["robots"]["access"]}
    assert {row["token"] for row in client.crawlers} == checked
    for row in client.crawlers:
        assert row["operator"] and row["purpose"]
        if not row["allowed"] and row["critical"]:
            assert row["advice"].startswith("Allow")


def test_category_detail_names_every_signal_in_plain_words(audited):
    client = _client(audited)
    shown = [signal for group in client.category_detail for signal in group["signals"]]
    measured = [s for s in audited["signals"] if s["class"] != "advisory"]
    assert len(shown) == len(measured)
    for signal in shown:
        assert not re.fullmatch(r"[a-z]+\.[a-z_]+", signal["name"]), f"an id, not a name: {signal['name']}"


def test_pages_analysed_lists_every_crawled_page(audited):
    client = _client(audited)
    assert [page["url"] for page in client.pages_analysed] == [p["url"] for p in audited["crawl"]["pages"]]
    assert sum(page["findings"] for page in client.pages_analysed) > 0


def test_the_report_carries_every_new_section(audited, site):
    html = html_of(site)
    for heading in ("Summary", "The plan", "AI crawler access", "Category detail",
                    "Pages analysed", "Glossary"):
        assert f">{heading}<" in html, f"missing section {heading!r}"


def test_a_category_outside_the_run_is_named_not_left_to_guesswork(audited, site):
    """seomator.com's table added up to a weight of 80, and nothing said why:
    brand needs a brand name, and none was given. A client adding up the column
    deserves the answer on the page."""
    client = _client(audited)
    assert client.unscored == [{"name": "brand", "weight": 20}]
    assert "brand (weight 20) was not part of this run" in html_of(site)


def test_the_report_says_how_many_signals_the_score_was_computed_on(audited, site):
    """PRD §3.4: a missing capability nulls signals and lowers completeness, and
    "the report says 'computed on 31 of 36 signals'". It did not say it anywhere."""
    completeness = audited["completeness"]
    client = _client(audited)
    expected = f"Computed on {completeness['computed']} of {completeness['total']} signals"
    assert client.completeness_note.startswith(expected)
    html = html_of(site)
    assert expected in html
    for signal_id in completeness["missing"]:
        assert signal_id not in html, "missing signals are named, never shown as ids"
