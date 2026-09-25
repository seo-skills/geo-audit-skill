"""`--rescore` reads audits, and every audit it can find.

1.1.0 started handing `_assemble` the pages each consequence is explained on,
and set it on two of the three branches of `rescore`. The third - a record from
before snapshots existed, which every 0.4 audit still on disk is - raised
UnboundLocalError and came back as GEO_E_INTERNAL, "this is a bug". The same
release's missing-run hint listed `geo score` run ids beside audit ones, and a
score record has no crawl and no snapshot, so it reached that branch too.
"""

from __future__ import annotations

import io
import json

from geo_audit import state
from geo_audit.cli import main

BASE = ["--allow-private", "--rate", "50", "--max-pages", "20"]


def run(args):
    buffer = io.StringIO()
    code = main(args + ["--json", "--quiet"], out=buffer)
    return code, json.loads(buffer.getvalue())


def _only_record(geo_home) -> tuple[str, list[dict]]:
    (path,) = geo_home.glob("projects/*/audits.jsonl")
    slug = path.parent.name
    return slug, state.read_audits(slug)[0]


def test_a_record_from_before_snapshots_is_rescored_from_its_findings(site, geo_home):
    _, envelope = run(["audit", f"{site.url}/hub.html", *BASE])
    slug, records = _only_record(geo_home)
    # What a 0.4 audit looks like on disk: the same record with no snapshot.
    legacy = {key: value for key, value in records[0].items() if key != "snapshot"}
    state.audits_path(slug).write_text(json.dumps(legacy) + "\n", encoding="utf-8")

    code, rescored = run(["audit", f"{site.url}/hub.html", "--allow-private",
                          "--rescore", envelope["run_id"]])
    assert code == 0, rescored["error"]
    assert rescored["rescore"]["from"] == "record"
    assert rescored["scores"]["composite"] == envelope["scores"]["composite"]


def test_a_score_run_is_not_offered_or_rescored_as_an_audit(site, geo_home):
    _, audited = run(["audit", f"{site.url}/hub.html", *BASE])
    _, scored = run(["score", f"{site.url}/hub.html", "--allow-private"])
    _, records = _only_record(geo_home)
    assert {record["command"] for record in records} == {"audit", "score"}

    code, envelope = run(["audit", f"{site.url}/hub.html", "--allow-private",
                          "--rescore", scored["run_id"]])
    assert code == 2
    assert envelope["error"]["code"] == "GEO_E_BAD_ARGS"
    assert audited["run_id"] in envelope["error"]["message"]
    assert scored["run_id"] not in envelope["error"]["message"].split("Recorded here:", 1)[1]
