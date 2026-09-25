"""A site that was never reached has no score.

`errors.py` gives exit 3 to a network failure on the start URL, and `geo fetch`
and `geo score` honoured it. `geo audit` did not: the crawl filed the start
URL's error as one failed page among none, and the audit went on to score the
empty set - `ok: true`, 0/100 "poor", appended to history. The skill reads that
as a measurement, and the next `geo compare` reported the site losing every
point it had.
"""

from __future__ import annotations

import io
import json
import socket

from geo_audit.cli import main
from geo_audit.errors import ERRORS, EXIT_NETWORK


def run(args):
    buffer = io.StringIO()
    code = main(args + ["--json", "--quiet"], out=buffer)
    return code, json.loads(buffer.getvalue())


def closed_port() -> int:
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


def test_an_audit_whose_start_url_refuses_the_connection_is_a_network_error(geo_home):
    code, envelope = run(["audit", f"http://127.0.0.1:{closed_port()}/", "--allow-private",
                          "--rate", "50", "--timeout", "5"])
    assert code == EXIT_NETWORK
    assert envelope["ok"] is False
    assert envelope["error"]["code"] == "GEO_E_CONNECT"
    assert envelope["scores"] is None


def test_an_audit_refused_before_any_request_says_so(site, geo_home):
    # The fixture server is on loopback, so without --allow-private no request
    # is ever sent: the same refusal `geo fetch` reports for this URL.
    code, envelope = run(["audit", f"{site.url}/hub.html", "--rate", "50"])
    assert envelope["ok"] is False
    assert envelope["error"]["code"] == "GEO_E_PRIVATE_ADDRESS"
    assert code == ERRORS["GEO_E_PRIVATE_ADDRESS"].exit_code
    assert envelope["scores"] is None


def test_an_unreached_site_leaves_no_run_to_compare_against(site, geo_home):
    run(["audit", f"{site.url}/hub.html", "--rate", "50"])
    run(["audit", f"http://127.0.0.1:{closed_port()}/", "--allow-private", "--rate", "50", "--timeout", "5"])
    assert not list(geo_home.glob("projects/*/audits.jsonl"))


def test_a_crawl_that_reached_nothing_says_why(geo_home):
    code, envelope = run(["crawl", f"http://127.0.0.1:{closed_port()}/", "--allow-private",
                          "--rate", "50", "--timeout", "5"])
    assert code == EXIT_NETWORK
    assert envelope["error"]["code"] == "GEO_E_CONNECT"


def test_an_http_error_on_the_start_url_is_still_a_report(site, geo_home):
    """The other half of the contract: a response is not a network failure. A
    404 or a 403 challenge on the start URL is what the report is for."""
    code, envelope = run(["audit", f"{site.url}/no-such-page", "--allow-private", "--rate", "50",
                          "--max-pages", "3"])
    assert code == 0
    assert envelope["ok"] is True
    assert envelope["evidence"]["stamp"] == "PARTIAL"
