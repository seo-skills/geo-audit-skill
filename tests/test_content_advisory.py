"""The content category, and the invariant that advisory judgement is never a number."""

from __future__ import annotations

import io
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from geo_audit import data
from geo_audit.cli import main
from geo_audit.lib.extract import extract
from geo_audit.scoring import content as content_scorer
from geo_audit.scoring.model import ADVISORY, SCORED_CLASSES, composite
from geo_audit.report import advisory as advisory_lib

URL = "https://example.com/guide"
BASE = ["--allow-private", "--rate", "50", "--max-pages", "20"]
NOW = datetime(2026, 9, 20, tzinfo=timezone.utc)


def run(args):
    buffer = io.StringIO()
    code = main(args + ["--json", "--quiet"], out=buffer)
    return code, json.loads(buffer.getvalue())


def doc_of(html: str):
    return extract(html, URL)


# --- the invariant ---------------------------------------------------------


def test_advisory_is_excluded_from_the_scored_classes():
    assert ADVISORY not in SCORED_CLASSES


def test_an_advisory_signal_cannot_move_a_composite():
    """Structural, not a policy: `composite` filters on class.

    Give an advisory signal a full-marks value it should never have had and
    the number must not move.
    """
    from geo_audit.scoring.model import Signal

    scored = [Signal(id="a.b", cls="heuristic", max=10, value=5)]
    baseline, coverage = composite(scored)

    poisoned = scored + [Signal(id="a.advisory.c", cls=ADVISORY, max=100, value=100)]
    after, coverage_after = composite(poisoned)

    assert after == baseline == 50
    assert coverage == coverage_after, "advisory must not affect completeness either"


def test_an_audit_emits_the_questions_with_no_value(site, geo_home):
    _, envelope = run(["audit", f"{site.url}/hub.html", *BASE])
    advisory = [s for s in envelope["signals"] if s["class"] == ADVISORY]
    assert advisory, "the rubric must travel with the data"
    for signal in advisory:
        assert signal["value"] is None
        assert signal["max"] == 0
        assert signal["detail"]["enters_score"] is False
        assert signal["detail"]["rubric"]


def test_advisory_signals_are_not_counted_in_completeness(site, geo_home):
    _, envelope = run(["audit", f"{site.url}/hub.html", *BASE])
    advisory = {s["id"] for s in envelope["signals"] if s["class"] == ADVISORY}
    scored_total = sum(
        len(category["signals"]) for name, category in data.weights().items()
        if name in envelope["completeness"]["categories"]["declared"]
    )
    assert envelope["completeness"]["total"] == scored_total
    assert not (advisory & set(envelope["completeness"]["missing"]))


def test_advisory_survives_a_rescore_without_becoming_a_score(site, geo_home):
    _, first = run(["audit", f"{site.url}/hub.html", *BASE])
    _, again = run(["audit", f"{site.url}/hub.html", "--rescore", first["run_id"]])
    assert again["scores"]["composite"] == first["scores"]["composite"]
    assert [s["id"] for s in again["signals"] if s["class"] == ADVISORY] == [
        s["id"] for s in first["signals"] if s["class"] == ADVISORY
    ]


# --- answering the questions ----------------------------------------------


def answers_file(tmp_path: Path, payload: dict) -> Path:
    target = tmp_path / "advisory.json"
    target.write_text(json.dumps(payload), encoding="utf-8")
    return target


def test_an_answer_reaches_the_report_but_not_the_score(site, geo_home, tmp_path):
    _, audited = run(["audit", f"{site.url}/hub.html", *BASE])
    answers = answers_file(
        tmp_path,
        {
            "content.advisory.experience": {
                "verdict": "partial",
                "note": "Names specific versions but never reports anything failing.",
            }
        },
    )
    _, envelope = run(["report", f"{site.url}/hub.html", "--advisory", str(answers)])
    assert envelope["scores"]["composite"] == audited["scores"]["composite"]
    assert envelope["report"]["advisory_answered"] == ["content.advisory.experience"]

    rendered = Path(envelope["report"]["path"]).read_text(encoding="utf-8")
    assert "Names specific versions but never reports anything failing." in rendered
    assert "model judgement, not scored" in rendered


def test_an_unanswered_question_says_so_rather_than_being_hidden(site, geo_home):
    run(["audit", f"{site.url}/hub.html", *BASE])
    _, envelope = run(["report", f"{site.url}/hub.html"])
    rendered = Path(envelope["report"]["path"]).read_text(encoding="utf-8")
    assert "Not assessed" in rendered


def test_an_answer_to_a_question_nobody_asked_is_refused(site, geo_home, tmp_path):
    run(["audit", f"{site.url}/hub.html", *BASE])
    answers = answers_file(tmp_path, {"content.advisory.invented": {"verdict": "yes", "note": "x"}})
    code, envelope = run(["report", f"{site.url}/hub.html", "--advisory", str(answers)])
    assert code == 2
    assert "is not an advisory question" in envelope["error"]["message"]


def test_a_bad_verdict_is_refused(site, geo_home, tmp_path):
    run(["audit", f"{site.url}/hub.html", *BASE])
    answers = answers_file(tmp_path, {"content.advisory.experience": {"verdict": "9/10", "note": "x"}})
    code, envelope = run(["report", f"{site.url}/hub.html", "--advisory", str(answers)])
    assert code == 2
    assert "must be one of" in envelope["error"]["message"]


def test_a_model_written_note_is_capped_and_escaped(tmp_path):
    answers = answers_file(
        tmp_path,
        {"content.advisory.experience": {"verdict": "yes", "note": "<script>x</script>" + "y" * 2000}},
    )
    loaded = advisory_lib.load(answers)
    note = loaded["content.advisory.experience"]["note"]
    assert len(note) <= advisory_lib.MAX_NOTE
    assert "<" not in note and ">" not in note


# --- the measurable signals -----------------------------------------------


def test_depth_caps_a_thin_page():
    thin = doc_of("<html><body><main><h1>T</h1><p>Two sentences only. That is all.</p></main></body></html>")
    points, detail = content_scorer.depth(thin)
    assert detail["thin"] is True
    assert points <= 6.0


def test_depth_rewards_substance_and_structure():
    body = "".join(
        f"<h2>Section {i}</h2><p>{'word ' * 120}</p>" for i in range(5)
    )
    rich = doc_of(f"<html><body><main><h1>T</h1>{body}<ul><li>a</li></ul></main></body></html>")
    assert content_scorer.depth(rich)[0] > 20


def test_expertise_wants_a_named_person_with_credentials():
    anonymous = doc_of("<html><body><main><p>x</p></main></body></html>")
    named = doc_of(
        '<html><head><script type="application/ld+json">'
        '{"@type":"Person","name":"Dana","jobTitle":"Engineer","url":"/about",'
        '"sameAs":["https://example.com/dana"]}</script>'
        '<meta name="author" content="Dana"></head><body><main><p>x</p></main></body></html>'
    )
    assert content_scorer.expertise(anonymous)[0] == 0.0
    points, detail = content_scorer.expertise(named)
    assert points >= 22
    assert "credentials" in detail["present"]


def test_freshness_scores_zero_without_a_date():
    plain = doc_of("<html><body><main><p>x</p></main></body></html>")
    points, detail = content_scorer.freshness(plain, NOW)
    assert points == 0.0
    assert detail["reason"] == "no date on the page"


def test_freshness_decays_with_age():
    def dated(days: int):
        when = (NOW - timedelta(days=days)).strftime("%Y-%m-%d")
        return doc_of(
            f'<html><head><meta property="article:modified_time" content="{when}">'
            "</head><body><main><p>x</p></main></body></html>"
        )

    recent = content_scorer.freshness(dated(10), NOW)[0]
    middling = content_scorer.freshness(dated(400), NOW)[0]
    ancient = content_scorer.freshness(dated(2000), NOW)[0]
    assert recent > middling > ancient
    assert recent == 25.0
    assert ancient == 8.0, "a stale page still gets credit for being datable"


def test_a_published_date_alone_scores_less_than_a_modified_one():
    when = NOW.strftime("%Y-%m-%d")
    published = doc_of(
        f'<html><head><meta property="article:published_time" content="{when}"></head>'
        "<body><main><p>x</p></main></body></html>"
    )
    modified = doc_of(
        f'<html><head><meta property="article:modified_time" content="{when}"></head>'
        "<body><main><p>x</p></main></body></html>"
    )
    assert content_scorer.freshness(published, NOW)[0] < content_scorer.freshness(modified, NOW)[0]


def test_readability_prefers_shorter_sentences():
    short = doc_of("<html><body><main><p>" + "The cat sat down. " * 30 + "</p></main></body></html>")
    long = doc_of("<html><body><main><p>" + ("word " * 60 + ". ") * 10 + "</p></main></body></html>")
    assert content_scorer.readability(short)[0] > content_scorer.readability(long)[0]
    assert content_scorer.readability(short)[0] == 25.0


def test_readability_reports_the_numbers_behind_it():
    doc = doc_of("<html><body><main><p>" + "One two three four five. " * 20 + "</p></main></body></html>")
    detail = content_scorer.readability(doc)[1]
    assert detail["sentences"] == 20
    assert detail["mean_words"] == 5.0
    assert detail["long_sentences"] == 0


def test_content_produces_every_declared_signal():
    from tests.test_technical_schema import FakePage

    produced = {s.id for s in content_scorer.score(FakePage(doc=doc_of("<main><p>x</p></main>")))}
    assert produced == set(data.weights()["content"]["signals"])
