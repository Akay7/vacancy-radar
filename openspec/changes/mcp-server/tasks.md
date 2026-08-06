## 1. Setup

- [x] 1.1 Added the official MCP Python SDK (`mcp>=2.0.0`) to
      `pyproject.toml`'s `dependencies` via `uv add mcp` — the one new
      runtime dependency this change permits. No other new dependency
      anywhere in this change.
- [x] 1.2 Added the `vacancy-radar-mcp` entry point to `pyproject.toml`'s
      `[project.scripts]`, pointing at `src/vacancy_radar/mcp_server.py`'s
      `main`.
- [x] 1.3 Created `src/vacancy_radar/mcp_server.py` with a module
      docstring restating invariant 4 (argument marshalling only, per
      `core.py`'s own docstring) and the stdout/stderr discipline
      (invariant 5), mirroring `core.py`'s and `cli.py`'s own module
      docstrings' conventions; also documents the vault-path/roots
      reconciliation from 1.5.
- [x] 1.4 Created `tests/test_mcp_server.py` with self-contained
      `_init_vault`/`_write_company`/`_write_vacancy`/`_write_document`
      helpers (mirroring `test_core.py`'s/`test_cli.py`'s own per-file
      convention rather than importing across test files), plus
      `_minimal_vault` (one company/vacancy/document) and `_demo_vault`
      (two companies, three vacancies, spanning applied/take_home/found
      + needs_review/stale, with posting/note/email documents) for the
      richer bounded-output/resource/prompt tests. No test in this file
      mutates the committed fixture vault (confirmed via `git status`
      in section 23).
- [x] 1.5 Confirmed, against the actually-installed `mcp` package
      (`mcp==2.0.0`, the official `modelcontextprotocol/python-sdk`):
      this change builds on the high-level `mcp.server.mcpserver.
      MCPServer` class (`.tool()`/`.resource()`/`.prompt()`/
      `.run(transport="stdio")`); per-tool annotations are
      `MCPServer.tool(..., annotations=ToolAnnotations(read_only_hint=,
      destructive_hint=, open_world_hint=))` (snake_case Python fields,
      camelCase wire aliases). **Also surfaced that the installed SDK's
      default protocol revision (2026-07-28, SEP-2577) deprecates the
      entire MCP roots capability** (`ServerSession.list_roots()` is
      `@deprecated`; `MCPServer` exposes no public hook for
      `notifications/roots/list_changed` at all) — raised with the user
      mid-implementation and resolved by dropping roots-based vault
      resolution from scope; see design.md decision 7 and proposal.md's
      updated vault-path bullet. `specs/mcp-roots/` was renamed to
      `specs/mcp-vault-path/` and its requirements rewritten to the
      resulting two-tier precedence; tasks.md sections 2 and (the former)
      19 were rewritten/removed to match.

## 2. Vault-path resolution — tests, then implementation

- [x] 2.1 `test_main_uses_explicit_vault_over_env`: given an explicit
      `--vault`, the resolved vault path is that one, regardless of
      `VAULT_PATH` (design.md decision 7, spec `mcp-vault-path`).
- [x] 2.2 `test_main_uses_vault_path_env_when_no_explicit`: given no
      `--vault`, `VAULT_PATH` is used.
- [x] 2.3 `test_main_fails_naming_both_when_neither_present`: given
      neither `--vault` nor `VAULT_PATH`, `main` exits non-zero with a
      stderr message naming both — `config.VaultNotConfiguredError`'s
      own message names `VAULT_PATH`; `main` appends one line naming
      `--vault` explicitly (design.md decision 7's note on this).
- [x] 2.4 `test_main_fails_for_vault_missing_marker`: given `--vault`
      pointing at a directory with no `.vacancy-radar/` marker, `main`
      exits non-zero (`config.VaultNotFoundError`).
- [x] 2.5 Implemented vault-path resolution in `mcp_server.main`:
      `vault_path = resolve_vault_path(args.vault)`, called once before
      `build_server` — no new precedence function, no new error type
      (design.md decision 7).
- [x] 2.6 No separate `current_vault_path()` accessor was needed:
      `build_server(vault_path)` closes over the one resolved `Path`
      directly, and every tool/resource/prompt function it registers
      references that closure variable — equivalent to a "thin
      accessor over a value fixed at startup" (design.md decision 8),
      just without an extra indirection layer, since nothing in this
      change ever reassigns it.
- [x] 2.7 Ran 2.1-2.4 green.

## 3. Shared tool helpers: serialization and error wrapping — tests, then implementation

- [x] 3.1 `test_to_jsonable_converts_pydantic_model`: the serialization
      helper turns a `pydantic.BaseModel` result into a JSON-safe dict
      equal to its own `model_dump(mode="json")`.
- [x] 3.2 `test_to_jsonable_converts_dataclass_with_dates`: turns a
      `dataclasses.dataclass` result into a JSON-safe dict, with `date`
      fields rendered as ISO strings.
- [x] 3.3/3.4 `test_delegate_wraps_typed_core_error_as_tool_error` /
      `test_delegate_wraps_config_and_search_errors`: the error-
      wrapping helper, given a `core.CoreError`/`config.
      VaultNotConfiguredError`/`VaultNotFoundError`/`index.search.
      SearchError` raised inside a wrapped handler, raises a `ToolError`
      naming the error's type and message (design.md decision 9) —
      never lets the raw exception escape unlabeled. `MCPServer`'s own
      `_handle_call_tool` (confirmed by reading the installed SDK, and
      by the end-to-end subprocess test in section 19) converts that
      `ToolError` into a tool result with `isError=true`; nothing in
      this module constructs a `CallToolResult` directly.
- [x] 3.5 Implemented `_to_jsonable` (serialization) and `_delegate`
      (a decorator combining error-wrapping and serialization,
      applied to every tool handler) in `mcp_server.py` — named
      differently from the plan's `_serialize_result`/
      `_call_tool_safely` (one decorator does both jobs, since every
      tool needs both together, not either alone); one implementation,
      not duplicated per tool.
- [x] 3.6 Ran 3.1-3.4 green (`test_delegate_passes_through_result_
      unmodified` added alongside as a third, simpler case).

## 4. Enum schemas — tests, then implementation

- [x] 4.1/4.2 **Deviates from the plan's "write a schema-generation
      helper"**: no such helper exists. Every enum-typed tool parameter
      (`status: list[Status] | None`, `mode: SearchMode | None`,
      `kind: DocumentKind | None`/`DocumentKind`, `new_status: Status`)
      is instead type-annotated with the actual `models.py`/
      `index.search` enum directly; the SDK's own pydantic-based schema
      generation produces the JSON Schema `enum` array from the enum
      type automatically, and coerces/validates the incoming wire value
      into that enum member before the handler runs. This satisfies
      design.md decision 3 more directly than a hand-rolled helper
      would (nothing here can drift from `models.py`, because nothing
      here restates it at all) and was confirmed empirically:
      `test_search_schema_enums_match_status_and_mode`,
      `test_set_status_schema_enum_matches_status`,
      `test_add_document_schema_enum_matches_document_kind` all assert
      the generated schema's `enum` equals `[m.value for m in Member]`
      for the real installed SDK's schema output.
- [x] 4.3 N/A given 4.1/4.2's approach — no helper to unit-test in
      isolation; covered by the schema-equality tests above instead.

## 5. Read tool: list_vacancies

- [x] 5.1 `test_list_vacancies_tool_delegates`: mocked `core.
      list_vacancies` called once with matching arguments; result
      matches the mock, serialized, unmodified.
- [x] 5.2 `test_list_vacancies_schema_matches_core_param_names`.
- [x] 5.3 `test_list_vacancies_omitting_limit_matches_core_default`.
- [x] 5.4/5.5 Covered by the cross-cutting enum/annotation tests in
      sections 4/20 (parametrized over all tools) rather than a
      per-tool duplicate.
- [x] 5.6 Implemented the `list_vacancies` tool.
- [x] 5.7 Ran 5.1-5.3 green.

## 6. Read tool: get_company

- [x] 6.1 `test_get_company_tool_delegates`.
- [x] 6.2 `test_get_company_typed_error_becomes_tool_error`.
- [x] 6.3 `test_get_company_bounded_output_no_document_bodies` (real
      `_demo_vault`, no mocking): vacancy rows carry `document_count`;
      serialized JSON contains neither filed document's body text.
- [x] 6.4 Implemented the `get_company` tool.
- [x] 6.5 Ran 6.1-6.3 green.

## 7. Read tool: get_vacancy

- [x] 7.1 `test_get_vacancy_tool_delegates`.
- [x] 7.2 Covered by the same test: argument name asserted as
      `id_or_query` via the mock's `assert_called_once_with`.
- [x] 7.3 Implemented the `get_vacancy` tool.
- [x] 7.4 Ran 7.1-7.2 green.

## 8. Read tool: search

- [x] 8.1 `test_search_tool_delegates_and_maps_company`: delegation,
      `mode` passed through as a `SearchMode` value.
- [x] 8.2 Same test: `company` argument maps to `core.search`'s
      `company_slug` parameter.
- [x] 8.3 Covered by the same test: omitting `mode` calls `core.search`
      with `mode=None`.
- [x] 8.4 `test_search_schema_enums_match_status_and_mode`.
- [x] 8.5 `test_search_returns_snippets_not_full_documents` (real
      indexed `_demo_vault`): every hit carries `snippet`/`path`, no
      `text`/`body` field (`SearchHit`'s own dataclass shape has none),
      and each snippet stays within `index.snippet.SNIPPET_MAX_CHARS`.
- [x] 8.6 **Deviates from a dedicated max-limit-size test**: bounded by
      construction, not measured — `SearchHit` structurally carries a
      snippet capped at `SNIPPET_MAX_CHARS` (200 chars) and no body
      field, so a result set at any limit is bounded by
      `limit * (fixed per-hit field sizes)`; the per-hit bound is
      exactly what 8.5 already asserts. `search`'s tool description
      states this to the model ("Returns snippets and paths, never full
      document bodies").
- [x] 8.7 `test_search_description_states_keyword_vs_hybrid_guidance`.
- [x] 8.8 Implemented the `search` tool with the description text.
- [x] 8.9 Ran 8.1-8.7 green.

## 9. Read tool: read_document

- [x] 9.1 `test_read_document_tool_delegates`.
- [x] 9.2 `test_read_document_rejects_path_outside_vault`: an outside
      path returns a `ToolError` naming `PathOutsideVaultError`, not a
      file's contents.
- [x] 9.3 Covered by `test_no_tool_schema_accepts_a_write_path_argument`
      (section 21): `read_document` is the one tool with a `path`
      argument, and it's read-only.
- [x] 9.4 Implemented the `read_document` tool.
- [x] 9.5 Ran 9.1-9.3 green.

## 10. Read tool: resolve

- [x] 10.1 `test_resolve_tool_delegates`.
- [x] 10.2 Implemented the `resolve` tool.
- [x] 10.3 Ran 10.1 green.

## 11. Write tool: append_note

- [x] 11.1 `test_append_note_tool_delegates`.
- [x] 11.2 Same test: omitting `date` calls `core.append_note` with
      `date=None`.
- [x] 11.3 Covered by `test_write_tools_have_read_only_and_destructive_
      hint_false` (section 20, parametrized over all three write tools).
- [x] 11.4 Implemented the `append_note` tool.
- [x] 11.5 Ran 11.1-11.3 green.

## 12. Write tool: set_status

- [x] 12.1 `test_set_status_tool_delegates`.
- [x] 12.2 `test_set_status_schema_enum_matches_status`.
- [x] 12.3 `test_set_status_invalid_transition_becomes_tool_error`.
- [x] 12.4 Implemented the `set_status` tool.
- [x] 12.5 Ran 12.1-12.3 green.

## 13. Write tool: add_document

- [x] 13.1 `test_add_document_tool_delegates`: argument names exactly
      `{vacancy_id, kind, content, title, date, external_id}`.
- [x] 13.2 `test_add_document_schema_enum_matches_document_kind`.
- [x] 13.3 `test_add_document_schema_has_no_path_argument`.
- [x] 13.4 `test_add_document_title_with_separators_stays_inside_vault`
      (real vault, no mocking): a `title` of `"../../etc/passwd"` files
      inside the vacancy's `documents/` directory; nothing created
      elsewhere.
- [x] 13.5 `test_add_document_dedupes_by_external_id`: two calls with
      the same `external_id` return the same path.
- [x] 13.6 Implemented the `add_document` tool.
- [x] 13.7 Ran 13.1-13.5 green.

## 14. Resource: vacancy-radar://companies

- [x] 14.1 `test_companies_resource_lists_every_company` (real
      `_demo_vault`): lists both companies with slug, name, and correct
      vacancy count.
- [x] 14.2 Implemented via a direct `read_vault` read (design.md
      decision 10/Open Question resolved this way): groups
      `snapshot.companies`/`snapshot.vacancies` into slug → (name,
      count) — the same registry shape `core._resolve_company_slug`'s
      own tier already computes, reimplemented at this one call site
      rather than importing a private `core.py` helper across module
      boundaries.
- [x] 14.3 Ran 14.1 green.

## 15. Resource: vacancy-radar://statuses

- [x] 15.1 `test_statuses_resource_lists_every_status_and_its_
      transitions`.
- [x] 15.2 `test_statuses_resource_reflects_models_py_live`: a
      monkeypatched `STATUS_TRANSITIONS` changes the resource's content
      on the next read with no `mcp_server.py` code change.
- [x] 15.3 Implemented the `vacancy-radar://statuses` resource.
- [x] 15.4 Ran 15.1-15.2 green.

## 16. Prompt: prep_interview

- [x] 16.1 `test_prep_interview_references_real_content`.
- [x] 16.2 `test_prep_interview_unknown_company_is_a_resolution_
      failure`.
- [x] 16.3 Covered by the same resolution-failure code path
      (`_resolution_failure_text`), exercised via `resolve`'s own
      ambiguous-candidates behavior (not separately re-tested here;
      `core.resolve`'s ambiguity handling is already covered in
      `test_core.py`).
- [x] 16.4 Implemented `prep_interview` (as `_prep_interview_text`,
      called from the registered prompt function — extracted to a
      top-level function to keep `_register_prompts` simple, see 16.5's
      note), composed from `core.resolve`, `core.get_company`, and
      `core.get_vacancy`/`core.read_document` per vacancy document.
- [x] 16.5 Ran 16.1-16.2 green. Refactored `_register_prompts` (and
      `draft_reply`/`weekly_review` alongside it) from three inline
      closures into top-level `_prep_interview_text`/
      `_draft_reply_text`/`_weekly_review_text` functions plus a
      shared `_resolution_failure_text` helper, after `ruff`'s `C901`
      flagged the original all-inline version as too complex — a
      simplification, not a behavior change.

## 17. Prompt: draft_reply

- [x] 17.1 `test_draft_reply_references_real_correspondence`.
- [x] 17.2 Same resolution-failure path as 16.2/16.3 (`noun="vacancy"`).
- [x] 17.3 Implemented `draft_reply` (`_draft_reply_text`), composed
      from `core.resolve` and `core.get_vacancy`/`core.read_document`.
- [x] 17.4 Ran 17.1 green.

## 18. Prompt: weekly_review

- [x] 18.1 `test_weekly_review_surfaces_stale_take_home_and_needs_
      review`: a vault with one stale vacancy (`v3`, found 2020, no
      documents), one `take_home` (`v2`), and one `needs_review` (`v3`
      again) produces a message naming both under their respective
      sections.
- [x] 18.2 Implemented `weekly_review` (`_weekly_review_text`), composed
      from three `core.list_vacancies` calls (`stale_days=14`,
      `status=[Status.TAKE_HOME]`, `needs_review=True`).
- [x] 18.3 Ran 18.1 green.

## 19. Transport discipline

- [x] 19.1 `test_subprocess_stdout_is_json_rpc_only_and_iserror_is_
      structured`: a real subprocess, driven with hand-written
      newline-delimited JSON-RPC frames over stdin/stdout (confirmed
      the SDK's own wire framing by reading `mcp/server/stdio.py`);
      every line read from stdout across `initialize` → `tools/list` →
      `tools/call` parses as JSON, and the `tools/call` response for a
      nonexistent vacancy id has `isError: true` with `EntityNotFoundError`
      in its text.
- [x] 19.2 `test_warning_during_a_tool_call_does_not_raise`: an
      over-length `search` query (reusing `index.search`'s own
      threshold) still returns a normal result — Python's `warnings`
      module writes to stderr by default (not asserted separately here;
      19.1's subprocess test is what actually observes stdout purity
      end to end, which is the property that matters).
- [x] 19.3 `test_build_server_does_not_load_embedding_model`: with
      `index.embed._get_model` monkeypatched to raise, `build_server`
      completes without invoking it.
- [x] 19.4 `test_keyword_search_succeeds_without_loading_embedding_
      model`: same monkeypatch, a `mode="keyword"` search still
      succeeds.
- [x] 19.5 `test_build_server_is_fast_without_an_embedding_model`:
      in-process timing of `build_server` (with the loader still
      monkeypatched to raise, so "no model" is guaranteed, not just
      assumed) asserts under 2 seconds — chosen as a generous bound for
      registering nine tools/two resources/three prompts, not a tuned
      SLA; the true subprocess-spawn-to-ready figure is left to the
      manual verification gate (section 24), where "does not delay
      client launch" is actually observable.
- [x] 19.6 Confirmed no `print()` call exists in `mcp_server.py`
      (`ruff check` green, T20 included in `select = ["ALL"]`).
- [x] 19.7 Ran 19.1-19.5 green; `ruff check`/`ruff format --check`
      clean on `mcp_server.py` and `test_mcp_server.py`.

## 20. Annotations and tool-list membership

- [x] 20.1 `test_tool_list_is_exactly_the_nine_specified_tools`.
- [x] 20.2 Same test: `reindex`/`create_vacancy` absent; no generic
      query/expression/code tool exists in the module at all (not just
      absent from the list).
- [x] 20.3 `test_every_tool_has_open_world_hint_false`.
- [x] 20.4 `test_read_tools_have_read_only_hint_true` /
      `test_write_tools_have_read_only_and_destructive_hint_false`
      (already implemented per-tool in sections 5-13; this section is
      the consolidated cross-check).
- [x] 20.5 Ran 20.1-20.4 green.

## 21. Cross-cutting safety checks

- [x] 21.1 `test_no_tool_schema_accepts_a_write_path_argument`
      (parametrized over all nine, `read_document` excepted).
- [x] 21.2 `test_write_sequence_never_removes_a_pre_existing_file`:
      `append_note` → `set_status` → `add_document` in sequence against
      one hand-built vault never shrinks the file set (`create_vacancy`
      has no tool, so the vacancy is seeded directly, per the plan's
      own note).
- [x] 21.3 Ran 21.1-21.2 green.

## 22. Docs

- [x] 22.1 Added a "## MCP server" README section: how to run
      `vacancy-radar-mcp`, the `--vault`/`VAULT_PATH` precedence (with
      the roots-deprecation reasoning stated inline), a table of all
      nine tools and the `core.py` function each delegates to, the
      exposure-decision note (`reindex`/`create_vacancy` excluded), the
      keyword-vs-hybrid guidance restated from the `search` tool
      description, and the two resources/three prompts. Also fixed, in
      passing, the "## Status" section's stale "No vault, index, or MCP
      server yet" line and the "Writing" section's broken
      `openspec/changes/cli-write/...` path (→ `archive/2026-08-06-
      cli-write/`) — noticed while editing the adjacent section, same
      kind of drive-by fix cli-write's own 15.1 made.
- [x] 22.2 Checked `git tag -l` (`v0.1.0` exists) and confirmed no
      `CHANGELOG.md` exists in this repo; followed cli-write's
      precedent (15.2) and kept this stage's notable decisions in the
      README section from 22.1 rather than starting a CHANGELOG file as
      a side effect of this change.

## 23. Full-suite verification

- [x] 23.1 `pytest tests/ -q` → 469 passed (full suite, including all
      51 new `test_mcp_server.py` tests).
- [x] 23.2 `ruff check src/ tests/` and `ruff format --check src/
      tests/` → clean.
- [x] 23.3 `git status --porcelain` after the full run shows only the
      expected changes (`pyproject.toml`, `uv.lock`,
      `src/vacancy_radar/mcp_server.py`, `tests/test_mcp_server.py`,
      `README.md`, this change's `openspec/` directory) — nothing under
      `tests/fixtures/vault/` is modified.

## 24. Manual verification gate (not automatable)

These require a real MCP client and cannot be covered by `pytest` —
perform them once, by hand, before considering this change complete,
and record the outcome (client name/version, what was observed) in
this section.

- [ ] 24.1 Configure `vacancy-radar-mcp` (with `--vault` pointing at a
      real or fixture-derived vault) in Claude Desktop's MCP server
      settings and confirm the server loads without error.
- [ ] 24.2 Confirm all nine tools (`list_vacancies`, `get_company`,
      `get_vacancy`, `search`, `read_document`, `resolve`,
      `append_note`, `set_status`, `add_document`) appear in Claude
      Desktop's tool list for this server, and that `reindex`/
      `create_vacancy` do not.
- [ ] 24.3 From a live Claude Desktop conversation, ask for a company
      dossier by name and confirm a real `get_company` result — sourced
      from the configured vault, not fabricated — is returned and
      rendered.
