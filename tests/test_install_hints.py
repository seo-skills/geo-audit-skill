"""A hint that installs the browser extra has to leave `playwright` runnable.

`uv tool install 'seomator-geo-audit[browser]' && playwright install chromium`
was the hint in `geo doctor` and in the report's PDF-unavailable message, and it
failed on a clean machine with 1.0.0: `uv tool` puts only the tool's own
commands on PATH, so the second half ran into command not found. The doctor's
other browser hint told a user it had just found without the command on PATH
to run that command.
"""

from __future__ import annotations

import io
import json
import os
import re
import shlex
import sys

import pytest

from geo_audit import _version
from geo_audit import copy as copytext
from geo_audit.cli import main
from geo_audit.commands import doctor
from geo_audit.lib import browser


def _words(command: str) -> list[str]:
    if os.name == "nt":
        return [word.strip('"') for word in shlex.split(command, posix=False)]
    return shlex.split(command)


def _commands(hint: str) -> list[list[str]]:
    """Each shell command a hint asks for, split into words."""
    return [_words(part) for snippet in re.findall(r"`([^`]+)`", hint) for part in snippet.split("&&")]


def _checks() -> dict:
    buffer = io.StringIO()
    main(["doctor", "--json", "--quiet"], out=buffer)
    return {check["id"]: check for check in json.loads(buffer.getvalue())["checks"]}


def _exposes_playwright(install: list[str]) -> bool:
    return install[:3] == ["uv", "tool", "install"] and "--with-executables-from" in install and (
        install[install.index("--with-executables-from") + 1] == "playwright"
    )


@pytest.mark.parametrize("published", [False, True], ids=["before-publish", "after-publish"])
def test_the_browser_install_exposes_the_command_run_after_it(monkeypatch, published):
    monkeypatch.setattr(_version, "PUBLISHED_ON_PYPI", published)
    assert _exposes_playwright(_words(f"uv tool install {_version.install_target('browser')}"))
    assert "--with-executables-from" not in _version.install_target()


def test_the_doctor_hint_installs_what_it_then_runs(geo_home, monkeypatch):
    monkeypatch.setattr(browser, "available", lambda: False)
    install, then = _commands(_checks()["browser_extra"]["hint"])
    assert _exposes_playwright(install)
    assert then == ["playwright", "install", "chromium"]


def test_the_pdf_message_installs_what_it_then_runs():
    message = copytext.PDF_UNAVAILABLE.format(
        reason="the browser component is not installed", path="report.html", install=_version.install_target("browser")
    )
    install, then = _commands(message)
    assert _exposes_playwright(install)
    assert then == ["playwright", "install", "chromium"]


@pytest.mark.parametrize("python", [sys.executable, os.path.join(os.sep, "opt", "my tools", "bin", "python3")])
def test_a_command_missing_from_path_is_run_through_the_interpreter_instead(geo_home, monkeypatch, python):
    """The check fires exactly when `playwright` is importable but not on PATH,
    so the hint has to reach it through the interpreter that imports it - a
    path with a space in it included."""
    monkeypatch.setattr(browser, "available", lambda: True)
    monkeypatch.setattr(doctor.shutil, "which", lambda name: None)
    monkeypatch.setattr(doctor.sys, "executable", python)
    (command,) = _commands(_checks()["browser_binary"]["hint"])
    assert command == [python, "-m", "playwright", "install", "chromium"]
