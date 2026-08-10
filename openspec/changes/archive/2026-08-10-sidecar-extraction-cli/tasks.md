## 1. core.py: extract_sidecars parameter on reindex

- [x] 1.1 Write `tests/test_core.py::test_reindex_extract_sidecars_true_creates_sidecar_for_eligible_pdf` — using `tests/fixtures/pdfs.py`'s `write_valid_pdf` (add the `_FIXTURES_DIR` sys.path snippet + `from pdfs import ...` to `tests/test_core.py`, mirroring `tests/index/test_extract.py`'s own setup)
- [x] 1.2 Write `tests/test_core.py::test_reindex_default_extract_sidecars_false_creates_no_sidecar` — same vault/PDF, no `extract_sidecars` argument, regression check against today's behavior
- [x] 1.3 Write `tests/test_core.py::test_reindex_extract_sidecars_true_malformed_pdf_returns_warning_not_crash` — using `write_malformed_pdf`; corrected from the task's original "no sidecar" assumption once the test run showed `extract_to_sidecar` still writes an empty-body sidecar on a handled failure (its own documented contract) - asserts empty body + `IndexReport.warnings` names the file instead; fixed the same wording in specs/reindexing/spec.md
- [x] 1.4 Add `extract_sidecars: bool = False` to `core.reindex`'s signature, forwarded to `build_index` unchanged (design.md decision 1)
- [x] 1.5 Run 1.1-1.3, then run every existing `tests/test_core.py` `reindex`/`test_reindex_*` test and confirm all still pass unmodified — 8/8 passed

## 2. cli.py: reindex --extract-sidecars and warning output

- [x] 2.1 Write `tests/test_cli.py::test_reindex_extract_sidecars_flag_creates_sidecar` — add the `pdfs` import to `tests/test_cli.py` (the `_FIXTURES_DIR` sys.path snippet already exists there)
- [x] 2.2 Write `tests/test_cli.py::test_reindex_without_flag_creates_no_sidecar` — regression check
- [x] 2.3 Write `tests/test_cli.py::test_reindex_plain_text_output_includes_extraction_warning` — malformed PDF, `--extract-sidecars`, no `--json`, asserts the warning message appears in `result.output`
- [x] 2.4 Write `tests/test_cli.py::test_reindex_plain_text_output_includes_encrypted_pdf_warning` — scope adjusted from a `vanished_source`-shaped warning: that race (a snapshot gone stale between `read_vault` and `build_index`) isn't reachable through this CLI's black-box invocation since `core.reindex` always reads fresh immediately before building, and this file has no precedent for mocking `core` to fake one. Used a second, distinct real extraction-warning kind (`encrypted_pdf`) instead, still proving the plain-text branch prints whatever `IndexReport.warnings` carries rather than special-casing one kind - noted inline in the test
- [x] 2.5 Write `tests/test_cli.py::test_reindex_json_warnings_field_populated_on_extraction_failure` — found along the way: each warning in `--json` output serializes as `str(VaultWarning)`'s repr, not a structured object - `dataclasses.asdict` doesn't recurse into a pydantic `BaseModel` nested in a dataclass field, so `json.dumps`'s `default=` fallback stringifies it whole. Pre-existing, unchanged by this change (only the plain-text branch was touched) - the test asserts the real string-repr shape, not the structured one originally assumed; not fixed here, out of this change's scope (proposal.md only committed to "same shape as before," not improving it)
- [x] 2.6 Add `--extract-sidecars` option to `reindex_command`, passed through to `core.reindex`; print each `report.warnings` entry's message in the plain-text branch (the `--json` branch already includes `warnings` via `dataclasses.asdict(report)` - no change needed there)
- [x] 2.7 Run 2.1-2.5 — 8/8 passed

## 3. cli.py: add's non-UTF-8 content handling

- [x] 3.1 Write `tests/test_cli.py::test_add_command_file_non_utf8_exits_cleanly_not_with_traceback` — a valid PDF (via `pdfs.write_valid_pdf`) passed via `--file`
- [x] 3.2 Write `tests/test_cli.py::test_add_command_file_non_utf8_error_names_the_pdf_workaround` — asserts the error output mentions `documents/` and `reindex --extract-sidecars`
- [x] 3.3 Write `tests/test_cli.py::test_add_command_stdin_non_utf8_exits_cleanly_not_with_traceback` — binary bytes piped via `input=` (bytes, not str) to `--stdin`
- [x] 3.4 Covered by the pre-existing `test_add_command_from_file_creates_a_document_with_matching_content`/`test_add_command_stdin_creates_a_document_with_piped_content` tests, which still pass unmodified — a dedicated new regression test would duplicate them
- [x] 3.5 Catch `UnicodeDecodeError` around both the `--file` and `--stdin` reads in `_read_document_content`, printing a message naming the file (for `--file`) or standard input (for `--stdin`), stating it isn't valid text, and naming the `documents/`/`reindex --extract-sidecars` workaround, then `typer.Exit(code=1)` - same shape as `_read_document_content`'s two existing error branches (design.md decision 3)
- [x] 3.6 Run 3.1-3.3 plus the two pre-existing valid-content tests — 8/8 `add_command` tests passed

## 4. README.md

- [x] 4.1 Replace the "Attaching a PDF (limited - see caveat)" section (added while diagnosing this gap) with the now-working workflow: `cp` into `documents/`, then `vacancy-radar reindex --extract-sidecars`; drop the "Caveat" paragraph since it's no longer true — also added a `reindex --extract-sidecars` example to the main code block and a `reindex --extract-sidecars` mention in the `## MCP server` area was not needed (extraction isn't MCP-exposed)
- [x] 4.2 Added a one-line mention near the `add` example that `--file`/`--stdin` are text-only and fail cleanly on binary content, pointing at the PDF section below

## 5. Verification

- [x] 5.1 Run `uv run pytest` — 526 passed
- [x] 5.2 Run `uv run ruff check .` and `uv run ruff format --check .` — both clean
- [x] 5.3 Confirm no `print()` call was added anywhere in `src/vacancy_radar/` (T20) — grep found none beyond pre-existing `console.print`/`error_console.print`
- [x] 5.4 Confirm `pyproject.toml` has no new runtime dependency — `git diff --stat pyproject.toml` is empty
- [x] 5.5 Confirm `extract_sidecars`'s default is still `False` at every call site — `core.reindex`'s signature defaults to `False`; the three other internal `reindex(vault=vault_root)` calls (`add_document`, `set_status`, `create_vacancy`) pass no `extract_sidecars` argument at all
