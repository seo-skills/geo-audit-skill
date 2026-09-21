# Releasing

Everything up to the tag is automated and already verified by CI. Two steps need a
person with account access, and they are only needed once.

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

Then create the matching GitHub environment - Settings → Environments → **New
environment** → `pypi`. The `publish` job declares `environment: pypi`, so the job
waits for an environment that does not exist rather than failing loudly.

Both names must match exactly. A mismatch surfaces at the end of the release run as a
rejected OIDC token, after the build has already succeeded.

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

## Checking a build without releasing

```bash
uv build && uvx twine check dist/*
```

`twine check` validates the metadata PyPI will reject on upload, which is the failure
that otherwise appears only after a tag is already pushed and public.

## After the first publish

`README.md` carries a note saying the package is not on PyPI yet, and offers a
`git+https://` install instead. Once the release lands, delete that note - a test in
`tests/test_docs.py` exists to be deleted with it.
