## 1. models.py: Vacancy.source_url becomes optional

- [x] 1.1 Located: `tests/test_models.py`. Removed `"source_url"` from `test_omitting_a_mandatory_field_is_rejected`'s parametrize list; wrote `tests/test_models.py::test_vacancy_omitting_source_url_parses`
- [x] 1.2 `test_source_url_must_be_http_or_https` unchanged, confirmed still passing
- [x] 1.3 Added `test_vacancy_with_valid_source_url_still_stored`
- [x] 1.4 Changed `Vacancy.source_url` to `str | None = None`; `_validate_source_url_scheme` returns `None` unchanged when the value is `None`
- [x] 1.5 Ran all of `tests/test_models.py` — 43 passed

## 2. core.py: reorder create_vacancy, add optional source_url

- [x] 2.1 Write `tests/test_core.py::test_create_vacancy_without_source_url_creates_vacancy_with_none`
- [x] 2.2 Write `tests/test_core.py::test_create_vacancy_with_source_url_still_stores_it`
- [x] 2.3 Write `tests/test_core.py::test_create_vacancy_invalid_source_url_scheme_still_raises`
- [x] 2.4 Reordered `core.create_vacancy`'s signature: `company, role, found_date, status, source_url=None, applied_date=None, stage_note=None, salary_note=None, recruiter=None, tags=None, *, vault=None`; updated the `Vacancy(...)` construction to match
- [x] 2.5 Updated `cli.py`'s `new_command` call and `mcp_server.py`'s `create_vacancy` tool call to keyword arguments; `cli.py`'s `--url` option made optional in the same edit (task 4 folded in here since it's the same lines)
- [x] 2.6 Converted all 18 existing `core.create_vacancy(...)` positional calls in `tests/test_core.py` to keyword arguments via a scripted transform, verified line-by-line against the diff (indentation, `with pytest.raises` blocks, and calls with extra kwargs like `applied_date=`/`stage_note=` all preserved correctly)
- [x] 2.7 Ran all `create_vacancy`-related tests (embedding and non-embedding) — 13/13 passed

## 3. core.py: find_existing's source_url becomes optional

- [x] 3.1 Write `tests/test_core.py::test_find_existing_no_source_url_still_matches_by_company`
- [x] 3.2 Write `tests/test_core.py::test_find_existing_no_source_url_never_false_matches_across_companies`
- [x] 3.3 Write `tests/test_core.py::test_find_existing_omitting_source_url_never_matches_via_that_tier`
- [x] 3.4 Write `tests/test_core.py::test_find_existing_with_real_source_url_unchanged`
- [x] 3.5 Changed `core.find_existing`'s signature to `source_url: str | None = None`; guarded the source_url-tier comparison with `if source_url is not None:` around the loop
- [x] 3.6 Ran all `find_existing` tests — 9/9 passed

## 4. cli.py: new command's --url becomes optional

- [x] 4.1 Write `tests/test_cli.py::test_new_command_without_url_creates_vacancy_with_no_source_url` — fixed along the way: `show <company-name>` resolves to the *company* dossier, not the vacancy, so the test captures the vacancy id from `new --json`'s output and does `show <id> --json` instead. Also found and fixed `core.VacancyDetail.source_url` still being required `str` (missed in task 2's model sweep) — changed to `str | None = None`
- [x] 4.2 Write `tests/test_cli.py::test_new_command_with_url_still_works` — regression
- [x] 4.3 Changed `new_command`'s `url` option to `str | None = None` (done together with 2.5)
- [x] 4.4 Ran all `new_command` tests — 5/5 passed

## 5. mcp_server.py: create_vacancy tool's source_url becomes optional

- [x] 5.1 Write `tests/test_mcp_server.py::test_create_vacancy_tool_without_source_url_creates_vacancy_with_none` (end-to-end against a real vault, via `get_vacancy` afterward)
- [x] 5.2 Write `tests/test_mcp_server.py::test_create_vacancy_description_states_no_source_url_convention`
- [x] 5.3 Changed the `create_vacancy` tool's `source_url` parameter to `str | None = None`; updated its description; also fixed two existing mocked-delegation tests (`test_create_vacancy_tool_delegates`, `test_create_vacancy_omitting_optional_fields_matches_core_defaults`) whose `mock.assert_called_once_with(...)` still asserted the old positional call shape
- [x] 5.4 Ran all `create_vacancy` tool tests — 18/18 passed

## 6. mcp_server.py: find_existing tool's source_url becomes optional

- [x] 6.1 Write `tests/test_mcp_server.py::test_find_existing_tool_without_source_url_still_matches_by_company`
- [x] 6.2 Changed the `find_existing` tool's `source_url` parameter to `str | None = None`; updated its description
- [x] 6.3 Ran all `find_existing` tool tests — 6/6 passed

## 7. README.md

- [x] 7.1 Added a one-line note near the `new` example that `--url` is optional, for the case where the only source is a PDF with no posting link

## 8. Verification

- [x] 8.1 Run `uv run pytest` — 539 passed
- [x] 8.2 Run `uv run ruff check .` and `uv run ruff format --check .` — both clean
- [x] 8.3 Confirm no `print()` call was added — grep found none beyond pre-existing `console.print`/`error_console.print`
- [x] 8.4 Confirm `pyproject.toml` has no new runtime dependency — `git diff --stat pyproject.toml` is empty
- [x] 8.5 Confirm `ids.py` untouched — `git diff --stat src/vacancy_radar/ids.py` is empty
- [x] 8.6 Confirm `find_existing`'s None-vs-None guard — `core.py:1253` reads `if source_url is not None:` wrapping the comparison loop
