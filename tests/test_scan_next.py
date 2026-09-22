"""The command `geo scan` suggests next is about the site it was given.

`geo scan SEOmator --site https://seomator.com` ended with
`Next: geo scan "SEOmator" --site https://example.com`: the placeholder was
printed whatever site had been named, so copying the suggestion scanned
someone else's domain. With a site named, the next step is the audit that folds
brand presence into that site's score.
"""

from __future__ import annotations

import io

from geo_audit.cli import main
from geo_audit.commands import scan as scan_cmd


class FakeTTY(io.StringIO):
    def isatty(self) -> bool:
        return True


def _nobody_has_heard_of_it(name, brand, spec, allow_private=False):
    return {"platform": name, "label": spec["label"], "checked": True, "status": 200,
            "results": 0, "examples": [], "docs": spec["docs"], "observed_at": "2026-09-22T00:00:00Z"}


def _next_line(args: list[str]) -> str:
    out = FakeTTY()
    main(args + ["--quiet"], out=out)
    return out.getvalue().strip().splitlines()[-1]


def test_a_scan_of_a_named_site_suggests_auditing_that_site(site, geo_home, monkeypatch):
    monkeypatch.setattr(scan_cmd, "check", _nobody_has_heard_of_it)
    line = _next_line(["scan", "Acme", "--site", f"{site.url}/ssr-rich.html", "--allow-private"])
    assert line == f'Next: geo audit {site.url}/ssr-rich.html --brand "Acme"'


def test_a_scan_without_a_site_suggests_naming_one(geo_home, monkeypatch):
    monkeypatch.setattr(scan_cmd, "check", _nobody_has_heard_of_it)
    line = _next_line(["scan", "Acme"])
    assert line.startswith('Next: geo scan "Acme" --site ')
