"""The command an audit suggests next has to be one that works.

After `--rescore`, the terminal suggested rescoring the rescore's own run id. A
rescore is not recorded - it recomputes, it does not observe - so following the
suggestion answered "No audit with run id ... was found".
"""

from __future__ import annotations

import io
import json
import re

from geo_audit.cli import main


class FakeTTY(io.StringIO):
    def isatty(self) -> bool:
        return True


def _next_command(text: str) -> list[str]:
    match = re.search(r"Next: (geo .+)", text)
    assert match, text
    return match.group(1).strip().strip("`").split()


def test_the_command_suggested_after_a_rescore_can_be_run(site, geo_home):
    buffer = io.StringIO()
    main(["audit", f"{site.url}/hub.html", "--allow-private", "--rate", "50", "--max-pages", "6",
          "--json", "--quiet"], out=buffer)
    recorded = json.loads(buffer.getvalue())["run_id"]

    out = FakeTTY()
    main(["audit", f"{site.url}/hub.html", "--rescore", recorded, "--quiet"], out=out)
    suggested = _next_command(out.getvalue())
    assert suggested[suggested.index("--rescore") + 1] == recorded

    again = io.StringIO()
    code = main(suggested[1:] + ["--json", "--quiet"], out=again)
    assert code == 0, json.loads(again.getvalue())["error"]
