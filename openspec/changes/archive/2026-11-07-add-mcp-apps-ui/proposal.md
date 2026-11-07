## Why

Every read tool in the MCP server hands the client a JSON blob, and the
model re-narrates it into prose — a `list_vacancies` call becomes a wall
of text, a `get_vacancy` a paragraph that buries the status timeline and
the document list. The `mcp` SDK now ships the MCP Apps extension
(`io.modelcontextprotocol/ui`), which lets a tool point at a sandboxed
HTML view the host renders inline. Adding it turns those same results
into a compact card or table for clients that support it, while every
other client sees exactly the text it sees today.

## What Changes

- Build the server on `FastMCP` with its Apps support, so it advertises
  the `io.modelcontextprotocol/ui` capability.
- Ship a small set of self-contained `ui://` HTML resources — one per
  view — served as `text/html;profile=mcp-app`, each rendering **only**
  from the tool result it is handed via the Apps host bridge, with no
  network access and a locked-down CSP.
- Stamp `_meta.ui.resourceUri` on the matching existing read tools so a
  UI-capable host knows which view to render:
  - `list_vacancies` → a status-grouped table of vacancy summaries
  - `get_vacancy` → a detail card: status, dates, recruiter, stage_note,
    tags, and the document list
  - `get_company` → a dossier card: recruiters, notes, vacancies
  - `search` → a ranked list of hits with snippets and paths
- Keep the tool surface at exactly the same twelve tools with the same
  annotations and the same text output — the UI is additive `_meta` and
  degrades to that text on any client that did not negotiate Apps, with
  no configuration to enable or disable.

## Capabilities

### New Capabilities
- `mcp-apps-ui`: the MCP Apps extension registration, the set of read
  tools that carry a `ui://` view reference, the contract that each
  `ui://` resource is static, self-contained, network-free, and renders
  only from its tool's result, and the guarantee that UI-bound tools
  still return identical text for non-Apps clients.

### Modified Capabilities
- `mcp-transport`: the "exactly the … specified tools" requirement
  gains a scenario that a `_meta.ui` entry on a tool does not change the
  tool set, the count, or the `openWorldHint=false` / `readOnlyHint`
  hints; the startup-time bound must still hold with the `ui://`
  resources registered. (The requirement's text is also corrected from
  "eleven" to "twelve" — `edit_vacancy` was added in v0.2.0 and the
  main spec was not updated; the code and its tests already expect
  twelve.)
- `mcp-resources`: `ui://` app resources are exposed alongside
  `vacancy-radar://companies` and `vacancy-radar://statuses`; the two
  data resources are unchanged.

## Impact

- **Code**: `src/vacancy_radar/mcp_server.py` stays the only MCP module
  (extension registration, `_meta` on four read tools, and a small
  asset loader); new `src/vacancy_radar/assets/mcp_ui/` holds the view
  `.html`/`.css`/`.js` files; `tests/test_mcp_server.py` and new
  `tests/test_mcp_ui_views.py`.
- **Dependencies**: the runtime dependency is `fastmcp[apps]>=4.0.0b5`
  (which brings `mcp>=2.1`), replacing the bare `mcp>=2.0.0`; it
  provides `fastmcp.apps`. One test-only dev dependency,
  `playwright`, for the headless-browser render checks (they skip when
  its Chromium build is absent; CI installs it on one leg).
- **Invariant 4** (no logic beyond argument marshalling): preserved —
  the server registers static HTML and stamps metadata; no server-side
  rendering, and the views contain no vault business rules.
- **Invariant 5** (stdout is JSON-RPC only): unaffected — `ui://`
  resources travel as ordinary `resources/read` frames.
- **Clients**: no behaviour change for any client that does not
  negotiate the Apps extension.
