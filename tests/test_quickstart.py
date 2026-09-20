"""The README quickstart is executable, and CI runs it.

The literal block is extracted from README.md and run command by command. Two
substitutions are made and no others: the example URL becomes the fixture
server, and score commands gain `--allow-private`, because the fixture server
is necessarily on loopback and refusing loopback by default is the behaviour
being preserved elsewhere.

The functional pass is the gate. The elapsed time is reported, not asserted.
"""

from __future__ import annotations

import re
import shutil
import subprocess
import sys
import time
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
EXAMPLE_URL = "https://example.com/pricing"


def quickstart_commands() -> list[str]:
    readme = (ROOT / "README.md").read_text(encoding="utf-8")
    section = readme.split("## Quickstart", 1)[1]
    block = re.search(r"```bash\n(.*?)```", section, re.DOTALL)
    assert block, "README has no runnable quickstart block"
    return [line for line in block.group(1).strip().splitlines() if line.strip()]


def geo_invocation() -> list[str]:
    """Prefer the installed console script: it is the shipped artifact."""
    from geo_audit._version import DIST_NAME

    console = shutil.which("geo")
    if console and DIST_NAME in subprocess.run(
        [console, "--version"], capture_output=True, text=True
    ).stdout:
        return [console]
    return [sys.executable, "-m", "geo_audit"]


def test_the_readme_quickstart_block_is_the_documented_first_success():
    commands = quickstart_commands()
    assert commands[0] == "geo doctor"
    assert any(c.startswith("geo score ") for c in commands)
    assert all(c.startswith("geo ") for c in commands)


def test_quickstart_runs_clean(site, geo_home, tmp_path, capsys):
    invocation = geo_invocation()
    started = time.monotonic()

    for line in quickstart_commands():
        redirect = None
        if ">" in line:
            line, _, redirect = line.partition(">")
            redirect = redirect.strip()
        parts = line.strip().split()
        assert parts[0] == "geo"
        args = parts[1:]
        args = [f"{site.url}/ssr-rich.html" if a == EXAMPLE_URL else a for a in args]
        if args and args[0] == "score":
            args += ["--allow-private", "--no-render"]

        target = tmp_path / (redirect or "stdout.txt")
        with open(target, "w", encoding="utf-8") as handle:
            result = subprocess.run(
                invocation + args, stdout=handle, stderr=subprocess.PIPE, text=True
            )
        assert result.returncode == 0, f"`{line.strip()}` exited {result.returncode}: {result.stderr}"
        if redirect:
            import json

            assert json.loads(target.read_text(encoding="utf-8"))["ok"] is True

    elapsed = time.monotonic() - started
    with capsys.disabled():
        print(f"\nquickstart smoke: {elapsed:.1f}s")


@pytest.mark.skipif(shutil.which("geo") is None, reason="console script not installed")
def test_the_console_script_is_the_shipped_artifact():
    result = subprocess.run([shutil.which("geo"), "--version"], capture_output=True, text=True)
    assert result.returncode == 0
    from geo_audit._version import DIST_NAME

    assert result.stdout.startswith(f"{DIST_NAME} ")
