"""The single HTTP entry point.

Everything that touches the network goes through `fetch`. Redirects are
followed by hand rather than by requests, because every hop has to be
re-validated: a public URL that 302s to 169.254.169.254 is the whole point of
the guard.

Caps, all enforced here so no caller can forget one:

* redirect chain length
* declared Content-Length, before a byte is read
* decoded body size, while reading (this is the decompression limit: a 10 KB
  gzip bomb that inflates to 2 GB trips it at the cap, not at 2 GB)
* content type, on 2xx only
"""

from __future__ import annotations

import re
import socket
import time
from dataclasses import dataclass, field
from urllib.parse import urljoin, urlsplit

import requests

from geo_audit.errors import GeoError
from geo_audit.lib import net
from geo_audit.lib.headers import headers as build_headers

DEFAULT_TIMEOUT = 30.0
DEFAULT_MAX_BYTES = 5_000_000
DEFAULT_MAX_REDIRECTS = 5

HTML_TYPES = ("text/html", "application/xhtml+xml")

_META_CHARSET = re.compile(rb'charset=["\']?([a-zA-Z0-9_\-]+)', re.IGNORECASE)
_REDIRECT_STATUSES = frozenset({301, 302, 303, 307, 308})

# Response headers worth recording. The rest are dropped: an envelope is not a
# HAR file, and some headers carry session identifiers.
KEEP_HEADERS = (
    "content-type",
    "content-length",
    "content-encoding",
    "etag",
    "last-modified",
    "cache-control",
    "x-robots-tag",
    "server",
    "location",
    "vary",
)


@dataclass(frozen=True)
class Hop:
    url: str
    status: int
    location: str | None


@dataclass
class FetchResult:
    requested_url: str
    final_url: str
    status: int
    headers: dict[str, str]
    body: str
    body_bytes: int
    encoding: str
    elapsed_ms: int
    peer_address: str | None
    peer_verified: bool
    chain: list[Hop] = field(default_factory=list)

    @property
    def content_type(self) -> str | None:
        raw = self.headers.get("content-type")
        return raw.split(";")[0].strip().lower() if raw else None

    @property
    def ok(self) -> bool:
        return 200 <= self.status < 300


def new_session() -> requests.Session:
    session = requests.Session()
    session.trust_env = True
    # `session.max_redirects` is deliberately left at the library default.
    # Every request here sets allow_redirects=False, but requests still peeks
    # one hop ahead to populate `response._next`, and that peek raises
    # TooManyRedirects if the session limit is 0. Our own cap is the one that
    # governs; see the loop in `fetch`.
    return session


def _peer_address(response: requests.Response) -> str | None:
    """The address we actually connected to, or None if urllib3 hid it.

    Reaching into private attributes is deliberate. The alternative is
    trusting a name we resolved a moment ago, which is exactly the assumption
    DNS rebinding breaks.
    """
    raw = getattr(response, "raw", None)
    candidates = [getattr(raw, "_connection", None), getattr(raw, "connection", None)]
    fp = getattr(raw, "_fp", None)
    candidates.append(getattr(getattr(fp, "fp", None), "raw", None))
    for candidate in candidates:
        sock = getattr(candidate, "sock", None) or getattr(candidate, "_sock", None)
        if sock is None:
            continue
        try:
            peer = sock.getpeername()
        except OSError:
            continue
        if isinstance(peer, tuple) and peer:
            return str(peer[0]).split("%")[0]
    return None


def _connection_reason(exc: Exception) -> str:
    """Classify a ConnectionError into something a reader can act on.

    A refused connection, a reset, and a server that hung up before
    responding have three different causes and three different fixes.
    """
    cause = exc.__cause__ or exc.__context__
    text = f"{type(cause).__name__} {cause}" if cause else str(exc)
    lowered = text.lower()
    if "refused" in lowered:
        return "the connection was refused"
    if "reset by peer" in lowered or "connectionreset" in lowered:
        return "the server reset the connection"
    if "remotedisconnected" in lowered or "without a response" in lowered:
        return "the server closed the connection before sending a response"
    if "connection aborted" in lowered:
        return "the connection was aborted mid-request"
    if "broken pipe" in lowered:
        return "the connection broke while the request was being sent"
    if "timed out" in lowered:
        return "the connection timed out"
    if "too many open" in lowered or "cannot assign" in lowered:
        return "this machine ran out of sockets"
    return "the connection failed"


def _hard_close(response: requests.Response) -> None:
    """Close the socket so a half-read response cannot be pooled.

    `Response.close()` *releases* a streaming connection back to the pool. If
    the body was not fully read, the next request on that pool picks up the
    previous response's leftover bytes. Aborting a download is exactly when
    that happens, so those connections are closed rather than released.
    """
    raw = getattr(response, "raw", None)
    for target in (getattr(raw, "_connection", None), raw):
        try:
            if target is not None:
                target.close()
        except Exception:  # noqa: BLE001 - teardown must not mask the real error
            pass


def _drain(response: requests.Response, limit: int) -> None:
    """Read and discard a body so the connection closes with FIN, not RST.

    Redirect bodies are normally a few bytes, and abandoning them mid-response
    resets the socket. The limit is still honoured: an abusive server that
    attaches a huge body to a 302 gets reset, which is the correct outcome.
    """
    read = 0
    try:
        for chunk in response.iter_content(chunk_size=8192):
            read += len(chunk)
            if read > limit:
                return
    except requests.RequestException:
        return


def _decode(raw: bytes, content_type: str | None) -> tuple[str, str]:
    encoding = None
    if content_type and "charset=" in content_type.lower():
        encoding = content_type.lower().split("charset=", 1)[1].split(";")[0].strip()
    if not encoding:
        match = _META_CHARSET.search(raw[:4096])
        if match:
            encoding = match.group(1).decode("ascii", "ignore")
    if not encoding:
        encoding = "utf-8"
    try:
        return raw.decode(encoding, errors="replace"), encoding
    except LookupError:
        return raw.decode("utf-8", errors="replace"), "utf-8"


def _validate_target(url: str, allow_private: bool, first_hop: bool) -> None:
    parts = urlsplit(url)
    scheme = (parts.scheme or "").lower()
    if scheme not in net.ALLOWED_SCHEMES:
        raise GeoError(
            "GEO_E_BLOCKED_SCHEME",
            f"Refused to fetch {url!r}: only http and https are supported.",
        )
    host = parts.hostname
    if not host:
        raise GeoError("GEO_E_BAD_URL", f"{url!r} has no hostname.")
    port = parts.port or (443 if scheme == "https" else 80)

    try:
        _, reason = net.check_host(host, port, allow_private)
    except socket.gaierror:
        raise GeoError("GEO_E_DNS", f"Couldn't resolve {host}.") from None
    if reason is None:
        return
    if first_hop:
        raise GeoError(
            "GEO_E_PRIVATE_ADDRESS",
            f"{host} resolves to a {reason.replace('_', ' ')}, which is not "
            f"fetched by default.",
        )
    raise GeoError(
        "GEO_E_REDIRECT_BLOCKED",
        f"A redirect pointed at {host}, a {reason.replace('_', ' ')}. "
        f"The chain was not followed.",
    )


def _verify_peer(response: requests.Response, url: str, allow_private: bool) -> tuple[str | None, bool]:
    peer = _peer_address(response)
    if peer is None:
        return None, False
    if allow_private:
        return peer, True
    reason = net.classify(peer)
    if reason is not None:
        raise GeoError(
            "GEO_E_PRIVATE_ADDRESS",
            f"{urlsplit(url).hostname} connected to {peer}, a "
            f"{reason.replace('_', ' ')}. The response was discarded.",
        )
    return peer, True


def fetch(
    url: str,
    *,
    allow_private: bool = False,
    timeout: float = DEFAULT_TIMEOUT,
    max_bytes: int = DEFAULT_MAX_BYTES,
    max_redirects: int = DEFAULT_MAX_REDIRECTS,
    accept_types: tuple[str, ...] | None = HTML_TYPES,
    extra_headers: dict[str, str] | None = None,
    session: requests.Session | None = None,
) -> FetchResult:
    owned = session is None
    session = session or new_session()
    started = time.monotonic()
    chain: list[Hop] = []
    current = url

    try:
        for _ in range(max_redirects + 1):
            _validate_target(current, allow_private, first_hop=not chain)
            try:
                response = session.get(
                    current,
                    headers=build_headers(extra_headers),
                    timeout=timeout,
                    allow_redirects=False,
                    stream=True,
                )
            except requests.exceptions.SSLError as exc:
                raise GeoError(
                    "GEO_E_TLS", f"TLS handshake with {urlsplit(current).hostname} failed."
                ) from exc
            except requests.exceptions.Timeout as exc:
                raise GeoError(
                    "GEO_E_TIMEOUT",
                    f"Couldn't reach {urlsplit(current).hostname}: connection timed out "
                    f"after {timeout:g} s.",
                ) from exc
            except requests.exceptions.ConnectionError as exc:
                if isinstance(exc.__cause__, socket.gaierror) or "NameResolution" in repr(exc):
                    raise GeoError(
                        "GEO_E_DNS", f"Couldn't resolve {urlsplit(current).hostname}."
                    ) from exc
                raise GeoError(
                    "GEO_E_CONNECT",
                    f"Couldn't connect to {urlsplit(current).hostname}: "
                    f"{_connection_reason(exc)}.",
                ) from exc

            drained = False
            try:
                peer, verified = _verify_peer(response, current, allow_private)
                status = response.status_code
                location = response.headers.get("location")

                if status in _REDIRECT_STATUSES and location:
                    _drain(response, max_bytes)
                    drained = True
                    chain.append(Hop(url=current, status=status, location=location))
                    current = urljoin(current, location)
                    continue

                kept = {
                    k.lower(): v
                    for k, v in response.headers.items()
                    if k.lower() in KEEP_HEADERS
                }
                declared = kept.get("content-length")
                if declared and declared.isdigit() and int(declared) > max_bytes:
                    raise GeoError(
                        "GEO_E_TOO_LARGE",
                        f"{current} declared {int(declared):,} bytes, over the "
                        f"{max_bytes:,} byte cap.",
                    )

                content_type = (kept.get("content-type") or "").split(";")[0].strip().lower()
                if 200 <= status < 300 and accept_types and content_type:
                    if content_type not in accept_types:
                        raise GeoError(
                            "GEO_E_BAD_CONTENT_TYPE",
                            f"{current} returned {content_type}, which is not scored.",
                        )

                buffer = bytearray()
                for chunk in response.iter_content(chunk_size=65536):
                    if not chunk:
                        continue
                    buffer.extend(chunk)
                    if len(buffer) > max_bytes:
                        raise GeoError(
                            "GEO_E_TOO_LARGE",
                            f"{current} exceeded the {max_bytes:,} byte cap while "
                            f"downloading.",
                        )

                drained = True
                body, encoding = _decode(bytes(buffer), kept.get("content-type"))
                return FetchResult(
                    requested_url=url,
                    final_url=current,
                    status=status,
                    headers=kept,
                    body=body,
                    body_bytes=len(buffer),
                    encoding=encoding,
                    elapsed_ms=int((time.monotonic() - started) * 1000),
                    peer_address=peer,
                    peer_verified=verified,
                    chain=chain,
                )
            finally:
                if not drained:
                    _hard_close(response)
                response.close()

        raise GeoError(
            "GEO_E_TOO_MANY_REDIRECTS",
            f"{url} redirected more than {max_redirects} times without settling.",
        )
    finally:
        if owned:
            session.close()
