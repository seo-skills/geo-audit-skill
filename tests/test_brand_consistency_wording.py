"""The brand.consistency finding says what is missing, not what the site already did.

Its wording in data/findings.json is written for a site whose Organization sameAs
lists no profiles. popupsmart.com lists sixteen and scored half, and was told to
"add the profiles found here to sameAs".
"""

from __future__ import annotations

from geo_audit import copy as copytext
from geo_audit.commands.scan import brand_findings, build_signals

CHECKED = {"checked": True, "results": 3}


def _consistency(same_as):
    signals = build_signals({"wikipedia": CHECKED, "wikidata": CHECKED, "reddit": CHECKED}, same_as)
    return next(f for f in brand_findings(signals, "https://acme.example") if f.id == "brand.consistency")


def test_a_site_that_lists_profiles_is_told_what_is_missing():
    finding = _consistency(["https://www.linkedin.com/company/acme", "https://www.g2.com/products/acme"])
    assert finding.title == copytext.BRAND_CONSISTENCY_LINKED_TITLE
    assert "already lists 2 profiles" in finding.remediation
    assert "Wikipedia" in finding.remediation


def test_a_site_with_no_profiles_keeps_the_original_advice():
    finding = _consistency([])
    assert finding.title == "The site does not link itself to the profiles that identify it"


def test_a_rescored_brand_audit_keeps_the_wording(serve, site, geo_home, monkeypatch):
    import io
    import json

    from geo_audit.cli import main
    from geo_audit.commands import scan

    monkeypatch.setattr(scan, "_same_as_for", lambda *args: ["https://www.linkedin.com/company/acme"])
    monkeypatch.setattr(scan, "_platforms", lambda: {})
    out = io.StringIO()
    base = ["audit", f"{site.url}/hub.html", "--allow-private", "--rate", "50", "--max-pages", "3"]
    main(base + ["--brand", "Acme", "--json", "--quiet"], out=out)
    audited = json.loads(out.getvalue())
    run_id = audited["run_id"]
    assert {f["id"]: f["title"] for f in audited["findings"]}["brand.consistency"] == (
        copytext.BRAND_CONSISTENCY_LINKED_TITLE
    )
    out = io.StringIO()
    main(base + ["--rescore", run_id, "--json", "--quiet"], out=out)
    titles = {f["id"]: f["title"] for f in json.loads(out.getvalue())["findings"]}
    assert titles["brand.consistency"] == copytext.BRAND_CONSISTENCY_LINKED_TITLE
