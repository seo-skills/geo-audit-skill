# Releasing

Everything up to the tag is automated and already verified by CI. One step needs a
person with account access, and only once.

## One-time: let GitHub publish to PyPI

Publishing uses [trusted publishing](https://docs.pypi.org/trusted-publishers/), so no
long-lived token is stored in this repository. Nothing can be published until the
publisher exists on PyPI.

The project has never been published, so use the *pending* publisher form at
<https://pypi.org/manage/account/publishing/> and paste these exact values:

| Field | Value |
|---|---|
| PyPI project name | `seomator-geo-audit` |
| Owner | `seo-skills` |
| Repository name | `geo-audit-skill` |
| Workflow name | `release.yml` |
| Environment name | `pypi` |

The environment name must match the workflow's `environment: pypi` exactly. A
mismatch surfaces at the end of the release run as a rejected OIDC token, after the
build has already succeeded.

There is no need to create the `pypi` environment on GitHub: the first run that
references it creates it, with no protection rules. Create it yourself only to add
one. A required reviewer on `pypi` lets a pushed tag verify, test and build on its
own, then wait for a person before anything reaches PyPI - the last point at which a
release can still be stopped, because PyPI never accepts the same version twice.

## Each release

1. `VERSION` holds the number. Update it, and give `CHANGELOG.md` a section with the
   same number and today's date - the release workflow checks both and refuses a tag
   that disagrees with either.
2. Push to `main` and let CI go green. The release re-runs the suite on three
   operating systems anyway, so a red `main` only wastes a tag.
3. Tag and push:

   ```bash
   git tag -a "v$(cat VERSION)" -m "v$(cat VERSION)"
   git push origin "v$(cat VERSION)"
   ```

The tag starts `release.yml`, which verifies the tag against `VERSION` and the
changelog, runs the suite plus the skill lint on three operating systems, builds the
wheel and the sdist, and publishes. No step needs a person once the publisher exists.

A release is also the only way a skill change reaches someone who already installed
the plugin. `/plugin update` compares `version` and nothing else: pushing a skill fix
to `main` without a bump leaves every installed copy as it was, and reports it as
current.

## Checking a build without releasing

```bash
uv build && uvx twine check dist/*
```

`twine check` validates the metadata PyPI will reject on upload, which is the failure
that otherwise appears only after a tag is already pushed and public.

## After the first publish

**Pin the marketplace to the release.** Until now the plugin's `source` is `./`, so
the marketplace serves whatever is on `main`: two users can both be on 0.4.0 with
different skills, and a skill on `main` can depend on a CLI change PyPI does not have
yet. Once the tag exists, point the entry in `.claude-plugin/marketplace.json` at it:

```json
"source": {
  "source": "url",
  "url": "https://github.com/seo-skills/geo-audit-skill.git",
  "ref": "v0.4.0"
}
```

From then on every release bumps `ref` alongside `VERSION`, and the skill lint fails
if they disagree. Use `url`, not `github`: a `github` source clones over SSH with no
HTTPS fallback, so it fails for anyone without GitHub keys - the lint rejects it.
Both were verified by installing from a clean config, not assumed.

`README.md` carries a note saying the package is not on PyPI yet. Delete it once the
release lands. That note is the switch for every other install instruction: with it
gone, the skill lint and the doc tests fail on each skill preflight and each doc page
that still offers the source install, naming every one, so nothing is left pointing
at a workaround. `test_the_prepublication_note_disappears_once_the_package_is_published`
in `tests/test_docs.py` can go at the same time.
