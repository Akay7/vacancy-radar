## Why

The FastMCP 3 migration moved tool bodies onto worker threads and, in
the same uncommitted work, replaced the in-process `_CORE_LOCK` with a
reentrant cross-process `FileLock` (`_serialized_write`/`_write_lock`
in `core.py`). That lock is created with `thread_local=False`, so a
second thread in the same process re-enters it instead of waiting:
concurrent MCP write calls are no longer serialized at all. Rather than
patch the lock, remove the need for one. The vault files are the source
of truth and the index is a derived, content-hashed cache, so every
write can be made safe with filesystem primitives and an eventually
consistent index — no lock to deadlock, time out, or get wrong.

## What Changes

- Remove `_serialized_write`, `_write_lock`, and the `filelock`
  dependency. MCP tools keep running via `asyncio.to_thread` with no
  lock around them; the CLI and multiple MCP server processes share a
  vault the same way.
- New-file writes become no-clobber at the OS level: `_atomic_write`
  with `overwrite=False` publishes its temp file with a hard link that
  fails if the target exists, instead of an `exists()` check followed
  by `replace()` (which can silently overwrite under a race).
- `add_document`/`append_note` retry with the next collision-suffixed
  filename when another writer takes the derived one first;
  `create_vacancy` retries with the next minted id, and treats a
  `_company.md` created concurrently by another writer as success.
- `external_id` dedupe stays exact for calls that don't overlap.
  Overlapping calls with the same `external_id` can each file a
  document (a rare duplicate, never a lost or overwritten file). This
  is a stated residual: lock-free convergence would require deleting
  another writer's file or adding claim files to the vault.
- `set_status`/`edit_vacancy` re-check `vacancy.md` immediately before
  replacing it and, if another writer changed it since it was read,
  write nothing and raise a typed error the caller can retry on.
  Agents normally work on different vacancies, so this is rare; a
  residual window of microseconds between the re-check and the rename
  is accepted and documented.
- The reindex at the end of every write becomes best-effort: a LanceDB
  commit conflict is retried a bounded number of times; if it still
  fails, the write returns successfully and logs a warning, leaving the
  index stale until the next reindex (which search's existing
  staleness warning already reports).
- CHANGELOG entry replaced; lock tests replaced with concurrency tests.

## Capabilities

### New Capabilities
- `concurrent-writes`: guarantees for vault writes issued concurrently
  from threads of one process or from several processes without any
  lock — no clobbered files, no lost vacancy edits outside a
  documented residual window, non-destructive `external_id` dedupe
  under contention, and a write never failing because the index
  refresh contended.

### Modified Capabilities
- `reindexing`: `reindex` itself (the explicit call) still raises on
  failure; the post-write refresh inside write functions becomes
  best-effort with bounded retry, qualifying the "searchable without a
  separate reindex" guarantees in `note-taking`, `vacancy-creation`,
  `vacancy-editing`, and `mcp-write-tools` for the contended case.
  That qualification is stated once, in `concurrent-writes`, rather
  than repeated in each spec.

## Impact

- `src/vacancy_radar/core.py`: `_atomic_write`, `add_document`,
  `append_note`, `set_status`, `edit_vacancy`, `create_vacancy`, the
  post-write reindex call; lock code removed.
- `src/vacancy_radar/index/build.py`: a first build racing another
  first build reopens the table instead of failing on "already
  exists"; the retry itself wraps `build_index` from `core.py`.
- `src/vacancy_radar/mcp_server.py`: no change beyond what the
  migration already did (`asyncio.to_thread` without `_CORE_LOCK`).
- `pyproject.toml`/`uv.lock`: drop `filelock` (it may remain as a
  transitive dependency of other packages; we stop importing it).
- `tests/test_core.py`: remove the two lock tests; add concurrency
  tests. `CHANGELOG.md`: rewrite the Unreleased "Fixed" entry.
- Filesystems without hard-link support (e.g. some FUSE/exFAT mounts)
  need a fallback path; see design.md.
