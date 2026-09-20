"""Version constants.

`VERSION` at the repo root is the single source of truth. `tools/lint_skills.py`
asserts that this file, pyproject.toml, .claude-plugin/plugin.json and every
skill frontmatter agree with it.

The four contract versions below move independently of the CLI version and each
appears in every envelope, audit record and report footer:

* schema_version     envelope shape
* scoring_version    the formula
* data_version       thresholds, weights, tiers, crawler lists (see data/meta.json)
* normalizer_version content extraction, and therefore evidence hash identity
"""

CLI_VERSION = "0.1.0"

SCHEMA_VERSION = 1
SCORING_VERSION = "1.0"
NORMALIZER_VERSION = 1
STATE_VERSION = 1
