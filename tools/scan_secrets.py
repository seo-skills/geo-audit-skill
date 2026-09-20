#!/usr/bin/env python3
"""A dependency-free secret scan over tracked files.

This is a floor, not a replacement for GitHub's own secret scanning, which is
enabled on the repository and catches provider-issued credentials this cannot.
What it does catch is the common accident: a key pasted into a fixture, a doc,
or a test while debugging.

A line carrying the marker `geo-secret-scan-allow` is skipped. It exists for
exactly one case: the tests that prove this scanner works have to contain
strings that look like secrets.

Run: python tools/scan_secrets.py
"""

from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

PATTERNS: list[tuple[str, re.Pattern]] = [
    ("AWS access key id", re.compile(r"\b(?:AKIA|ASIA)[0-9A-Z]{16}\b")),
    ("private key block", re.compile(r"-----BEGIN (?:RSA |EC |OPENSSH |PGP )?PRIVATE KEY")),
    ("GitHub token", re.compile(r"\bgh[pousr]_[A-Za-z0-9]{36,}\b")),
    ("Slack token", re.compile(r"\bxox[abprs]-[A-Za-z0-9-]{10,}\b")),
    ("PyPI token", re.compile(r"\bpypi-AgEIcHlwaS5vcmc[A-Za-z0-9_-]{20,}")),
    ("OpenAI-style key", re.compile(r"\bsk-[A-Za-z0-9]{32,}\b")),
    ("Anthropic-style key", re.compile(r"\bsk-ant-[A-Za-z0-9_-]{32,}\b")),
    ("Google API key", re.compile(r"\bAIza[0-9A-Za-z_-]{35}\b")),
    (
        "assigned secret literal",
        re.compile(
            r"(?i)\b(?:api[_-]?key|secret|passwd|password|token)\b\s*[:=]\s*"
            r"['\"][A-Za-z0-9/+_-]{24,}['\"]"
        ),
    ),
]

FORBIDDEN_NAMES = re.compile(
    r"(?:^|/)(?:\.env(?:\.[a-z]+)?|id_rsa|id_ed25519|.*\.pem|.*\.p12|.*\.pfx|"
    r"credentials\.json|service-account.*\.json)$"
)

ALLOW_MARKER = "geo-secret-scan-allow"

SKIP_DIRS = {
    ".git", ".venv", "venv", "__pycache__", "node_modules", "dist", "build",
    ".pytest_cache", ".ruff_cache", ".mypy_cache", "htmlcov", ".eggs",
}
BINARY_SUFFIXES = {".png", ".jpg", ".jpeg", ".gif", ".pdf", ".ico", ".woff", ".woff2", ".zip"}


def tracked_files() -> list[Path]:
    try:
        output = subprocess.run(
            ["git", "ls-files", "-z"], cwd=ROOT, capture_output=True, text=True, check=True
        ).stdout
        names = [n for n in output.split("\0") if n]
        if names:
            return [ROOT / name for name in names]
    except (subprocess.CalledProcessError, FileNotFoundError):
        pass
    return [
        path
        for path in ROOT.rglob("*")
        if path.is_file() and not SKIP_DIRS & set(path.relative_to(ROOT).parts)
    ]


def main() -> int:
    problems: list[str] = []
    for path in tracked_files():
        relative = path.relative_to(ROOT).as_posix()
        if FORBIDDEN_NAMES.search(relative):
            problems.append(f"{relative}: a file of this kind should never be committed")
            continue
        if path.suffix.lower() in BINARY_SUFFIXES or not path.exists():
            continue
        # This scanner's own pattern table is not a finding.
        if relative == "tools/scan_secrets.py":
            continue
        try:
            text = path.read_text(encoding="utf-8")
        except (UnicodeDecodeError, OSError):
            continue
        for line_number, line in enumerate(text.splitlines(), start=1):
            if ALLOW_MARKER in line:
                continue
            for label, pattern in PATTERNS:
                if pattern.search(line):
                    problems.append(f"{relative}:{line_number}: possible {label}")

    if problems:
        print(f"secret scan: {len(problems)} finding(s)", file=sys.stderr)
        for problem in problems:
            print(f"  {problem}", file=sys.stderr)
        return 1
    print("secret scan: clean")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
