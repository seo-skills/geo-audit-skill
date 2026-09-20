"""GEO_HOME: override, permissions, append-only history, torn lines, refusal."""

from __future__ import annotations

import json
import os
import stat

import pytest

from geo_audit import state
from geo_audit._version import STATE_VERSION
from geo_audit.errors import GeoError


def test_geo_home_defaults_under_the_home_directory(monkeypatch):
    monkeypatch.delenv("GEO_HOME", raising=False)
    assert state.geo_home().name == ".geo"


def test_geo_home_env_override_is_honoured(geo_home):
    assert state.geo_home() == geo_home


def test_init_creates_the_tree_with_owner_only_permissions(geo_home):
    state.init()
    assert geo_home.is_dir()
    assert (geo_home / "logs").is_dir()
    assert (geo_home / "projects").is_dir()
    if os.name != "nt":
        assert stat.S_IMODE(geo_home.stat().st_mode) == 0o700


def test_init_is_idempotent_and_keeps_created_at(geo_home):
    state.init()
    first = state.read_state()["created_at"]
    state.init()
    assert state.read_state()["created_at"] == first


def test_history_is_append_only(geo_home):
    state.init()
    for index in range(3):
        state.append_audit("example-com", {"run_id": f"R{index}"})
    records, damaged = state.read_audits("example-com")
    assert [r["run_id"] for r in records] == ["R0", "R1", "R2"]
    assert damaged == 0


def test_a_torn_trailing_line_is_discarded_silently(geo_home):
    state.init()
    state.append_audit("example-com", {"run_id": "R0"})
    path = state.audits_path("example-com")
    with open(path, "a", encoding="utf-8") as handle:
        handle.write('{"run_id": "R1", "partial')  # killed mid-write
    records, damaged = state.read_audits("example-com")
    assert [r["run_id"] for r in records] == ["R0"]
    assert damaged == 0, "a half-written last record is Ctrl-C, not corruption"


def test_a_damaged_middle_line_is_counted(geo_home):
    state.init()
    path = state.audits_path("example-com")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text('{"run_id":"R0"}\nnot json at all\n{"run_id":"R2"}\n', encoding="utf-8")
    records, damaged = state.read_audits("example-com")
    assert [r["run_id"] for r in records] == ["R0", "R2"]
    assert damaged == 1


def test_reading_a_project_with_no_history_is_not_an_error(geo_home):
    assert state.read_audits("never-seen") == ([], 0)


def test_newer_state_is_refused_and_nothing_is_changed(geo_home):
    state.init()
    path = geo_home / state.STATE_FILE
    path.write_text(
        json.dumps({"state_version": STATE_VERSION + 1, "cli_version": "9.9.9"}),
        encoding="utf-8",
    )
    before = path.read_text(encoding="utf-8")
    with pytest.raises(GeoError) as raised:
        state.init()
    assert raised.value.code == "GEO_E_STATE_NEWER"
    assert raised.value.exit_code == 4
    assert "Nothing was changed." in raised.value.message
    assert path.read_text(encoding="utf-8") == before


def test_older_state_is_accepted_and_stamped_forward(geo_home):
    state.init()
    path = geo_home / state.STATE_FILE
    path.write_text(json.dumps({"state_version": 0, "created_at": "2026-01-01"}), encoding="utf-8")
    state.init()
    assert state.read_state()["state_version"] == STATE_VERSION


def test_unreadable_state_reports_a_state_error(geo_home):
    state.init()
    (geo_home / state.STATE_FILE).write_text("{not json", encoding="utf-8")
    with pytest.raises(GeoError) as raised:
        state.read_state()
    assert raised.value.code == "GEO_E_STATE_UNREADABLE"


def test_atomic_write_leaves_no_temporary_file_behind(geo_home):
    state.init()
    target = geo_home / "thing.json"
    state.write_atomic(target, "{}\n")
    assert target.read_text(encoding="utf-8") == "{}\n"
    assert [p.name for p in geo_home.iterdir() if p.name.startswith(".thing")] == []


def test_sync_drive_detection(monkeypatch, tmp_path):
    monkeypatch.setenv("GEO_HOME", str(tmp_path / "Dropbox" / "geo"))
    assert state.on_sync_drive() == "Dropbox"
    monkeypatch.setenv("GEO_HOME", str(tmp_path / "plain" / "geo"))
    assert state.on_sync_drive() is None


def test_display_home_is_tilde_relative_when_possible(monkeypatch):
    monkeypatch.delenv("GEO_HOME", raising=False)
    assert state.display_home().startswith("~/")
