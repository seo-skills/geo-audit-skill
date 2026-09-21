"""Page bodies on disk: stored once by content, apart from the record, never printed.

The PRD kept no pages on disk; the maintainer lifted that on 2026-09-21. What the
rule protected is kept by how pages are stored: apart from `audits.jsonl`, so
sharing an audit shares no client's pages; never printed, so the CLI's output
boundary is unchanged; and once per content, so an unchanged page costs nothing.
"""

from __future__ import annotations

import gzip
import hashlib
import io
import json
import os
import time

from geo_audit import state
from geo_audit.cli import main
from geo_audit.lib import pages
from geo_audit.lib.slug import project_slug
from tests.fixture_server import Reply

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


def _age(slug: str, digest: str, hours: float = 48) -> None:
    """Make a stored page look as if it was last written `hours` ago."""
    then = time.time() - hours * 3600
    os.utime(pages.store_dir(slug) / f"{digest}{pages.SUFFIX}", (then, then))


def _prune(*flags) -> dict:
    buffer = io.StringIO()
    main(["prune", *flags, "--json", "--quiet"], out=buffer)
    return json.loads(buffer.getvalue())["prune"]


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
    _age(_slug(site), orphan)
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


# --- a re-audit reads the site as it is now ------------------------------------

ROBOTS = Reply(body="User-agent: *\nAllow: /\n", content_type="text/plain; charset=utf-8")
GUIDE = ("<html><head><title>Guide</title></head><body><main><h1>Guide</h1><p>"
         + "Steady content that does not change between audits. " * 40 + "</p></main></body></html>")
LLMS = "# Fixture Guide\n\n> A guide that does not change.\n\n## Docs\n\n- [Guide](/guide.html): the guide\n"


def _audit_guide(site) -> dict:
    buffer = io.StringIO()
    main(["audit", f"{site.url}/guide.html", "--allow-private", "--rate", "50", "--max-pages", "3",
          "--json", "--quiet"], out=buffer)
    return json.loads(buffer.getvalue())


def _signal(envelope: dict, signal_id: str) -> float:
    return next(s["value"] for s in envelope["signals"] if s["id"] == signal_id)


def test_a_reaudit_sees_a_header_fix_on_an_unchanged_page(serve, geo_home):
    """A 304 says a page's bytes are unchanged, not its headers, and two signals
    are read from headers. Dropping `X-Robots-Tag: noindex` from a server's
    config leaves the bytes and the ETag as they were, so a re-audit that
    trusted the 304 would go on reporting the page as blocked - on exactly the
    run made to confirm the fix. A re-audit asks for every page plainly."""
    served = {"noindex": True, "conditional": 0}

    def guide(path, headers):
        if headers.get("If-None-Match") == '"v1"':
            served["conditional"] += 1
            return Reply(status=304, body="", headers={"ETag": '"v1"'})
        extra = {"ETag": '"v1"', **({"X-Robots-Tag": "noindex"} if served["noindex"] else {})}
        return Reply(body=GUIDE, headers=extra)

    site = serve({"/guide.html": guide, "/robots.txt": ROBOTS})
    assert _signal(_audit_guide(site), "technical.indexability") == 0
    served["noindex"] = False
    assert _signal(_audit_guide(site), "technical.indexability") > 0
    assert served["conditional"] == 0


def test_a_rescore_rereads_llms_txt_with_todays_rules(serve, geo_home, monkeypatch):
    """llms.txt is read and judged by this tool like robots.txt, so it is kept
    like robots.txt: a rescore judges the stored file by today's rules."""
    from geo_audit.commands import llmstxt

    site = serve({"/guide.html": Reply(body=GUIDE), "/robots.txt": ROBOTS,
                  "/llms.txt": Reply(body=LLMS, content_type="text/plain; charset=utf-8")})
    original = _audit_guide(site)
    judge = llmstxt.parse
    monkeypatch.setattr(llmstxt, "parse", lambda text: {**judge(text), "valid": False})
    buffer = io.StringIO()
    main(["audit", f"{site.url}/guide.html", "--rescore", original["run_id"], "--json", "--quiet"], out=buffer)
    again = json.loads(buffer.getvalue())
    assert again["rescore"]["from"] == "pages"
    assert _signal(original, "platform.llms_txt") > _signal(again, "platform.llms_txt") > 0


# --- storing pages safely beside other runs -------------------------------------


def test_prune_spares_a_page_too_new_to_be_an_orphan(site, geo_home):
    """An audit stores its pages before it appends the record that names them,
    so a page no record names yet may belong to a run still in progress. The
    rule git applies to loose objects: nothing young is collected."""
    _audit(site)
    fresh = pages.put(_slug(site), "<html><body>stored by a run still going</body></html>")
    report = next(p for p in _prune()["projects"] if p["project"] == _slug(site))
    assert fresh in pages.stored(_slug(site))
    assert report["pages_deleted"] == 0


def test_storing_a_page_again_marks_it_in_use(geo_home):
    """An unchanged page is not written twice, so storing it again has to renew
    its age, or a run that just reused it could lose it to prune."""
    digest = pages.put("reuse", "<html><body>unchanged since last run</body></html>")
    _age("reuse", digest)
    pages.put("reuse", "<html><body>unchanged since last run</body></html>")
    path = pages.store_dir("reuse") / f"{digest}{pages.SUFFIX}"
    assert time.time() - path.stat().st_mtime < 3600


def test_prune_leaves_a_history_that_grew_while_it_ran_alone(site, geo_home, monkeypatch):
    """prune rewrites audits.jsonl from what it read. An audit that lands in
    between would be erased, so a file that grew is left alone to prune again."""
    from geo_audit.commands import prune

    _audit(site)
    _audit(site)
    plan = prune.plan_for

    def plan_while_an_audit_lands(records, limits, now):
        planned = plan(records, limits, now)
        state.append_audit(_slug(site), {"command": "audit", "run_id": "zz-landed-mid-prune",
                                         "observed_at": now.isoformat()})
        return planned

    monkeypatch.setattr(prune, "plan_for", plan_while_an_audit_lands)
    report = next(p for p in _prune("--keep", "1")["projects"] if p["project"] == _slug(site))
    records, _ = state.read_audits(_slug(site))
    assert "zz-landed-mid-prune" in [r.get("run_id") for r in records]
    assert len(records) == 3
    assert report["skipped"] is True and report["runs_dropped"] == 0


def test_a_damaged_stored_page_reads_as_missing(site, geo_home):
    """A page is stored under the hash of its bytes, so reading it back can check
    them. A damaged or altered copy reads as missing, and a rescore falls back to
    the recorded ratios instead of scoring bytes the audit never read."""
    original = json.loads(_audit(site))
    fetched = [f["body"] for f in _snapshot(site)["fetches"] if f["body"]]
    folder = pages.store_dir(_slug(site))
    (folder / f"{fetched[0]}{pages.SUFFIX}").write_bytes(b"not gzip at all")
    (folder / f"{fetched[1]}{pages.SUFFIX}").write_bytes(gzip.compress(b"<html>altered</html>"))
    assert pages.get(_slug(site), fetched[0]) is None
    assert pages.get(_slug(site), fetched[1]) is None
    again = _rescore(site, original["run_id"])
    assert again["rescore"]["from"] == "ratios"
    assert again["scores"] == original["scores"]


def test_the_page_store_keeps_itself_out_of_version_control(site, geo_home):
    """Pages are other people's content. A GEO_HOME inside a git repository - a
    dotfiles repo is the usual way - must not commit them by accident; the
    records beside them are the user's own and stay visible."""
    _audit(site)
    assert (pages.store_dir(_slug(site)) / ".gitignore").read_text(encoding="utf-8") == "*\n"
    assert not (state.project_dir(_slug(site)) / ".gitignore").exists()


# --- a budget for the page store ----------------------------------------------


def test_the_page_store_keeps_the_newest_runs_whole_within_its_budget(geo_home):
    """Measured on seomator.com: 62 KB a page gzipped. Storing a page once bounds
    growth only for pages that do not change; a site that changes every page on
    every run would add megabytes an audit. So pages get their own budget, and
    the oldest runs lose theirs first - their records stay, and rescore from the
    recorded ratios. A run keeps all its pages or none, so no replay is partial."""
    slug = "budget-test"
    old = pages.put(slug, "".join(f"old page line {i}\n" for i in range(3000)))
    new = pages.put(slug, "".join(f"new page line {i}\n" for i in range(3000)))
    shared = pages.put(slug, "robots.txt shared by both runs\n")
    newest_first = [
        {"snapshot": {"fetches": [{"body": new}], "robots": {"body": shared}}},
        {"snapshot": {"fetches": [{"body": old}], "robots": {"body": shared}}},
    ]

    def size(digest):
        return (pages.store_dir(slug) / f"{digest}{pages.SUFFIX}").stat().st_size

    room_for_one = size(new) + size(shared)
    assert pages.plan_keep(slug, newest_first, room_for_one) == {new, shared}
    assert pages.plan_keep(slug, newest_first, room_for_one + size(old)) == {new, shared, old}
    assert pages.plan_keep(slug, newest_first, room_for_one - 1) == set(), "whole runs or nothing"
