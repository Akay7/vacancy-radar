# Releasing

vacancy-radar publishes to PyPI from GitHub Actions
(`.github/workflows/release.yml`), authenticated with PyPI Trusted
Publishing. There is no PyPI token in this repository, in CI secrets, or
in anyone's shell history — the workflow mints a short-lived OIDC token
per run and exchanges it with the index.

**The one rule that shapes everything below: a version published to PyPI
can be yanked, but never replaced or re-uploaded.** The workflow
therefore builds once, installs and runs that exact artifact in a clean
environment, and only then uploads it.

## One-time setup

Do these once, by hand. None of it can be scripted from this repo.

### 1. Create the GitHub Environments

In **Settings → Environments**, create two environments with these exact
names:

- `pypi`
- `testpypi`

They hold no secrets. They exist to be a named, protectable boundary:
the workflow's `publish` job runs under one of them, deployments to them
are logged separately from workflow runs, and a required-reviewer rule
can be attached later without editing the workflow.

### 2. Register the Trusted Publisher on both indexes

On **https://pypi.org** and again on **https://test.pypi.org**, under
the project's *Publishing* settings (or "pending publisher" if the
project does not exist on that index yet), register a GitHub publisher
with exactly these four values:

| field | value |
| ----- | ----- |
| PyPI project name | `vacancy-radar` |
| Owner | `Akay7` |
| Repository | `vacancy-radar` |
| Workflow name | `release.yml` |
| Environment | `pypi` on PyPI, `testpypi` on TestPyPI |

All four are matched exactly. A mismatch does not fail early — it
surfaces as an opaque **403 at the upload step** of an otherwise-green
release. The TestPyPI dry run below exists to find that before a real
version is at stake.

> **Renaming or moving `release.yml` breaks publishing.** PyPI binds the
> publisher to the workflow *filename*. If the file is ever renamed,
> update the Workflow name field on both indexes in the same change.

### 3. Confirm the name is still ours

The name `vacancy-radar` was unclaimed when this process was written,
and an unclaimed name is not a reserved one. Before the first upload:

```bash
curl -s -o /dev/null -w '%{http_code}\n' https://pypi.org/pypi/vacancy-radar/json
```

`404` means it is still available. Anything else means someone else took
it, and the fallback is renaming the distribution (metadata, the
`importlib.metadata.version` argument in `src/vacancy_radar/__init__.py`,
and the docs) before releasing.

## Cutting a release

1. **Bump the version.** Edit `[project].version` in `pyproject.toml`,
   if it does not already hold the version you are about to release.
   That field is the single source of truth — `vacancy_radar.__version__`
   reads it back out of the installed distribution's metadata, so
   nothing else needs editing.
2. **Update the changelog.** Move the `[Unreleased]` entries in
   `CHANGELOG.md` into a new `## [X.Y.Z] - YYYY-MM-DD` section. The entry
   must exist *before* the tag — it is what the release points at.
3. **Commit** both, on `main`, and **push. Wait for CI to go green
   before tagging.**

   ```bash
   git push origin main
   ```

   This step is the one that runs the test suite. The release workflow
   deliberately does not: it builds the wheel, installs it in a clean
   environment, and runs `--version` and `--help`, which catches a
   broken entry point or an unresolvable dependency set but not a
   broken `search`. Tagging a commit whose CI is red, or that never ran
   CI, publishes it anyway — and the version number is then spent.

4. **Tag and push the tag:**

   ```bash
   git tag vX.Y.Z
   git push origin vX.Y.Z
   ```

   The tag must be `v` + exactly the version in `pyproject.toml`. The
   workflow checks this and fails the run before anything is uploaded if
   they disagree — see "When something goes wrong" below.
5. **Watch the run** under Actions → Release. It is three jobs in order:

   - **build** — `uv build`, then assert the tag agrees with the built
     version, then upload `dist/` as a workflow artifact.
   - **verify** — install *that wheel* into a fresh venv with no repo
     checkout and no `uv.lock` in sight, then run
     `vacancy-radar --version` (asserting it prints the released
     version) and `vacancy-radar-mcp --help` (asserting exit 0).
   - **publish** — download the same artifact and upload it with
     `pypa/gh-action-pypi-publish`. It does not rebuild, so what shipped
     is byte-identical to what was verified. The action also signs and
     uploads a PEP 740 attestation for each file, so the release's
     Security tab on PyPI shows provenance linking it to this repo and
     workflow.

6. **Check the project page** at https://pypi.org/project/vacancy-radar/
   — README rendered, MIT license shown, repository and issue links
   present.

## Dry run against TestPyPI

Before the first real release, and any time the release machinery
itself changes, run the whole chain against TestPyPI:

1. Actions → Release → **Run workflow**. The `target` input defaults to
   `testpypi`; leave it. (Manual runs need no tag — the version
   agreement check only applies to tag-triggered runs.)
2. Confirm build and verify both pass, and that publish succeeds — a 403
   here means the Trusted Publisher registration above does not match.
3. Install from TestPyPI into a scratch environment and exercise it:

   ```bash
   uv venv /tmp/vr-check
   uv pip install --python /tmp/vr-check/bin/python \
       --index-url https://test.pypi.org/simple/ \
       --extra-index-url https://pypi.org/simple/ \
       vacancy-radar
   /tmp/vr-check/bin/vacancy-radar --version
   /tmp/vr-check/bin/vacancy-radar-mcp --help
   ```

   The extra index is required: TestPyPI does not carry this project's
   runtime dependencies.

> **TestPyPI consumes version numbers permanently too.** A dry run at
> `0.2.0` means `0.2.0` can never be uploaded to TestPyPI again. For
> repeat attempts at the same release, use a dev suffix
> (`0.2.0.dev1`, `0.2.0.dev2`, …) rather than burning the real number.

## When something goes wrong

**The tag and `pyproject.toml` disagree.** The build job fails at the
version-agreement check and nothing is uploaded. Fix whichever is wrong,
then delete and re-push the tag:

```bash
git tag -d vX.Y.Z && git push origin :refs/tags/vX.Y.Z
# fix, commit, then tag again
```

**Verification failed.** The publish job never runs — this is the
mechanism working. The usual cause is a dependency that resolves in this
repo only because `uv.lock` pins it, so check `[project.dependencies]`
floors before retrying.

**A bad version reached PyPI.** It cannot be replaced. Re-uploading the
same version is rejected by the index, and deleting a release does not
free the number. The only recovery is:

1. **Yank** the bad version on PyPI (project → Manage → Releases →
   Options → Yank). Yanking leaves it installable for anyone who pins it
   exactly, but takes it out of ordinary resolution.
2. **Fix, bump to a new patch version, and release again** following the
   steps above.

Never delete a release in the hope of re-uploading it — the version
number stays consumed either way, and deleting only removes the artifact
for people who already depend on it.
