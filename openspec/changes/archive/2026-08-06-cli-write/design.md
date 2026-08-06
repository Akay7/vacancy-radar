## Context

Stage 6 (`cli-read`) established the pattern this change extends: business
logic lives in `core.py` as typed functions with typed errors; `cli.py`
is parse-call-render only (invariant 4). This change adds the write
half over the same vault and index modules stage 6 read from —
`vault.paths`, `vault.reader.read_vault`, `frontmatter`, `ids`,
`index.build.build_index` — without changing any of their existing
behavior.

The vault is hand-edited and git-tracked (per `frontmatter.py`'s own
docstring: "the vault is hand-edited and git-tracked"). Every write in
this change has to hold two things in tension: it must be safe to call
from an LLM at stage 8 acting on untrusted content (a recruiter email
is attacker-controlled text passed as `add_document`'s `content` and
`title`), and it must produce diffs a human reviewing their vault's git
history would recognize as sane — no reformatted files, no clobbered
edits, no orphaned temp files left behind by a crash.

The stage plan's deliverable text gives `set_status` the signature
`set_status(vacancy_id, new_status, note=None) -> StatusChange` with no
`applied_date` parameter, yet `Vacancy`'s own model validator
(`models.py`'s `_check_applied_date_matches_status`) requires
`applied_date` on every non-`found` status and forbids it on `found`.
Since a vacancy sitting at `found` always has `applied_date=None` (the
same validator enforces that), no transition off `found` can construct
a valid `Vacancy` without an `applied_date` coming from somewhere. This
design resolves that gap explicitly in Decision 7, below, rather than
silently defaulting `applied_date` to "today" (a guess a caller didn't
make) or silently dropping the model's own invariant.

## Goals / Non-Goals

**Goals:**
- Every write function in `core.py` is either strictly append-only at
  the filesystem level (`append_note`, `add_document`, `create_vacancy`)
  or a validated, typed-error-guarded in-place update confined to
  `vacancy.md`'s frontmatter and a single append-only body section
  (`set_status`) — invariant 3, enforced in code, not just by
  convention.
- A write never leaves a partial file in the vault, on success or
  failure — atomic replace, never in-place truncate-then-write.
- A write's affected document(s) are searchable in the same process,
  without a separate `reindex` call.
- Filenames and vacancy directory names for anything created by this
  change are always derived, never accepted verbatim from a caller —
  the safety property stage 8 depends on.
- `cli.py` commands resolving a vacancy reuse `core.resolve` unchanged
  and write nothing on an ambiguous match.

**Non-Goals:**
- MCP tools, schemas, or transport — stage 8.
- Any delete path, `--force`-to-delete, or cleanup helper — explicitly
  out of scope per the stage plan's constraints, not deferred, not
  planned.
- Rewriting or reformatting any vault file this change doesn't
  explicitly write to (`frontmatter.py`'s round-trip guarantee is
  reused, not re-implemented).
- A general markdown-section parser — the status-history block's
  append strategy (Decision 6) is deliberately simple, not a generic
  document-editing capability.

## Decisions

### 1. Documents are filed into one flat `documents/` directory; `kind` lives in frontmatter, not in a subdirectory

The stage plan's `add_document` prose says "writes into the directory
for its kind," which reads as a kind-split tree
(`documents/postings/`, `documents/emails/`, ...). The vault layout
this codebase actually has — established by `vault/paths.py`'s own
docstring, which documents the stage 1 reconciliation away from a
kind-split tree — is a single flat `{vacancy}/documents/*`, with
`kind` recorded in each document's frontmatter and read back by
`vault.reader._read_document`. `add_document` follows the vault that
exists: "the directory for its kind" resolves to the vacancy's one
`documents/` directory (created if the vacancy has no documents yet),
and `kind` is written into the new document's frontmatter, exactly
mirroring how every existing fixture document already stores it. This
is the same kind of plan/reality reconciliation stage 6's proposal.md
called out for `_search`/`_eval` — noted here so it isn't silently
reinterpreted without a trace.

### 2. Filenames and document ids are derived: `{date}-{kind}-{slug(title)}.md`, collision-suffixed against the filesystem

`add_document`'s filename is `{date.isoformat()}-{kind.value}-{slug}.md`,
where `slug` is `ids.slugify(title)` truncated the same way
`new_vacancy_id` truncates a role slug. The document's `id` (frontmatter
`id:`, matching every fixture document's own id-equals-filename-stem
convention) is that filename's stem. If the derived path already
exists, a numeric suffix (`-2`, `-3`, ...) is appended before the
extension until the path is free — the same collision strategy
`ids.new_vacancy_id` uses for vacancy ids, but checked against the
filesystem rather than an in-memory id set, since `ids.py` deliberately
has no filesystem access (its own docstring: "No filesystem access
here"). `append_note` is `add_document` with `kind=DocumentKind.NOTE`,
a fixed `title="Note"`, and `content=text` — it does not duplicate the
derivation logic, it calls it.

Why derived rather than caller-supplied (the design note the stage plan
asks for explicitly): at stage 8 the caller filing a document is an LLM
acting on a recruiter's email — `title` is attacker-controlled text.
`ids.slugify` collapses any run of non-alphanumeric characters
(including `/`, `\`, and `..`) to a single hyphen, so a title of
`"../../etc/password"` or `"notes/../../evil"` slugifies to an inert
string like `passwd` or `notes-evil` with no path-traversal meaning
left in it — there is no code path where a hostile `title` chooses
where a byte lands on disk. A caller-supplied filename or path
parameter would be a traversal primitive the moment it's exposed as an
MCP tool argument; deriving the name removes the primitive rather than
sanitizing an accepted one. `vault.paths.is_within` is checked on the
final resolved path before every write anyway, as defense in depth —
belt (derivation can't produce a path outside the vacancy's own
`documents/` directory) and suspenders (a containment check that would
catch it if it somehow did).

### 3. `external_id` dedupe short-circuits before any filesystem write

`add_document` reads the vault fresh, and if `external_id` is given and
already matches a document filed under the same vacancy, returns that
document's existing path immediately — no directory listing, no
filename derivation, no write. This matters operationally, not just
as a nice-to-have: an MCP-connected mail client will be asked to file
the same Gmail thread more than once (a user re-runs a chat turn, an
agent retries after a timeout, a recruiter's follow-up email quotes
the original thread). Content-based dedupe doesn't work here — a
forwarded or quoted-reply version of the same email has different
bytes — so identity has to come from something stable the source
system provides (a Gmail thread id, a message id), checked as an exact
match against what's already filed for that vacancy, not fuzzy-matched
against content. The second `add_document` call for the same thread
must be a no-op, not a duplicate entry cluttering the vacancy's
document list and the search index alike.

### 4. Index refresh reuses stage 3's incremental `build_index`, unchanged, called eagerly after every write

`reindex(force=False)` is `build_index(read_vault(vault),
default_index_path(vault), force=force)` — a thin, undecorated wrapper.
`append_note`, `set_status`, `add_document`, and `create_vacancy` each
call this same wrapper (with `force=False`) as the last step before
returning, over a freshly re-read `VaultSnapshot` that includes the
write just made.

This works, and stays cheap, because `build_index` already diffs by
content hash (`index/build.py`'s `_existing_hashes`/content-hash
comparison): a post-write refresh re-embeds only the row(s) whose
content actually changed — the one new document, or the one vacancy
row whose composed text now mentions a new status — and resyncs
denormalized columns on everything else via `_resync_denormalized_columns`,
which explicitly never re-embeds. A `set_status` call therefore leaves
every one of that vacancy's *document* rows with their `status` column
updated and their `vector` column byte-identical, while the vacancy's
own row (whose composed text — `_compose_vacancy_text` — includes
`status.value`) is re-embedded, correctly, because its content did
change. No new partial-index-update code is needed in `core.py`; the
existing full-snapshot diff already produces exactly the partial
update each write needs, because most of the vault didn't change.

Why eager, not lazy (the design note the stage plan asks for
explicitly): a lazy scheme — mark the index dirty on write, rebuild on
the next `search` call — pushes an unpredictable latency spike onto
whichever `search` happens to run first after a write, in whichever
process runs it. For a CLI, that means one `vacancy-radar search`
invocation, somewhere in the future, in a different process, pays for
a note you appended in a prior invocation, seemingly at random. For an
MCP server (stage 8), it's worse: the first tool call an LLM makes in
a session eats the latency of every write any client made since the
index was last fresh, and the LLM has no way to know that's what's
happening. Paying the (small, diff-bounded) cost synchronously, inside
the write call that caused it, keeps the cost attributable and
predictable — "a write takes slightly longer" beats "search
mysteriously stalls sometimes."

### 5. The status graph is data in `models.py`; `set_status` only looks it up

`models.py` gains `STATUS_TRANSITIONS: Mapping[Status, frozenset[Status]]`,
built once from a linear pipeline order (`found, applied, screening,
take_home, interview, offer`) plus the two terminal statuses
(`rejected`, `ghosted`): every pipeline status's permitted-without-force
set is every *later* pipeline status (not just the immediate next one
— real pipelines skip `take_home` or go straight from `screening` to
`offer`) union `{rejected, ghosted}`; `rejected` and `ghosted` map to
an empty set (nothing is a normal, un-forced follow-on to a terminal
status). `set_status` does exactly one thing with this: `new_status in
STATUS_TRANSITIONS[current_status]`. No `if`/`elif` chain over status
names lives in `set_status` itself — the transition rule is data a
future MCP resource can serialize and hand to an LLM directly (`GET
vacancy://status-transitions`-shaped), without `core.py` growing a
second, string-based description of the same rule that could drift
from the code enforcing it.

A same-status call (`new_status == current_status`) is checked before
consulting the graph at all and is unconditionally a no-op — it isn't
a "permitted transition" the graph would need to encode, and `force`
has no effect on it either way.

### 6. Status history is an append-only block, always the last thing in `vacancy.md`'s body

`set_status` appends one line — `- {today}: {old} -> {new}` (plus the
note text, if given) — under a `## Status History` heading, creating
the heading (once, at the end of the existing body) the first time a
vacancy transitions. This is deliberately not a general markdown-
section editor: the block is treated as owning everything from its
heading to end-of-file, and every new entry is appended at the literal
end of the body. Nothing in this codebase parses markdown structure
today (`frontmatter.py` only splits YAML-frontmatter from body text as
one opaque block), and building a real section-boundary parser to
support inserting content *before* a later human-authored section is
more machinery than one append-only log block justifies. The
documented constraint — humans write above `## Status History`, never
below it — is simple enough to hold in practice and is stated here so
it's a known trade-off, not a silent landmine (see Risks).

Everything else in `vacancy.md` — frontmatter fields other than
`status`/`applied_date`, comments, key order, quoting, and body text
above the status-history block — passes through `frontmatter.parse`
and `frontmatter.serialize` untouched, which is what gives the stage 1
round-trip guarantee (byte-identical apart from the status field and
the history block) for free. `stage_note` is a frontmatter field this
function never assigns to, by construction — there is no code path in
`set_status` that writes it.

### 7. `set_status` gains an `applied_date` parameter beyond the stage plan's listed signature, and the CLI gains `--applied-date`

As laid out in Context, above: `Vacancy`'s own conditional-`applied_date`
rule makes an `applied_date`-less transition off `found` structurally
impossible to satisfy without either (a) a value from the caller, or
(b) a silent default. This design picks (a):
`set_status(vacancy_id, new_status, note=None, applied_date=None, *,
force=False) -> StatusChange`. When the transition moves off `found`
and the vacancy has no `applied_date` yet, `applied_date` must be
supplied or `set_status` raises a typed `MissingAppliedDateError`
naming the vacancy and the target status — this is exactly the "raises
when it is absent" scenario the stage plan's requirements section asks
for. `vacancy-radar status set` gains a matching `--applied-date`
option.

The alternative — defaulting `applied_date` to "today" whenever it's
missing — was rejected: an applied date is a fact about when a real
action happened, and a CLI invocation's timestamp is frequently *not*
that (status is often updated retroactively, catching up a vault after
a week of not looking at it). Guessing a wrong applied date silently
is worse than asking once; this mirrors `resolve`'s stage 6 rationale
for returning candidates instead of picking one.

### 8. `create_vacancy` is in scope for this change, not deferred

It's the one function here that isn't append-only at the level of "one
call, one new file inside an existing directory" — it can create a new
company directory and `_company.md` alongside a new vacancy directory.
It's included anyway, for two reasons. First, the stage plan's CLI
surface requires it directly: `vacancy-radar new` has no meaning
without a function to back it, and deferring `create_vacancy` alone
would leave `new` unimplementable within this change while still being
listed as one of its deliverables. Second, and more importantly, it
still satisfies invariant 3's actual intent — nothing here *deletes or
overwrites* existing vault content. `create_vacancy` only ever adds a
new subtree (a company directory + `_company.md` when the slug is new,
a vacancy directory + `vacancy.md` always) or adds a vacancy directory
under an already-existing, untouched company directory. It never opens
an existing file for writing. The "not append-only" property is about
directory *creation*, not content mutation — the same category of
operation `add_document` already performs when a vacancy's first
document creates its `documents/` directory. Re-running `create_vacancy`
with the same inputs is not idempotent (it mints a second, collision-
suffixed vacancy, by design — unlike `add_document`'s `external_id`
dedupe, there is no natural identity key for "the same vacancy" to
dedupe against), and that asymmetry is called out explicitly rather
than left implicit.

### 9. Atomic writes: temp file in the target directory, then `os.replace`

Every write in this change (new files and `vacancy.md`'s in-place
frontmatter update alike) goes through one private helper:
write the full final content to a temp file created in the *same*
directory as the target (`tempfile.mkstemp(dir=target.parent)`,
extension-preserving, dot-prefixed name), then `os.replace(tmp_path,
target)`. Same-directory placement keeps the replace on one filesystem
(no cross-device rename failure), and `os.replace` is atomic on every
platform this project targets — a reader (including a concurrently
running `read_vault`) sees either the old file in full or the new file
in full, never a truncated partial write, regardless of when a crash
happens.

Interaction with the vault being a git repo: the dot-prefixed temp name
(matching `vault.paths.is_skipped_name`'s "dotfiles are skipped"
convention already used for `.vacancy-radar/` and `.index/`) means
that if a write is interrupted between `mkstemp` and `replace` — a
kill -9, a power loss — the orphaned temp file is invisible to
`read_vault`'s traversal even though it may remain on disk. A user's
`git status` in the vault could still show it as an untracked file
after such a crash (this codebase doesn't ship or manage a vault-side
`.gitignore`); that residual is called out in Risks rather than solved
here, since solving it fully would mean this change taking ownership
of the vault's `.gitignore`, which is out of scope.

## Risks / Trade-offs

- [`## Status History` is treated as always the final section of
  `vacancy.md`'s body] → if a human adds their own heading below it,
  the next `set_status` call appends after that content, not before
  it, silently interleaving machine and human sections. Mitigated by
  documenting the convention (Decision 6) and by every `create_vacancy`-
  produced `vacancy.md` starting with an empty body, so the section
  only ever gets *created* by `set_status` itself, at the true end.
  Revisit only if real usage shows humans routinely writing content
  below it.
- [A crash between `mkstemp` and `os.replace` can leave a dot-prefixed
  temp file in the vault] → invisible to `read_vault`
  (`is_skipped_name`) and to the index, but not to `git status`.
  Acceptable: the vault itself was already never fully crash-swept by
  this project (no vault-side `.gitignore` is managed here); a stray
  temp file is a visible, harmless leftover a user can delete, never a
  corrupted vault file.
- [Eager reindex-on-write re-reads and re-hashes the whole vault on
  every single write, same as `core.search`/`doctor` already do on
  every call] → no new I/O pattern (Decision 4's cost analysis); the
  same trade-off stage 6's design.md already accepted for read paths,
  now accepted for writes too. Revisit if vault size makes per-write
  `read_vault` calls measurably slow.
- [`create_vacancy`'s non-idempotent re-run (Decision 8) could surprise
  a caller expecting `add_document`-style dedupe] → intentional; no
  natural identity key exists for "this is the same vacancy" the way
  `external_id` exists for documents. A caller that wants idempotent
  vacancy creation is expected to check `resolve`/`list_vacancies`
  first, the same way a human would before hand-creating a directory.

## Migration Plan

Purely additive: `core.py` and `cli.py` gain new functions/commands;
`models.py` gains new module-level data (`STATUS_TRANSITIONS`,
`TERMINAL_STATUSES`). No existing function's signature or behavior
changes. No vault or index schema change — writes produce files in the
exact shape `vault.reader.read_vault` and `index.build.build_index`
already expect, and status-history/`## Status History` is new content
in a place (`vacancy.md`'s body) nothing previously read structurally.
Rollback is a plain revert; no prior stage depends on any function this
change adds.

## Open Questions

- None blocking. The exact `MAX_TITLE_SLUG_LENGTH` truncation length
  for derived document filenames (mirroring `ids.MAX_ROLE_SLUG_LENGTH`)
  is an implementation parameter, not a design fork — pick a value
  during tasks.md's filename-derivation tests and keep filenames
  readable in a file browser.
