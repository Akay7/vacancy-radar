## Context

Stages 1-5 left three independent read paths: `vault.reader.read_vault`
(a full in-memory snapshot), `index.search.search` (LanceDB queries
over the disposable index), and nothing at all for "give me one
vacancy" or "give me one company" — those questions currently require
filtering a `VaultSnapshot` by hand. Stage 6 is the first place that
composes these into the shapes an actual caller wants, and the first
place with two callers in view at once: the CLI now, the MCP server at
stage 8. `core.py` is new territory — every prior module was one
mechanism (parsing, hashing, embedding, searching); this one is
business logic that calls several of them.

The stage plan's requirement text asks to "remove the private
`_search` entry point from stage 4." Checked against `cli.py`
directly: no such command exists. The retrieval change (stage 4)
never added a hidden CLI command — it shipped `index.search.search` as
a library function only. The eval-harness change (stage 5) is what
added a hidden command, `_eval`. This design proceeds on the
assumption that the plan meant `_eval` (the only hidden command that
exists) and that reference to "stage 4" was a mismatch between the
plan's numbering and the actual archived changes; see proposal.md's
note. If a private `_search` command turns up during implementation
that this survey missed, remove it the same way as `_eval` and update
tasks.md accordingly — but `git grep '"_search"' src/` finds nothing
today.

## Goals / Non-Goals

**Goals:**
- One function per read operation in `core.py`, callable identically
  by a CLI command now and an MCP tool later (invariant 4).
- Every dossier-shaped return (`get_company`, `get_vacancy`) is bounded
  by construction: paths, titles, and counts, never document bodies.
- `resolve` never guesses: ambiguous input returns candidates, not a
  pick.
- A stale index degrades search and `doctor` output with a warning; it
  never raises and never blocks either command.
- `cli.py` commands are argument-parsing and Rich-rendering shells
  around `core.py` calls — no filtering, sorting, path-safety, or
  resolution logic lives in `cli.py`.
- `--json` output is a stable, documented shape suitable for piping.

**Non-Goals:**
- Any write path (`append_note`, `set_status`, `add_document`) —
  stage 7.
- MCP tools, schemas, or transport — stage 8.
- Changing `index.search.search`'s ranking, fusion, or predicate
  behavior — this change wraps it, never edits it.
- A general-purpose fuzzy-matching library — `resolve`'s fuzzy tier
  uses `difflib` from the standard library, honoring "no new runtime
  dependencies."

## Decisions

### 1. `core.py` holds every function; `cli.py` holds none

Restating invariant 4 for whoever implements this: `cli.py` commands
must be parse-call-render, full stop. The test for whether a piece of
logic belongs in `core.py` is not "does it currently have only one
caller" — it's "would stage 8's MCP server need this exact behavior."
Every one of `list_vacancies`, `get_company`, `get_vacancy`,
`read_document`, `resolve`, and `search` answers yes: an MCP tool for
"show me Acme's history" needs precisely the same bounded dossier a
`vacancy-radar show acme` call renders, computed the same way,
raising the same typed errors. If `get_company`'s filtering or
`resolve`'s candidate-ranking were written inside a `@app.command`
function, stage 8 would face a choice between duplicating that logic
(drift risk: the CLI and the MCP server silently start answering
"have I dealt with this company before" differently) or awkwardly
importing a function that closes over a Typer `Context`. Neither is
acceptable, so it doesn't happen: `cli.py` functions receive
already-typed arguments from Typer, call exactly one `core.py`
function, and pass the result to a renderer. A command body containing
an `if`/`for` that inspects vacancy fields, sorts a list, or joins a
path is a defect against this rule, not a style nit — flag it in
review the same way a `print()` call gets flagged by T20.

### 2. Bounded output for `get_company` and `get_vacancy`

Both dossiers return document metadata (id, title, kind, date, path)
and counts, never a document's text. The rule is the same for both
because they answer the same *kind* of question — "here is
everything this vacancy/company touches" — and the failure mode is
the same for both: a company with fifteen vacancies each with five
documents is seventy-five document bodies, most of which are
irrelevant to whatever the caller actually asked. At the CLI, an
unbounded dossier is merely a very long terminal scroll a human
skims past. At stage 8, the same unbounded dossier is context an LLM
must read, token by token, before it can answer anything — and every
token spent on a stage-note from 2023 is a token not available for
the document that actually matters. Bounding the *shape* now (paths
and counts only, `read_document` as the explicit, deliberate follow-up
call for a body) means stage 8 doesn't need a second, MCP-specific
truncation layer bolted on later; it inherits the bound for free by
calling the same function.

### 3. `resolve` returns candidates, never picks

`resolve`'s ordered strategy (exact id, exact `company_slug`, unique
case-insensitive company match, then fuzzy) stops as soon as one tier
produces exactly one match. If a tier produces more than one, or the
fuzzy tier's best matches are close enough to be ambiguous, `resolve`
returns them all as a `Resolution.candidates` list and resolves to
nothing — it does not fall through to "pick the first" or "pick the
highest-scoring." The cost of guessing wrong is asymmetric with the
cost of asking again: at the CLI, a human sees "which one?" and
retypes a more specific query. At stage 8, there is no human in the
loop by default — an MCP tool that silently resolves "Acme" to the
wrong `acme-corp-2` and returns its dossier produces an LLM that reads
someone else's rejection history and answers a question about it with
complete, unwarranted confidence. A `Resolution` with candidates is a
correct, useful answer; a wrong single guess is a plausible-looking
wrong answer, which is worse than an explicit failure. `resolve`
structurally cannot produce the second kind.

Fuzzy matching (the last tier, reached only when no id/slug/exact-name
tier matched) uses `difflib.get_close_matches` against the set of
company display names — no new dependency, and adequate for
typo-tolerance over a vault-sized company list (see Risks for where
this is expected to reach its limits).

### 4. Index staleness is a warning, computed in `index-freshness`

`build_index` already tracks `content_hash` per row (`index/build.py`)
and `read_vault` already hashes every file
(`vault/reader.py`). Freshness is: does the vault's current
`{path: content_hash}` set (from a fresh `read_vault` call) match what
the index's table actually has? The check lives in one function,
called from both `core.search` (attaches the warning to
`SearchResults`) and `core.py`'s `doctor`-supporting function (reports
it alongside the fix command, `vacancy-radar build-index` from an
earlier stage). Neither caller raises on a stale index — staleness
degrades (search still returns whatever the index has; `doctor` still
exits 0 unless something else is actually broken) rather than
blocking, mirroring `vault.reader`'s file-level resilience contract
(one bad file becomes a `VaultWarning`, never an aborted read). Putting
the check in one place, rather than inlining a hash comparison in both
`core.search` and the doctor path, is what lets stage 8's MCP server
inherit it automatically — it calls `core.search`, and gets the
warning for free.

### 5. The `--json` contract

Every `--json` command emits one JSON document to stdout and nothing
else — no Rich formatting, no ANSI codes, no interleaved warnings on
stdout (warnings go to stderr or into the JSON's own `warnings` field,
never mixed into stdout's structure). The shape mirrors each
`core.py` return type field-for-field: `list --json` is an array of
`VacancySummary`-shaped objects; `show --json` is a `VacancyDetail` or
`CompanyDossier` object tagged with which one it is; `search --json`
includes `hits`, `mode`, and (with `--scores`) each hit's
`keyword_rank`/`semantic_rank`/`score`; `doctor --json` is a
`{checks: [...], warnings: [...]}` object. These field names and
nesting are the stable contract — this is deliberate, since `--json`
is what gets piped during the eventual migration away from ad hoc
vault edits, and a shape that reshuffles between this change and the
next would break that pipe silently. Additive fields (a new key
appearing later) are fine; renaming or removing a field a prior stage
shipped is a breaking change to be called out the way this proposal
calls out `_eval`'s removal.

### 6. `search`'s vault resolution seam

`core.search` accepts the same vault-path precedence as
`resolve_vault_path` (explicit argument, then `VAULT_PATH`) and
resolves the vault and index handle itself before delegating to
`index.search.search`, rather than requiring the CLI to resolve a
vault and pass an `IndexHandle` in. This keeps `cli.py`'s `search`
command to argument-parsing and rendering (decision 1) and gives
stage 8 the same one-call surface an MCP tool needs — a client-
supplied root, once resolved, is just `core.search`'s existing
`vault` argument.

## Risks / Trade-offs

- [`difflib`'s fuzzy tier is weaker than a real string-distance
  library] → acceptable for this vault's scale (tens to low hundreds
  of companies); `resolve`'s design explicitly favors returning
  ambiguous candidates over a confident wrong match, so a weak fuzzy
  tier fails toward "no match" or "too many candidates," not toward a
  wrong single answer. Revisit only if a later stage's real usage
  shows the fuzzy tier missing matches a human finds obvious.
- [Index staleness is computed by hashing the whole vault again on
  every `search`/`doctor` call] → the same `read_vault` cost `list`
  and `show` already pay; no new I/O pattern, and vault sizes here are
  small enough that this hasn't needed caching through stage 5.
  Revisit if `doctor`/`search` latency becomes visible at real vault
  scale.
- [The stage plan's "remove the private `_search` entry point" doesn't
  match anything in the codebase] → addressed by proceeding as if it
  meant `_eval` (Context, above); flagged explicitly in proposal.md so
  it isn't silently reinterpreted without a trace.
- [`get_company`/`get_vacancy`'s bounded-output rule means a caller
  who actually wants "everything" must issue N `read_document` calls]
  → intentional (Decision 2); N is bounded by the dossier's own
  document count, which the caller already has before deciding to
  fetch bodies.

## Migration Plan

Purely additive at the module level (`core.py` is new) plus one
removal (`_eval` → `eval`). No data migration: nothing here writes to
the vault or index format. Rollback is a plain revert — no prior
stage depended on `core.py` existing.

## Open Questions

- None blocking. `resolve`'s exact fuzzy-match threshold
  (`difflib.get_close_matches`'s `cutoff`) is an implementation
  parameter, not a design fork — tune it during tasks.md's fuzzy-tier
  tests against the fixture vault's company names.
