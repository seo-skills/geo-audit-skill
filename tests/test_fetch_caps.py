"""Size, redirect and content-type caps."""

from __future__ import annotations

import pytest

from geo_audit.errors import GeoError
from geo_audit.lib import http


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


def test_non_html_content_type_is_refused(site):
    with pytest.raises(GeoError) as raised:
        http.fetch(f"{site.url}/not-html", allow_private=True)
    assert raised.value.code == "GEO_E_BAD_CONTENT_TYPE"


def test_content_type_allowlist_does_not_apply_to_error_pages(site):
    """A 403 that returns JSON is still a finding, not a fetch failure."""
    result = http.fetch(f"{site.url}/bot-block", allow_private=True)
    assert result.status == 403


def test_headers_are_filtered_to_the_allowlist(site):
    result = http.fetch(f"{site.url}/ssr-rich.html", allow_private=True)
    assert set(result.headers) <= set(http.KEEP_HEADERS)
    assert "content-type" in result.headers
