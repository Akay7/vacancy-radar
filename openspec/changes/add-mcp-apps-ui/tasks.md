## 1. The four ui:// views

- [x] 1.1 Write `vacancy-list` HTML: standalone doc, inline CSS/JS only, reads the tool result from the Apps host bridge, renders rows grouped by status (company, role, id, dates, doc count).
- [x] 1.2 Write `vacancy-detail` HTML: header (role @ company, status), source_url, dates, recruiter, stage_note, salary_note, external_id, tags, document list (id/kind/title/date/path, no bodies). `VacancyDetail` has no status history — render none.
- [x] 1.3 Write `company-dossier` HTML: display name, domains, recruiters, notes, vacancy summaries.
- [x] 1.4 Write `search-results` HTML: ranked hits with title/path, kind, score, snippet.
- [x] 1.5 Keep the views as real files under `src/vacancy_radar/assets/mcp_ui/` (`page.html`, `view.css`, `bridge.js`, `helpers.js`, one render `.js` per view). `mcp_server.py` — the only MCP Python module — reads them via `importlib.resources` and concatenates them once at import; hatchling packages them with no config. Bridge JS: send `ui/initialize` → `ui/notifications/initialized`, render on `ui/notifications/tool-result`, re-theme on `ui/notifications/host-context-changed`, post `ui/notifications/size-changed` after layout.
- [x] 1.6 Confirm every view body has no `<script src>`, no `<link href>`, no `fetch`/`XMLHttpRequest`/`WebSocket`, no `http(s)://` or `//` subresource.

## 2. Server wiring

- [x] 2.1 In `build_server`, register the four views as `TextResource`s with `mime_type=UI_MIME_TYPE` and `meta={"ui": app_config_to_meta_dict(AppConfig(csp=ResourceCSP(connect_domains=[], resource_domains=[], frame_domains=[])))}`, no `permissions`.
- [x] 2.2 Build the server as `FastMCP(...)`; its Apps support advertises the capability.
- [x] 2.3 Add `app=AppConfig(resource_uri="ui://vacancy-radar/<view>")` to the `@server.tool(...)` calls for `list_vacancies`, `get_vacancy`, `get_company`, `search`; all other tools unchanged.
- [x] 2.4 Keep the `_delegate` wrapper and every tool's `core.py` call untouched — no server-side rendering, no result reshaping. `_parse_args` keeps its single `--vault` argument.

## 3. Tests (`tests/test_mcp_server.py`, section 23)

- [x] 3.1 `tools/list` is exactly the twelve tools with `openWorldHint=false`; the four read tools also report `readOnlyHint=true`. (Existing `test_tool_list_is_exactly_the_twelve_specified_tools` / `test_every_tool_has_open_world_hint_false` / `test_read_tools_have_read_only_hint_true` still pass unchanged.)
- [x] 3.2 The four tools carry `_meta.ui.resourceUri`, each resolving to a registered resource; no other tool has `_meta.ui`. → `test_four_read_tools_reference_a_registered_ui_view`
- [x] 3.3 The server advertises the `io.modelcontextprotocol/ui` capability; the CLI exposes no UI toggle. → `test_server_advertises_the_apps_extension`, `test_cli_exposes_no_ui_toggle`
- [x] 3.4 Each `ui://` resource is `text/html;profile=mcp-app`, parses as one HTML document, has empty/unset CSP connect/resource/frame domains, and contains no external subresource or network-call token. → `test_ui_resources_are_self_contained_app_documents`
- [x] 3.5 Each UI-bound tool's serialized result equals its one `core.py` call serialized — no second "server without the extension" to diff against; comparing to core's own output is the stronger claim (the `search` wall-clock `elapsed_ms` excluded, it jitters call-to-call). → `test_ui_bound_tools_return_their_core_result_untouched`
- [x] 3.6 `vacancy-radar://companies` and `vacancy-radar://statuses` still return their own content and remain the only `vacancy-radar://` resources alongside the four `ui://` ones. → `test_ui_resources_do_not_disturb_the_data_resources`
- [x] 3.7 View-level check: the `vacancy-detail` render function references only fields on `VacancyDetail`/`DocumentSummary` (a `core.py` rename fails it), never `body`/`text`/`content`, and a real `get_vacancy` result carries every field it reads. → `test_vacancy_detail_view_reads_only_vacancy_detail_fields`

## 4. Browser render tests (`tests/test_mcp_ui_views.py`, Playwright)

- [x] 4.1 Add `playwright` as a dev dependency; CI installs `--with-deps chromium` on the 3.12 leg (cached), other legs skip the browser tests.
- [x] 4.2 Function-scoped `chromium_browser` fixture (session scope conflicts with `test_mcp_server.py`'s `asyncio.run` — the sync Playwright API holds a live loop while open); `pytest.skip` when Chromium is absent.
- [x] 4.3 `render_view(tool, structured_content)` helper: inject a `postMessage` recorder as the first `<head>` script, `set_content` the shipped view, `dispatchEvent` the `ui/notifications/tool-result`, return `{text, html, messages}`.
- [x] 4.4 Per view: every result field renders; `vacancy-detail` shows the document index but no body text; `search` shows each hit from its own fields incl. the snippet; empty/malformed results degrade to "No …" not a blank frame; bridge posts `ui/initialize` + trailing `ui/notifications/size-changed`; `host-context-changed` sets `data-theme`.
- [x] 4.5 `test_all_four_views_reference_only_their_result_fields` — browser-free structural check across all four render functions (catches a `core.py` rename even without Chromium).

## 5. Docs, changelog, CI

- [x] 5.1 README: note under the MCP server reference that UI-capable hosts render `list_vacancies`/`get_vacancy`/`get_company`/`search` inline, with no setup and no effect on other clients.
- [x] 5.2 CHANGELOG: `## [Unreleased]` (a `v0.2.0` tag exists) with an `### Added` entry for the views and a `### Fixed` entry for the eleven→twelve tool-count correction.
- [x] 5.3 `openspec/project.md`: invariant 4 now notes the `ui://` views are static assets, not a server-side-rendering exception.
- [x] 5.4 `.github/workflows/ci.yml`: cache + `playwright install --with-deps chromium` on the 3.12 leg only.

## 6. Verification

- [x] 6.1 `build_server` with the four `ui://` resources registered: ~0.015 s (5 runs, warm import), against the `mcp-transport` bound of 2.0 s (`test_build_server_is_fast_without_an_embedding_model`). Well within.
- [x] 6.2 View rendering is verified automatically in headless Chromium (`tests/test_mcp_ui_views.py`) — the automated stand-in for screenshotting in a real host. `test_subprocess_serves_ui_views_and_unchanged_text_to_a_plain_client` covers the non-Apps client end to end over stdio.
- [ ] 6.3 (optional, needs a real host) Open the views once in an ext-apps-capable MCP host for a visual-polish pass; nothing functional rides on this.
