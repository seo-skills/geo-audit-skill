"""The gain printed beside a fix is on the scale of the score printed above it.

`geo audit` printed "GEO score 91/100" and then each fix's `points_lost` as
"+9 points available". Those are points on one category's 0-100 scale, so the
five fixes shown for seomator.com claimed 26.7 points on a site that could gain
nine; the HTML report said "up to +1.8 overall" for the same fix. The audit's
text output now prints the overall gain, and a page score, which carries no
overall gain per fix, names the category its points belong to.
"""

from __future__ import annotations

import io
import json
import re

from geo_audit import render
from geo_audit.cli import main


class FakeTTY(io.StringIO):
    def isatty(self) -> bool:
        return True


def _audit(site) -> dict:
    buffer = io.StringIO()
    main(["audit", f"{site.url}/hub.html", "--allow-private", "--rate", "50", "--max-pages", "6", "--json", "--quiet"],
         out=buffer)
    return json.loads(buffer.getvalue())


def test_an_audit_prints_each_fix_on_the_overall_scale(site, geo_home):
    envelope = _audit(site)
    shown = [f for f in envelope["findings"][:3] if f.get("impact")]
    assert shown, "the fixture site has scored findings to show"
    out = FakeTTY()
    render.render(envelope, out)
    text = out.getvalue()
    for finding in shown:
        assert f"up to +{finding['impact']:g} overall" in text
    assert "points available" not in text
    gains = [float(g) for g in re.findall(r"up to \+([\d.]+) overall", text)]
    assert sum(gains) <= 100 - envelope["scores"]["composite"] + 0.5


def test_a_page_score_names_the_category_its_points_belong_to(site, geo_home):
    out = FakeTTY()
    main(["score", f"{site.url}/weak-prose.html", "--allow-private", "--no-render", "--quiet"], out=out)
    assert re.search(r"\+[\d.]+ (citability|content|schema|technical|platform) points available", out.getvalue())
