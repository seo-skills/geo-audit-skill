"""Extractability asks whether the content is in the HTML a crawler receives.

Round four of the practitioner eval led two reports, Adafruit's and EFF's, with
"Little usable content is present in the HTML the crawler receives" and the
advice to server-render. The pages it named were product and about pages that
are simply short. Rendered in a browser, not one of the five gained a single
character: static and rendered text matched exactly, so the advice was wrong
for every page it named. The cause was a cap for pages under 1,200 characters,
which measured length - content.depth's question - and then answered this one.

Without a browser, the evidence that content needs JavaScript is what the page
says about itself: an app mount with nothing in it, or a notice that JavaScript
is required on a page that serves too little to have its content anyway. A page
with neither has its content in the HTML, however much of it there is.
"""

from __future__ import annotations

import io
import json

from geo_audit.cli import main
from geo_audit.lib.extract import extract
from geo_audit.scoring import citability
from tests.fixture_server import Reply

URL = "https://example.com/page"
SHORT = "<main><h1>Kit</h1><p>" + "A short description of what is in the kit. " * 12 + "</p></main>"
LONG = "<main><h1>Guide</h1><p>" + "Server-rendered prose that a crawler receives in full. " * 40 + "</p></main>"
NOTICE = "<noscript>You need to enable JavaScript to run this app.</noscript>"


def _points(body: str) -> tuple[float, dict]:
    return citability.extractability(extract(f"<html><head><title>t</title></head><body>{body}</body></html>", URL))


def test_a_short_server_rendered_page_has_its_content_in_the_html():
    points, detail = _points(SHORT)
    assert detail["content_chars"] < 1200
    assert detail["js_gated"] is False
    assert points == 15


def test_a_javascript_notice_on_a_page_that_serves_its_content_is_template_boilerplate():
    """App templates carry the notice even when the server rendered everything."""
    points, detail = _points(NOTICE + LONG)
    assert detail["js_required_notice"] is True
    assert detail["js_gated"] is False
    assert points == 15


def test_a_notice_on_a_page_with_almost_nothing_is_what_the_crawler_got():
    points, detail = _points(NOTICE + '<div id="root"><p>Loading.</p></div>')
    assert detail["js_gated"] is True
    assert points <= 3


def test_an_app_mount_that_holds_its_content_is_not_gated():
    points, detail = _points(f'<div id="__next">{LONG}</div>')
    assert detail["empty_framework_root"] is False
    assert detail["js_gated"] is False
    assert points == 15


def test_short_server_rendered_pages_are_not_told_to_server_render(serve, geo_home):
    """The eval's defect end to end: a site of short pages hears about their
    length from content.depth, and nothing about rendering."""
    page = f"<html><head><title>Kit</title></head><body>{SHORT}</body></html>"
    links = "".join(f'<a href="/product/{n}">Kit {n}</a> ' for n in range(3))
    home = f"<html><head><title>Shop</title></head><body><main><h1>Shop</h1>{links}</main></body></html>"
    routes = {"/": Reply(body=home), "/robots.txt": Reply(body="User-agent: *\nAllow: /\n", content_type="text/plain")}
    routes.update({f"/product/{n}": Reply(body=page) for n in range(3)})
    site = serve(routes)

    buffer = io.StringIO()
    main(["audit", f"{site.url}/", "--allow-private", "--rate", "50", "--json", "--quiet"], out=buffer)
    envelope = json.loads(buffer.getvalue())
    ids = [finding["id"] for finding in envelope["findings"]]
    assert "citability.extractability" not in ids
    assert "content.depth" in ids
