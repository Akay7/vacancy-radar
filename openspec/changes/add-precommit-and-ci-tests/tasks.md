## 1. Dependencies

- [x] 1.1 Add `pre-commit` to the `dev` dependency group in
      `pyproject.toml` and run `uv sync --all-groups` to update
      `uv.lock`.

## 2. Pre-commit configuration

- [x] 2.1 Create `.pre-commit-config.yaml` with the
      `astral-sh/ruff-pre-commit` repo (hooks: `ruff` with `--fix`,
      `ruff-format`), pinned to a `rev` compatible with the `ruff`
      version in `pyproject.toml`.
- [x] 2.2 Add `pre-commit/pre-commit-hooks` hygiene hooks:
      `trailing-whitespace`, `end-of-file-fixer`, `check-yaml`,
      `check-toml`, `check-merge-conflict`.
- [x] 2.3 Verify locally: `uv run pre-commit run --all-files` passes
      clean on the current codebase.

## 3. CI enforcement

- [x] 3.1 In `.github/workflows/ci.yml`'s `test` job, replace the
      "Lint" (`uv run ruff check .`) and "Check formatting"
      (`uv run ruff format --check .`) steps with a single step
      running `uv run pre-commit run --all-files`.
- [x] 3.2 Confirm the `pytest` step is untouched and still runs after
      the new pre-commit step.

## 4. Documentation

- [x] 4.1 Add a "Pre-commit hooks" note to `README.md`'s Development
      section documenting `uv run pre-commit install` for local setup.

## 5. Verification

- [x] 5.1 Confirm scenarios in `specs/dev-workflow/spec.md` hold:
      a lint violation and a malformed YAML file each block a local
      commit once hooks are installed.
- [ ] 5.2 Open a throwaway PR (or push to a branch) to confirm the
      updated CI `test` job runs `pre-commit run --all-files` followed
      by `pytest`, with no leftover standalone `ruff check`/
      `ruff format --check` steps.
