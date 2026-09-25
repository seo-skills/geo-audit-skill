"""A platform's API key never reaches a scan's output or an audit's record.

Some fetch errors name the full URL they were fetching, and a keyed platform
(YouTube) carries its key in that URL's query string. Before this was fixed, a
redirect loop at the platform printed the key in `scan.platforms[].reason`.
"""

from __future__ import annotations

import io
import json

from geo_audit.cli import main
from geo_audit.commands import scan
from tests.fixture_server import Reply

KEY = "yt-canary-7Qp2+z/w"


def _looping_youtube(serve, monkeypatch):
    server = serve({"/loop": Reply(status=302, headers={"Location": "/loop?again=1"}, body="")})
    monkeypatch.setattr(scan, "_platforms", lambda: {"youtube": {
        "label": "YouTube", "url": f"{server.url}/loop?q={{query}}&key={{key}}", "docs": "d",
        "needs_key": "GEO_YOUTUBE_API_KEY"}})
    monkeypatch.setenv("GEO_YOUTUBE_API_KEY", KEY)
    return server


def test_a_platform_error_names_no_key(serve, geo_home, monkeypatch):
    _looping_youtube(serve, monkeypatch)
    out = io.StringIO()
    main(["scan", "Acme", "--allow-private", "--json", "--quiet"], out=out)
    reason = json.loads(out.getvalue())["scan"]["platforms"][0]["reason"]
    assert reason.startswith("GEO_E_TOO_MANY_REDIRECTS") and "[key]" in reason
    for form in (KEY, "yt-canary-7Qp2%2Bz%2Fw"):
        assert form not in out.getvalue()


def test_an_audit_records_no_platform_key(serve, site, geo_home, monkeypatch):
    _looping_youtube(serve, monkeypatch)
    main(["audit", f"{site.url}/hub.html", "--allow-private", "--rate", "50", "--max-pages", "3",
          "--brand", "Acme", "--json", "--quiet"], out=io.StringIO())
    record = next(geo_home.rglob("audits.jsonl")).read_text(encoding="utf-8")
    assert "yt-canary" not in record
