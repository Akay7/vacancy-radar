## 1. Model and write paths

- [x] 1.1 Add `resume: str | None = None` to `models.Vacancy` with a validator that trims, rejects blank, multi-line, and >64-character values; add cases to `tests/test_models.py` (valid, trimmed, blank, multi-line, too long, valid at `found`) and verify `uv run pytest tests/test_models.py` passes.
- [x] 1.2 Add `resume` to `core.create_vacancy` (after `tags`, forwarded to `Vacancy`, omitted from frontmatter when `None`); add tests to `tests/test_core.py` for stored and omitted, and verify they pass.
- [x] 1.3 Add `resume` to `core.edit_vacancy`: extend `EDITABLE_FIELDS` and `NULLABLE_EDITABLE_FIELDS`, the `given` mapping, and the signature; tests for set, clear, history entry, no-op restate, and whitespace-only rejection (vault unchanged); verify `resolve_field_edits` accepts `resume` and `--clear resume`.
- [x] 1.4 Add `resume` to `core.set_status`: written in the same atomic write; appends an `## Edit History` entry (reusing `_append_edit_history`/`FieldChange`) only when the value changes; same-status call stays a no-op. Tests: apply with resume, omit leaves it alone, same-status ignores it, round trip differs only in the lines the `status-transitions` delta lists; verify they pass.
- [x] 1.5 Update the `Purpose` sentence in `openspec/specs/vacancy-editing/spec.md` ("nine fields" → "ten") by hand, and verify `openspec validate add-resume-tracking --strict` still passes.

## 2. Reading and filtering

- [x] 2.1 Add `resume` to `VacancySummary` and `VacancyDetail` and populate them in `_vacancy_summary` / `get_vacancy`; tests for present and `null`; verify existing `list_vacancies`/`get_vacancy` tests still pass unchanged.
- [x] 2.2 Add the `resume` filter to `core.list_vacancies` (case-insensitive, trimmed, intersected with the other filters); tests for match, case/whitespace, no-resume vacancies excluded, and combination with `status`; verify they pass.
- [x] 2.3 Implement `core.resume_stats(since=None, vault=None)` and the `ResumeStats` row model: group applied vacancies by lower-cased label, per-status counts, `advanced`, `advance_rate` (`None` at zero), the `None`-resume row only when non-empty, deterministic ordering, `since` on `applied_date`. Tests mirror every scenario in `resume-tracking`; verify they pass and that no index is opened (run with the index directory absent).

## 3. CLI

- [x] 3.1 Add `--resume` to `edit`, `status set`, `new`, and `list`; extend the edit/list/show renderers to print the resume when present (`show` prints `resume:` beside `recruiter:`). CLI tests: set via each command, `--clear resume`, `show --json` includes it; verify `uv run pytest tests/test_cli.py` passes.
- [x] 3.2 Add `vacancy-radar resumes [--since] [--json]` rendering the rows as a table with absolute counts shown beside the rate, and the empty-vault message. CLI tests for table, `--json` equals `core.resume_stats`, and empty; verify they pass.

## 4. MCP

- [x] 4.1 Add `resume` to the `list_vacancies`, `set_status`, `create_vacancy`, and `edit_vacancy` tools (marshalling only; `edit_vacancy` also accepts `clear=["resume"]`), mentioning the A/B use in each docstring; update the argument-name and schema-property tests in `tests/test_mcp_server.py`; verify they pass.
- [x] 4.2 Add the read-only `resume_stats` tool (`_READ_ONLY`, `_delegate`, no `_meta.ui`) delegating to one `core.resume_stats` call; update the tool-list tests (twelve → thirteen, `resume_stats` in the read-only-hint set, absent from the `_meta.ui` set) and add a delegation test with `core.resume_stats` mocked; verify the whole `tests/test_mcp_server.py` passes.
- [x] 4.3 Confirm the `ui://` views are untouched: `tests/test_mcp_ui_views.py` passes unchanged, and `git diff --stat` shows nothing under `assets/mcp_ui/`.

## 5. Docs and verification

- [x] 5.1 README: document `--resume`, `vacancy-radar resumes`, and the `resume_stats` tool, including the caveat that variants should be compared on comparable roles and that rates come from current status; verify each documented command runs against `tests/fixtures/vault` copied to a temp dir.
- [x] 5.2 CHANGELOG: add an `### Added` entry under `## [Unreleased]` (tag `v0.2.0` exists) describing resume tracking and the comparison.
- [ ] 5.3 Run `uv run pytest`, `uv run ruff check`, and the type checker the project's pre-commit uses; verify all pass, and `openspec validate add-resume-tracking --strict` passes.
- [x] 5.4 End-to-end on a scratch vault: create two applied vacancies with different `--resume` labels, set one to `interview` via `status set`, run `vacancy-radar resumes` and the MCP `resume_stats` tool, and verify the counts match `list --resume` output for each label.
