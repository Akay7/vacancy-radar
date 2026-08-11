## Context

vacancy-radar builds today — `uv build` produces a wheel and an sdist from
hatchling with `packages = ["src/vacancy_radar"]` — but nothing has ever
been published. The gap between "builds" and "publishable" is metadata,
process, and trust:

- `[project]` carries name, version, description, readme, `requires-python`,
  `license = "MIT"`, dependencies, and two scripts. It has no `authors`, no
  `classifiers`, no `[project.urls]`, and no `license-files`. PEP 639's
  SPDX-string `license` field requires a reasonably recent hatchling to be
  interpreted correctly, and without `license-files` the LICENSE at the
  repo root is not guaranteed into the wheel.
- `__version__` already resolves through `importlib.metadata.version(
  "vacancy-radar")` with a `"0.0.0"` fallback, so `[project].version` in
  `pyproject.toml` is the single source of truth. Nothing needs a
  version-bump tool.
- The repo has one workflow, `ci.yml`, on push-to-main and PRs. There is no
  release trigger and no PyPI credential anywhere.
- `v0.1.0` is already tagged in git, but nothing was published under it.
- The name `vacancy-radar` returns 404 from the PyPI JSON API — unclaimed as
  of this change's authoring. Whoever uploads first owns it.

Constraints inherited from the project: uv is the toolchain (so `uv build`
and `uv publish`, not `python -m build` + `twine`); Python floor is 3.12;
the maintainer is a single person, so the process must not assume a release
manager or a review queue.

One structural fact drives several decisions below: `[project.scripts]`
declares **two** entry points, `vacancy-radar` and `vacancy-radar-mcp`.
`uvx <name>` runs the console script whose name matches what was requested,
resolving the package from the same string. `uvx vacancy-radar` therefore
works; `uvx vacancy-radar-mcp` would try to install a *distribution* called
`vacancy-radar-mcp`, which will not exist. The MCP server's invocation must
be `uvx --from vacancy-radar vacancy-radar-mcp`, and the docs must say so
rather than leave the user to discover it from a resolution error.

## Goals / Non-Goals

**Goals:**

- A user with only `uv` installed can run the CLI (`uvx vacancy-radar`),
  install it persistently (`uv tool install vacancy-radar`), and wire the
  MCP server into a client config, with no checkout and no `uv.lock`.
- Releases are produced by tagging, not by a laptop. No PyPI token is
  stored in the repository or in a maintainer's shell history.
- A broken artifact is caught *before* it reaches PyPI, because PyPI
  version numbers are permanently consumed.
- The PyPI project page is a real landing page: description, README,
  license, links to the repo and the issue tracker.

**Non-Goals:**

- Splitting `lancedb` / `fastembed` into optional extras. Real concern
  (first `uvx` run pulls hundreds of MB), but every CLI command except
  `--version` reaches the index, so a slim default would be a default that
  cannot work. Separate change, with measurements.
- Automated version bumping, conventional-commit-driven releases, or a
  release-please style PR bot. One maintainer, low release frequency; the
  ceremony would cost more than it saves.
- Publishing to conda-forge, Homebrew, or shipping standalone binaries.
- Signing artifacts beyond what PyPI's Trusted Publishing attestations give
  for free.
- Any change to `src/vacancy_radar/` behavior. This change is packaging and
  process only.

## Decisions

### Decision 1: Trusted Publishing (OIDC), not a stored API token

`uv publish` authenticates with a short-lived OIDC token minted by GitHub
Actions for the workflow, exchanged with PyPI for an upload token scoped to
this project and valid for minutes. The alternative — a PyPI API token in
`secrets.PYPI_TOKEN` — is a long-lived credential that grants upload rights
to anyone who can run a workflow, including a workflow added by a malicious
PR if branch protections are ever misconfigured.

Trusted Publishing binds the upload to four things checked by PyPI: the
repository (`Akay7/vacancy-radar`), the workflow filename
(`release.yml`), the environment name, and the identity provider. A fork
cannot mint a usable token; a different workflow in the same repo cannot
either.

Cost: a one-time manual setup on pypi.org and test.pypi.org that cannot be
scripted from this repo, plus the requirement that the job declare
`permissions: id-token: write`. Recorded as a setup checklist in
`docs/releasing.md` rather than left implicit.

Alternative considered: `pypa/gh-action-pypi-publish`. It is the
better-known route and also supports OIDC, but it shells out to twine and
would be the only non-uv tool in the pipeline. `uv publish` covers the same
ground with the toolchain already in use.

### Decision 2: Gate on a GitHub Environment, and make the environment the audit point

Both upload jobs run with `environment: pypi` (or `testpypi`). This matters
for two reasons beyond matching PyPI's Trusted Publisher config: the
environment is where a required-reviewer rule can be attached later without
touching the workflow, and environment deployments are logged separately
from workflow runs, so "what was published, when, by which run" is
answerable after the fact.

The environment holds no secrets. Its entire job is to be a named,
protectable boundary.

### Decision 3: Verify the built wheel in a clean environment before uploading

The release workflow is three ordered jobs, not one:

1. **build** — assert tag/version agreement, `uv build`, upload
   `dist/` as a workflow artifact.
2. **verify** — download `dist/`, install *the built wheel* into a fresh
   throwaway venv with `uv` (no `--frozen`, no `uv.lock`, no repo checkout
   on the path), run `vacancy-radar --version`, and assert the output
   equals the tag's version. Also assert `vacancy-radar-mcp --help` exits
   0.
3. **publish** — needs `verify`; downloads the *same* artifact and uploads
   it. It does not rebuild, so what was tested is byte-identical to what is
   published.

The clean-venv detail is the point. `uv sync` in the repo resolves from
`uv.lock`, which can mask a dependency that is under-specified in
`[project.dependencies]` — a floor that is too low, or a transitive
dependency that only `uv.lock` was pinning. Installing the wheel from a
directory with no lockfile is the only way that class of bug surfaces
before a user hits it. A `pip install vacancy-radar` that fails to resolve
is not fixable by editing; it needs a new version number.

Alternative considered: publish to TestPyPI on every tag and to PyPI only
after a manual approval. Rejected as the default path — it doubles the
version-number burn rate on TestPyPI and adds a wait to every release. The
TestPyPI target exists (Decision 5) but is opt-in.

### Decision 4: Tag is the trigger; tag and `[project].version` must agree

Trigger is `push: tags: ['v*']`. The build job's first step compares the
tag (stripped of `v`) against `[project].version` read back out of the
built metadata, and fails the job on mismatch.

This exists because the two can drift in both directions and both are
silent: tagging `v0.2.0` while pyproject still says `0.1.0` would attempt
to re-upload an already-published version (a hard PyPI error, but only
discovered at the last step), and bumping pyproject without tagging
publishes nothing at all. Checking in the build job means the failure is
the first thing that happens, not the last.

Rejected: deriving the version from the tag via `hatch-vcs` /
`setuptools-scm`. It removes the drift class entirely, but it also makes
`[project].version` dynamic, which means a source checkout without git
history (an sdist, a tarball download) has no version — and
`vacancy_radar.__version__` is asserted by an existing test to be a
three-part numeric string. Keeping the version literal in `pyproject.toml`
keeps that guarantee and keeps the file readable. The drift is caught by a
three-line check.

### Decision 5: TestPyPI is a `workflow_dispatch` input, not a separate workflow

`workflow_dispatch` with a `target` choice input (`testpypi` | `pypi`,
defaulting to `testpypi`) runs the identical build → verify → publish
chain against the chosen index. Duplicating the workflow into
`release-test.yml` would mean the dry run exercises a *different* file than
the real release, which defeats the purpose of a dry run.

Because TestPyPI is a real index with real permanent version numbers,
`docs/releasing.md` notes that dry runs consume versions there too and
suggests a `.devN` local suffix for repeat attempts.

### Decision 6: Packaging assertions are a pytest test against a locally built wheel

A new `tests/test_packaging.py` builds the distribution into a temp dir and
inspects the wheel's `METADATA` and `entry_points.txt`: both console
scripts present, `License-File: LICENSE` present, `Classifier:` lines
non-empty, `Requires-Python` present, long-description content type set.

Putting this in pytest rather than only in the release workflow means the
metadata contract is enforced on every PR — the moment someone deletes a
classifier block, CI says so, instead of the next release shipping a
degraded PyPI page. The test builds via `uv build` in a subprocess and
skips (rather than fails) if `uv` is not on PATH, so it stays honest in a
bare environment. It needs no network: `uv build` with hatchling does not
resolve dependencies.

### Decision 7: `license-files` is explicit, and `license` stays an SPDX string

`license = "MIT"` as a bare string is PEP 639's SPDX expression form,
which requires hatchling ≥ 1.27 to be emitted as `License-Expression:`
rather than misinterpreted. The build-system `requires` gains that floor.
`license-files = ["LICENSE"]` is added so the file is guaranteed into both
the wheel's `.dist-info` and the sdist, and asserted by Decision 6's test.

Without both halves, the PyPI page shows no license and the wheel ships
none — a real problem for anyone whose employer has a policy about
unlicensed dependencies.

### Decision 8: README documents the installed tool first, the checkout second

The README's `## Install` becomes two subsections: **Use it** (`uvx
vacancy-radar …`, `uv tool install vacancy-radar`) and **Work on it**
(`uv sync --all-groups`, `uv run …`). Command examples in the body keep
their `uv run` prefix — rewriting sixty-odd lines to be prefix-agnostic
would churn the whole document — but the install section states plainly
that an installed user drops the `uv run`.

The MCP section's example changes from `uv run vacancy-radar-mcp --vault
…` to a client-config JSON block using `uvx --from vacancy-radar
vacancy-radar-mcp`, because that is the form a user actually pastes into
Claude Desktop, and because the `--from` requirement (see Context) is
non-obvious enough that showing the wrong form once would be a support
burden.

## Risks / Trade-offs

**A published version can never be replaced, only yanked.** → The three-job
build/verify/publish split (Decision 3) plus the opt-in TestPyPI run
(Decision 5) mean the artifact is installed and executed in a clean
environment before upload. `docs/releasing.md` documents yank-and-bump as
the only recovery, explicitly, so the instinct to "just re-upload" never
gets tried.

**The name `vacancy-radar` is unclaimed but not reserved.** Anyone can take
it before the first release. → The first release should be cut soon after
this change lands; `docs/releasing.md` puts "confirm the name is still
ours" in the one-time setup checklist. If it is taken by then, the fallback
is a rename, which is cheap now (metadata + `importlib.metadata.version`
argument + docs) and expensive later.

**Trusted Publishing setup is out-of-band and easy to get subtly wrong.**
The environment name, workflow filename, and repo must match exactly on
both PyPI and TestPyPI; a mismatch surfaces as an opaque 403 at the upload
step of an otherwise-green release. → The checklist in `docs/releasing.md`
lists the exact four values to enter, and the TestPyPI dry run is the
intended way to discover a misconfiguration without burning a real version.

**`uvx vacancy-radar` will be slow on first run** — `lancedb` + `fastembed`
resolve to hundreds of MB, and fastembed downloads its model on first
search on top of that. → Not solved here (explicit non-goal). The README's
install section states the expectation so a 90-second first run reads as
"large dependencies", not "hung". The extras split gets its own change.

**Renaming or moving `release.yml` silently breaks publishing**, because
PyPI's Trusted Publisher is bound to the filename. → Noted in
`docs/releasing.md` next to the setup checklist; the failure is loud (403
at upload) rather than silent, and the fix is a one-field edit on PyPI.

**The packaging test shells out to `uv build`**, so it is slower than the
rest of the suite and depends on a tool outside the Python environment. →
It skips cleanly when `uv` is absent, and builds into a temp dir so it
never touches the repo's `dist/`. CI always has `uv`, so coverage is real
where it matters.
