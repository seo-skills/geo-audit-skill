"""A capped crawl says so where the score is shown.

seomator.com's sitemap lists 309 URLs. The audit stopped at its 50-page limit,
and neither the terminal output nor the client report said so: both presented
the number for 50 pages as the site's. The skill reading the JSON noticed; a
client reading the report could not have.
"""

from __future__ import annotations

import io
import json
from pathlib import Path

from geo_audit import render
from geo_audit.cli import main
from geo_audit.lib.crawl import urls_found


class FakeTTY(io.StringIO):
    def isatty(self) -> bool:
        return True


def _audit(site, max_pages: int) -> dict:
    buffer = io.StringIO()
    main(["audit", f"{site.url}/hub.html", "--allow-private", "--rate", "50", "--max-pages", str(max_pages),
          "--json", "--quiet"], out=buffer)
    return json.loads(buffer.getvalue())


def _text(envelope: dict) -> str:
    out = FakeTTY()
    render.render(envelope, out)
    return out.getvalue()


def _client_report(site) -> str:
    buffer = io.StringIO()
    main(["report", f"{site.url}/hub.html", "--json", "--quiet"], out=buffer)
    return Path(json.loads(buffer.getvalue())["report"]["path"]).read_text(encoding="utf-8")


def test_a_capped_audit_says_how_much_of_the_site_it_read(site, geo_home):
    envelope = _audit(site, 2)
    crawl = envelope["crawl"]
    assert crawl["stopped_because"] == "max_pages"
    assert urls_found(crawl) > crawl["pages_crawled"]
    note = (f"The crawl stopped at its 2-page limit after finding {urls_found(crawl)} URLs, "
            f"so the score covers {envelope['evidence']['pages_ok']} of them.")

    text = _text(envelope)
    assert note in text
    assert "Raise the limit with --max-pages." in text

    html = _client_report(site)
    assert note in html
    assert "--max-pages" not in html, "a client does not run the CLI"


def test_a_crawl_that_read_everything_it_found_says_nothing_about_a_limit(site, geo_home):
    envelope = _audit(site, 50)
    assert envelope["crawl"]["stopped_because"] != "max_pages"
    assert "page limit" not in _text(envelope)
    assert "page limit" not in _client_report(site)
