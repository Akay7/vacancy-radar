## Context

See proposal.md - Why. This change builds on the uncommitted FastMCP 3
migration work in the working tree: `mcp_server._delegate` already runs
sync tool bodies via `asyncio.to_thread` without `_CORE_LOCK`, and
`core.py` carries the `_serialized_write`/`_write_lock` FileLock that
this change removes.

Relevant current behavior:

- `_atomic_write` (core.py) writes a dot-prefixed temp file in the
  target's directory and `os.replace`s it. With `overwrite=False` it
  first checks `path.exists()`; the check and the replace are separate,
  so a concurrent creator can be silently overwritten.
- `_derive_document_filename` and `new_vacancy_id` pick a free name or
  id by looking at the directory, which is also a check-then-act race.
- `set_status`/`edit_vacancy` read `vacancy.md`, validate against a
  snapshot, and replace the whole file.
- Every write ends in `reindex()`, i.e. `build_index`: incremental,
  content-hash based, so rerunning it after a partial run is cheap.
- The vault reader already ignores dot-prefixed files
  (`vault/paths.py`), so temp files are invisible to reads.

LanceDB 0.37.1 behavior under concurrency, measured with 6 threads
against one table (scratch experiment, not committed):

- `merge_insert`, `update`, and `delete` never failed; Lance resolves
  those conflicts internally.
- `table.optimize()` and `create_index(..., replace=True)` (FTS) fail
  with `RuntimeError("lance error: Retryable commit conflict for
  version N: ... Please retry.")`.
- Two first builds racing `open_table` → `create_table` fail with
  `ValueError("Table 't' already exists")`; found during
  implementation, `open_table` during another's `create_table` fails
  with `RuntimeError("... exists but could not be loaded ...")`, and
  an update can fail with `RuntimeError("... Incompatible transaction
  ...")` against a first build's overwrite.

## Goals / Non-Goals

**Goals:**
- No lock of any kind on the write or read path.
- The `concurrent-writes` spec's guarantees, from both threads and
  processes, with no new files inside the vault.

**Non-Goals:**
- Exact `external_id` dedupe under overlapping calls (see spec
  residual).
- Closing the final re-check-to-rename window for `vacancy.md`
  updates; POSIX has no conditional rename.
- Making `build_index` itself concurrency-aware beyond the table
  creation race; the retry lives in `core.py`.
- Windows-specific behavior beyond what `os.link` provides there.

## Decisions

1. **No-clobber publish via hard link.** `_atomic_write(...,
   overwrite=False)` writes the temp file as today, then
   `os.link(tmp, path)` and unlinks the temp in a `finally`. `link`
   fails atomically with `FileExistsError` if `path` exists, so the
   file appears complete or not at all, and never replaces anything.
   The `exists()` pre-check stays as a fast path that avoids writing a
   temp file when the name is obviously taken.
   *Alternatives:* `O_CREAT|O_EXCL` on the target and writing into it
   directly - atomic claim but readers can see a partly written file;
   `renameat2(RENAME_NOREPLACE)` - Linux only, not exposed by the
   stdlib.
   *Fallback:* if `os.link` raises an `OSError` other than
   `FileExistsError` (filesystems without hard links: some FUSE, exFAT,
   network mounts), claim the target with `O_CREAT|O_EXCL` and then
   `os.replace(tmp, path)`. The claim still gives no-clobber; a reader
   can briefly see an empty file, which the vault reader already
   reports as a warning rather than crashing.

2. **Retry the name, not the whole write.** `add_document` loops:
   derive filename → `_atomic_write(overwrite=False)` → on
   `DocumentAlreadyExistsError`, derive again (the directory now shows
   the winner's file, so the next suffix comes out), up to
   `_MAX_FILENAME_SUFFIX_ATTEMPTS` total. The `Document` model's `id`
   is the filename stem, so it is rebuilt per attempt.
   `create_vacancy` does the same with ids: add the lost id to
   `existing_ids`, mint again. `_company.md` losing its race is
   swallowed: the winner wrote an equivalent record for the same slug.
   *Alternative:* pre-claim a name by creating the file empty first -
   same race, plus visible empty files.

3. **Compare-before-replace for `vacancy.md`, no retry loop.**
   `set_status` and `edit_vacancy` keep their existing body and swap
   the final `_atomic_write(..., overwrite=True)` for a new
   `_replace_if_unchanged(path, expected=original_text, text=new_text)`.
   That helper writes the temp file, re-reads `path`, and only if the
   bytes still equal `expected` does it `os.replace`; otherwise it
   removes the temp and raises a new
   `ConcurrentModificationError(CoreError)`, which the MCP layer
   already turns into a `ToolError` through `core.CoreError`. Compare
   bytes, not `mtime_ns`: mtime resolution varies by filesystem and a
   same-second rewrite could go unnoticed.
   *Alternative:* retry internally from `read_vault` - rejected: agents
   normally work on separate vacancies, so contention here is rare, and
   the caller retrying re-validates just as well with less code.
   *Residual:* a write landing between the re-read and `os.replace` is
   lost. The window is short in wall time, but two calls that start
   together do near-identical work and converge on it: in a stress
   test (a status change and an edit on one vacancy, released by a
   barrier) 9 of 40 runs lost one change, 19 refused one cleanly, 12
   applied both. Accepted per the spec, on the premise that agents
   work on different vacancies.

4. **Best-effort post-write refresh, strict explicit reindex.** Split
   today's `reindex` into a private `_reindex_with_retry(vault_root,
   ...)` that calls `build_index` up to 5 times, retrying only
   `RuntimeError`s whose message contains `"Retryable commit
   conflict"` or `"Incompatible transaction"` (the latter found during
   implementation: an update racing another first build's overwrite), with 50 ms × 2^n backoff plus jitter. Public `reindex()`
   calls it and lets the final error propagate (reindexing delta). The
   write functions call a second private helper, `_refresh_after_write`,
   which catches that final conflict error, logs a warning through a
   module logger (`logging.getLogger(__name__)`, stderr for the MCP
   server), and returns. Any other exception still propagates. The
   message match is the only discriminator LanceDB 0.37 offers; the
   helper that matches it is one function with a test pinned to a real
   conflict so a wording change in LanceDB fails the test loudly.
   Retrying the whole build is cheap because rows written by the
   failed attempt already have matching hashes; only FTS and
   `optimize()` rerun.
   *Alternative:* retry only `create_index`/`optimize` inside
   `build_index` - more targeted, but puts concurrency policy into the
   index module and misses future conflicting operations.

5. **Table-creation race in `build.py`.** `_open_or_create_table`
   catches `ValueError` from `create_table` and, if `open_table` now
   succeeds, returns that table as not fresh. `open_table` waits (about
   two seconds at most) while the table "could not be loaded" because
   another writer's `create_table` hasn't committed yet. The dimension-mismatch
   drop-and-recreate path is left as is (see Risks).

6. **`external_id` residual, no claim files.** The pre-write dedupe
   check stays as is. Exact dedupe under overlap would need either a
   claim file in `documents/` (new vault content) or deleting another
   writer's document (violates `mcp-write-tools`); both are worse than
   an occasional duplicate note the user can see.

7. **Remove, don't disable.** Delete `_write_locks`,
   `_write_locks_guard`, `_write_lock`, `_serialized_write`, the
   `@_serialized_write` decorators, the `filelock`, `hashlib`,
   `threading`, and `functools` imports if nothing else uses them, and
   `filelock` from `pyproject.toml`.

## Risks / Trade-offs

- [Lost update in the re-check-to-rename window] → Accepted and
  specified. Needs two writes to the same `vacancy.md` in flight at
  once; when that happens with near-simultaneous starts it is common
  (see decision 3), not microsecond-rare. A per-vacancy in-process
  lock would close it for one MCP server's parallel tool calls, at the
  cost of the "no locks" goal.
- [LanceDB changes its conflict message or exception type] → The
  matcher test fails with a real conflict; the fallback behavior is
  "propagate", i.e. today's behavior.
- [A stale snapshot's refresh finishes after a newer one and writes
  older row content] → The index is eventually consistent: the next
  refresh sees a hash mismatch against the file and fixes the row.
  Search's staleness warning covers missing rows, not stale content;
  noted, not addressed.
- [Two processes on different embedding models trigger
  drop-and-recreate concurrently] → Out of scope; a model change is a
  deliberate, rare operation. `vacancy-radar reindex --force` repairs.
- [Hard-link fallback shows an empty file briefly] → Only on
  filesystems without links; the reader warns and the next read sees
  the full file.
- [A caller sees `ConcurrentModificationError` it didn't expect] →
  The message says the vacancy changed concurrently and to retry;
  agents already handle `ToolError`s by re-reading.

## Migration Plan

No data migration: vault format and index schema are unchanged. The
FileLock never shipped in a tagged release (it exists only in the
uncommitted migration work), so no stale lock files need cleanup
beyond whatever `/tmp/vacancy-radar-*.lock` files local testing left.
Rollback is reverting the change.
