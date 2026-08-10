## 1. Distribution metadata

- [ ] 1.1 Add `authors` and `keywords` to `[project]` in `pyproject.toml`
- [ ] 1.2 Add a `classifiers` list to `[project]`: development status,
      `License :: OSI Approved :: MIT License`, `Intended Audience ::
      End Users/Desktop`, `Programming Language :: Python :: 3`,
      `Programming Language :: Python :: 3.12`, and an environment/topic
      classifier
- [ ] 1.3 Add a `[project.urls]` table with `Homepage`, `Repository`,
      and `Issues` pointing at `https://github.com/Akay7/vacancy-radar`
- [ ] 1.4 Add `license-files = ["LICENSE"]` to `[project]` and raise the
      `[build-system].requires` floor to `hatchling>=1.27` so the SPDX
      `license = "MIT"` string is emitted as `License-Expression`
- [ ] 1.5 Run `uv build` and inspect the wheel's `METADATA`,
      `entry_points.txt`, and `.dist-info/licenses/` by hand to confirm
      authors, project URLs, classifiers, `Description-Content-Type`,
      both console scripts, and the LICENSE are all present
- [ ] 1.6 Confirm the sdist contains `LICENSE`, `README.md`,
      `pyproject.toml`, and the full `src/vacancy_radar` tree

## 2. Packaging test

- [ ] 2.1 Add `tests/test_packaging.py` that runs `uv build --out-dir
      <tmp_path>` in a subprocess, skipping the module when `uv` is not
      on PATH
- [ ] 2.2 Assert the wheel's `entry_points.txt` declares both
      `vacancy-radar` and `vacancy-radar-mcp` under `console_scripts`
- [ ] 2.3 Assert the wheel's `METADATA` has a `License-Expression`, at
      least four `Classifier` lines, at least one `Project-URL`, an
      author field, a `Requires-Python` admitting 3.12, and a Markdown
      `Description-Content-Type` with a non-empty body
- [ ] 2.4 Assert a `LICENSE` file is present under
      `.dist-info/licenses/` in the wheel and at the root of the sdist
- [ ] 2.5 Mark the test session-scoped (or cache the build via a
      fixture) so the suite builds the distribution at most once, and
      confirm `uv run pytest` stays acceptably fast

## 3. Release workflow

- [ ] 3.1 Create `.github/workflows/release.yml` triggered on
      `push: tags: ['v*']` and on `workflow_dispatch` with a `target`
      choice input (`testpypi` default, `pypi`)
- [ ] 3.2 Write the `build` job: checkout, install uv (pinned as in
      `ci.yml`), `uv build`, then assert the tag with `v` stripped
      equals the version in the built metadata — failing the job on
      mismatch — and upload `dist/` as a workflow artifact
- [ ] 3.3 Make the version-agreement check apply only to tag-triggered
      runs, so a `workflow_dispatch` dry run does not need a tag
- [ ] 3.4 Write the `verify` job: `needs: build`, download the `dist/`
      artifact into a directory with no repo checkout, create a fresh
      venv, install the built wheel from the artifact without
      consulting `uv.lock`, and run `vacancy-radar --version` asserting
      the output matches the built version
- [ ] 3.5 Add `vacancy-radar-mcp --help` to the `verify` job, asserting
      exit 0
- [ ] 3.6 Write the `publish` job: `needs: verify`, `environment` set
      from the target input (`pypi` / `testpypi`), `permissions:
      id-token: write`, download the same artifact, and `uv publish`
      with the index URL selected by the target — no rebuild, no secret
- [ ] 3.7 Confirm the workflow references no PyPI token, username, or
      password secret anywhere
- [ ] 3.8 Verify `.github/workflows/ci.yml` is untouched — same
      triggers, no publish step, no `id-token` permission

## 4. Documentation

- [ ] 4.1 Add `CHANGELOG.md` in Keep a Changelog form with an
      `[Unreleased]` section and a `0.1.0` entry summarizing the stages
      shipped to date (the `v0.1.0` tag already exists)
- [ ] 4.2 Write `docs/releasing.md` one-time setup checklist: register
      the Trusted Publisher on PyPI and on TestPyPI with owner `Akay7`,
      repository `vacancy-radar`, workflow `release.yml`, environments
      `pypi` and `testpypi`; create both GitHub Environments; note that
      renaming `release.yml` breaks publishing until PyPI is updated
- [ ] 4.3 Write the per-release steps in `docs/releasing.md`: bump
      `[project].version`, move the `[Unreleased]` entries into a dated
      version section, commit, tag `vX.Y.Z`, push the tag, watch the
      run
- [ ] 4.4 Document the dry run in `docs/releasing.md`: dispatch the
      workflow against `testpypi`, install from TestPyPI to confirm,
      and note that TestPyPI versions are consumed permanently too
- [ ] 4.5 Document recovery in `docs/releasing.md`: a published version
      can be yanked but never replaced or re-uploaded; recovery is yank
      plus a new patch version
- [ ] 4.6 Rewrite the README's `## Install` into a **Use it** section
      (`uvx vacancy-radar …`, `uv tool install vacancy-radar`) followed
      by a **Work on it** contributor section (`uv sync --all-groups`,
      `uv run …`), stating that installed users drop the `uv run`
      prefix used in the examples below
- [ ] 4.7 State the first-run expectation in the README install
      section: a large dependency download, plus an embedding-model
      download on first search
- [ ] 4.8 Replace the README's MCP invocation with a client-config JSON
      block using `uvx --from vacancy-radar vacancy-radar-mcp --vault
      <path>`, and grep the README and `docs/` to confirm no bare
      `uvx vacancy-radar-mcp` form remains

## 5. Pre-release verification

- [ ] 5.1 Run `uv run pre-commit run --all-files` and `uv run pytest`
      and confirm both pass
- [ ] 5.2 Re-check that `vacancy-radar` is still unclaimed on PyPI
      (`https://pypi.org/pypi/vacancy-radar/json` returns 404) before
      the first upload
- [ ] 5.3 Complete the out-of-band setup from `docs/releasing.md`:
      create the `pypi` and `testpypi` GitHub Environments and register
      both Trusted Publishers
- [ ] 5.4 Dispatch the release workflow against `testpypi` and confirm
      build, version check, and clean-environment verification all pass
- [ ] 5.5 Install from TestPyPI into a scratch environment and run
      `vacancy-radar --version` and `vacancy-radar-mcp --help` against
      it
- [ ] 5.6 Deliberately verify the failure path once: dispatch or tag
      with a mismatched version and confirm the run aborts before any
      upload
- [ ] 5.7 Tag `v0.1.1` (or the agreed first published version), push,
      and confirm the PyPI project page renders the README, license,
      and links
- [ ] 5.8 From a machine with no checkout, confirm `uvx vacancy-radar
      --version`, `uv tool install vacancy-radar`, and `uvx --from
      vacancy-radar vacancy-radar-mcp --vault <path>` all work
