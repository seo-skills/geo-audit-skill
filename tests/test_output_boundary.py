"""The output boundary: the main defence against prompt injection.

CLI output is read by an agent with tool access, so it carries derived signals
and length-capped, delimiter-escaped excerpts, and never page text.
"""

from __future__ import annotations

import io
import json
from pathlib import Path

import pytest

from geo_audit.cli import main

FIXTURES = Path(__file__).parent / "fixtures" / "site"
EXCERPT_CAP = 280


def run(args) -> tuple[str, dict]:
    buffer = io.StringIO()
    main(args + ["--json", "--quiet"], out=buffer)
    raw = buffer.getvalue()
    return raw, json.loads(raw)


def page_windows(name: str, width: int) -> list[str]:
    """Sliding windows of the fixture's visible text, `width` characters wide.

    Excerpts are allowed to quote the page: that is what they are for, and they
    are capped at EXCERPT_CAP. The rule being tested is that no *unbounded* run
    of page text survives, so the window is wider than the cap.
    """
    import re

    text = (FIXTURES / name).read_text(encoding="utf-8")
    body = re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", text)).strip()
    return [body[i : i + width] for i in range(0, max(len(body) - width, 0), 25)]


@pytest.mark.parametrize("page", ["ssr-rich.html", "weak-prose.html", "injection.html"])
def test_no_run_of_page_text_longer_than_the_excerpt_cap_reaches_the_output(
    site, geo_home, page
):
    raw, _ = run(["score", f"{site.url}/{page}", "--allow-private", "--no-render"])
    for window in page_windows(page, EXCERPT_CAP + 40):
        assert window not in raw, f"page text leaked past the cap: {window[:60]}"


@pytest.mark.parametrize("page", ["ssr-rich.html", "weak-prose.html", "injection.html"])
def test_page_derived_strings_are_individually_capped(site, geo_home, page):
    """Every string anywhere in the envelope respects the excerpt cap."""
    _, envelope = run(["score", f"{site.url}/{page}", "--allow-private", "--no-render"])
    remediation = {
        template["remediation"]
        for kind in ("signals", "checks")
        for template in __import__(
            "geo_audit.data", fromlist=["load"]
        ).load("findings")[kind].values()
    }

    def walk(node, path="$"):
        if isinstance(node, dict):
            for key, value in node.items():
                walk(value, f"{path}.{key}")
        elif isinstance(node, list):
            for index, value in enumerate(node):
                walk(value, f"{path}[{index}]")
        elif isinstance(node, str) and node not in remediation:
            assert len(node) <= EXCERPT_CAP, f"{path} is {len(node)} characters"

    walk(envelope)


@pytest.mark.parametrize("command", ["fetch", "score"])
def test_output_stays_far_below_a_page_of_text(site, geo_home, command):
    raw, _ = run([command, f"{site.url}/ssr-rich.html", "--allow-private"])
    source = (FIXTURES / "ssr-rich.html").stat().st_size
    assert len(raw) < 60_000
    assert len(raw) < source * 12, "output should be derived, not a copy of the page"


def test_every_excerpt_is_capped_and_escaped(site, geo_home):
    _, envelope = run(["score", f"{site.url}/weak-prose.html", "--allow-private", "--no-render"])
    excerpts = [f["excerpt"] for f in envelope["findings"] if f.get("excerpt")]
    assert excerpts, "this fixture is expected to produce at least one excerpt"
    for excerpt in excerpts:
        assert len(excerpt) <= EXCERPT_CAP
        assert "`" not in excerpt
        assert "<" not in excerpt and ">" not in excerpt


def test_signal_details_carry_counts_not_prose(site, geo_home):
    _, envelope = run(["score", f"{site.url}/ssr-rich.html", "--allow-private", "--no-render"])
    for signal in envelope["signals"]:
        for key, value in signal["detail"].items():
            if isinstance(value, str) and key not in ("reason", "content_root"):
                assert len(value) <= EXCERPT_CAP, f"{signal['id']}.{key} is unbounded"


def test_fetch_never_returns_a_body_field(site, geo_home):
    _, envelope = run(["fetch", f"{site.url}/ssr-rich.html", "--allow-private"])
    assert "body" not in envelope["page"]
    assert "html" not in envelope["page"]
    assert "text" not in envelope["page"]
