"""A local HTTP server for the fixture site.

Every fixture page in tests/fixtures/site was authored for this repository.
Checking real third-party HTML into a public MIT repo would redistribute other
people's copyrighted content, so nothing here was captured from the web.
"""

from __future__ import annotations

import threading
from dataclasses import dataclass, field
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Callable

FIXTURE_DIR = Path(__file__).parent / "fixtures" / "site"

DEFAULT_ROBOTS = """\
User-agent: *
Disallow: /private/
Allow: /

User-agent: GPTBot
Disallow: /

Sitemap: /sitemap.xml
"""


@dataclass
class Reply:
    status: int = 200
    body: str | bytes = ""
    content_type: str | None = "text/html; charset=utf-8"
    headers: dict[str, str] = field(default_factory=dict)
    raw: bool = False
    delay: float = 0.0
    # Reply without a Connection header and close anyway, reproducing a server
    # that drops an idle keep-alive connection without notice.
    silent_close: bool = False

    def encoded(self) -> bytes:
        return self.body if isinstance(self.body, bytes) else self.body.encode("utf-8")


Route = Reply | Callable[[str], Reply]


def _page(name: str) -> Reply:
    return Reply(body=(FIXTURE_DIR / name).read_text(encoding="utf-8"))


def site_routes() -> dict[str, Route]:
    routes: dict[str, Route] = {
        f"/{path.name}": _page(path.name) for path in sorted(FIXTURE_DIR.glob("*.html"))
    }
    routes["/robots.txt"] = Reply(body=DEFAULT_ROBOTS, content_type="text/plain; charset=utf-8")
    routes["/bot-block"] = Reply(
        status=403,
        body="<html><body><h1>Access denied</h1>"
        "<p>Enable JavaScript and cookies to continue.</p></body></html>",
    )
    routes["/server-error"] = Reply(status=500, body="<html><body>500</body></html>")
    routes["/gone"] = Reply(status=404, body="<html><body>Not found</body></html>")
    routes["/not-html"] = Reply(
        body='{"ok": true}', content_type="application/json; charset=utf-8"
    )
    routes["/oversize"] = Reply(
        body="<html><body><p>" + ("padding " * 400_000) + "</p></body></html>"
    )
    routes["/oversize-stream"] = Reply(
        body="<html><body><p>" + ("padding " * 400_000) + "</p></body></html>", raw=True
    )
    moved = "<html><body><h1>302 Found</h1><p>The document has moved.</p></body></html>"
    routes["/redirect-loop"] = Reply(
        status=302, body=moved, headers={"Location": "/redirect-loop"}
    )
    routes["/redirect-private"] = Reply(
        status=302, body=moved, headers={"Location": "http://127.0.0.1:1/unreachable"}
    )
    for hop in range(1, 4):
        target = "/ssr-rich.html" if hop == 1 else f"/redirect/{hop - 1}"
        routes[f"/redirect/{hop}"] = Reply(
            status=302, body=moved, headers={"Location": target}
        )
    routes["/private/secret.html"] = _page("schema-none.html")
    routes["/whitepaper.pdf"] = Reply(
        body="%PDF-1.4 not really a pdf", content_type="application/pdf"
    )
    # Two pages reachable only from the sitemap, so a crawl that ignores it
    # finds strictly less than one that does not.
    routes["/sitemap.xml"] = Reply(
        body=(
            '<?xml version="1.0" encoding="UTF-8"?>\n'
            '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n'
            "  <url><loc>{base}/schema-broken.html</loc></url>\n"
            "  <url><loc>{base}/injection.html</loc></url>\n"
            "</urlset>\n"
        ),
        content_type="application/xml; charset=utf-8",
    )
    return routes


class _Server(ThreadingHTTPServer):
    # Counts accepted TCP connections, so a test can tell connection reuse from
    # a fresh handshake per request.
    connections = 0

    # The stdlib default is 5. The socket starts listening in the constructor
    # but nothing accepts until the serving thread is scheduled, so a burst
    # arriving in that window fills the queue and the kernel refuses it.
    request_queue_size = 128
    daemon_threads = True

    def __init__(self, *args, **kwargs) -> None:
        # Every path requested, so a test can assert that a URL was never
        # fetched rather than only that it produced no result.
        self.requests_seen: list[str] = []
        self._log_lock = threading.Lock()
        super().__init__(*args, **kwargs)

    def note(self, path: str) -> None:
        with self._log_lock:
            self.requests_seen.append(path)


class _Handler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"
    routes: dict[str, Route] = {}

    def log_message(self, *args) -> None:  # noqa: D102 - silence the test run
        pass

    def setup(self) -> None:
        super().setup()
        self.server.connections += 1

    def handle_one_request(self) -> None:
        # Aborting a download mid-stream is the expected outcome of the size-cap
        # tests. Let the connection die quietly instead of printing a traceback
        # into every test run.
        try:
            super().handle_one_request()
        except (BrokenPipeError, ConnectionResetError):
            self.close_connection = True

    def do_GET(self) -> None:  # noqa: N802 - BaseHTTPRequestHandler API
        import time

        path = self.path.split("?", 1)[0]
        self.server.note(self.path)
        route = self.routes.get(path)
        if route is None:
            reply = Reply(status=404, body="<html><body>no fixture route</body></html>")
        else:
            # A route that takes two arguments is also handed the request headers,
            # so a fixture can answer a conditional request with 304.
            if callable(route):
                import inspect

                wants_headers = len(inspect.signature(route).parameters) > 1
                reply = route(path, self.headers) if wants_headers else route(path)
            else:
                reply = route

        if reply.delay:
            time.sleep(reply.delay)

        payload = reply.encoded()
        self.send_response(reply.status)
        if reply.content_type:
            self.send_header("Content-Type", reply.content_type)
        if reply.silent_close:
            # Close without announcing it: the shape that broke CI. The client
            # keeps the socket in its pool and the next request on it fails
            # with RemoteDisconnected.
            self.close_connection = True
        elif self.headers.get("Connection", "").strip().lower() == "close":
            # http.server honours a client's `Connection: close` internally but
            # never says so on the wire. Echo it, the way a real server does.
            self.send_header("Connection", "close")
        for key, value in reply.headers.items():
            self.send_header(key, value)
        if reply.raw:
            # No Content-Length: the body ends when the connection closes, which
            # exercises the streaming size cap rather than the declared one.
            self.end_headers()
            self.wfile.write(payload)
            self.close_connection = True
            return
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)


class FixtureServer:
    def __init__(self, routes: dict[str, Route]) -> None:
        self._routes = routes
        handler = type("BoundHandler", (_Handler,), {"routes": routes})
        self._server = _Server(("127.0.0.1", 0), handler)
        self._thread = threading.Thread(target=self._server.serve_forever, daemon=True)

    def _materialise_origin(self) -> None:
        """Fill `{base}` in any route body with this server's real origin."""
        for route in self._routes.values():
            if isinstance(route, Reply) and isinstance(route.body, str) and "{base}" in route.body:
                route.body = route.body.replace("{base}", self.url)

    @property
    def requests_seen(self) -> list[str]:
        return list(self._server.requests_seen)

    def reset_requests(self) -> None:
        self._server.requests_seen.clear()

    @property
    def connection_count(self) -> int:
        return self._server.connections

    def reset_connection_count(self) -> None:
        self._server.connections = 0

    @property
    def url(self) -> str:
        host, port = self._server.server_address[:2]
        return f"http://{host}:{port}"

    def __enter__(self) -> "FixtureServer":
        self._thread.start()
        self._await_ready()
        self._materialise_origin()
        return self

    def _await_ready(self, attempts: int = 100) -> None:
        """Block until the server is actually accepting.

        Starting the thread is not the same as serving: without this, the
        first burst of requests can arrive before anything calls accept().
        """
        import socket
        import time

        host, port = self._server.server_address[:2]
        for _ in range(attempts):
            try:
                with socket.create_connection((host, port), timeout=0.5):
                    return
            except OSError:
                time.sleep(0.02)
        raise RuntimeError(f"fixture server never started on {host}:{port}")

    def __exit__(self, *exc) -> None:
        self._server.shutdown()
        self._server.server_close()
        self._thread.join(timeout=5)
