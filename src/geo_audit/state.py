"""$GEO_HOME: history and evidence, not resume state.

Three properties this module has to hold:

* A crashed run leaves nothing to clean up. Audit history is append-only JSONL
  written one record per `write()`; everything else is written to a temporary
  file and renamed. The reader discards a torn trailing line without comment,
  because a half-written last record is the expected outcome of Ctrl-C, not
  corruption.
* State carries a version. A CLI that finds newer state refuses to run and
  changes nothing, rather than migrating someone's history downward.
* Nothing takes a cross-process lock, because an audit must never wait on
  another command. Appends need none: a record is one `write()` to a file
  opened for append. The one rewrite, `geo prune`, re-checks the file's size
  before replacing it and leaves a file that grew alone. Stored pages are
  written by rename under the hash of their bytes, and prune spares any page
  written or reused within its grace period, because an audit stores its pages
  before it appends the record that names them.
"""

from __future__ import annotations

import json
import os
import stat
import tempfile
from datetime import datetime, timezone
from pathlib import Path

from geo_audit._version import CLI_VERSION, DIST_NAME, STATE_VERSION
from geo_audit.errors import GeoError

STATE_FILE = "state.json"
LOG_RELATIVE = "logs/last-run.log"

# Directories whose contents are replicated by a sync client. GEO_HOME there
# means two machines writing one append-only file, which is the one thing this
# design assumes never happens.
SYNC_MARKERS = (
    "Library/Mobile Documents",
    "iCloud Drive",
    "Dropbox",
    "OneDrive",
    "Google Drive",
    "pCloud",
    "Sync.com",
)


def geo_home() -> Path:
    override = os.environ.get("GEO_HOME")
    return Path(override).expanduser() if override else Path.home() / ".geo"


def log_path() -> Path:
    return geo_home() / LOG_RELATIVE


def display_home() -> str:
    home = geo_home()
    try:
        return "~/" + str(home.relative_to(Path.home()))
    except ValueError:
        return str(home)


def on_sync_drive(path: Path | None = None) -> str | None:
    target = str(path or geo_home())
    for marker in SYNC_MARKERS:
        if marker in target:
            return marker
    return None


def ensure_home() -> Path:
    home = geo_home()
    try:
        home.mkdir(parents=True, exist_ok=True)
        os.chmod(home, stat.S_IRWXU)
        (home / "logs").mkdir(exist_ok=True)
        (home / "projects").mkdir(exist_ok=True)
    except OSError as exc:
        raise GeoError(
            "GEO_E_STATE_WRITE", f"Couldn't create {display_home()}: {exc.strerror}."
        ) from exc
    return home


def read_state() -> dict:
    path = geo_home() / STATE_FILE
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise GeoError(
            "GEO_E_STATE_UNREADABLE",
            f"{display_home()}/{STATE_FILE} could not be read.",
        ) from exc


def check_version() -> None:
    """Refuse to run against state written by a newer CLI. Changes nothing."""
    state = read_state()
    found = state.get("state_version")
    if found is None or found <= STATE_VERSION:
        return
    written_by = state.get("cli_version", "a newer release")
    raise GeoError(
        "GEO_E_STATE_NEWER",
        f"{display_home()} was written by {DIST_NAME} {written_by} "
        f"(state v{found}); this is {CLI_VERSION} (state v{STATE_VERSION}). "
        f"Nothing was changed.",
    )


def write_atomic(path: Path, payload: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    handle = tempfile.NamedTemporaryFile(
        "w", encoding="utf-8", dir=path.parent, prefix=f".{path.name}.", delete=False
    )
    try:
        with handle:
            handle.write(payload)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(handle.name, path)
    except OSError as exc:
        Path(handle.name).unlink(missing_ok=True)
        raise GeoError("GEO_E_STATE_WRITE", f"Couldn't write {path.name}: {exc.strerror}.") from exc


def init() -> Path:
    """Create GEO_HOME if needed and stamp the state version."""
    check_version()
    home = ensure_home()
    state = read_state()
    if state.get("state_version") != STATE_VERSION:
        write_atomic(
            home / STATE_FILE,
            json.dumps(
                {
                    "state_version": STATE_VERSION,
                    "cli_version": CLI_VERSION,
                    "created_at": state.get(
                        "created_at", datetime.now(timezone.utc).isoformat(timespec="seconds")
                    ),
                },
                indent=2,
                sort_keys=True,
            )
            + "\n",
        )
    return home


def write_atomic_bytes(path: Path, payload: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    handle = tempfile.NamedTemporaryFile(dir=path.parent, prefix=f".{path.name}.", delete=False)
    try:
        with handle:
            handle.write(payload)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(handle.name, path)
    except OSError as exc:
        Path(handle.name).unlink(missing_ok=True)
        raise GeoError("GEO_E_STATE_WRITE", f"Couldn't write {path.name}: {exc.strerror}.") from exc


def project_dir(slug: str) -> Path:
    return geo_home() / "projects" / slug


def audits_path(slug: str) -> Path:
    return project_dir(slug) / "audits.jsonl"


def append_audit(slug: str, record: dict) -> Path:
    path = audits_path(slug)
    path.parent.mkdir(parents=True, exist_ok=True)
    line = json.dumps(record, sort_keys=True, separators=(",", ":")) + "\n"
    try:
        with open(path, "a", encoding="utf-8") as handle:
            handle.write(line)
    except OSError as exc:
        raise GeoError(
            "GEO_E_STATE_WRITE", f"Couldn't append to {path.name}: {exc.strerror}."
        ) from exc
    return path


def read_audits(slug: str) -> tuple[list[dict], int]:
    """Every intact record, plus the number of lines that could not be parsed.

    A torn trailing line is discarded silently: it is what a killed process
    leaves behind. A broken line anywhere else is counted and reported, because
    that is something else.
    """
    path = audits_path(slug)
    if not path.exists():
        return [], 0
    try:
        raw = path.read_text(encoding="utf-8", errors="replace")
    except OSError as exc:
        raise GeoError(
            "GEO_E_STATE_UNREADABLE", f"Couldn't read {path.name}: {exc.strerror}."
        ) from exc

    lines = raw.split("\n")
    if lines and lines[-1] == "":
        lines.pop()
    records: list[dict] = []
    damaged = 0
    for index, line in enumerate(lines):
        if not line.strip():
            continue
        try:
            records.append(json.loads(line))
        except json.JSONDecodeError:
            if index != len(lines) - 1:
                damaged += 1
    return records, damaged


def write_log(lines: list[str]) -> Path:
    path = log_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).isoformat(timespec="seconds")
    write_atomic(path, f"# {DIST_NAME} {CLI_VERSION} — {stamp}\n" + "\n".join(lines) + "\n")
    return path
