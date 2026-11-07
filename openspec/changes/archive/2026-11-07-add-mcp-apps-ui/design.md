## Context

`mcp_server.py` exposes eleven tools, each a thin delegate to one
`core.py` call, returning that call's result serialized by `_to_jsonable`.
Clients receive JSON; the model turns it into prose. `list_vacancies`,
`get_vacancy`, `get_company`, and `search` are the results a user most
often wants to *scan* rather than read — a table, a timeline, a ranked
list.

The installed `fastmcp` (4.0.0b5, on `mcp` 2.1) ships MCP Apps support
at `fastmcp.apps` (`io.modelcontextprotocol/ui`, ext-apps / SEP-2133).
It registers `ui://` HTML resources (served as
`text/html;profile=mcp-app`), advertises the capability, and lets a tool
carry `_meta.ui.resourceUri` pointing at one
of those resources. The host renders the resource in a sandboxed iframe
and passes the tool's result to it over a `postMessage` bridge; the HTML's
own JS draws the view. Clients that did not negotiate the extension never
see the `ui://` resources and fall back to the tool's text result —
`client_supports_apps(ctx)` reports which case applies.

Binding constraints from `openspec/project.md` and the existing MCP specs:

- **Invariant 4**: the MCP server contains no logic beyond argument
  marshalling. No vault business rules, no reshaping of `core.py` output.
- **Invariant 5**: nothing to stdout but JSON-RPC.
- `mcp-transport`: a fixed tool set (twelve, since `edit_vacancy` was
  added in v0.2.0 — the main spec still says "eleven" and this change
  corrects it), `openWorldHint=false` on every tool, bounded startup
  time, typed errors as tool results.
- `mcp-read-tools`: each read tool returns its one `core.py` call's
  result "unmodified apart from serialization".

## Goals / Non-Goals

**Goals:**

- A UI-capable host renders `list_vacancies`, `get_vacancy`,
  `get_company`, and `search` results as inline views.
- Every other client sees byte-for-byte the same tool output as today.
- No new runtime dependency (the `mcp` SDK already ships the Apps
  extension), no server-side rendering, no business logic in the server
  or the views. A test-only `playwright` dev dependency drives the
  browser render checks.
- No configuration: the extension is always registered and relies on
  the host's capability negotiation to activate.
- Startup stays within the `mcp-transport` bound.

**Non-Goals:**

- UI for the write tools (`set_status`, `append_note`, `add_document`,
  `create_vacancy`, `edit_vacancy`) — a later change if wanted.
- Interactive views that call tools back from the iframe (forms,
  buttons that mutate the vault). v1 views are read-only renderings.
- Theming, charts, or a design system. Plain semantic HTML + minimal
  inline CSS.
- Replacing the `vacancy-radar://companies` / `://statuses` data
  resources or the three prompts.
- A CLI (`vacancy-radar`) equivalent — this is MCP-only.
- A launch flag to enable or disable the UI. The Apps extension
  degrades to text output on its own for any client that did not
  negotiate it (ext-apps / SEP-2133), so a toggle would only add a
  configuration surface with no behaviour to guard.

## Decisions

### Decision 1: use FastMCP's Apps support, wired in `build_server`

`build_server` constructs `FastMCP(...)`, registers the four `ui://`
resources and (see Decision 3) the tool `AppConfig`s. Rationale: it is
the supported, in-framework mechanism; it owns the capability
advertisement and the
`text/html;profile=mcp-app` MIME handling; no wire-format code of our
own. Alternative — hand-rolling `_meta.ui` and a raw `text/html` resource
— was rejected: it duplicates the SDK and risks the host refusing a
resource under the wrong MIME type.

### Decision 2: bind the view to the existing tool via `_meta`, add no tools

The four tools keep their identity, signature, annotations, and text
result. We only add `_meta={"ui": {"resourceUri": "ui://vacancy-radar/<view>"}}`
via `server.tool(meta=...)` (the SDK's `add_tool` already accepts `meta`).
We do **not** use `apps.tool()` (which would register *new* tools) — that
would break `mcp-transport`'s "exactly eleven tools". Rationale: the
eleven-tool contract is load-bearing and the UI is genuinely additive
metadata. Alternative — `*_view` tools — rejected on the count rule and
because it splits one capability across two tools.

### Decision 3: the `ui://` resources are static, self-contained HTML strings

The views live as real `.html`/`.css`/`.js` files under
`src/vacancy_radar/assets/mcp_ui/` — one `page.html` shell, one
`view.css`, one `bridge.js`, one `helpers.js`, and one render function
per view. `mcp_server.py` reads them through `importlib.resources` and
concatenates them into four whole documents once at import: a pure
join of static fragments, no vault data. Keeping them as files (rather
than Python string literals) gives the CSS and JS real editor support
and keeps the 88-column lint rule off markup — `mcp_server.py` stays
the only MCP Python module, holding ~40 lines of loading, not markup.
Hatchling packages anything under the package directory, so no
packaging config is needed; a wheel install resolves the assets the
same way. Each document carries inline CSS and inline JS only: no
`<script src>`, no `<link href>`, no `fetch`. The JS speaks the ext-apps host↔iframe
protocol (JSON-RPC 2.0 over `postMessage` to `window.parent`): on load
it sends `ui/initialize`, then `ui/notifications/initialized`, then
renders when the host pushes `ui/notifications/tool-result` (the tool's
`content` + `structuredContent`), re-themes on
`ui/notifications/host-context-changed`, and posts
`ui/notifications/size-changed` after layout. It renders with DOM APIs
only; it calls no tool back (`tools/call` from the view is a non-goal). Registered with a locked `ResourceCSP`
(`connect_domains=[]`, `resource_domains=[]`, `frame_domains=[]`) and no
`ResourcePermissions`. Rationale: keeps Invariant 4 intact (no
server-side rendering; the view is an asset), keeps the vault's
"it's yours / offline" property (a view can't phone home), and keeps
`resources/read` responses to plain static text. Alternative —
templating the HTML server-side with the result baked in — rejected:
that is rendering logic in the server, and the SDK's bridge already
delivers the result to the iframe.

### Decision 4: the four views and what each renders

| Tool | View | Renders (from the result only) |
|---|---|---|
| `list_vacancies` | `ui://vacancy-radar/vacancy-list` | rows grouped by status: company, role, id, dates, doc count |
| `get_vacancy` | `ui://vacancy-radar/vacancy-detail` | header (role @ company, status), source_url, dates, recruiter, stage_note, salary_note, tags, document list (id/kind/title/date/path, no bodies) — `VacancyDetail` carries no status history, so the view shows none |
| `get_company` | `ui://vacancy-radar/company-dossier` | display name, domains, recruiters, notes, vacancy summaries |
| `search` | `ui://vacancy-radar/search-results` | ranked hits: title/path, kind, score, snippet |

Every field shown is already present in the tool's existing serialized
result. No view fetches, computes, or infers anything.

### Decision 5: no launch flag — the extension is always registered

`build_server` always constructs `Apps()`, registers the four
resources, stamps the `_meta`, and passes `extensions=[apps]`. There is
no `--ui` / `--no-ui`. Rationale: ext-apps / SEP-2133 requires a host
to ignore extension metadata it did not negotiate, so a non-Apps client
already sees exactly today's text — a flag would guard nothing. It also
keeps `_parse_args` at its single `--vault` argument. Alternative — a
`--no-ui` escape hatch for a client that mishandles unknown `_meta` —
rejected: that is a client bug to report upstream, not a reason for a
permanent config surface; reverting the change is the fallback.

### Decision 6: three test layers — in-process, stdio subprocess, headless browser

1. **In-process** (`test_mcp_server.py` §23): the four tools carry
   `_meta.ui` and no other tool does; `get_capabilities()` advertises
   the extension; each UI-bound tool's result equals its one `core.py`
   call serialized, so the view adds nothing a client reads; the two
   data resources still return their own content and stay the only
   `vacancy-radar://` pair; every `ui://` resource is
   `text/html;profile=mcp-app`, parses as one HTML doc, has an
   all-empty CSP, and contains no external-reference or network-call
   token. There is deliberately **no** second "server without the
   extension" to diff against — comparing against `core.py`'s own
   output is the stronger claim, and the subprocess layer below proves
   the degradation on the wire.
2. **stdio subprocess** (`test_mcp_server.py` §23): launch the real
   server, drive `initialize` / `tools/list` / `resources/list` /
   `resources/read` / `tools/call` with hand-written frames from a
   client that negotiates **no** extension — the `_meta.ui` refs, the
   `ui://` resources, and the unchanged JSON tool results all arrive.
3. **Headless browser** (`test_mcp_ui_views.py`, Playwright/Chromium):
   load each real shipped view, `dispatchEvent` the
   `ui/notifications/tool-result` message with a serialized `core` model,
   and assert on `#vr-root` — every result field shows, no document body
   text shows, the bridge posted `ui/initialize` and a trailing
   `ui/notifications/size-changed`, and `host-context-changed` re-themes.
   Skips cleanly when Chromium is absent; CI installs it on one leg.

The browser fixture is **function-scoped**: the sync Playwright API runs
an asyncio loop on the test thread while open, and `test_mcp_server.py`
uses `asyncio.run(...)`, which refuses to nest — opening and fully
closing Playwright per test keeps them apart regardless of order.

**Wire note:** `ServerCapabilities.extensions` is a 2026-07-28 field.
The plain `initialize` handshake negotiates at most 2025-11-25 (this
SDK's `_negotiate_initialize` caps there), and the serializer drops
`extensions` at that version — so a legacy-handshake client does not see
the capability line, though it still gets the `ui://` resources and the
tool `_meta.ui`. A 2026-aware host negotiates the modern wire and gets
the capability too. This is an SDK/protocol detail, not a gap in this
change; the in-process `get_capabilities()` check covers advertisement.

## Risks / Trade-offs

- **A client chokes on unknown `_meta.ui`** → the ext-apps / SEP-2133
  contract requires hosts to ignore unnegotiated extension metadata; a
  client that doesn't is a bug to report upstream, and reverting this
  change is the fallback (Decision 5).
- **View drifts from the result shape** when a `core.py` model gains or
  renames a field → the view renders what it knows and ignores the rest
  (no schema assertion in JS); a test reads a real fixture result
  through each view's expected field set to catch a rename.
- **Markup bloating the Python module** → resolved by Decision 3: the
  views are asset files, so `mcp_server.py` holds only the loader; the
  startup-time test guards against a regression.
- **No off switch for an operator who wants the minimal tool surface**
  → the tool set, count, and hints are provably unchanged (spec
  `mcp-transport`), and the extra `ui://` resources are inert for a
  non-Apps client; if a real need appears, a flag is an additive
  follow-up.
- **Scope creep toward interactive views** → explicitly a non-goal;
  v1 resources request no permissions and no `connect_domains`, so an
  interactive view would be a visible, reviewable follow-up change.
- **Invariant 4 challenge**: "is shipping HTML 'logic'?" → the server
  does no rendering; the view is a static asset delivered verbatim, the
  way a docstring or the `instructions` string is. The design keeps zero
  branching on vault content server-side.

## Migration Plan

Additive; no data or protocol migration. Deploy: ship the version, the
extension activates for hosts that negotiate it. Rollback: revert the
change — no persisted state, no vault format change, no client contract
broken. CHANGELOG: an `### Added` entry under a new version heading
(there is a prior `v0.2.0` tag, so `[Unreleased]` is also valid — see
the CHANGELOG-convention memory).

## Open Questions

- **Resolved — how to verify rendering without a real host.** A
  headless-Chromium test (`test_mcp_ui_views.py`, `playwright` dev
  dependency) loads each shipped view and drives it with the real
  ext-apps `ui/notifications/tool-result` message. A manual pass in an
  actual MCP Apps host is still worth doing once for visual polish, but
  it is no longer the only check.
- **New dev dependency: `playwright`.** Test-only; the render tests skip
  when its Chromium build is absent, so `uv run pytest` still works
  without `playwright install`. CI installs the browser on one leg.
