# Releasing

Everything up to the tag is automated and already verified by CI. One step needs a
person with account access, and only once.

## One-time: let GitHub publish to PyPI

*Done for this project on 2026-09-21; 0.4.0 was the first release through it. Kept for
a fork, or for moving the project to another PyPI account.*

Publishing uses [trusted publishing](https://docs.pypi.org/trusted-publishers/), so no
long-lived token is stored in this repository. Nothing can be published until the
publisher exists on PyPI.

For a project that has never been published, use the *pending* publisher form at
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

1. `VERSION` holds the number. Update it, give `CHANGELOG.md` a section with the same
   number and today's date, and set `ref` in `.claude-plugin/marketplace.json` to the
   new tag. The release workflow refuses a tag that disagrees with `VERSION` or the
   changelog, and the skill lint fails if `ref` and `VERSION` disagree.
2. Run the checks locally - `python tools/gen_docs.py --check`, `python tools/lint_skills.py`,
   `pytest`, and the build check below.
3. Commit, tag, and push the two together:

   ```bash
   git tag -a "v$(cat VERSION)" -m "v$(cat VERSION)"
   git push origin main "v$(cat VERSION)"
   ```

   Together, because the marketplace on `main` now names the new tag: pushed apart,
   a plugin install in between would look for a tag that does not exist yet.

The tag starts `release.yml`, which verifies the tag against `VERSION` and the
changelog, runs the suite plus the skill lint on three operating systems, builds the
wheel and the sdist, and publishes. A failure stops before the upload, and PyPI never
sees a version it did not accept, so the tag can be deleted and pushed again.

A release is also the only way a skill change reaches someone who already installed
the plugin. `/plugin update` compares `version` and nothing else: pushing a skill fix
to `main` without a bump leaves every installed copy as it was, and reports it as
current.

## Why the marketplace names a tag

The plugin's `source` in `.claude-plugin/marketplace.json` is the release tag, not
`main`, so every install gets exactly a release: two users on one version have the same
skills, and a skill never depends on a CLI change PyPI does not have yet. It is a `url`
source, not `github`: a `github` source clones over SSH with no HTTPS fallback, so it
fails for anyone without GitHub keys, and the lint rejects it. Both were verified by
installing from a clean config.

## Checking a build without releasing

```bash
uv build && uvx twine check dist/*
```

`twine check` validates the metadata PyPI will reject on upload, which is the failure
that otherwise appears only after a tag is already pushed and public.
