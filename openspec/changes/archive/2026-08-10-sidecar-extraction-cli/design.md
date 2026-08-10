## Context

Three stages already built everything this change needs except the
last wire: stage 3 (`index-build`) built `extract_to_sidecar` and gated
it behind `build_index(extract_sidecars=...)`, explicitly deferring
"a CLI or MCP surface for triggering a build or extraction" to stages
8-9 (its own design.md's Non-Goals). Stage 8 (`mcp-server`) built the
MCP tool surface without touching it (`reindex` isn't even an exposed
MCP tool, by design — see that stage's own exclusion). Stage 9
(`llm-import`) built conversational vacancy creation without touching
it either — its scope was `create_vacancy`/`find_existing`, not
`reindex`. The result, confirmed by running the commands rather than
just reading the code: `extract_sidecars=True` has never been passed
anywhere in this codebase outside `index/extract.py`'s and
`index/build.py`'s own docstrings describing what it's *for*.

`add`'s crash on binary input is unrelated in cause but related in
effect — both are things a user discovers only by trying to attach a
PDF and hitting a dead end, one silent (no sidecar, no error) and one
loud (a traceback).

## Goals / Non-Goals

**Goals:**
- `extract_sidecars` becomes reachable from the CLI, opt-in, without
  changing its default anywhere in the call chain.
- A warning `IndexReport` carries is visible in `reindex`'s ordinary
  (non-`--json`) output — today it's computed and immediately
  discarded by the CLI layer for every warning kind, not just
  extraction ones.
- `add`'s failure on non-text input is a message a user reads and acts
  on, not a stack trace.

**Non-Goals:**
- Flipping `extract_sidecars`'s default to `True`. Stage 3's reasoning
  ("a build must not silently create sidecar files on every run") is
  about surprising a user with new git-tracked files appearing from an
  otherwise-disposable operation — nothing about *making the flag
  reachable* weakens that reasoning, so this change doesn't revisit it.
- `.docx`, OCR, or any extractor beyond PDF — stage 3's own Non-Goals,
  untouched here.
- Making `add` accept binary content. `add_document`'s `content: str`
  parameter, and the filename-derivation logic built around a
  `title`/`date`/`kind` triple, both assume text — accepting PDFs
  through `add` would mean a second content-parameter shape (`bytes`
  alongside `str`) and a decision about whether a binary `add` call
  still derives its filename the same way or writes the source
  verbatim (closer to what dropping a file into `documents/` already
  does, for free, today). That's a real design fork, not a fix; this
  change's `add` half is scoped to "fail clearly," which needs none of
  those decisions.
- Auto-triggering extraction from `add`, `create_vacancy`, or any other
  write path. Those file *text* content the caller already has in
  hand; there is no PDF in play at the point any of them runs.

## Decisions

### 1. `extract_sidecars` stays opt-in; this change only adds the switch

`vacancy-radar reindex --extract-sidecars` (default: off, matching
`core.reindex`'s new `extract_sidecars: bool = False`). A user who
never attaches a PDF never sees a sidecar file appear from an ordinary
`reindex` — stage 3's design.md's reasoning holds exactly as written;
this change doesn't reopen it, only stops it from being unreachable in
practice. Every other write path's own internal `reindex(...)` call
(the one `append_note`/`set_status`/`add_document`/`create_vacancy`
each already make before returning) keeps passing no
`extract_sidecars` argument at all — those calls never involve a PDF,
so there's nothing for the flag to do there.

### 2. Plain-text `reindex` prints every warning, not only extraction ones

`IndexReport.warnings` already exists and already carries real
diagnostics — `vanished_source`, `stale_sidecar`, and now (once
reachable) `malformed_pdf`/`encrypted_pdf`/`empty_extraction` — none
of which have ever been visible outside `--json` output, since
`reindex_command`'s plain-text branch only ever printed the five count
fields. Scoping this change's warning-printing to "extraction warnings
only" would mean writing a second, narrower code path next to a
general one that already exists and already carries the data — more
code for a distinction the CLI output has no reason to make. Printing
every warning `IndexReport` returns, unconditionally, is also the only
way `--extract-sidecars` is actually useful without `--json`: an
encrypted PDF failing extraction needs to be visible in the command a
user actually ran, not require them to already know to add `--json`
to see why.

### 3. `add`'s fix is a caught exception and a message, not new capability

`_read_document_content`'s two existing failure branches
(`--file`+`--stdin` together, neither given) already follow the same
shape this needs: print a clear `error_console` message, `typer.Exit
(code=1)`. `file.read_text(encoding="utf-8")` raising
`UnicodeDecodeError` gets a third branch in that same function, same
shape, naming the file and pointing at the real PDF-attachment path
(`documents/` + `reindex --extract-sidecars`) so the error is
actionable, not just accurate. `--stdin`'s `sys.stdin.read()` gets the
identical treatment for the same reason — a binary file piped in via
`--stdin` fails exactly the same way for exactly the same reason.

This lives in `cli.py`, not `core.py`: `_read_document_content` never
calls into `core.py` at all — it's how the CLI turns `--file`/`--stdin`
into the `content: str` `core.add_document` expects, entirely a
CLI-layer parsing concern, the same category `_parse_date_option`/
`_parse_kind` already occupy in this file.

## Risks / Trade-offs

- [Printing every `IndexReport` warning in plain-text `reindex` output
  changes that command's output for any vault that already had
  `vanished_source`/`stale_sidecar` warnings today, even without
  `--extract-sidecars`] → accepted, and desired: those warnings were
  always real, always silently dropped; surfacing them is a bug fix,
  not new behavior to opt into. `--json`'s shape is unchanged
  (`warnings` was always present there), so nothing that already
  parsed `--json` output breaks.
- [`add`'s new UTF-8-decode error message is a judgment call about
  what's "helpful enough" without being wrong for every possible
  non-PDF binary file (a `.docx`, a `.zip`)] → accepted: the message
  names the PDF workflow specifically because that's the one this
  codebase actually supports end to end after this change; a `.docx`
  or `.zip` dropped into `documents/` still gets auto-registered as a
  `takehome`-kind document (unrelated to this change, stage 2's
  existing behavior) even though it gets no sidecar — the error
  message doesn't need to enumerate every extension to be correct,
  only to not mislead someone attaching a PDF specifically.

## Migration Plan

Additive and backward compatible. `core.reindex`'s new parameter
defaults to today's exact behavior; every existing caller (CLI writes'
own internal `reindex()` calls, existing tests) is unaffected.
`reindex`'s plain-text output gaining warning lines is the one
user-visible change to existing behavior, and only for vaults that
already had warnings `read_vault`/`build_index` were generating and
discarding. Rollback is reverting the `core.reindex` signature, the
CLI flag, the warning-printing, and `add`'s exception handling —
nothing else depends on any of them.
