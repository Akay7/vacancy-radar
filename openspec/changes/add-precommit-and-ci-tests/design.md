## Context

CI (`.github/workflows/ci.yml`) already runs `uv run ruff check .`,
`uv run ruff format --check .`, and `uv run pytest` on push/PR to
`main`. Those same checks are not run locally before a commit, so
lint/format failures are only discovered after pushing. This change
introduces `pre-commit` as the local gate and makes CI run the exact
same hook set, so the two never drift apart.

## Goals / Non-Goals

**Goals:**
- Fast, local pre-commit hooks that catch what CI would catch
  (ruff lint + format, plus basic file hygiene) before a commit lands.
- CI runs the identical hook set via `pre-commit run --all-files`,
  replacing the existing separate `ruff check` / `ruff format --check`
  steps rather than running both — so a contributor who skips
  `pre-commit install` still gets caught in CI, with no duplicated
  lint/format execution.
- Keep the existing `pytest` step unchanged — pre-commit is for
  static checks, not test execution (tests stay a separate,
  unaffected step since they're not commit-time-cheap and shouldn't
  block every local commit).

**Non-Goals:**
- Running the full test suite as a pre-commit hook (too slow for a
  per-commit gate; stays a CI-only job).
- Enforcing commit message format or other non-code hygiene not
  already relevant to this repo.
- Changing what `ruff` checks (rule set in `pyproject.toml` is
  untouched).

## Decisions

- **Use `ruff`'s native pre-commit hooks** (`astral-sh/ruff-pre-commit`)
  rather than the `local`/`uv run` hook style. The hook repo pins a
  ruff version and runs against files staged for commit without
  needing a synced `uv` environment, which is faster than shelling out
  through `uv run` on every commit. It mirrors the same `ruff check`
  and `ruff format` commands CI already runs, so behavior stays
  identical to CI's `uv run ruff ...` invocations (same config in
  `pyproject.toml`).
  - Alternative considered: local hooks invoking `uv run ruff ...` —
    rejected because it requires a synced venv for every commit and is
    slower without added benefit, since the ruff version pinned by
    `pre-commit` and the one in `uv.lock` are kept in sync manually
    either way.
- **Add `pre-commit-hooks`' standard hygiene hooks**
  (`trailing-whitespace`, `end-of-file-fixer`, `check-yaml`,
  `check-toml`, `check-merge-conflict`) — cheap, uncontroversial, and
  catch mistakes ruff doesn't (e.g. malformed `ci.yml`).
- **CI enforcement replaces the existing lint/format steps**: in the
  `test` job of `.github/workflows/ci.yml`, replace the "Lint"
  (`uv run ruff check .`) and "Check formatting"
  (`uv run ruff format --check .`) steps with a single
  `uv run pre-commit run --all-files` step, run before the `pytest`
  step. This avoids running ruff twice per CI invocation (once
  directly, once via pre-commit) while still gaining the extra
  hygiene hooks pre-commit adds.
  - Alternative considered: add a separate parallel `pre-commit` job
    alongside the untouched `test` job — rejected because it re-runs
    `ruff check`/`ruff format` a second time per CI invocation for no
    benefit, doubling that part of CI time and creating two sources
    of truth for the same checks.
- **`pre-commit` itself as a `uv` dev dependency** (not a global pipx
  install) so `uv run pre-commit install` works with no extra tooling
  and the version is lockfile-pinned like other dev tools.

## Risks / Trade-offs

- [Hook versions drift from `pyproject.toml`'s `ruff` version, causing
  local pre-commit and CI's `uv run ruff` to disagree] → Both are
  pinned explicitly (ruff-pre-commit hook `rev`, and `ruff` in the
  `dev` dependency group); bumping one should be paired with bumping
  the other, called out in README.
- [Contributors forget to run `pre-commit install` locally] →
  Mitigated by CI's `pre-commit run --all-files` step, which still
  catches unstaged hooks before merge.
- [`--all-files` in CI is slower than a diff-only run] → Acceptable at
  this repo's current size; revisit if the codebase grows large enough
  to matter.

## Migration Plan

No data or runtime migration.
1. Add `.pre-commit-config.yaml` and `pre-commit` dev dependency.
2. Swap the CI "Lint" and "Check formatting" steps for a single
   `pre-commit run --all-files` step.
3. Document `uv run pre-commit install` in README.

Rollback is reverting the CI step swap and deleting the config file;
no other system depends on it.
