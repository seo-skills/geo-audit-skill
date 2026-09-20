from __future__ import annotations

import pytest

from geo_audit.lib.ids import is_run_id, new_run_id
from geo_audit.lib.slug import host_of, project_slug


@pytest.mark.parametrize(
    "url,expected",
    [
        ("https://www.Example.com/pricing", "example-com"),
        ("https://example.com", "example-com"),
        ("http://sub.example.co.uk/a/b", "sub-example-co-uk"),
        ("http://localhost:3000/app", "localhost"),
        ("http://127.0.0.1:8080/", "127-0-0-1"),
        ("not a url", "unknown"),
    ],
)
def test_project_slug(url, expected):
    assert project_slug(url) == expected


def test_slug_ignores_the_port():
    assert project_slug("http://localhost:3000") == project_slug("http://localhost:8080")


def test_host_strips_www_and_lowercases():
    assert host_of("https://WWW.Example.COM/x") == "example.com"


def test_run_ids_are_valid_and_unique():
    ids = {new_run_id() for _ in range(200)}
    assert len(ids) == 200
    assert all(is_run_id(value) for value in ids)


def test_run_ids_sort_chronologically():
    early = new_run_id(now_ms=1_700_000_000_000)
    late = new_run_id(now_ms=1_800_000_000_000)
    assert early < late
