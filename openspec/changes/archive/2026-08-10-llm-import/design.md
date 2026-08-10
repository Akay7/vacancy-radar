## Context

Stage 8 (`openspec/changes/mcp-server/`) built the MCP server and is
fully implemented — `src/vacancy_radar/mcp_server.py`,
`tests/test_mcp_server.py`, nine tools, two resources, three prompts —
but its change directory hasn't been archived into `openspec/specs/`
yet, so `mcp-write-tools`, `mcp-read-tools`, and `mcp-transport` don't
exist under `openspec/specs/` for this change's delta specs to modify
in the usual way. This change's delta specs for those three
capabilities are therefore written against stage 8's own (unarchived)
`ADDED Requirements` text as the current baseline — the same
requirements the shipped code already satisfies — not against a
missing `openspec/specs/` file. **Recommendation, not a blocker**:
archive `mcp-server` before or alongside applying this change, so the
sync step folds stage 8's originals and this change's deltas into
`openspec/specs/` in the normal order rather than skipping straight
from "never archived" to "modified twice."

`core.create_vacancy` (stage 7) and the MCP server's write-tool
registration (stage 8) are both small, stable, and already tested;
this change's core.py surface area is one signature extension and one
new function, not a rewrite.

## Goals / Non-Goals

**Goals:**
- `create_vacancy` and `find_existing` are exposed exactly like every
  other MCP tool in this codebase: a thin `async def` wrapper,
  `@server.tool(annotations=...)`, `@_delegate`, one `core.py` call,
  nothing else in the handler body (invariant 4, unchanged from stage
  8).
- `core.create_vacancy`'s new parameters are additive and optional —
  every existing caller (`cli.py`'s `new` command, stage 7/8's own
  tests) keeps working unmodified.
- `find_existing` is itself a `core.py` function, not server-side
  composition, so it satisfies the same "delegates to exactly one
  `core.py` function" rule stage 8 already enforces test-by-test —
  see Decision 2.
- Every import convention this change relies on (the `unknown`/
  `needs_review` pairing, the synthesized-`found_date`/`migrated`
  pairing) is stated in `create_vacancy`'s tool description and
  nowhere else in code — there is no importer module to put it in
  instead (see Decision 6).

**Non-Goals:**
- No importer module, interchange format, CSV/xlsx/JSONL parser, or
  batch-execution tool. The conversation *is* the importer; mapping a
  tracker's columns onto this vault's vocabulary is a per-vault,
  per-language judgment call `docs/import-guide.md` teaches a human
  (via Claude) to make, not something a schema could encode once for
  every tracker (Decision 8).
- No CLI exposure of the four new `create_vacancy` parameters
  (`stage_note`, `salary_note`, `recruiter`, `tags`). `vacancy-radar
  new` keeps its existing four options; a human at a terminal creating
  one vacancy at a time hasn't asked for this, and adding four more
  CLI flags for a capability only the conversational path currently
  uses would be speculative. Revisit if a real workflow wants it.
- No change to `reindex`'s exposure. The reversal (Decision 1) is
  scoped to `create_vacancy` only — `reindex`'s exclusion rested on "no
  legitimate task-shaped reason for a model to trigger one," a claim
  about the operation itself, not about batch-script invisibility, so
  nothing about conversational import changes it.
- No transactionality, rollback, or dry-run mode for a sequence of
  `create_vacancy` calls. Accepted as a limitation (Decision 9); batch
  size and per-batch verification are the mitigation, not a new
  mechanism.

## Decisions

### 1. The reversal: what changed about the risk model, and what didn't

Stage 8's design.md (Decision 1) excluded `create_vacancy` for a
specific reason: "an operation belongs at the CLI, not behind a tool,
exactly when a misclassification of its outcome would be hard to
notice from inside a single tool-call/tool-result turn and easy to
notice looking at a terminal or `git diff`." That test was written
against the only import shape the stage plan had in view at the time —
a batch script running unattended, where a bad row is invisible until
someone goes looking. Stage 9 doesn't build that script. Every
`create_vacancy` call this change enables happens inside a
conversation the user is actively reading: Claude proposes a batch,
the user sees each row's mapped fields before confirming, and
`docs/import-guide.md`'s batch-of-ten-to-twenty convention keeps any
one turn's blast radius small enough to actually read. The
misclassification-is-invisible premise stage 8 relied on doesn't hold
here — so the same test that excluded `create_vacancy` at stage 8
now argues for exposing it.

`reindex` is unaffected by this because its exclusion never rested on
that premise: stage 8's design.md gave it a separate reason ("every
stage-7 write already calls it as its own last step... there is no
legitimate task-shaped reason for a client-connected LLM to trigger a
full reindex"). Conversational import doesn't change what `reindex`
is for — every `create_vacancy` call still reindexes itself, per
Requirement "a created vacancy is immediately retrievable" — so there
is still no call site where a model reaching for `reindex` would be
doing anything other than working around a bug this change doesn't
otherwise have.

### 2. `find_existing` is a `core.py` function, not server-side composition

The proposal describes `find_existing` as "a thin wrapper over stage 6
`resolve` and `list_vacancies`" — true of its *purpose*, but stage 8's
own invariant 4 ("every tool is a thin `async def` wrapper... call
exactly one `core.py` function") is enforced test-by-test
(`mcp-read-tools`'s "each read tool delegates to exactly one core.py
function" requirement, checked by mocking `core.<function>` and
asserting it's called once). Composing `resolve` and `list_vacancies`
*inside the tool handler* would mean `find_existing` is the one read
tool in the server that calls two `core.py` functions, breaking that
test's pattern for no good reason. So `core.find_existing(company,
source_url, vault=None) -> list[VacancySummary]` is a new `core.py`
function, and the MCP tool delegates to it exactly like every other
tool.

Inside `core.py`, `find_existing` reads the vault snapshot once and
reuses the existing private helpers `_resolve` (company-tier matching,
already non-raising) and `_vacancy_summary` (the same row-shaping
`list_vacancies`/`get_company` already use) rather than calling the
*public* `resolve()` and `list_vacancies()` — which would each call
`read_vault` again, for a total of three reads of the same vault state
inside one function. `resolve()`/`list_vacancies()` re-read fresh on
every call because each is independently invoked at unpredictable
times by unrelated callers (stage 8's design.md Decision 10 accepts
this cost for resources for the same reason); `find_existing` doesn't
have that problem — it's one function, one snapshot, one moment in
time — so reusing the private helpers avoids the redundant reads
without duplicating either helper's matching rule.

### 3. `find_existing` never raises — an ambiguous or unresolved company is just "no company-tier match"

`resolve()` already returns an unresolved/ambiguous result without
raising; the *raising* variants (`EntityNotFoundError`,
`AmbiguousEntityError`) live in `_resolve_company_slug`, used by
`list_vacancies(company=...)` and `get_company`. `find_existing` is a
best-effort pre-check, not a resolution primitive a caller depends on
picking exactly one entity — a model asking "does something like this
already exist" gets more value from "here's everything the source_url
matched, and nothing else" than from an error it has to catch and
retry around. So `find_existing` uses `_resolve` directly (the
non-raising form): a company argument that resolves ambiguously or not
at all simply contributes no rows from the company tier, and
`source_url` matching still runs independently. This is also why
`find_existing`'s only failure mode is "empty list" — never a typed
error — matching the "Returns empty for a company that does not
exist" requirement literally rather than requiring the caller to catch
`EntityNotFoundError` first.

### 4. Why `find_existing` is a separate tool rather than relying on the collision suffix

`create_vacancy` already can't collide destructively — `new_vacancy_id`
(stage 1) suffixes a colliding id rather than overwriting — so a model
could, in principle, "check for a duplicate" by calling `create_vacancy`
and inspecting whether the returned id carries a collision suffix. That
tells the model about the duplicate *after* it has already minted a
second vacancy directory for the same real-world posting — the
fragmentation stage 8's design.md Decision 1 specifically worried
about ("duplicate companies with slightly different display names,
silently fragmenting `resolve`'s fuzzy-match tier for everyone after
it") already happened by the time the suffix is visible. `find_existing`
moves that check before the write: the model calls it, reads back
zero, one, or several `VacancySummary` rows, and decides whether to
proceed with `create_vacancy` at all — the tool result is something to
act on, not evidence of a mistake already made.

### 5. `create_vacancy`'s signature extension is additive, mechanical, and unvalidated beyond what `Vacancy` already validates

`stage_note: str | None = None`, `salary_note: str | None = None`,
`recruiter: str | None = None`, and `tags: list[str] | None = None`
join `core.create_vacancy`'s signature after `applied_date`, forwarded
to the `Vacancy(...)` constructor exactly like `company`/`role`/
`source_url` already are — `tags=tags or []`, since `Vacancy.tags` is
`list[str]` (not `Optional`) with `default_factory=list`, everything
else passed through unchanged including `None`. No new validation is
added: `Vacancy`'s existing field/model validators (`vault-model`
spec, unchanged by this change) already accept or reject these fields
exactly as they do today for `set_status`/`add_document`'s equivalent
inputs. This is the same kind of extension stage 7's design.md would
recognize as "argument marshalling, not business logic" — the fields
already exist on the model; `create_vacancy` simply stops being the
one write path that can't set them.

### 6. Where import conventions live: tool descriptions, and the drift risk that comes with it

There is no importer module for a rule like "role defaults to
`unknown`, tag it `needs_review`" to live in — Decision in the
proposal's Non-Goals is explicit that this change ships no such
module. The only place left for that rule, and for "`found_date` may
be synthesized from `applied_date`, tag it `migrated`," is
`create_vacancy`'s own MCP tool description — the same choice stage
8's design.md made for `search`'s keyword-vs-hybrid guidance (Decision
4 there), and for the same reason: the tool description is the one
artifact a calling model actually reads before deciding how to call
the tool.

This carries a real drift risk stage 8 already named for `search`:
`docs/import-guide.md` restates both conventions in prose for the
human reader, and nothing mechanically keeps the tool description and
the doc in sync if one changes without the other. The mitigation is
the same one stage 8 used for `search`'s description
(`test_search_description_states_keyword_vs_hybrid_guidance`): this
change adds an equivalent test asserting `create_vacancy`'s tool
description contains the literal words `unknown`, `needs_review`,
`migrated`, and a check-before-create instruction — a description edit
that silently drops one of these conventions fails CI, even though
nothing enforces that `docs/import-guide.md`'s prose says the same
thing in the same words. Revisit only if this doc/description pair
actually drifts in practice; duplicating the convention a third time
(e.g., a shared constant string) would make the tool description read
like generated text instead of the reviewed prose stage 8 treated tool
descriptions as.

### 7. `create_vacancy`'s tool result reports the created path and the derived id

`core.create_vacancy` returns a `Path`; the proposal's signature is
`-> created path and id`. `cli.py`'s existing `new_command` already
derives `vacancy_id = path.parent.name` after the call and treats this
as "a structural fact, not business logic" (`vault/paths.py`'s own
directory-is-named-after-its-id convention, not something
`new_command` invents). The MCP tool does the same one-line derivation
after calling `core.create_vacancy`, for the same reason: it isn't
reshaping `core.py`'s return value, filtering it, or deciding anything
— it's reading a value already encoded in the path's structure, the
same fact `cli.py` has relied on since stage 7. `_delegate`'s test
convention ("the tool result contains the mocked return value,
unmodified apart from serialization") is honored by asserting the
mocked path passes through unmodified *and* that the reported id
equals that mock path's parent directory name — not by asserting the
tool computed nothing at all, which stage 8 never required of
`add_document`'s or `append_note`'s `Path`-returning tools either
(their results are already "a path," not "a path and something read
off it," only because no caller has needed the second part until now).

### 8. Why no interchange format ships

Every existing tracker a user might import has different columns, in a
different language, with different stage vocabulary, different date
formats, and different ideas about what counts as "found" versus
"applied." A schema-first importer would need to either enumerate
every tracker shape in advance (impossible) or expose a mapping
configuration flexible enough to describe arbitrary column semantics —
at which point the configuration *is* the hard part, and a human would
still have to write it once per tracker. A conversation does that
mapping for free: the model reads a batch of rows, proposes a mapping
per column against the vocabulary `docs/import-guide.md` names, and
the user confirms or corrects it in the same turn — the exact
per-tracker judgment call a static format can't make. This is also why
`create_vacancy`'s parameters are a flat, already-typed record
(`company`, `role`, `source_url`, ...) rather than anything
shaped like a row from an unknown source format: the shape a schema
would need to accommodate never appears in `core.py` at all, only in
the conversation that produces one `create_vacancy` call at a time.

### 9. Non-transactional import is accepted; batch size is the mitigation, not a fix

Each `create_vacancy` call is atomic on its own (validation happens
before either file is written, per `core.py`'s existing
`create_vacancy` body — a rejected record writes nothing). A *batch*
of them is not: ten sequential tool calls interrupted after the sixth
leaves six real vacancies on disk and four rows still unimported, with
no marker distinguishing "this batch is half-done" from "this batch is
finished." Building transactionality (a staging area, a commit/rollback
tool, a batch-id) is out of scope — it would be new business logic in
exactly the place `core.py`'s existing design keeps free of it, for a
failure mode `docs/import-guide.md`'s batch-of-ten-to-twenty convention
already keeps cheap to recover from by hand: `vacancy-radar list`
after each batch shows exactly what landed, and resuming a half-done
batch means re-running the remaining rows, not reconciling a
partially-committed transaction.

### 10. `mcp-transport`'s tool-count requirement updates; its `reindex` rationale doesn't

The single requirement enumerating "exactly the nine specified tools"
becomes "exactly the eleven specified tools" (`create_vacancy` and
`find_existing` added, `reindex` still absent). This is a mechanical
update to a requirement whose only content is a fixed set membership
test — Decision 1 above is where the actual rationale for what's in
that set lives; `mcp-transport`'s delta just states the new set.

## Risks / Trade-offs

- [`create_vacancy`'s tool description is the only place the
  `unknown`/`needs_review` and synthesized-`found_date`/`migrated`
  conventions are encoded, and nothing keeps `docs/import-guide.md`'s
  prose in sync with it] → accepted, mitigated by a description-text
  test (Decision 6); revisit only if drift is observed in practice.
- [A batch interrupted partway leaves some rows created and others
  not, with no in-vault marker of which batch they came from] →
  accepted (Decision 9); mitigated by small batch size and
  per-batch `vacancy-radar list` verification, not a new mechanism.
- [`find_existing`'s source_url match is exact-string, not normalized
  (trailing slash, query string, tracking parameters, http vs https)]
  → accepted: `Vacancy.source_url`'s own validator (`vault-model`
  spec) only requires an http/https scheme, not a canonical form, so
  two postings for the same job at differently-tracked URLs won't
  match here either. `find_existing` is a best-effort check, not a
  guarantee; `docs/import-guide.md` tells the user duplicates can
  still slip through and `vacancy-radar list` remains the way to catch
  one after the fact. Revisit if this proves to miss real duplicates
  often enough to matter.
- [Extending `core.create_vacancy`'s signature makes it a five-required
  -plus-five-optional-parameter function, `noqa: PLR0913`/`PLR0917`
  already applied per its own docstring's precedent] → accepted, same
  trade-off the function's existing `noqa` comment already documents
  ("the deliverable's public signature; each is meaningful").

## Migration Plan

Additive only. `core.create_vacancy`'s four new parameters default to
`None`/absent and change no existing caller's behavior;
`core.find_existing` is new. `mcp_server.py` gains two tool
registrations in `_register_write_tools`/`_register_read_tools` and one
updated docstring/instructions string on `MCPServer(...)` (the
"Bulk/structural operations... are intentionally not exposed here"
sentence in `build_server` needs to stop naming `create_vacancy`
alongside `reindex`, since only `reindex` is still true). `README.md`'s
tool table and tool count update to match. No file this change touches
is deleted; rollback is reverting the two new tool registrations, the
`core.py` signature/function, and the doc files.

## Open Questions

- Whether `find_existing`'s source_url matching should normalize
  trailing slashes or strip tracking query parameters before
  comparing — deferred (Risks/Trade-offs); revisit if real-vault usage
  shows it missing duplicates a human would catch by eye.
- Whether `vacancy-radar new` should eventually expose
  `stage_note`/`salary_note`/`recruiter`/`tags` too — deferred
  (Non-Goals); not blocking, since nothing about this change makes
  that harder to add later.
