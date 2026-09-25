"""A request that times out is reported as a timeout and is never sent twice.

The session retries once for a pooled connection the server dropped. urllib3
counts a read timeout as a read error too, so before this was fixed every slow
response was requested a second time, doubling the wait (and, for a paid API,
possibly the charge), and the spent retry surfaced as GEO_E_CONNECT.
"""

from __future__ import annotations

import io
import json
import socket
import threading
import time

import pytest

from geo_audit import assistants
from geo_audit.cli import main
from geo_audit.commands import scan
from geo_audit.errors import GeoError
from geo_audit.lib import http
from tests.fixture_server import Reply


def test_a_slow_response_is_one_request_and_a_timeout(serve):
    server = serve({"/slow": Reply(body="<html><body>late</body></html>", delay=1.5)})
    with pytest.raises(GeoError) as caught:
        http.fetch(f"{server.url}/slow", allow_private=True, timeout=0.5)
    assert caught.value.code == "GEO_E_TIMEOUT"
    assert server.requests_seen.count("/slow") == 1


def _stalling_server():
    """Headers and half a body, then silence: a stream that stalls mid-download."""
    listener = socket.socket()
    listener.bind(("127.0.0.1", 0))
    listener.listen(1)

    def serve_once():
        conn, _ = listener.accept()
        conn.recv(65536)
        conn.sendall(b"HTTP/1.1 200 OK\r\nContent-Type: text/html\r\nContent-Length: 1000\r\n\r\n<html>")
        time.sleep(2)
        conn.close()
        listener.close()

    threading.Thread(target=serve_once, daemon=True).start()
    return f"http://127.0.0.1:{listener.getsockname()[1]}/"


def test_a_body_that_stalls_is_a_timeout_not_a_crash():
    with pytest.raises(GeoError) as caught:
        http.fetch(_stalling_server(), allow_private=True, timeout=0.5)
    assert caught.value.code == "GEO_E_TIMEOUT"


def test_a_slow_assistant_is_asked_once(serve, geo_home, monkeypatch):
    server = serve({
        "/info": Reply(body=json.dumps({"IsActive": True, "RemainingMonthlyRequest": 5000}),
                       content_type="application/json"),
        "/plugin/chatgpt/chat": Reply(body="{}", content_type="application/json", delay=1.5),
    })
    monkeypatch.setattr(assistants, "BASE", server.url)
    monkeypatch.setattr(assistants, "ENGINES", {
        name: type(engine)(**{**engine.__dict__, "timeout": 0.5}) for name, engine in assistants.ENGINES.items()
    })
    monkeypatch.setattr(scan, "_platforms", lambda: {})
    monkeypatch.setenv(assistants.TOKEN_ENV, "test-token")
    out = io.StringIO()
    main(["scan", "Acme", "--allow-private", "--assistants", "chatgpt", "--json", "--quiet"], out=out)
    question = json.loads(out.getvalue())["scan"]["assistants"]["engines"][0]["brand_question"]
    assert question["reason"] == "GEO_E_TIMEOUT"
    assert sum(path.startswith("/plugin/chatgpt/chat") for path in server.requests_seen) == 1
