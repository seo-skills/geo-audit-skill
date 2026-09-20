"""`geo doctor` — answer "why did that not work" before the user has to ask.

Every check reports one of ok / warn / fail and, when it is not ok, the exact
next command. A warning never stops anything: an optional extra that is not
installed is a fact about this machine, not a defect.
"""

from __future__ import annotations

import os
import platform
import shutil
import stat
import sys
from pathlib import Path

from geo_audit import data, envelope, state
from geo_audit._version import CLI_VERSION, DIST_NAME, STATE_VERSION
from geo_audit.errors import GeoError
from geo_audit.lib import browser


def _check(id_: str, status: str, detail: str, hint: str | None = None) -> dict:
    return {"id": id_, "status": status, "detail": detail, "hint": hint}


def _python_check() -> dict:
    version = platform.python_version()
    if sys.version_info >= (3, 11):
        return _check("python", "ok", f"{version} on {platform.system()}")
    return _check(
        "python",
        "fail",
        f"{version} is below the 3.11 minimum",
        "Install seomator-geo-audit with a 3.11+ interpreter: `uv tool install --python 3.12 seomator-geo-audit`.",
    )


def _path_check() -> dict:
    found: list[str] = []
    names = ("geo.exe", "geo.cmd", "geo") if os.name == "nt" else ("geo",)
    for directory in os.environ.get("PATH", "").split(os.pathsep):
        if not directory:
            continue
        for name in names:
            candidate = Path(directory) / name
            if candidate.exists() and str(candidate) not in found:
                found.append(str(candidate))
    if not found:
        return _check(
            "geo_on_path",
            "warn",
            "no `geo` executable found on PATH",
            "This usually means the CLI was run as `python -m geo_audit`. "
            "Install it with `uv tool install seomator-geo-audit` to get the `geo` command.",
        )
    if len(found) > 1:
        return _check(
            "geo_on_path",
            "warn",
            f"{len(found)} executables named geo: {', '.join(found)}",
            "PATH order decides which one runs. Remove the one you do not want, "
            "or call this tool as `python -m geo_audit`.",
        )
    return _check("geo_on_path", "ok", found[0])


def _home_check() -> dict:
    home = state.geo_home()
    if not home.exists():
        return _check("state_home", "ok", f"{state.display_home()} (not created yet)")
    mode = stat.S_IMODE(home.stat().st_mode)
    if mode & (stat.S_IRWXG | stat.S_IRWXO):
        return _check(
            "state_home",
            "warn",
            f"{state.display_home()} is mode {mode:04o}, not 0700",
            f"Audit history is readable by other users. Fix with `chmod 700 {home}`.",
        )
    return _check("state_home", "ok", f"{state.display_home()} (mode {mode:04o})")


def _state_version_check() -> dict:
    try:
        state.check_version()
    except GeoError as exc:
        return _check("state_version", "fail", exc.message, exc.spec.hint)
    found = state.read_state().get("state_version", STATE_VERSION)
    return _check("state_version", "ok", f"state v{found}, CLI expects v{STATE_VERSION}")


def _sync_check() -> dict:
    marker = state.on_sync_drive()
    if marker:
        return _check(
            "state_sync_drive",
            "warn",
            f"{state.display_home()} sits inside {marker}",
            "Audit history is append-only and assumes one writer. Two machines "
            "syncing the same file will corrupt it. Move it with "
            "`export GEO_HOME=~/.geo`.",
        )
    return _check("state_sync_drive", "ok", "not on a detected sync drive")


def _browser_check() -> dict:
    if browser.available():
        return _check("browser_extra", "ok", "Playwright is importable")
    return _check(
        "browser_extra",
        "warn",
        "Playwright is not installed; render and PDF signals will be null",
        "Optional. To enable: `uv tool install 'seomator-geo-audit[browser]' && playwright install chromium`",
    )


def _data_check() -> dict:
    try:
        version = data.data_version()
        signals = len(data.weights()["citability"]["signals"])
        crawlers = len(data.crawlers())
    except Exception as exc:  # pragma: no cover - packaging failure
        return _check("data_files", "fail", f"package data could not be read: {exc}",
                      "Reinstall with `uv tool install --force seomator-geo-audit`.")
    return _check(
        "data_files", "ok", f"data {version}: {signals} citability signals, {crawlers} crawler tokens"
    )


def _write_check() -> dict:
    try:
        state.init()
    except GeoError as exc:
        return _check("state_writable", "fail", exc.message, exc.spec.hint)
    return _check("state_writable", "ok", f"{state.display_home()} is writable")


def run(args, run_id: str) -> dict:
    checks = [
        _python_check(),
        _check("cli_version", "ok", f"{DIST_NAME} {CLI_VERSION}"),
        _path_check(),
        _data_check(),
        _home_check(),
        _state_version_check(),
        _write_check(),
        _sync_check(),
        _browser_check(),
    ]
    if shutil.which("playwright") is None and browser.available():
        checks.append(
            _check(
                "browser_binary",
                "warn",
                "the playwright package is installed but its CLI is not on PATH",
                "Run `playwright install chromium` once to download the browser.",
            )
        )
    # `ok` describes whether the command produced a valid result, and doctor
    # always does. A failing check is a fact about this machine that doctor
    # successfully discovered, so the exit code stays 0 and callers read
    # `checks[].status`. The next real command is the one that exits 4.
    return envelope.build(
        "doctor",
        ok=True,
        run_id=run_id,
        error=None,
        extra={"checks": checks},
    )
