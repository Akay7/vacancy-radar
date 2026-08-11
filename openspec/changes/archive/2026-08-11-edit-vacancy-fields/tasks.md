## 1. History-block plumbing

- [x] 1.1 Add `_append_to_section(body, heading, entry)` to `core.py`: append `entry` as the last line of the section owned by `heading` (bounded by the next `##` heading or end of body), creating the section at the end of the body when the heading is absent (design decision 6)
- [x] 1.2 Rewrite `_append_status_history` to call `_append_to_section` with `STATUS_HISTORY_HEADING`, keeping its entry format unchanged
- [x] 1.3 Add `EDIT_HISTORY_HEADING = "## Edit History"` and `_append_edit_history(body, changes)` producing one `- <ISO date>: <field>: <old> -> <new>` line per change, rendering absent values as `(none)` and collapsing multi-line values to a single-line summary
- [x] 1.4 Tests in `tests/test_core.py`: status-history output is byte-identical to the pre-change behavior when `## Status History` is the body's last section; a status entry lands inside its own block when `## Edit History` follows it; an edit entry lands inside its own block when `## Status History` precedes it; a missing block is created at the end of the body
- [x] 1.5 Tests: a multi-line value and a value shaped like a history entry each yield exactly one new line in the block

## 2. core.edit_vacancy

- [x] 2.1 Add the `UNSET` sentinel, the `EDITABLE_FIELDS` and nullable-field sets, and typed errors `UneditableFieldError`, `NotNullableFieldError`, `ConflictingEditError` (each naming the offending field; `UneditableFieldError` also listing the editable fields)
- [x] 2.2 Add the frozen `EditResult` dataclass: `vacancy_id`, `changed`, and the changed fields with their old and new values
- [x] 2.3 Implement `edit_vacancy(vacancy_id, *, source_url=UNSET, role=UNSET, stage_note=UNSET, salary_note=UNSET, recruiter=UNSET, external_id=UNSET, tags=UNSET, found_date=UNSET, applied_date=UNSET, vault=None)`: resolve the vault, raise `EntityNotFoundError` for an unknown id, parse the file, compute the changed set against the parsed `Vacancy` (not raw YAML), and return the no-op `EditResult` without writing or reindexing when nothing changed
- [x] 2.4 Apply the changed fields to the parsed frontmatter mapping (removing keys set to `None`), validate with `Vacancy(**metadata)` wrapping failures in `InvalidVacancyDataError`, then `_append_edit_history` + `frontmatter.serialize` + `_atomic_write(..., overwrite=True)` + `reindex`, in that order
- [x] 2.5 Add a `resolve_field_edits(values, clear)` helper for string-named callers that maps value/clear inputs onto the keyword arguments, raising `UneditableFieldError`, `NotNullableFieldError`, and `ConflictingEditError`
- [x] 2.6 Tests in `tests/test_core.py` for the editable set: each field sets successfully; `status=`/`company=`/`id=` raise `TypeError`; omitted fields are untouched; an explicit `None` clears a nullable field
- [x] 2.7 Tests for validation: bad `source_url` scheme, empty `role`, clearing `applied_date` on a non-`found` vacancy, `found_date` after the stored `applied_date`, future `found_date` — each raises `InvalidVacancyDataError` and leaves the file's bytes unchanged
- [x] 2.8 Tests for no-op semantics: no fields given; identical values re-applied; `tags=[]` against an absent `tags` — each reports `changed=False`, writes nothing, appends nothing
- [x] 2.9 Tests for preservation and identity: only the edited keys and the appended entry differ (frontmatter comments and body preserved); the `# <role>` H1 is not rewritten; editing `found_date` leaves id, directory, and path unchanged; `status` is never altered
- [x] 2.10 Tests for freshness: an edited `role` is returned by `get_vacancy` and matched by `search` in the same process, with no explicit `reindex`
- [x] 2.11 Tests for `resolve_field_edits`: clearing `status`/an unknown name, clearing `role`/`found_date`/`tags`, and setting-plus-clearing one field each raise their typed error

## 3. CLI `edit` command

- [x] 3.1 Add the `edit` command to `cli.py` with one option per editable field (`--source-url`, `--role`, `--stage-note`, `--salary-note`, `--recruiter`, `--external-id`, `--tags`, `--found-date`, `--applied-date`), a repeatable `--clear FIELD`, and `--json`
- [x] 3.2 Resolve the vacancy argument via `_resolve_vacancy_or_fail`, parse dates with `_parse_date_option`, split `--tags` on commas (empty string → empty list), and map values/clears through `core.resolve_field_edits`
- [x] 3.3 Render success without `--json` as the vacancy id plus one line per changed field with old and new values, and a no-op as unchanged; render `--json` as an outcome plus the changed fields
- [x] 3.4 Route every typed core error through `_fail` so the command exits non-zero with a message and no traceback
- [x] 3.5 Tests in `tests/test_cli.py`: single-option and multi-option edits exit 0 and apply; `--help` exposes no `status`/`company`/`id` option
- [x] 3.6 Tests: `--clear` removes a field and repeats; clearing `status`, clearing `role`, and setting-plus-clearing one field each exit non-zero with the field named and nothing written
- [x] 3.7 Tests: a malformed `--found-date` exits non-zero naming the option; an ambiguous vacancy query exits non-zero printing candidates with nothing written; an invalid `--source-url` exits non-zero
- [x] 3.8 Tests: `--tags` replaces the list, `--tags ""` empties it; `--json` output is valid JSON naming the changed fields, and reports the no-op outcome when no field option is given

## 4. MCP `edit_vacancy` tool

- [x] 4.1 Register `edit_vacancy` in `_register_write_tools` with `vacancy_id` required, one optional parameter per editable field named as in `core.edit_vacancy`, and an optional `clear: list[str]`; delegate through `core.resolve_field_edits` + `core.edit_vacancy` with no other logic
- [x] 4.2 Declare `readOnlyHint=false` and `destructiveHint=false` on the tool, matching the other write tools
- [x] 4.3 Ensure `EditResult` serializes through the server's existing `_to_jsonable` path
- [x] 4.4 Tests in `tests/test_mcp_server.py`: with `core.edit_vacancy` mocked, the tool calls it exactly once with the given arguments and returns the result unmodified
- [x] 4.5 Tests: the tool's schema declares exactly the expected properties with `vacancy_id` as the only required one; the annotations report both hints false
- [x] 4.6 Tests against a real vault: omitted parameters leave fields untouched; `clear=["recruiter"]` removes it; an edited role is visible to `get_vacancy` in the same process
- [x] 4.7 Tests: an invalid `source_url`, `clear=["status"]`, and an unknown `vacancy_id` each return a typed error result naming the error class, with no unhandled exception and no vault file modified
- [x] 4.8 Test: an applied edit modifies only the target `vacancy.md`, leaving that vacancy's document files' bytes unchanged

## 5. Documentation and invariants

- [x] 5.1 Restate architectural invariant 3 in `openspec/project.md` to cover validated field edits that record what they changed (design decision 10)
- [x] 5.2 Document the `edit` command in `README.md` alongside the other write commands, including `--clear` and the `--tags` replace semantics
- [x] 5.3 Add a CHANGELOG entry (check `git tag -l` first to confirm whether an `[Unreleased]` section applies)
- [x] 5.4 Run `uv run pytest`, `ruff check`, and `ruff format --check` (or the configured pre-commit hooks) and fix anything they flag
- [x] 5.5 Run `openspec validate edit-vacancy-fields` and confirm the implementation satisfies every scenario in the four delta specs
