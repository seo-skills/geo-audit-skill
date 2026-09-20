"""Size, redirect and content-type caps."""

from __future__ import annotations

import pytest

from geo_audit.errors import GeoError
from geo_audit.lib import http
from tests.fixture_server import Reply


def test_declared_content_length_is_refused_before_download(site):
    with pytest.raises(GeoError) as raised:
        http.fetch(f"{site.url}/oversize", allow_private=True, max_bytes=1000)
    assert raised.value.code == "GEO_E_TOO_LARGE"
    assert "declared" in raised.value.message


def test_streaming_body_is_capped_without_a_content_length(site):
    with pytest.raises(GeoError) as raised:
        http.fetch(f"{site.url}/oversize-stream", allow_private=True, max_bytes=5000)
    assert raised.value.code == "GEO_E_TOO_LARGE"
    assert "while downloading" in raised.value.message


def test_redirect_chain_is_followed_and_recorded(site):
    result = http.fetch(f"{site.url}/redirect/3", allow_private=True)
    assert result.status == 200
    assert [hop.status for hop in result.chain] == [302, 302, 302]
    assert result.final_url.endswith("/ssr-rich.html")
    assert result.requested_url.endswith("/redirect/3")


def test_redirect_loop_trips_the_cap(site):
    with pytest.raises(GeoError) as raised:
        http.fetch(f"{site.url}/redirect-loop", allow_private=True, max_redirects=3)
    assert raised.value.code == "GEO_E_TOO_MANY_REDIRECTS"
    assert raised.value.exit_code == 3


def test_redirect_to_a_private_host_is_refused(site, monkeypatch):
    from geo_audit.lib import net

    real = net.check_host
    seen = {"hops": 0}

    def selective(host, port, allow):
        seen["hops"] += 1
        if seen["hops"] == 1:
            return ["203.0.113.10"], None
        return real(host, port, allow)

    monkeypatch.setattr(net, "check_host", selective)
    with pytest.raises(GeoError) as raised:
        http.fetch(f"{site.url}/redirect-private", allow_private=False)
    assert raised.value.code in {"GEO_E_REDIRECT_BLOCKED", "GEO_E_PRIVATE_ADDRESS"}


def test_an_abandoned_redirect_chain_leaves_the_server_usable(site):
    """A failed redirect chain must not take the next request down with it.

    One redirect-loop test used to fail the dozen tests that followed it,
    because the connection it left behind was the one they picked up.
    """
    for _ in range(5):
        with pytest.raises(GeoError):
            http.fetch(f"{site.url}/redirect-loop", allow_private=True, max_redirects=5)
    assert http.fetch(f"{site.url}/ssr-rich.html", allow_private=True).status == 200


def test_a_long_redirect_chain_does_not_disturb_later_requests(site):
    for _ in range(10):
        assert http.fetch(f"{site.url}/redirect/3", allow_private=True).status == 200
    assert http.fetch(f"{site.url}/schema-none.html", allow_private=True).status == 200


def test_non_html_content_type_is_refused(site):
    with pytest.raises(GeoError) as raised:
        http.fetch(f"{site.url}/not-html", allow_private=True)
    assert raised.value.code == "GEO_E_BAD_CONTENT_TYPE"


def test_content_type_allowlist_does_not_apply_to_error_pages(site):
    """A 403 that returns JSON is still a finding, not a fetch failure."""
    result = http.fetch(f"{site.url}/bot-block", allow_private=True)
    assert result.status == 403


def test_an_aborted_download_does_not_corrupt_the_next_request(site):
    """Aborting a download must leave the session usable.

    `Response.close()` releases a streaming connection back to the pool rather
    than closing it, so a body we stopped reading would leave its remaining
    bytes on a pooled socket for the next request to read as its own response.
    Now that connections are kept alive, that pool is actually reused.
    """
    session = http.new_session()
    try:
        for _ in range(3):
            with pytest.raises(GeoError) as raised:
                http.fetch(
                    f"{site.url}/oversize", allow_private=True, max_bytes=2000, session=session
                )
            assert raised.value.code == "GEO_E_TOO_LARGE"

            result = http.fetch(f"{site.url}/ssr-rich.html", allow_private=True, session=session)
            assert result.status == 200
            assert result.body.lstrip().startswith("<!DOCTYPE html>")
            assert "How server-side rendering affects AI crawlers" in result.body
    finally:
        session.close()


def test_a_rejected_content_type_does_not_corrupt_the_next_request(site):
    """The same hazard, reached without reading a single body byte."""
    session = http.new_session()
    try:
        for _ in range(3):
            with pytest.raises(GeoError) as raised:
                http.fetch(f"{site.url}/not-html", allow_private=True, session=session)
            assert raised.value.code == "GEO_E_BAD_CONTENT_TYPE"

            result = http.fetch(f"{site.url}/schema-none.html", allow_private=True, session=session)
            assert result.status == 200
            assert "Deployment checklist" in result.body
    finally:
        session.close()


def test_connections_are_kept_alive_rather_than_closed_per_request():
    """A crawler fetching fifty pages from one host wants one connection.

    Sending `Connection: close` on every request also hid a server bug behind
    a client workaround, which is how the CI failure stayed invisible locally.
    """
    from geo_audit.lib.headers import DEFAULT_HEADERS

    assert "Connection" not in DEFAULT_HEADERS


def test_the_session_retries_a_connection_level_failure_once():
    """The keep-alive race is real against any server with an idle timeout.

    It cannot be reproduced deterministically - whether it fires depends on
    whether the server's FIN has arrived before urllib3 checks the pooled
    socket - so the configuration is asserted directly.
    """
    session = http.new_session()
    try:
        retries = session.get_adapter("https://example.com").max_retries
        assert retries.total == 1
        assert retries.connect == 1
        assert retries.read == 1
        assert not retries.redirect, "redirects are followed by hand, per hop"
        assert "GET" in retries.allowed_methods
    finally:
        session.close()


def test_a_warm_session_opens_no_new_connections(site):
    """The actual fix for the CI failure, measured at the server.

    Sending `Connection: close` on every request meant a fresh handshake per
    page - and, because http.server honours that header without announcing it
    on the wire, a pooled socket the server was about to drop. Keep-alive
    removes both. A crawl of fifty pages should cost one connection, not
    fifty.
    """
    session = http.new_session()
    try:
        http.fetch(f"{site.url}/ssr-rich.html", allow_private=True, session=session)
        site.reset_connection_count()

        result = http.fetch(f"{site.url}/redirect/3", allow_private=True, session=session)
        assert len(result.chain) == 3
        for page in ("schema-none.html", "weak-prose.html", "injection.html"):
            assert http.fetch(f"{site.url}/{page}", allow_private=True, session=session).status == 200

        assert site.connection_count == 0, (
            f"seven requests on a warm session opened "
            f"{site.connection_count} new connections"
        )
    finally:
        session.close()
        site.reset_connection_count()


def test_a_server_that_closes_without_announcing_it_is_still_served(serve):
    """The exact shape that broke CI: close the socket, say nothing.

    urllib3 keeps the socket pooled and only notices if the FIN has already
    arrived. On a loaded Linux runner it often had not, and the next request
    came back as "closed the connection before sending a response".
    """
    routes = {
        "/a": Reply(body="<main><p>first page body here.</p></main>", silent_close=True),
        "/b": Reply(body="<main><p>second page body here.</p></main>", silent_close=True),
    }
    server = serve(routes)
    session = http.new_session()
    try:
        for _ in range(8):
            assert http.fetch(f"{server.url}/a", allow_private=True, session=session).status == 200
            assert http.fetch(f"{server.url}/b", allow_private=True, session=session).status == 200
    finally:
        session.close()


def test_headers_are_filtered_to_the_allowlist(site):
    result = http.fetch(f"{site.url}/ssr-rich.html", allow_private=True)
    assert set(result.headers) <= set(http.KEEP_HEADERS)
    assert "content-type" in result.headers
