## Context

`config.resolve_vault_path` (stage 2) is the one seam every later
stage's vault-path resolution goes through — `core.py`'s functions,
`cli.py`'s commands, and the MCP server's startup all call it, directly
or through `core.py`. Its contract (`vault-config` spec, unchanged by
this change) is deliberately strict: the target must already exist, be
a directory, and already carry a `.vacancy-radar/` marker, or it raises
`VaultNotFoundError`/`VaultNotConfiguredError`. That strictness is
correct for every *existing* caller — `list`, `search`, `new`, and so
on all operate on a vault that's supposed to already exist, and a
typed error is exactly the right response to "there's nothing here."

Nothing in this codebase can make that first marker exist. This change
adds exactly that, as a CLI command, following the same "core.py holds
the logic, cli.py renders it" split every prior stage already
established.

## Goals / Non-Goals

**Goals:**
- `vacancy-radar init` is the one command that makes
  `resolve_vault_path` start succeeding for a given path — everything
  downstream of it (every other command, the MCP server) is otherwise
  unaware this change exists.
- `resolve_vault_path`'s own behavior, signature, and error messages
  are byte-for-byte unchanged for every existing caller — `vault-config`
  spec's requirements are not touched by this change's delta.
- `init_vault` is idempotent and never destructive, matching every
  other write path in this codebase (`create_vacancy`'s never-
  overwrites stance, `add_document`'s dedupe-not-collide stance).

**Non-Goals:**
- No MCP tool. The MCP server resolves one fixed vault path once at
  startup (stage 8 design.md decisions 7-8) and serves it for the
  process's whole lifetime — there is no point in that lifecycle where
  creating a *different* vault at a caller-supplied path means
  anything, and the stage 8/9 constraint against any tool accepting a
  caller-supplied filesystem path for writing rules it out
  independently. `init` follows `reindex`'s existing shape exactly: a
  `core.py` function the CLI exposes and the MCP server deliberately
  does not.
- No vault scaffolding beyond the marker directory. No starter
  `_company.md`, no README dropped into the vault, no `.gitignore`, no
  `git init`. An initialized vault is exactly the empty-marker vault
  every test's own `_init_vault` helper already builds by hand — this
  change gives that helper's logic a real, user-facing home, not a
  richer starting point than it already represents.
- No multi-vault or vault-switching concept. `init` creates one vault
  at one path per call, same as every other command operates on one
  vault per process.

## Decisions

### 1. `init` is CLI-only; the MCP server never gets this tool

Two independent reasons, either sufficient alone:

- The MCP server's vault path is resolved once at startup and fixed
  for the process's lifetime (stage 8 design.md decision 8 — no
  mutable session state, no handle-caching, nothing that could point
  at a second vault mid-process). There is no tool call shape where
  "create a vault at some other path" fits a server that is, by
  design, already pointed at the one vault it will ever serve.
- The stage 8/9 constraint "do not add a tool that accepts a
  caller-supplied filesystem path for writing" applies directly:
  `init`'s one argument *is* a caller-supplied filesystem path, and
  its entire purpose is to write there.

This is not a new rule invented for this change — it's `reindex`'s own
exposure shape (a `core.py` function, CLI-exposed, deliberately absent
from every MCP tool list from stage 8 through llm-import) applied to a
second function for the same underlying reasons.

### 2. A new resolution helper in `config.py`, not a flag on `resolve_vault_path`

`init_vault` needs the same explicit-argument-then-`VAULT_PATH`
precedence `resolve_vault_path` already implements, but without the
marker-existence check — that check is exactly the invariant `init`
exists to *establish*, not assume.

Two ways to get there: add a `require_existing: bool = True` parameter
to `resolve_vault_path` itself, or extract the precedence-only step
into its own function and have `resolve_vault_path` call it. This
change takes the second path. A boolean parameter changes
`resolve_vault_path`'s signature for every existing caller (even at
its default value, it's a new parameter every call site and every
test's mock/monkeypatch surface has to be aware could exist), for a
behavior only one new caller needs; every other function in this
codebase that varies its own strictness does so by being a different
function (`resolve` vs. `_resolve_company_slug`'s raising counterpart
is the closest precedent), not a flag threaded through an existing,
already-widely-called one. The extraction also matches this codebase's
own stated discipline: `resolve_vault_path`'s module docstring already
frames it as "the seam" future callers reuse — reusing the
precedence half of that seam without reusing the validation half is a
narrower, not a different, seam.

Concretely: `config.py` gains a private `_resolve_candidate_path(explicit)
-> Path` (precedence + `.resolve()` to absolute, raising
`VaultNotConfiguredError` when neither is given — the one error
`init_vault` and `resolve_vault_path` both still need identically) and
a new public `config.resolve_target_path(explicit=None) -> Path`
(same precedence, no marker check, no existence check at all — the
path returned may not exist yet). `resolve_vault_path` becomes: call
`_resolve_candidate_path`, then run its own existence/directory/marker
checks on the result, unchanged in every observable way. `vault-config`
spec's existing requirements and scenarios continue to describe
`resolve_vault_path` exactly as before; this change's delta spec
covers only the new `resolve_target_path` function.

### 3. Idempotent no-op, not an error, on an already-initialized vault

`create_vacancy` never overwrites (a collision mints a suffixed id,
not an error); `add_document` treats a same-content re-file as a
dedupe, not a collision; `append_note` just gets a second file for a
second same-day note. Every write path in this codebase treats "you
asked for something that, in effect, already exists" as something to
report, not fail on. `init_vault` follows the same instinct: running
`vacancy-radar init` a second time against a path that's already a
valid vault reports `created=False` and exits 0, not
`VaultAlreadyInitializedError`. The alternative (erroring) would make
`init` the one write command in this codebase where re-running a
successful command on its own prior output is a failure — surprising
given the rest of the CLI's stance, and actively unhelpful for the
realistic case (a user re-running `init` defensively, unsure whether
it already ran, e.g. in a setup script).

### 4. Adopting an existing, non-vault directory only ever adds the marker

`init_vault` on a directory that already exists and already has
content (a user's existing notes folder, an existing git repo) creates
only the `.vacancy-radar/` marker inside it — nothing already there is
touched, moved, or read. This is the same containment discipline
`core.py`'s writes already apply within a vault (never touch a file
outside what the current call is explicitly creating), extended to the
one operation that runs before a vault's containment boundary exists
at all.

### 5. No scaffolding beyond the marker

A starter `_company.md`, a vault-local README, or a `.gitignore` would
each be a guess about what the user wants in a directory this change
has no visibility into (are they going to `git init` it themselves?
do they already have a `.gitignore`? do they want example content or
an empty vault?). The marker directory is the one thing every other
command in this codebase actually requires to exist — `init` creates
exactly that and nothing it would have to guess about.

## Risks / Trade-offs

- [`init`'s idempotent-no-op on an already-initialized vault means a
  typo'd path that happens to already be *some other* initialized
  vault silently "succeeds" against the wrong vault] → accepted: the
  same is already true of every other command today (pointing `list`
  at the wrong `VAULT_PATH` "succeeds" against the wrong vault too);
  `init`'s `--json`/plain output always names the resolved absolute
  path, so a wrong target is visible in the same way a wrong `list`
  target already is.
- [Adopting an existing, populated directory means `init` can be run
  against a directory with unrelated content, silently turning it into
  a vault root] → accepted: this is the explicit point of decision 4
  (adopting an existing git repo, notes folder, etc.), and it only
  ever *adds* the marker — nothing already present is at risk.

## Migration Plan

Purely additive. `resolve_vault_path`'s public behavior is unchanged
(decision 2); every existing test, command, and the MCP server are
unaffected. Rollback is removing `init_vault`, `resolve_target_path`,
and the `init` CLI command — nothing else depends on any of them.
