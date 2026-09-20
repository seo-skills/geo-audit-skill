"""The SSRF matrix.

The guard exists twice on purpose: once before we connect, against the name,
and once after, against the address we actually reached. Only the second
survives DNS rebinding, so both are tested.
"""

from __future__ import annotations

import pytest

from geo_audit.errors import GeoError
from geo_audit.lib import http, net

BLOCKED = [
    ("127.0.0.1", "loopback_address"),
    ("127.53.0.1", "loopback_address"),
    ("::1", "loopback_address"),
    ("0.0.0.0", "unspecified_address"),
    ("10.0.0.5", "private_address"),
    ("172.16.31.9", "private_address"),
    ("192.168.1.1", "private_address"),
    ("169.254.169.254", "link_local_address"),
    ("fe80::1", "link_local_address"),
    ("fd00::1", "private_address"),
    ("224.0.0.1", "multicast_address"),
    ("::ffff:127.0.0.1", "loopback_address"),
    ("::ffff:10.1.2.3", "private_address"),
    ("not-an-address", "unparseable_address"),
]

ALLOWED = ["93.184.216.34", "8.8.8.8", "2606:2800:220:1:248:1893:25c8:1946"]


@pytest.mark.parametrize("address,reason", BLOCKED)
def test_blocked_addresses(address, reason):
    assert net.classify(address) == reason
    assert not net.is_public(address)


@pytest.mark.parametrize("address", ALLOWED)
def test_public_addresses(address):
    assert net.classify(address) is None
    assert net.is_public(address)


def test_ipv4_mapped_ipv6_does_not_bypass():
    assert net.classify("::ffff:169.254.169.254") == "link_local_address"


def test_private_start_url_is_refused_by_default(site):
    with pytest.raises(GeoError) as raised:
        http.fetch(f"{site.url}/ssr-rich.html", allow_private=False)
    assert raised.value.code == "GEO_E_PRIVATE_ADDRESS"
    assert raised.value.exit_code == 2


def test_allow_private_opts_in(site):
    result = http.fetch(f"{site.url}/ssr-rich.html", allow_private=True)
    assert result.status == 200


def test_non_http_scheme_is_refused():
    for url in ("file:///etc/passwd", "ftp://example.com/x", "gopher://example.com"):
        with pytest.raises(GeoError) as raised:
            http.fetch(url)
        assert raised.value.code == "GEO_E_BLOCKED_SCHEME"


def test_redirect_hop_to_a_private_address_is_blocked_not_refused():
    """A later hop reports GEO_E_REDIRECT_BLOCKED, not the start-URL code.

    The distinction matters to the user: one means "you asked for something
    private", the other means "the site pointed us somewhere private".
    """
    with pytest.raises(GeoError) as raised:
        http._validate_target("http://127.0.0.1/x", allow_private=False, first_hop=False)
    assert raised.value.code == "GEO_E_REDIRECT_BLOCKED"
    assert raised.value.exit_code == 3


def test_dns_rebinding_is_caught_by_the_peer_check(site, monkeypatch):
    """Pre-flight resolution says public; the socket lands on loopback.

    Patching `check_host` simulates a name that resolved to a public address a
    moment ago. Nothing else is patched, so the request really is made and the
    only thing that can stop it is validating the connected peer.
    """
    monkeypatch.setattr(net, "check_host", lambda host, port, allow: (["203.0.113.10"], None))
    with pytest.raises(GeoError) as raised:
        http.fetch(f"{site.url}/ssr-rich.html", allow_private=False)
    assert raised.value.code == "GEO_E_PRIVATE_ADDRESS"
    assert "127.0.0.1" in raised.value.message


def test_peer_address_is_actually_observed(site):
    result = http.fetch(f"{site.url}/ssr-rich.html", allow_private=True)
    assert result.peer_verified is True
    assert result.peer_address == "127.0.0.1"
