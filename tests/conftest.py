from __future__ import annotations

import pytest

from tests.fixture_server import FixtureServer, Reply, site_routes


@pytest.fixture(scope="session")
def site():
    with FixtureServer(site_routes()) as server:
        yield server


@pytest.fixture
def serve():
    """Spin up a throwaway server with a custom route table."""
    servers = []

    def _serve(routes):
        server = FixtureServer(routes)
        server.__enter__()
        servers.append(server)
        return server

    yield _serve
    for server in servers:
        server.__exit__(None, None, None)


@pytest.fixture
def geo_home(tmp_path, monkeypatch):
    home = tmp_path / "geo-home"
    monkeypatch.setenv("GEO_HOME", str(home))
    return home


@pytest.fixture
def reply():
    return Reply
