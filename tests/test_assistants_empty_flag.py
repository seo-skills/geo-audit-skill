"""An empty --assistants value is a usage error, not a run that silently asks nothing.

`geo scan Acme --assistants "$ENGINES"` with the variable unset passed an empty
string, which read as "flag not given": exit 0 and no scan.assistants block.
"""

from __future__ import annotations

import io
import json

import pytest

from geo_audit.cli import main
from geo_audit.commands import scan


@pytest.mark.parametrize("command", [
    ["scan", "Acme", "--allow-private"],
    ["audit", "https://acme.example", "--brand", "Acme"],
])
def test_an_empty_engine_list_is_refused(command, geo_home, monkeypatch):
    monkeypatch.setattr(scan, "_platforms", lambda: {})
    out = io.StringIO()
    code = main(command + ["--assistants", "", "--json", "--quiet"], out=out)
    assert code == 2
    assert json.loads(out.getvalue())["error"]["code"] == "GEO_E_BAD_ARGS"
