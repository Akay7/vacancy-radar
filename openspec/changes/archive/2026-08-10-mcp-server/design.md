## Context

Stages 1-7 gave this codebase a `core.py` that both `cli.py` and this
stage call identically (invariant 4, restated in `core.py`'s own
module docstring: "shared by the CLI and, later, the MCP server (stage
8)"). Every read function resolves its own vault from an optional
`vault: Path | None` argument or `VAULT_PATH` (`config.
resolve_vault_path`); every write function is append-only or a
validated transition and refreshes the index before returning. None of
that changes here. What stage 8 adds is a second caller of the same
functions — a stdio MCP server — resolving the vault path via the
exact same `config.resolve_vault_path` precedence and validation
`core.py`'s own docstring already names as this stage's seam (see
Decision 7): no new resolution rule, no protocol-supplied path.

The content flowing through this server is more adversarial than
anything the CLI has handled so far. A human typing `vacancy-radar add
<id> --title "..."` chose that title. An MCP tool call filing a
recruiter's email is different: the model is relaying `title` and
`content` from text it did not write and does not fully trust either —
this is the scenario stage 7's design.md flagged when it justified
derived filenames "for stage 8, where the content being filed... is
attacker-controlled text." This design treats that as already solved
by `core.py` (Decision 4 below just restates why it holds) and focuses
on what's actually new: transport, schemas, vault-path resolution, and
which nine functions get a tool at all.

**A note on process**: this design was written, and the corresponding
specs approved, before the MCP Python SDK was actually installed and
inspected. Task 1.5 of tasks.md exists specifically to confirm SDK
specifics against the real package rather than a guess — and doing so
surfaced a genuine fork (Decision 7, below), not just an API-naming
detail: the installed `mcp` package (`2.0.0`, the official
`modelcontextprotocol/python-sdk`) speaks a protocol revision
(`2026-07-28`, SEP-2577) that deprecates the roots capability this
design originally built vault-path resolution around. That
reconciliation is recorded in Decision 7 rather than silently
reflected only in code, per this codebase's own convention (stage 6's
proposal.md did the same for a plan/reality gap in `_search`/`_eval`;
stage 7's design.md Decision 1 did it for the documents-directory
layout).

## Goals / Non-Goals

**Goals:**
- Every tool is a thin `async def` wrapper: parse arguments (already
  JSON-Schema-validated by the SDK before the handler runs), call
  exactly one `core.py` function with the current vault path, serialize
  the result. No tool contains an `if`, a sort key, a path join, or a
  format string beyond serialization.
- The vault path is resolved once, deterministically, from the same
  two mechanisms every other `core.py` caller already supports
  (`--vault`, `VAULT_PATH`) — no new resolution rule, no dependency on
  a deprecated protocol capability (Decision 7).
- Every enum-typed schema field is generated from the same
  `models.py`/`index.search` enums `core.py` already validates against
  — `Status`, `DocumentKind`, `SearchMode` — so the schema cannot drift
  from what a call would actually accept.
- Tool descriptions are written and reviewed as carefully as the
  schemas: they are the only lever this change has over which mode a
  model reaches for by default, and the stage 5 measurement (linear-
  combination fusion, vector_weight 0.5, beating RRF and tying keyword/
  hybrid on most categories, but keyword still ahead specifically on
  exact-name queries) only pays off if `search`'s description states
  that explicitly.
- `read_document`, `set_status`, and `add_document` inherit `core.py`'s
  existing safety properties (containment check, derived filenames, no
  overwrite) unmodified — this change adds no new safety logic, it
  relies on stage 7's.

**Non-Goals:**
- Any new business logic. If a tool needs behavior `core.py` doesn't
  provide, that's a `core.py` change proposed separately (constraints,
  proposal.md).
- `reindex`, `create_vacancy`, or any stage 9 import/migration path as
  tools — see Decision 1.
- A generic query/eval/exec tool, or any tool taking a caller-supplied
  filesystem path for writing — explicitly excluded by the stage plan's
  constraints, not an oversight.
- Multi-vault serving, or switching the active vault at runtime, in one
  process — the vault path is fixed for the life of the process
  (Decision 7).
- Building on the MCP roots capability at all. It is deprecated as of
  the protocol revision the installed SDK speaks by default; this
  change does not use it, tested or otherwise (Decision 7).

## Decisions

### 1. `reindex` and `create_vacancy` are not exposed; the general rule is that bulk/structural operations stay where a human reviews the outcome

Every other write in stage 7 changes one bounded thing a caller named
explicitly: one note, one status transition, one document under one
already-existing vacancy. `create_vacancy` and `reindex` are different
in kind, not degree. `create_vacancy` can silently mint a new company
directory and `_company.md` as a side effect of a single call with no
natural dedupe key (stage 7's design.md Decision 8 calls this out: a
second call with the same inputs mints a *second* vacancy, not a no-
op) — an LLM given this tool free rein to "track a new opportunity" is
one misfire away from duplicate companies with slightly different
display names, silently fragmenting `resolve`'s fuzzy-match tier for
everyone after it. `reindex` is a full-vault operation whose only
purpose is to fix the index in bulk; every stage-7 write already calls
it (`vault=vault_root`, `force=False`) as its own last step, so a
model calling it directly would only ever be working around a bug this
change doesn't otherwise have — there is no legitimate task-shaped
reason for a client-connected LLM to trigger a full reindex, and giving
it the tool anyway would turn "the index looked stale" into a tool the
model reaches for speculatively.

The general rule this change follows: an operation belongs at the CLI,
not behind a tool, exactly when a misclassification of its outcome
would be hard to notice from inside a single tool-call/tool-result
turn and easy to notice looking at a terminal or `git diff` — i.e.
when a human is already in the loop reviewing what happened. Every
tool this change *does* expose fails that test the other way: a wrong
`set_status` call is one obviously-wrong status string, a wrong
`add_document` call is one extra file with a self-describing name, both
visible and undoable by inspection (nothing here deletes). `create_
vacancy` and `reindex` fail it because their blast radius (a new
directory tree; a full re-embed) isn't legible from the tool result
alone. The stage 9 import/migration path is excluded by the same rule,
one degree further: it's explicitly bulk and explicitly structural.

### 2. Delegation is enforced by one shared wrapper per tool category, not by convention alone

Every read tool's body is exactly: unpack the SDK-parsed arguments into
`core.py`'s own keyword names (never renamed — the "argument names
match core parameter names" requirement is what makes this
mechanically checkable), call the matching `core.py` function with
`vault=current_vault_path()`, and pass the return value to one shared
serializer that walks a `pydantic.BaseModel`/`dataclasses.dataclass`
result into a JSON-safe dict (`model_dump(mode="json")` for the
`BaseModel` results `core.py` already returns; `dataclasses.asdict`
plus the same date-handling `cli.py`'s `_json_default` already uses for
the few `dataclass` results like `Resolution`/`StatusChange`/
`SearchResults`). No tool writes its own field mapping. This is what
the stage 5 eval's promise depends on: a tool that reshapes `core.
search`'s hits before returning them would mean the model is no longer
exercising the exact ranked order and snippets the eval measured.

Tests enforce this directly (tasks.md): with `core.<function>` mocked,
each tool is called once and asserted to have called that mock exactly
once, with the given arguments passed through unmodified, and the
mock's return value present in the tool result unmodified apart from
serialization. A tool module containing a sort key, an `if company ==
...`, or a manual path join is a test failure, not a style nit.

### 3. Enum schemas are generated from `models.py`/`index.search`, never hand-typed

`status: Status`, `kind: DocumentKind`, and `mode: SearchMode`
parameters get their JSON Schema `enum` array from
`[s.value for s in Status]` / `[k.value for k in DocumentKind]` /
`[m.value for m in SearchMode]` at server-definition time, not a
literal list written into `mcp_server.py`. This is the same
"don't restate a rule the code already encodes" instinct stage 7's
design.md applied to `STATUS_TRANSITIONS` (Decision 5 there: data in
`models.py`, looked up, never re-branched). Adding a `Status` member or
a `SearchMode` value later changes every tool's schema for free; a
hand-typed enum list would silently drift the first time someone
forgets to update it in two places.

### 4. `search`'s tool description states the keyword-vs-hybrid guidance explicitly, citing the measured numbers

Per `config.py`'s own `SearchConfig` docstring, hybrid (linear-
combination fusion, vector_weight 0.5) is the *overall* winner
(recall@5 0.794 vs. keyword's 0.761), but keyword search "held on the
`exact_name` category specifically." A model with no guidance defaults
to whatever the tool description implies is the safe general choice —
hybrid — for every query including ones that are exact-name lookups,
which is precisely the case the eval found keyword still ahead on.
`search`'s tool description states this directly: prefer `mode=
"keyword"` for an exact company name, job title, or other proper-noun
lookup; leave `mode` unset (hybrid, the configured default) for
conceptual or paraphrased queries. This is a docstring decision, but
the stage plan calls it out as load-bearing enough to review like a
schema, and it's documented here so the exact numbers backing it (see
`config.py`'s `SearchConfig` docstring and this repo's README
evaluation table) don't drift out of sync with the description that
cites them.

### 5. `search` and `read_document` are a deliberate pair: search returns snippets and paths, never bodies

`core.search`'s hits are already bounded (`SearchHit.snippet`, not the
full document text — stage 4's `index.snippet.extract_snippet`), and
`get_company`/`get_vacancy` already return `VacancySummary`/
`DocumentSummary` rows with counts and paths, never document bodies
(stage 6's design.md, restated in each model's own docstring: "never
document bodies"). This change adds nothing new here — it just relies
on that shape being what a tool call returns. The reason this matters
specifically at stage 8: a `search` tool that returned five full
document bodies to satisfy one query would spend a meaningful fraction
of a model's context window on four documents it never asked to read,
on every single search call. Keeping `search`'s tool result to
snippets-and-paths, with `read_document` as the explicit, separate tool
a model calls when it actually wants a body, means the model spends
context proportional to what it actually reads, not what a query
happened to match against.

### 6. Filenames stay derived; this change trusts stage 7's containment/derivation, and restates why

Restated because this is the property that makes `add_document`/
`append_note` safe to expose as tools at all, not something this
change re-derives: `title` and `content` arriving through
`add_document`'s tool are, in the motivating case, text out of a
recruiter's email that a model is relaying, not authoring — the same
attacker-controlled-content framing stage 7's design.md used to justify
deriving the filename from `date`/`kind`/`slugify(title)` rather than
accepting one. This change adds no `path`-shaped parameter to any tool
(a hard constraint from the stage plan, checked directly in
tasks.md's schema tests) and no tool that writes to a caller-chosen
location. `read_document`'s `path` parameter is the one path-shaped
tool argument this change has at all, and it's read-only, already
containment-checked by `core.read_document` (`vault.paths.is_within`,
raising `PathOutsideVaultError` for anything outside the vault) before
this change existed.

### 7. Vault-path resolution reuses `config.resolve_vault_path` unchanged; MCP roots are not used

**This reverses the stage plan's roots-based precedence**, decided
during implementation (task 1.5) once the installed SDK was actually
inspected, not guessed at proposal time — recorded here rather than
silently built to a different shape than proposal.md/specs describe.

The reason: the installed MCP Python SDK (`mcp==2.0.0`, the official
`modelcontextprotocol/python-sdk`) speaks protocol revision
`2026-07-28` (SEP-2577) by default, which deprecates the entire roots
capability. Concretely, in the installed package:
- `ServerSession.list_roots()` (the call that would issue a `roots/
  list` request) is decorated `@deprecated(...)`, emitting
  `MCPDeprecationWarning` on every call.
- `MCPServer` — the high-level, decorator-based server class this
  change is otherwise built on (`.tool()`, `.resource()`, `.prompt()`,
  `.run(transport="stdio")`) — exposes **no public hook** for
  `notifications/roots/list_changed` at all. Only the low-level
  `mcp.server.lowlevel.Server`'s constructor accepts an
  `on_roots_list_changed` callback, and passing one now itself emits
  the same deprecation warning; `MCPServer` doesn't forward it, so
  using it from `MCPServer` means reaching into its private
  `_lowlevel_server` attribute.

Building the roots-based four-tier precedence this design originally
specified would mean either depending on a capability the protocol
itself now deprecates (and that current, non-legacy clients may stop
sending), or reaching into a private SDK attribute to work around
`MCPServer` not supporting it — both worse than the alternative: reuse
`config.resolve_vault_path` exactly as `core.py`'s own module docstring
already promised this stage would ("the seam a future MCP-roots-based
caller (stage 8) will use... without this function's signature
changing" — the promise was the seam, not specifically roots).

Resolution is now two-tier, decided once, at server startup, before
any tool is registered:
1. an explicit `--vault` CLI argument to `vacancy-radar-mcp`
2. the `VAULT_PATH` environment variable
3. neither present → `resolve_vault_path` itself raises
   `VaultNotConfiguredError`, whose existing message already names both
   mechanisms ("pass an explicit path or set the VAULT_PATH environment
   variable") — `mcp_server.py` adds no new error type or message here,
   it lets `config.py`'s own typed error surface as the startup
   failure.

No new precedence-resolution function or error type exists in
`mcp_server.py`: startup is `vault_path = config.resolve_vault_path
(args.vault)`, called once, exactly as any other `core.py` caller
already resolves its vault. `main` does add one line to stderr on a
`VaultNotConfiguredError` — `config.py`'s own message already names
`VAULT_PATH` but has no concept of a CLI flag to name, so `mcp_server.
py` appends "pass --vault or set VAULT_PATH" itself, the same kind of
boundary-specific framing `cli.py`'s own `_fail` already adds around a
`core.py`/`config.py` message, never a duplicated validation rule. If a
later stage needs to switch vaults at runtime (e.g. a transport where
that's meaningful again), that's a new design question for that stage,
not something this change works around now.

### 8. The resolved vault path is a plain value, passed to every tool call — no mutable session state

Since nothing in this change changes the active vault after startup
(Decision 7), `mcp_server.py` needs no mutable container for it: the
`Path` `resolve_vault_path` returns at startup is captured once (a
closure over the tool-registration functions, or an equivalent
constant) and passed as `vault=` to every tool's one `core.py` call.

This still matters for the reason `index.store`'s own module docstring
warns about ("Never a module-level singleton... a handle bound at
import time would silently keep querying/writing the first vault's
table"), even without runtime switching in scope: what must never
happen is `mcp_server.py` itself resolving an `IndexHandle` once (e.g.
`get_index_handle(vault_path)` called at server-startup time and
cached in a module global) and handing tools that cached handle
instead of the path. Every tool passes the plain vault `Path` into its
`core.py` call, and `core.search` resolves its own `IndexHandle` via
`get_index_handle(vault_root)` fresh, per call, exactly as it already
does for the CLI — `mcp_server.py` adds no handle-caching of its own,
so there is nothing here that could go stale even if a later change
does add runtime vault switching.

### 9. Tool errors return structured tool-result error content, not JSON-RPC protocol errors

Every `core.py`/`config.py`/`index.search` typed error (the same
`CoreError`/`VaultNotConfiguredError`/`VaultNotFoundError`/
`SearchError` family `cli.py`'s `_CORE_ERRORS` tuple already catches
uniformly) is caught at the tool boundary and returned as a tool
result with `isError=true` and a structured JSON payload — error type
name, message, and any fields the exception itself carries (e.g.
`AmbiguousEntityError`'s candidates) — never allowed to propagate into
a raised exception that becomes a JSON-RPC-level error response.

This is a deliberate choice between two things the MCP spec allows,
and clients render them differently: a protocol-level error (a
JSON-RPC `error` object) is a transport-level failure the client's own
UI typically surfaces as "the tool call failed," often without handing
the message back to the model as something it can act on in the same
turn — appropriate for a malformed request the schema itself should
have rejected, or an actual server malfunction. A tool result with
`isError=true` and text content is handed back to the model as part of
the conversation, the same as a successful result, which is what lets
an ambiguous `resolve` (candidates listed) or an invalid status
transition (both statuses named) become something the model reads and
corrects on its next turn — exactly the self-correcting behavior
`cli.py`'s own error rendering gives a human at a terminal. Every typed
error this change's tools can raise is one a caller (human or model)
can act on given the message; none of them are transport malfunctions.
An out-of-range enum argument is the one case the SDK's own schema
validation catches before a tool handler runs at all, which the MCP
spec surfaces as a protocol-level invalid-params error — that path is
inherent to using JSON Schema for the tool's input, not a choice this
design makes.

### 10. Resources are read fresh per request, scoped to the active vault path

`vacancy-radar://companies` and `vacancy-radar://statuses` are not
pre-computed once at startup and cached: `companies` is built from a
minimal read straight off `vault.reader.read_vault(vault_path)`'s
`.companies`/`.vacancies` on every resource read — decided during
implementation without adding new logic to `core.py`, since the shape
needed (slug, display name, vacancy count) is exactly what
`read_vault`'s existing snapshot already carries. Reading fresh rather
than caching at startup matters even with the vault path fixed
(Decision 7): the vault is a hand-edited, git-tracked directory a human
can change between requests, and a resource that cached its first read
would silently drift from what's actually on disk. `statuses` is
`Status`'s members paired with `STATUS_TRANSITIONS[status]`, read from
`models.py` directly — no vault access at all, so it can never drift
from `models.py` because nothing in this change re-encodes the graph.

### 11. Prompts compose existing `core.py` reads; an unresolved company is a resolution failure, not a fabrication

`prep_interview(company)` calls `core.resolve` first: on no match or an
ambiguous match, the prompt returns a message describing the
resolution failure (or, for the ambiguous case, the candidates) instead
of a "dossier" — this is the same `resolve`-never-guesses contract
`cli.py` already depends on (stage 6 design.md, Decision 3), reused
here rather than re-implemented. On a resolved company, the prompt
composes `core.get_company`, and for each vacancy, `core.get_vacancy`
for its posting/notes/take-home documents — never inventing a company,
a vacancy, or a document that isn't in the vault. `draft_reply
(vacancy_id)` composes `core.get_vacancy` (for `stage_note`, prior
notes) plus the vacancy's document list to reconstruct prior tone from
real filed content, resolving `vacancy_id` via `core.resolve` the same
way. `weekly_review()` composes three `core.list_vacancies` calls
(`stale_days=`, a take-home filter over `status=[Status.TAKE_HOME]`,
`needs_review=True`) — no new query shape, three calls to the one
function that already supports each filter.

## Risks / Trade-offs

- [Dropping roots support (Decision 7) means a client that *does*
  support MCP roots and expects a server to follow its workspace
  folder gets no such behavior from this server] → accepted: the
  capability is deprecated in the protocol revision this SDK speaks by
  default, so building against it now would mean shipping against a
  capability with a shrinking client base and no supported hook in the
  server class this change is built on. `--vault`/`VAULT_PATH` cover
  every case a human operator configuring an MCP client already
  handles for every other stdio MCP server. Revisit if a later protocol
  revision reinstates an equivalent capability with first-class SDK
  support.
- [Resources re-read the vault on every request rather than caching]
  → the same trade-off `core.search`/`core.doctor` already accept on
  every call (stage 6 design.md); the fixture-vault sizes this project
  targets make a fresh read cheap enough that avoiding a stale-cache
  class of bug is worth more than the saved I/O. Revisit only if a real
  vault's size makes per-request reads measurably slow.
- [`isError=true` tool results (Decision 9) put the burden of noticing
  a failure on the model reading the conversation, rather than a
  transport-level failure a client might surface more insistently] →
  accepted: every error this change can raise is one where recovery
  requires reading the message anyway (which status values are valid,
  which candidates matched) — a model that ignores an isError result
  the same way it might ignore any other tool result is a model
  behavior problem, not something a protocol-level error would fix.

## Migration Plan

Purely additive: a new module, a new optional dependency, a new entry
point. No existing file's behavior changes — `core.py`, `cli.py`,
`models.py`, `config.py`, and every `index/`/`vault/` module are used
exactly as stage 7 left them. Rollback is removing the module and the
dependency; no later stage's design depends on anything this change
adds beyond stage 9 (xlsx migration) explicitly *not* consuming it (per
proposal.md's Impact section).

## Open Questions

- None blocking. The two questions this section originally carried are
  both resolved:
  - The `mcp` SDK surface for per-tool annotations is
    `MCPServer.tool(..., annotations=ToolAnnotations(read_only_hint=,
    destructive_hint=, open_world_hint=))` — confirmed against the
    installed `mcp==2.0.0` package (task 1.5); `ToolAnnotations`'
    Python-side fields are snake_case, serialized to the wire's
    camelCase (`readOnlyHint`, etc.) by the SDK itself.
  - Whether the server builds on the roots capability at all is
    resolved by Decision 7: it does not.
- Whether `vacancy-radar://companies` is served from a `core.py` call
  or a direct `read_vault` read (Decision 10) is a small implementation
  choice, not a design fork — either satisfies "no domain logic in
  `mcp_server.py`" as long as no filtering/sorting/grouping logic that
  doesn't already exist in `core.py`/`vault.reader` is written to
  produce it; resolved during implementation, not blocking.
