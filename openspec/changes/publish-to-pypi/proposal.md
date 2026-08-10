## Why

Every stage so far has assumed the user has cloned the repo: the README's
only install path is `uv sync --all-groups`, and every documented command
is prefixed `uv run`. That makes vacancy-radar unusable as a *tool* —
someone who wants to track their job applications, or point Claude Desktop
at the MCP server, has to become a contributor first. Publishing to PyPI
turns the two existing console scripts into things `uv tool install
vacancy-radar` and `uvx vacancy-radar` can reach, and lets an MCP client
config be a single `uvx` line instead of a checkout path.

The prerequisites are already in place — the package builds with hatchling,
`__version__` reads from installed metadata rather than a hardcoded string,
`[project.scripts]` declares both entry points, and the name
`vacancy-radar` is unclaimed on PyPI. What is missing is publishable
metadata, a release workflow, and a documented procedure.

## What Changes

- **Complete the distribution metadata in `pyproject.toml`.** Today the
  `[project]` table has no `authors`, no `keywords`, no `classifiers`, no
  `[project.urls]`, and declares `license = "MIT"` without a
  `license-files` entry — so the wheel ships without LICENSE and the PyPI
  page renders as an unattributed stub. Add all of these, and pin a
  `requires` floor on hatchling new enough for PEP 639 license
  expressions.
- **Publish via PyPI Trusted Publishing (OIDC), not an API token.** A new
  `.github/workflows/release.yml` triggers on `v*` tags, builds sdist +
  wheel with `uv build`, and uploads with `uv publish` from a GitHub
  Environment gated to the release job. No long-lived secret is stored in
  the repository.
- **Verify the artifact before it is published, not after.** The release
  workflow builds, then installs the built wheel into a clean throwaway
  environment and runs `vacancy-radar --version` against it. A wheel whose
  entry point is broken, or whose dependency set does not resolve outside
  this repo's `uv.lock`, fails the release instead of becoming an
  unyankable `0.x.y` on PyPI.
- **Make the version a release input rather than a hand-edited constant.**
  The workflow asserts that the `v*` tag matches `[project].version`;
  a mismatch aborts before any upload. Bumping the version stays a manual
  edit + tag, which suits a project with one maintainer.
- **Add a TestPyPI dry-run path** so the first real upload is not also the
  first upload ever. TestPyPI's Trusted Publisher is configured alongside
  the PyPI one, and the release workflow accepts a `workflow_dispatch`
  input selecting the TestPyPI target.
- **Rewrite the README's install section around the installed tool.**
  `uvx vacancy-radar` for one-off runs, `uv tool install vacancy-radar`
  for a persistent CLI, `uvx --from vacancy-radar vacancy-radar-mcp` for
  the MCP server (the second script is not reachable by bare `uvx`,
  because the script name differs from the package name). The `uv run`
  form stays, relabelled as the contributor path.
- **Document the release procedure** in a new `docs/releasing.md`: version
  bump, tag, what the workflow does, how to verify, and what to do when a
  release goes wrong (yank, never re-upload a version).
- Add a `CHANGELOG.md` with a `0.1.0` entry for the existing `v0.1.0` tag
  and an `[Unreleased]` section, so the first published release has
  release notes to point at.

**Not in scope:** splitting `lancedb` and `fastembed` into optional
extras. They are ~hundreds of MB resolved, which makes `uvx
vacancy-radar` a slow first run, but every command in the CLI except
`--version` reaches the index eventually, so an extras split would ship a
default install that cannot search. Deferred to its own change with its
own measurements.

## Capabilities

### New Capabilities

- `distribution-metadata`: what the published `vacancy-radar`
  distribution must declare — name, version source, license and its
  included file, authors, project URLs, classifiers, Python floor — and
  the requirement that the built wheel and sdist contain the package,
  both console scripts, the README as long description, and the LICENSE.
- `release-workflow`: the tag-triggered GitHub Actions release —
  tag/version agreement check, `uv build`, installed-wheel smoke test,
  Trusted Publishing upload with no stored token, TestPyPI dry-run
  target, and the constraint that a failed verification blocks the
  upload.
- `installed-usage`: what a user gets from a published install — `uvx
  vacancy-radar` and `uv tool install vacancy-radar` expose the CLI,
  `uvx --from vacancy-radar vacancy-radar-mcp` exposes the MCP server,
  and both work in an environment with no checkout and no `uv.lock`.

### Modified Capabilities

- `package-skeleton`: `__version__` is currently allowed to fall back to
  `"0.0.0"` when metadata is absent. That fallback is correct for a
  source tree, but it must not be what a *published* install reports —
  add a requirement that in an installed distribution `__version__`
  equals the distribution metadata version, and that `vacancy-radar
  --version` prints it. The existing requirements (usage on no args,
  non-zero on unknown command, three-part version string, import without
  the search stack) are unchanged.
- `dev-workflow`: CI currently covers push-to-main and pull requests
  only. Add a requirement that the release workflow is separate from
  `ci.yml`, runs on `v*` tags, and that release-time publishing is gated
  on a protected GitHub Environment rather than a repository secret.

## Impact

- **Modified files:** `pyproject.toml` (metadata block, hatchling floor,
  `license-files`), `README.md` (install section rewritten; MCP client
  config example switched to `uvx`).
- **New files:** `.github/workflows/release.yml`, `docs/releasing.md`,
  `CHANGELOG.md`.
- **New tests:** a packaging test asserting the built wheel's metadata
  (both entry points present, license file included, classifiers
  non-empty) — built from the repo under test, so it runs in normal
  `pytest` without network access.
- **No runtime dependency changes**, no source changes under
  `src/vacancy_radar/`, and no behavior change for anyone running from a
  checkout.
- **Out-of-repo prerequisites the maintainer must do by hand** (they
  cannot be scripted from here): register the `vacancy-radar` project's
  Trusted Publisher on PyPI and TestPyPI for repo `Akay7/vacancy-radar`,
  workflow `release.yml`, environment `pypi` / `testpypi`; create those
  two GitHub Environments. `docs/releasing.md` records these as a
  one-time setup checklist.
- **Irreversibility to be aware of:** a version published to PyPI can be
  yanked but never replaced or re-uploaded. The pre-upload smoke test and
  the TestPyPI dry run exist because of this.
