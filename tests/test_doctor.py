from __future__ import annotations

import pytest

import io
import json

from geo_audit.cli import main

EXPECTED_CHECKS = {
    "python",
    "cli_version",
    "geo_on_path",
    "data_files",
    "state_home",
    "state_version",
    "state_writable",
    "state_sync_drive",
    "browser_extra",
}


def run(args=None):
    buffer = io.StringIO()
    code = main(["doctor", "--json", "--quiet"] + (args or []), out=buffer)
    return code, json.loads(buffer.getvalue())


def test_doctor_reports_and_never_gates(geo_home):
    code, envelope = run()
    assert code == 0
    assert envelope["ok"] is True


def test_every_expected_check_is_present(geo_home):
    _, envelope = run()
    assert EXPECTED_CHECKS <= {check["id"] for check in envelope["checks"]}


def test_every_check_has_a_valid_status_and_a_hint_when_not_ok(geo_home):
    _, envelope = run()
    for check in envelope["checks"]:
        assert check["status"] in ("ok", "warn", "fail"), check
        assert check["detail"].strip(), check
        if check["status"] != "ok":
            assert check["hint"], f"{check['id']} needs a next action"


def test_doctor_creates_geo_home(geo_home):
    assert not geo_home.exists()
    run()
    assert geo_home.is_dir()


def test_doctor_warns_about_a_sync_drive(tmp_path, monkeypatch):
    monkeypatch.setenv("GEO_HOME", str(tmp_path / "Dropbox" / "geo"))
    _, envelope = run()
    sync = next(c for c in envelope["checks"] if c["id"] == "state_sync_drive")
    assert sync["status"] == "warn"
    assert "Dropbox" in sync["detail"]


def test_doctor_reports_the_missing_browser_extra_as_a_warning(geo_home, monkeypatch):
    from geo_audit.lib import browser

    monkeypatch.setattr(browser, "available", lambda: False)
    _, envelope = run()
    check = next(c for c in envelope["checks"] if c["id"] == "browser_extra")
    assert check["status"] == "warn"
    assert "playwright install chromium" in check["hint"]


@pytest.mark.parametrize("published", [False, True], ids=["before-publish", "after-publish"])
def test_every_install_hint_names_something_that_installs(monkeypatch, published):
    """The first real install: doctor's browser-extra hint named a PyPI package
    that did not exist yet, the dead end the skills and docs had already lost."""
    from geo_audit.commands import doctor

    monkeypatch.setattr(doctor, "PUBLISHED_ON_PYPI", published)
    plain, extra = doctor.install_target(), doctor.install_target("browser")
    if published:
        assert plain == "seomator-geo-audit" and extra == "'seomator-geo-audit[browser]'"
    else:
        assert plain == "git+https://github.com/seo-skills/geo-audit-skill"
        assert extra == "'seomator-geo-audit[browser] @ git+https://github.com/seo-skills/geo-audit-skill'"
