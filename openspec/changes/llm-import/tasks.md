## 1. core.py: extend create_vacancy's signature

- [x] 1.1 Write `tests/test_core.py::test_create_vacancy_stores_optional_fields` — `stage_note`, `salary_note`, `recruiter`, `tags` all provided, asserted present on the created vacancy
- [x] 1.2 Write `tests/test_core.py::test_create_vacancy_tags_defaults_to_empty_list` — `tags` omitted
- [x] 1.3 Write `tests/test_core.py::test_create_vacancy_optional_str_fields_default_absent` — `stage_note`/`salary_note`/`recruiter` omitted
- [x] 1.4 Extend `core.create_vacancy`'s signature with `stage_note: str | None = None`, `salary_note: str | None = None`, `recruiter: str | None = None`, `tags: list[str] | None = None`, forwarded to `Vacancy(...)` (`tags=tags or []`, the rest unchanged) — design.md decision 5
- [x] 1.5 Run 1.1-1.3 and confirm every existing `create_vacancy` test in `tests/test_core.py`/`tests/test_cli.py` still passes unmodified

## 2. core.py: add find_existing

- [x] 2.1 Write `tests/test_core.py::test_find_existing_matches_existing_company`
- [x] 2.2 Write `tests/test_core.py::test_find_existing_empty_for_unknown_company_and_url`
- [x] 2.3 Write `tests/test_core.py::test_find_existing_never_raises_on_ambiguous_company`
- [x] 2.4 Write `tests/test_core.py::test_find_existing_matches_by_source_url_across_company_spellings`
- [x] 2.5 Write `tests/test_core.py::test_find_existing_does_not_duplicate_a_vacancy_matching_both_tiers`
- [x] 2.6 Implement `core.find_existing(company: str, source_url: str, vault: Path | None = None) -> list[VacancySummary]`: one `read_vault` call, company tier via the existing private `_resolve` (non-raising), `source_url` tier via a scan of `snapshot.vacancies`, deduplicated, rows built with the existing private `_vacancy_summary` — design.md decisions 2-3
- [x] 2.7 Run 2.1-2.5

## 3. mcp_server.py: expose create_vacancy

- [x] 3.1 Write `tests/test_mcp_server.py::test_create_vacancy_tool_delegates` — mock `core.create_vacancy`, assert one call with unmodified arguments and a result reporting the mocked path plus the id derived from its parent directory name
- [x] 3.2 Write `test_create_vacancy_schema_matches_core_param_names`
- [x] 3.3 Write `test_create_vacancy_status_enum_matches_status`
- [x] 3.4 Write `test_create_vacancy_omitting_optional_fields_matches_core_defaults` — `applied_date`, `stage_note`, `salary_note`, `recruiter`, `tags` all omitted
- [x] 3.5 Write `test_create_vacancy_new_company_creates_directory` (real vault, `tmp_path`, no mocking)
- [x] 3.6 Write `test_create_vacancy_existing_company_leaves_company_md_untouched`
- [x] 3.7 Write `test_create_vacancy_result_is_immediately_listed` (via the `list_vacancies` tool, same process)
- [x] 3.8 Write `test_create_vacancy_result_is_immediately_searchable` (via the `search` tool, same process)
- [x] 3.9 Write `test_create_vacancy_same_day_company_unknown_role_gets_distinct_ids`
- [x] 3.10 Write `test_create_vacancy_missing_applied_date_returns_typed_error` — non-`found` status, no `applied_date`, asserts `InvalidVacancyDataError` and no files written
- [x] 3.11 Write `test_create_vacancy_applied_date_before_found_date_returns_typed_error`
- [x] 3.12 Write `test_create_vacancy_description_states_unknown_role_convention`
- [x] 3.13 Write `test_create_vacancy_description_states_migrated_convention`
- [x] 3.14 Write `test_create_vacancy_description_states_check_before_create_convention`
- [x] 3.15 Write `test_create_vacancy_ten_sequential_calls_produce_distinct_ids`
- [x] 3.16 Write `test_create_vacancy_failure_mid_batch_leaves_prior_creations_intact`
- [x] 3.17 Implement the `create_vacancy` tool in `_register_write_tools`: schema parameter names and types exactly matching `core.create_vacancy`'s new signature (`status` enum from `Status`), `annotations=_WRITE`, description stating the `unknown`/`needs_review`, synthesized-`found_date`/`migrated`, and check-before-create conventions (design.md decision 6), body computes `path = core.create_vacancy(...)` then `vacancy_id = path.parent.name` (design.md decision 7) and returns both
- [x] 3.18 Update `build_server`'s `MCPServer(instructions=...)` string: stop naming `create_vacancy` alongside `reindex` in the "intentionally not exposed" sentence — only `reindex` still is
- [x] 3.19 Run 3.1-3.16

## 4. mcp_server.py: expose find_existing

- [x] 4.1 Write `tests/test_mcp_server.py::test_find_existing_tool_delegates`
- [x] 4.2 Write `test_find_existing_schema_matches_core_param_names`
- [x] 4.3 Write `test_find_existing_tool_returns_matches_for_existing_company` (real vault)
- [x] 4.4 Write `test_find_existing_tool_returns_empty_for_unknown_company_and_url`
- [x] 4.5 Write `test_find_existing_tool_matches_source_url_across_company_spellings`
- [x] 4.6 Implement the `find_existing` tool in `_register_read_tools`: schema `{company, source_url}` matching `core.find_existing` exactly, `annotations=_READ_ONLY`, body delegates to `core.find_existing` unmodified
- [x] 4.7 Run 4.1-4.5

## 5. mcp_server.py: update the fixed tool-list and annotation tests

- [x] 5.1 Update `test_tool_list_is_exactly_the_nine_specified_tools` to assert the eleven-tool set (rename to `test_tool_list_is_exactly_the_eleven_specified_tools`), including that `reindex` is absent and `create_vacancy`/`find_existing` are present
- [x] 5.2 Update `test_read_tools_have_read_only_hint_true` to include `find_existing`
- [x] 5.3 Update `test_write_tools_have_read_only_and_destructive_hint_false` to include `create_vacancy`
- [x] 5.4 Update `test_no_tool_schema_accepts_a_write_path_argument` to cover `create_vacancy`'s and `find_existing`'s schemas
- [x] 5.5 Confirm `test_every_tool_has_open_world_hint_false` covers the two new tools without modification (it iterates the live tool list) — adjust only if it doesn't; also updated `_EXPECTED_TOOL_COUNT` (9→11) in the subprocess end-to-end test, which the task list didn't call out explicitly
- [x] 5.6 Run the full updated `tests/test_mcp_server.py`

## 6. docs/import-guide.md

- [x] 6.1 Write `docs/import-guide.md`: triage first (full records only for rows that got a reply; the rest to `_archive/index.md` by hand); batch size 10-20 rows per turn; map free-text stage columns onto the `Status` vocabulary in the same pass, keeping the original text verbatim in `stage_note`, model proposes and user confirms per batch; derive `role` from the job URL when the path carries a title, else `"unknown"` plus `needs_review`; call `find_existing` before each `create_vacancy`; verify each batch with `vacancy-radar list` before continuing; work `needs_review` afterwards with `vacancy-radar list --needs-review`
- [x] 6.2 Add a worked example using non-English column headers (e.g. a tracker with `Firma`/`Rolle`/`Status`/`Datum` columns), showing the proposed mapping and the resulting `create_vacancy`/`find_existing` calls
- [x] 6.3 State the non-transactional-import failure mode plainly: a batch interrupted halfway leaves some rows created, which is why batches stay small and are verified before moving on (design.md decision 9)

## 7. docs/evaluation.md

- [x] 7.1 Create `docs/evaluation.md`, moving the "Limitations" paragraph's real-vault-eval promise out of README.md's "Retrieval evaluation" section
- [x] 7.2 Document the procedure for a second eval run against a real vault after import — corrected from the task's original `uv run vacancy-radar eval --vault` framing: that flag doesn't exist (`eval_command` is hard-coded to the fixture vault/queries), so the documented procedure invokes `eval.run.load_queries`/`run_eval`/`FULL_SWEEP` directly against a hand-labeled real-vault queries file instead
- [x] 7.3 State plainly that the stage 5 fixture numbers characterize the retrieval design on adversarial fixtures, not a real corpus, and that real-corpus numbers (once run) are what should inform `SEARCH_DEFAULT_VECTOR_WEIGHT`/`SEARCH_FUSION_STRATEGY` retuning — ship no numbers from any specific run
- [x] 7.4 Update README.md's "Retrieval evaluation" section to point at `docs/evaluation.md` for the real-vault procedure instead of only promising it inline

## 8. README.md

- [x] 8.1 Add `create_vacancy` and `find_existing` rows to the MCP tool table
- [x] 8.2 Replace the "`reindex` and `create_vacancy` are deliberately **not** exposed" sentence with one naming only `reindex`, and note `create_vacancy`'s `find_existing`-first convention
- [x] 8.3 Update the "**Nine tools**" heading and any other tool-count references to eleven (also updated the top-of-file "Status" paragraph's stage 9 description, which the task list didn't call out explicitly)

## 9. Verification

- [x] 9.1 Run `uv run pytest` — 498 passed
- [x] 9.2 Run `uv run ruff check .` and `uv run ruff format --check .` — both clean (fixed two `E501` lines and three `PLR2004` magic numbers introduced by this change's own new tests along the way)
- [x] 9.3 Confirm no `print()` call was added anywhere in `src/vacancy_radar/` (T20) — `ruff check .`'s `T20` rule (part of `select = ["ALL"]`) passing is confirmation; a manual grep found only `console.print`/`error_console.print` (Rich, pre-existing), no bare `print(`
- [x] 9.4 Confirm `pyproject.toml` has no new runtime dependency — `git diff pyproject.toml` is empty
- [x] 9.5 Confirm no real vacancy, company, recruiter, or email data appears in `docs/import-guide.md`'s worked example or any test fixture — worked example uses fictional companies (Beispiel GmbH, Muster AG, Kleinfirma KG); new tests use the existing fixture-style Acme Corp/Widget Inc names already used throughout the suite
