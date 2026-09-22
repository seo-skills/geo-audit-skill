"""An audit's progress is a few lines, numbered consistently.

`geo audit https://seomator.com` wrote `[1/1] audit ...` and then fifty
`[2/4] Crawling seomator.com - N/50 pages` lines - on a terminal, in a log, and
in the output the audit skill reads back into its context - and never a step 3
or 4. The count now rewrites one line on a terminal, is written once anywhere
else, and the steps run 1 to 4.
"""

from __future__ import annotations

import io
import re
import sys

from geo_audit.cli import main

CRAWLING = re.compile(r"Crawling \S+ - (\d+)/(\d+) pages, (\d+) failed")


class FakeTTY(io.StringIO):
    def isatty(self) -> bool:
        return True


def _audit(site) -> None:
    main(["audit", f"{site.url}/hub.html", "--allow-private", "--rate", "50", "--max-pages", "6", "--json"],
         out=io.StringIO())


def _step_labels(lines: list[str]) -> list[str]:
    return [line.split("]", 1)[0] + "]" for line in lines]


def test_an_audit_writes_one_line_per_step_where_no_one_is_watching(site, geo_home, capsys):
    _audit(site)
    lines = capsys.readouterr().err.splitlines()
    assert _step_labels(lines) == ["[1/4]", "[2/4]", "[3/4]", "[4/4]"]
    assert CRAWLING.search(lines[1])


def test_a_terminal_sees_the_count_rewrite_one_line(site, geo_home, monkeypatch):
    stderr = FakeTTY()
    monkeypatch.setattr(sys, "stderr", stderr)
    _audit(site)
    lines = stderr.getvalue().split("\n")[:-1]
    assert _step_labels([line.lstrip("\r") for line in lines]) == ["[1/4]", "[2/4]", "[3/4]", "[4/4]"]
    updates = lines[1].split("\r")[1:]
    assert len(updates) > 2, "the count was written in place, page by page"
    done = [int(CRAWLING.search(update).group(1)) for update in updates]
    assert done == sorted(done), "a count that only grows needs no clearing"


def test_a_crawl_numbers_its_own_two_steps(site, geo_home, capsys):
    main(["crawl", f"{site.url}/hub.html", "--allow-private", "--rate", "50", "--max-pages", "4", "--json"],
         out=io.StringIO())
    assert _step_labels(capsys.readouterr().err.splitlines()) == ["[1/2]", "[2/2]"]
