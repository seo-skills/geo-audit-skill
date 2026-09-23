"""A preflight names one version line, the current one.

1.1.0 shipped three skills whose preflight said "Expected: `seomator-geo-audit
0.2.x` or newer" two lines above "Older than 1.1.0 -> stop". The lint asked only
that the current line appear somewhere in the preflight, and the stop line was
enough to satisfy it.
"""

from __future__ import annotations

from tests.test_skills_lint import VERSION, contract_block, lint_one, make_skill

LINE = VERSION.rsplit(".", 1)[0]


def test_a_stale_expected_line_beside_a_current_floor_is_caught(tmp_path):
    preflight = (
        "## Preflight\n\nRun `geo --version`.\n\n"
        "Expected: `seomator-geo-audit 0.2.x` or newer.\n\n"
        f"- **Older than {VERSION}** -> stop and say: \"This skill needs "
        f"seomator-geo-audit {VERSION} or newer.\"\n"
    )
    path = make_skill(tmp_path, body=contract_block(preflight=preflight))
    assert any("0.2.x" in error for error in lint_one(path))


def test_the_current_line_alone_passes(tmp_path):
    preflight = (
        "## Preflight\n\nRun `geo --version`.\n\n"
        f"Expected: `seomator-geo-audit {LINE}.x` or newer.\n\n"
        f"- **Older than {VERSION}** -> stop.\n"
    )
    path = make_skill(tmp_path, body=contract_block(preflight=preflight))
    assert lint_one(path) == []
