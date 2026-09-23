"""`--verbose` does what its help says.

It was declared once in `cli.py` and read nowhere: every command accepted it,
`docs/commands.md` promised "more progress on stderr" for all eleven, and it
changed nothing. Crawling is where there is more to say, so it asks for the
line per page that the single rewritten line replaced.
"""

from __future__ import annotations

import io
import re

from geo_audit.cli import main

CRAWLING = re.compile(r"\[2/4\] Crawling \S+ - (\d+)/\d+ pages, \d+ failed")


def _run(site, capsys, *extra: str) -> list[str]:
    main(["audit", f"{site.url}/hub.html", "--allow-private", "--rate", "50", "--max-pages", "6", "--json", *extra],
         out=io.StringIO())
    return [line for line in capsys.readouterr().err.splitlines() if line.strip()]


def test_verbose_reports_every_page_the_crawl_read(site, geo_home, capsys):
    lines = _run(site, capsys, "--verbose")
    counts = [int(m.group(1)) for m in (CRAWLING.search(line) for line in lines) if m]
    assert len(counts) > 1, "a line per page, not one line for the crawl"
    assert counts == sorted(counts) and counts[0] == 1


def test_without_it_the_crawl_is_one_line(site, geo_home, capsys):
    lines = _run(site, capsys)
    assert len([line for line in lines if CRAWLING.search(line)]) == 1


def test_the_steps_still_run_one_to_four(site, geo_home, capsys):
    for extra in ([], ["--verbose"]):
        lines = _run(site, capsys, *extra)
        steps = [line.split("]", 1)[0] + "]" for line in lines]
        assert steps[0] == "[1/4]" and steps[-1] == "[4/4]"
        assert set(steps) == {"[1/4]", "[2/4]", "[3/4]", "[4/4]"}


def test_quiet_wins_over_verbose(site, geo_home, capsys):
    assert _run(site, capsys, "--verbose", "--quiet") == []
