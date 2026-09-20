"""Address classification: the SSRF guard.

Two checks, not one. The name is validated before we connect, and the address
we actually connected to is validated after. Only the second survives DNS
rebinding, where a hostname resolves publicly on the first lookup and to
127.0.0.1 on the second.
"""

from __future__ import annotations

import ipaddress
import socket

ALLOWED_SCHEMES = frozenset({"http", "https"})


def classify(address: str) -> str | None:
    """Return a reason string if the address must not be fetched, else None."""
    try:
        ip = ipaddress.ip_address(address)
    except ValueError:
        return "unparseable_address"

    # An IPv4-mapped IPv6 address (::ffff:127.0.0.1) is the classic bypass.
    if isinstance(ip, ipaddress.IPv6Address) and ip.ipv4_mapped is not None:
        ip = ip.ipv4_mapped

    if ip.is_unspecified:
        return "unspecified_address"
    if ip.is_loopback:
        return "loopback_address"
    if ip.is_link_local:
        # Covers 169.254.169.254, the cloud metadata endpoint.
        return "link_local_address"
    if ip.is_multicast:
        return "multicast_address"
    if ip.is_private:
        return "private_address"
    if ip.is_reserved:
        return "reserved_address"
    return None


def is_public(address: str) -> bool:
    return classify(address) is None


def resolve(host: str, port: int) -> list[str]:
    """Every address `host` resolves to, deduplicated, in resolver order."""
    infos = socket.getaddrinfo(host, port, type=socket.SOCK_STREAM)
    seen: list[str] = []
    for info in infos:
        addr = info[4][0]
        if addr not in seen:
            seen.append(addr)
    return seen


def check_host(host: str, port: int, allow_private: bool) -> tuple[list[str], str | None]:
    """Resolve and classify.

    Returns (addresses, reason). `reason` is set when at least one resolved
    address is non-public: a host that resolves to a mix of public and private
    addresses is rejected as a whole, because which one we get is the
    resolver's choice, not ours.
    """
    addresses = resolve(host, port)
    if allow_private:
        return addresses, None
    for addr in addresses:
        reason = classify(addr)
        if reason is not None:
            return addresses, reason
    return addresses, None
