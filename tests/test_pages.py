"""Page bodies on disk: stored once by content, apart from the record, never printed.

The PRD kept no pages on disk; the maintainer lifted that on 2026-09-21. What the
rule protected is kept by how pages are stored: apart from `audits.jsonl`, so
sharing an audit shares no client's pages; never printed, so the CLI's output
boundary is unchanged; and once per content, so an unchanged page costs nothing.
"""

from __future__ import annotations

import hashlib
import io
import json

from geo_audit import state
from geo_audit.cli import main
from geo_audit.lib import pages
from geo_audit.lib.slug import project_slug

BASE = ["--allow-private", "--rate", "50", "--max-pages", "20"]
PAGE_SENTENCE = "Fixture Press publishes four articles"  # from hub.html's body


def _audit(site) -> str:
    buffer = io.StringIO()
    main(["audit", f"{site.url}/hub.html", *BASE, "--json", "--quiet"], out=buffer)
    return buffer.getvalue()


def _slug(site) -> str:
    return project_slug(f"{site.url}/hub.html")


def _snapshot(site) -> dict:
    records, _ = state.read_audits(_slug(site))
    return records[-1]["snapshot"]


def test_an_audit_keeps_every_page_it_read(site, geo_home):
    _audit(site)
    snapshot = _snapshot(site)
    assert len(snapshot["fetches"]) == len(snapshot["pages"])
    kept = [fetch for fetch in snapshot["fetches"] if fetch["body"]]
    assert kept, "readable pages are kept"
    for fetch in kept:
        body = pages.get(_slug(site), fetch["body"])
        assert body is not None
        assert hashlib.sha256(body.encode("utf-8")).hexdigest() == fetch["body"]


def test_an_unchanged_page_is_stored_once_across_runs(site, geo_home):
    _audit(site)
    first = set(pages.stored(_slug(site)))
    _audit(site)
    assert set(pages.stored(_slug(site))) == first


def test_robots_txt_is_kept_with_the_pages(site, geo_home):
    _audit(site)
    robots = _snapshot(site)["robots"]
    assert robots["body"] and "User-agent" in pages.get(_slug(site), robots["body"])


def test_pages_live_apart_from_the_record_and_off_stdout(site, geo_home):
    """Sharing audits.jsonl must not share a client's pages."""
    printed = _audit(site)
    assert PAGE_SENTENCE not in printed
    assert PAGE_SENTENCE not in state.audits_path(_slug(site)).read_text(encoding="utf-8")
    stored = [pages.get(_slug(site), digest) for digest in pages.stored(_slug(site))]
    assert any(PAGE_SENTENCE in body for body in stored)


def test_prune_collects_pages_no_kept_run_names(site, geo_home):
    _audit(site)
    referenced = set(pages.stored(_slug(site)))
    orphan = pages.put(_slug(site), "<html><body>nobody refers to me</body></html>")
    buffer = io.StringIO()
    main(["prune", "--json", "--quiet"], out=buffer)
    report = next(p for p in json.loads(buffer.getvalue())["prune"]["projects"] if p["project"] == _slug(site))
    assert orphan not in set(pages.stored(_slug(site)))
    assert set(pages.stored(_slug(site))) == referenced
    assert report["pages_deleted"] == 1


# --- rescoring from the pages themselves -------------------------------------


def _rescore(site, run_id) -> dict:
    buffer = io.StringIO()
    main(["audit", f"{site.url}/hub.html", "--rescore", run_id, "--json", "--quiet"], out=buffer)
    return json.loads(buffer.getvalue())


def test_a_rescore_reads_the_stored_pages(site, geo_home):
    original = json.loads(_audit(site))
    again = _rescore(site, original["run_id"])
    assert again["rescore"]["from"] == "pages"
    assert again["scores"] == original["scores"]
    assert [s["value"] for s in again["signals"]] == [s["value"] for s in original["signals"]]


def test_a_rescore_recomputes_rather_than_replays(site, geo_home, monkeypatch):
    """The point of keeping pages: a changed scoring rule can be re-applied to the
    exact bytes an old audit read. Stored values could never show a change."""
    from geo_audit.scoring import citability

    original = json.loads(_audit(site))
    monkeypatch.setattr(citability, "answer_first", lambda doc: (0.0, {"reason": "a changed rule"}))
    again = _rescore(site, original["run_id"])
    before = next(s for s in original["signals"] if s["id"] == "citability.answer_first")
    after = next(s for s in again["signals"] if s["id"] == "citability.answer_first")
    assert before["value"] > 0 and after["value"] == 0


def test_a_pruned_page_falls_back_to_the_recorded_ratios_and_says_so(site, geo_home):
    original = json.loads(_audit(site))
    victim = next(f["body"] for f in _snapshot(site)["fetches"] if f["body"])
    (pages.store_dir(_slug(site)) / f"{victim}{pages.SUFFIX}").unlink()
    again = _rescore(site, original["run_id"])
    assert again["rescore"]["from"] == "ratios"
    assert again["scores"] == original["scores"]
