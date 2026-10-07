## 1. Remove the lock

- [x] 1.1 Delete `_write_locks`, `_write_locks_guard`, `_write_lock`, `_serialized_write`, every `@_serialized_write` decorator, and now-unused imports (`filelock`, `hashlib`, `threading`, `functools`) from `core.py`; verify `grep -n "FileLock\|_serialized_write\|_write_lock" src/` is empty
- [x] 1.2 Remove `filelock` from `pyproject.toml` dependencies and run `uv lock`; verify `uv run python -c "import vacancy_radar.core"` succeeds
- [x] 1.3 Delete `test_write_lock_excludes_writers_in_other_processes` and `test_write_lock_is_reentrant_within_a_process` (and the `_HOLD_LOCK_SCRIPT`, `subprocess`, `filelock.Timeout` imports) from `tests/test_core.py`; verify the file still passes `ruff check`

## 2. No-clobber creates (design decisions 1, 2)

- [x] 2.1 Change `_atomic_write(overwrite=False)` to publish via `os.link(tmp, path)` (temp removed in `finally`), mapping `FileExistsError` to `DocumentAlreadyExistsError`; verify the existing `test_atomic_write_*` tests pass (done; the new-file failure test and the two interrupted-write tests now also patch `os.link`, since new files no longer publish via `os.replace`)
- [x] 2.2 Add the non-link fallback (`O_CREAT|O_EXCL` claim + `os.replace`) for `OSError`s other than `FileExistsError`; verify with a test that monkeypatches `os.link` to raise `PermissionError` and checks both a successful create and a refused existing path
- [x] 2.3 Add a test where the target appears between the `exists()` pre-check and the publish (monkeypatch to create it) and verify the existing file's bytes are unchanged and `DocumentAlreadyExistsError` is raised
- [x] 2.4 Make `add_document` re-derive the filename and rebuild its `Document` on `DocumentAlreadyExistsError`, bounded by `_MAX_FILENAME_SUFFIX_ATTEMPTS`; verify with a test that pre-empts the first derived name mid-call and asserts the note lands at the `-2` name with its own content
- [x] 2.5 Make `create_vacancy` re-mint the id on a lost `vacancy.md` create and treat a lost `_company.md` create as success; verify with tests pre-empting each path mid-call (distinct id returned; winner's `_company.md` bytes unchanged)

## 3. Optimistic vacancy.md updates (design decision 3)

- [x] 3.1 Add `ConcurrentModificationError(CoreError)` and `_replace_if_unchanged(path, expected, text)`; verify unit tests for the unchanged case (replaced) and the changed case (not replaced, no temp file left, internal signal raised)
- [x] 3.2 Use `_replace_if_unchanged` in `set_status`; verify a test where a hook edits `vacancy.md` just before the replace, `set_status` raises `ConcurrentModificationError`, the file keeps the other writer's bytes, and a repeated call then succeeds with both changes present
- [x] 3.3 Use `_replace_if_unchanged` in `edit_vacancy`; verify the same shape of test

## 4. Best-effort index refresh (design decisions 4, 5)

- [x] 4.1 Add `_is_retryable_conflict(exc)` and a test that provokes a real LanceDB `optimize()` conflict with threads and asserts the matcher recognizes it (guards against LanceDB wording changes)
- [x] 4.2 Add `_reindex_with_retry` (5 attempts, exponential backoff with jitter) and route public `reindex()` through it; verify tests for "conflict once then succeeds" (returns a report) and "conflict every time" (raises), with `build_index` monkeypatched
- [x] 4.3 Add `_refresh_after_write` (logs a warning on a persistent conflict, propagates anything else) and use it as the last step of every write function; verify a test where `append_note` returns its path, the file exists, a warning is captured via `caplog`, and a following `search` reports staleness
- [x] 4.4 In `index/build.py::_open_or_create_table`, reopen the table when `create_table` fails because it already exists; verify a test racing four first builds on an empty index path with threads, all succeeding (done; also needed a wait while another writer's `create_table` is uncommitted, and `Incompatible transaction` added to the retryable conflicts)

## 5. Concurrency tests (concurrent-writes spec)

- [x] 5.1 Add a threaded test: 8 concurrent `append_note` calls on one vacancy and date → 8 files, each call's returned path holds its own text
- [x] 5.2 Add a threaded test: 4 concurrent `create_vacancy` calls with identical inputs on a new company → 4 distinct ids, exactly one `_company.md`, no exceptions
- [x] 5.3 Add a threaded test: concurrent `set_status` and `edit_vacancy` on the same vacancy → each call either succeeds or raises `ConcurrentModificationError`, and every successful call's change is present in the final file
- [x] 5.4 Add a threaded test: 4 concurrent `add_document` calls with one `external_id` → 1–4 intact documents, each returned path is one of them; a following call dedupes and creates no file
- [x] 5.5 Add a multi-process test (2 subprocesses × several `append_note` calls on the same vault) → all notes present (children exit via `os._exit` to skip a pre-existing SIGSEGV at interpreter teardown), then `reindex()` + `search` finds every note with no staleness warning
- [x] 5.6 Add a test that reads (`list_vacancies`, `get_vacancy`) in a loop while writes run in other threads → no read raises
- [x] 5.7 Add an MCP-level test that fires several write tools concurrently through the server (as `tests/test_mcp_server.py` already drives tools) → all succeed and the vault reflects each write

## 6. Docs and verification

- [x] 6.1 Rewrite the CHANGELOG "Fixed" entry: tool bodies run in worker threads; concurrent writes from threads, processes, and the CLI are safe without locks (no-clobber creates, re-validated `vacancy.md` updates, index refresh that never fails a write); mention the `external_id` and `vacancy.md` residuals. Verify `git tag -l` shows a prior tag so `[Unreleased]` remains valid
- [x] 6.2 Update the `core.py` module docstring's atomic-write/concurrency description to match; verify it no longer mentions a lock
- [x] 6.3 Run `uv run pytest`, `uv run ruff check`, `uv run ruff format --check`, and the project's type checker; verify all pass (done; no type checker is configured in this project)
- [x] 6.4 Run `openspec validate lock-free-vault-writes --strict`; verify it passes
