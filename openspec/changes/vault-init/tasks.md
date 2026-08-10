## 1. config.py: resolve_target_path

- [x] 1.1 Write `tests/test_config.py::test_resolve_target_path_explicit_overrides_vault_path`
- [x] 1.2 Write `tests/test_config.py::test_resolve_target_path_uses_vault_path_when_no_argument`
- [x] 1.3 Write `tests/test_config.py::test_resolve_target_path_raises_vault_not_configured_when_neither_present`
- [x] 1.4 Write `tests/test_config.py::test_resolve_target_path_returns_a_path_that_does_not_exist_yet`
- [x] 1.5 Extract `resolve_vault_path`'s explicit-then-`VAULT_PATH` precedence into a private `_resolve_candidate_path(explicit) -> Path` (raising `VaultNotConfiguredError` when neither is given); add public `resolve_target_path(explicit=None) -> Path` calling it directly, with no existence/directory/marker check — design.md decision 2
- [x] 1.6 Rewrite `resolve_vault_path` to call `_resolve_candidate_path` then run its own existing existence/directory/marker checks, unchanged in every observable way
- [x] 1.7 Run 1.1-1.4, then run every existing `tests/test_config.py` test for `resolve_vault_path` and confirm all still pass unmodified — 19 passed

## 2. core.py: init_vault

- [x] 2.1 Write `tests/test_core.py::test_init_vault_creates_marker_under_new_path` — nonexistent path, including missing parent directories
- [x] 2.2 Write `tests/test_core.py::test_init_vault_adds_marker_to_existing_directory_without_touching_contents`
- [x] 2.3 Write `tests/test_core.py::test_init_vault_is_a_noop_on_already_initialized_vault` — no filesystem change, `created=False`
- [x] 2.4 Write `tests/test_core.py::test_init_vault_rejects_a_file_target` — typed error, no filesystem change
- [x] 2.5 Write `tests/test_core.py::test_init_vault_explicit_path_overrides_vault_path`
- [x] 2.6 Write `tests/test_core.py::test_init_vault_falls_back_to_vault_path`
- [x] 2.7 Write `tests/test_core.py::test_init_vault_raises_typed_error_when_neither_present`
- [x] 2.8 Add `VaultInitResult` (or equivalent typed result: `path: Path`, `created: bool`) and `core.init_vault(path: str | Path | None = None) -> VaultInitResult`, resolving via `config.resolve_target_path` and handling the four cases (new path, existing-non-vault directory, already-initialized, file-at-target) per design.md decisions 3-4 — used a frozen dataclass, matching `StatusChange`/`Resolution`'s style rather than a `BaseModel` (not MCP-exposed, so no serialization need)
- [x] 2.9 Run 2.1-2.7

## 3. cli.py: init command

- [x] 3.1 Write `tests/test_cli.py::test_init_on_new_path_reports_created`
- [x] 3.2 Write `tests/test_cli.py::test_init_on_already_initialized_vault_exits_zero_and_reports_no_error`
- [x] 3.3 Write `tests/test_cli.py::test_init_json_reports_created`
- [x] 3.4 Write `tests/test_cli.py::test_init_json_reports_already_initialized_outcome`
- [x] 3.5 Write `tests/test_cli.py::test_init_omitted_path_falls_back_to_vault_path_env`
- [x] 3.6 Write `tests/test_cli.py::test_list_succeeds_against_a_freshly_initialized_vault` — end-to-end: `init` then `list`, no `VaultNotFoundError`
- [x] 3.7 Implement `@app.command("init")`: optional positional `path` argument, calls `core.init_vault`, renders through `_render_write_outcome` (`outcome="created"` / `outcome="already initialized"`), same `--json` contract as `new`/`add`
- [x] 3.8 Run 3.1-3.6

## 4. README.md

- [x] 4.1 Add a short "Getting started" note (near the top, before the existing `Usage` examples) showing `vacancy-radar init /path/to/vault` and setting `VAULT_PATH` before the first `list`/`new` call

## 5. Verification

- [x] 5.1 Run `uv run pytest` — 515 passed
- [x] 5.2 Run `uv run ruff check .` and `uv run ruff format --check .` — both clean
- [x] 5.3 Confirm no `print()` call was added anywhere in `src/vacancy_radar/` (T20) — `ruff check .`'s `T20` rule passing confirms it; manual grep found none beyond pre-existing `console.print`/`error_console.print`
- [x] 5.4 Confirm `pyproject.toml` has no new runtime dependency — `git diff --stat pyproject.toml` is empty
- [x] 5.5 Confirm `resolve_vault_path`'s own behavior is unchanged — `git diff tests/test_config.py` shows only additions, no line of any existing test was changed, and all 19 `test_config.py` tests pass
