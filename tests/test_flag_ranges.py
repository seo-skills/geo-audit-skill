"""A number no run could honour is a usage error, not a crash.

`geo fetch <url> --timeout 0` reached the HTTP layer, raised ValueError, and
came back as GEO_E_INTERNAL: exit 1, "This is a bug in seomator-geo-audit ...
please open an issue", for a typo. `--max-bytes -1` was reported as the page
being too large. A negative rate, a negative page count and `--concurrency 0`
were taken as given and quietly changed what the crawl did.
"""

from __future__ import annotations

import io
import json

import pytest

from geo_audit.cli import main
from geo_audit.errors import EXIT_USAGE


def _run(argv: list[str]) -> tuple[int, dict]:
    buffer = io.StringIO()
    code = main([*argv, "--json", "--quiet"], out=buffer)
    return code, json.loads(buffer.getvalue())


@pytest.mark.parametrize("command, flag, value", [
    ("fetch", "--timeout", "0"),
    ("fetch", "--timeout", "-5"),
    ("fetch", "--max-bytes", "0"),
    ("fetch", "--max-bytes", "-1"),
    ("audit", "--max-pages", "0"),
    ("audit", "--max-pages", "-3"),
    ("audit", "--rate", "-2"),
    ("crawl", "--concurrency", "0"),
    ("crawl", "--concurrency", "-1"),
])
def test_a_number_outside_the_range_is_a_usage_error(command, flag, value):
    code, envelope = _run([command, "https://example.com", flag, value])
    assert code == EXIT_USAGE
    assert envelope["ok"] is False
    assert envelope["error"]["code"] == "GEO_E_BAD_ARGS"
    assert flag in envelope["error"]["message"], "the message names the flag that carried it"
    assert "bug in" not in envelope["error"]["hint"], "a typo is not an invitation to file a bug"


def test_a_rate_of_zero_still_removes_the_limit(site, geo_home):
    """Documented behaviour the range has to keep allowing: the fixture suite
    crawls at zero to run without waiting."""
    buffer = io.StringIO()
    code = main(["crawl", f"{site.url}/hub.html", "--allow-private", "--rate", "0", "--max-pages", "3",
                 "--json", "--quiet"], out=buffer)
    assert code == 0
    assert json.loads(buffer.getvalue())["crawl"]["limits"]["requests_per_second"] == 0


def test_the_values_a_run_can_honour_are_left_alone(site, geo_home):
    buffer = io.StringIO()
    code = main(["crawl", f"{site.url}/hub.html", "--allow-private", "--rate", "50", "--max-pages", "1",
                 "--concurrency", "1", "--timeout", "0.5", "--max-bytes", "5000000",
                 "--json", "--quiet"], out=buffer)
    assert code == 0
    assert json.loads(buffer.getvalue())["crawl"]["pages_crawled"] == 1
