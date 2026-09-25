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

CLI_VERSION = "1.2.0"

# The product's public identifiers, in one place so they cannot drift apart.
# `tools/lint_skills.py` asserts pyproject.toml and the plugin manifests agree.
#
# What is deliberately *not* renamed: the console script stays `geo` because it
# is what every command in every doc and skill types, the import package stays
# `geo_audit`, and the plugin stays `geo` so skills remain `/geo:audit`.
PRODUCT_NAME = "SEOmator GEO Audit Skill"
DIST_NAME = "seomator-geo-audit"
REPO_URL = "https://github.com/seo-skills/geo-audit-skill"
# Flip when the first release is on PyPI. `geo doctor` runs from the wheel and
# cannot read the README, so it keeps this copy of the switch; a test holds it
# to the README's "Not on PyPI yet" note, which rules every other install line.
PUBLISHED_ON_PYPI = True


def install_target(extra: str | None = None) -> str:
    """What `uv tool install` should be given today.

    Before the first release the package name resolves to nothing, so every hint
    that named it was a dead end - `geo doctor`'s browser-extra hint and the
    report's PDF-unavailable message among them. The source install works now
    and keeps working after.

    The browser extra also needs its command: `uv tool` puts only the tool's
    own commands on PATH, so the `playwright install chromium` every hint runs
    next failed with command not found until the flag exposed it.
    """
    if PUBLISHED_ON_PYPI:
        target = f"'{DIST_NAME}[{extra}]'" if extra else DIST_NAME
    else:
        source = f"git+{REPO_URL}"
        target = f"'{DIST_NAME}[{extra}] @ {source}'" if extra else source
    if extra == "browser":
        target += " --with-executables-from playwright"
    return target

SCHEMA_VERSION = 1
# 2.0: authorship, attribution and Article markup are scored on articles only. A
#      major bump because it moves the composite of a site that did not change,
#      and `compare` must refuse to report that as the site moving.
# 3.0: extractability scores evidence that content needs JavaScript, not length.
#      Short server-rendered pages had been capped and told to server-render.
# 4.0: expertise reads the article's author, not the first Person on the page (a
#      site-wide founder), and category, tag and author archives are not articles.
SCORING_VERSION = "4.0"
# 2: `<article>` is only the content root when the page has exactly one. Taking
#    the first of many reduced every listing page to a single teaser card.
# 3: and only when it carries the page's text. A lone `<article>` around a promo
#    banner reduced every page on userguiding.com to the banner.
NORMALIZER_VERSION = 3
STATE_VERSION = 1
