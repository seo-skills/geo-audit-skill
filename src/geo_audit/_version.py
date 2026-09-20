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

CLI_VERSION = "0.4.0"

# The product's public identifiers, in one place so they cannot drift apart.
# `tools/lint_skills.py` asserts pyproject.toml and the plugin manifests agree.
#
# What is deliberately *not* renamed: the console script stays `geo` because it
# is what every command in every doc and skill types, the import package stays
# `geo_audit`, and the plugin stays `geo` so skills remain `/geo:audit`.
PRODUCT_NAME = "SEOmator GEO Audit Skill"
DIST_NAME = "seomator-geo-audit"
REPO_URL = "https://github.com/seo-skills/geo-audit-skill"

SCHEMA_VERSION = 1
SCORING_VERSION = "1.0"
# 2: `<article>` is only the content root when the page has exactly one. Taking
#    the first of many reduced every listing page to a single teaser card.
NORMALIZER_VERSION = 2
STATE_VERSION = 1
