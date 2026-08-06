## 1. Fixture scaffolding for write tests

- [x] 1.1 Use `tests/test_core.py`'s existing `_minimal_built_vault`
      (and its `_init_vault`/`_write_company`/`_write_vacancy`/
      `_write_document`/`_simple_vacancy` building blocks, already
      present from the cli-read change) as the starting vault for write
      tests, built fresh per test at `tmp_path` — deviates from this
      task's original `shutil.copytree(FIXTURE_VAULT, ...)` plan:
      those hand-built helpers already exist, are already the
      established convention for `core.py` tests (stage 6 chose them
      over copying the full fixture for speed), and satisfy "no test
      mutates `tests/fixtures/vault/`" trivially since they never touch
      it. `FIXTURE_VAULT` itself remains available (already imported)
      for tests that specifically want the committed vault's shape.
- [x] 1.2 Added the equivalent `_minimal_vault` helper to
      `tests/test_cli.py`, reusing that file's own already-present
      `_init_vault`/`_write_company`/`_write_vacancy`/`_simple_vacancy`
      helpers (pre-dating this change, added for cli-read's staleness/
      ambiguity fixtures) — used by write-command tests via `env=
      {"VAULT_PATH": str(vault)}` passed to `runner.invoke`.
- [x] 1.3 No new named helper: `build_index(read_vault(vault),
      default_index_path(vault))` called directly, inline, is already
      `tests/test_core.py`'s established pattern (used repeatedly in
      its existing index-freshness/search tests) — followed as-is
      wherever a write test needs a pre-built, fresh index.
- [x] 1.4 N/A given 1.1-1.3's approach — nothing here copies
      `tests/fixtures/vault/`, so there is nothing that could mutate
      it; confirmed with `git status` after the full test run in
      later sections.

## 2. models.py: status transition graph — tests, then implementation

- [x] 2.1 Write `tests/test_models.py`: `STATUS_TRANSITIONS` contains
      every `Status` member as a key.
- [x] 2.2 Write `tests/test_models.py`: each pipeline status
      (`found`, `applied`, `screening`, `take_home`, `interview`) maps
      to every status *later* in the pipeline order plus `rejected` and
      `ghosted` — not only the immediate next status.
- [x] 2.3 Write `tests/test_models.py`: `offer`, `rejected`, and
      `ghosted` each map to an empty set of *pipeline* follow-ons
      (`offer` still reaches `rejected`/`ghosted`, like every other
      active status — it has no later pipeline stage, which is the
      property under test).
- [x] 2.4 Write `tests/test_models.py`: no status appears in its own
      permitted-transitions set (no self-loop encoded in the graph —
      the same-status no-op is handled by `set_status`, not the graph).
- [x] 2.5 Implement `STATUS_TRANSITIONS: dict[Status,
      frozenset[Status]]` (and `TERMINAL_STATUSES`) in
      `src/vacancy_radar/models.py`, built once from a linear pipeline
      order plus the two terminal statuses — data, no branching logic
      (design.md decision 5).
- [x] 2.6 Run 2.1-2.4 green against the implementation. (`pytest
      tests/test_models.py -q` → 42 passed)

## 3. core.py: atomic write and filename derivation helpers — tests, then implementation

- [x] 3.1 Write `tests/test_core.py`: writing through the atomic-write
      helper to a new path creates a file with the exact given content;
      no temp file remains afterward.
- [x] 3.2 Write `tests/test_core.py`: simulate a failure between the
      temp file being written and the rename (monkeypatch `os.replace`
      to raise) and confirm the target path is left absent (new-file
      case). Actual behavior is stronger than the original plan: the
      temp file is cleaned up in an `except` around the write/replace,
      so nothing dot-prefixed is left behind either, for any *caught*
      failure — the "may remain, dot-prefixed" case in design.md
      decision 9 is specifically the uncatchable kill -9/power-loss
      scenario no `except` block can run for.
- [x] 3.3 Write `tests/test_core.py`: the atomic-write helper used to
      *update* an existing file (the `vacancy.md` case) leaves the
      prior content intact if the write is interrupted before the
      rename.
- [x] 3.4 Write `tests/test_core.py`: the containment-check helper
      (`_ensure_within_vault`) raises `PathOutsideVaultError` for a
      path outside the vault and does not raise for one inside it —
      tested directly as the belt-and-suspenders unit it is (design.md
      decision 2); not reachable through `title` in practice since
      `ids.slugify` already prevents that path.
- [x] 3.5 Write `tests/test_core.py`: `title` values containing `/`,
      `\`, and `..` segments all produce a filename inside the target
      directory, with no file created elsewhere; a blank/punctuation-
      only title falls back to `"untitled"`.
- [x] 3.6 Write `tests/test_core.py`: a filename collision (target path
      already exists) is resolved by a numeric suffix, checked against
      the filesystem (one collision -> `-2`, two -> `-3`), and suffix
      attempts exhausted (via a monkeypatched low cap) raises
      `DocumentAlreadyExistsError`.
- [x] 3.7 Implemented `_atomic_write` (temp file via
      `tempfile.mkstemp(dir=target.parent)`, dot-prefixed name, then
      `os.replace`), `_ensure_within_vault` (wraps
      `vault.paths.is_within`, raises the existing `PathOutsideVaultError`
      from the read half), and `_derive_document_filename`
      (`{date}-{kind}-{slug(title)}.md`, filesystem-checked collision
      suffixing capped by `_MAX_FILENAME_SUFFIX_ATTEMPTS`) in
      `src/vacancy_radar/core.py`, per design.md decisions 2 and 9.
      Added `DocumentAlreadyExistsError` alongside the read half's
      existing `CoreError` subclasses.
- [x] 3.8 Run 3.1-3.6 green against the implementation. (`pytest
      tests/test_core.py -k "atomic_write or ensure_within_vault or
      derive_document_filename"` → 13 passed)

## 4. core.py: add_document() — tests, then implementation

- [x] 4.1 Write `tests/test_core.py`: filing a new document creates a
      file at the derived path, and the returned path matches it.
- [x] 4.2 Write `tests/test_core.py`: a derived path that already
      exists (constructed so every collision-suffix is also taken, via
      a monkeypatched `_MAX_FILENAME_SUFFIX_ATTEMPTS`) raises a typed
      error and creates no file.
- [x] 4.3 Write `tests/test_core.py`: `external_id` matching a document
      already filed under the same vacancy returns that document's
      existing path and creates no new file.
- [x] 4.4 Write `tests/test_core.py`: the same `content`/`title` filed
      again under a *different* `external_id` creates a second, distinct
      document.
- [x] 4.5 Write `tests/test_core.py`: after `add_document` returns, a
      `search` call in the same process (against a pre-built, fresh
      index) returns the new document as a hit, with no intervening
      `reindex` call.
- [x] 4.6 Write `tests/test_core.py`: `add_document` given a
      `vacancy_id` matching no vacancy raises a typed not-found error
      and creates no file (an exact-id lookup against
      `snapshot.vacancies`, not a full `resolve` fuzzy match - write
      functions take an already-resolved id; the CLI layer is what
      calls `resolve`, per design.md/proposal.md).
- [x] 4.7 Implemented `add_document(vacancy_id, kind, content, title,
      date, external_id=None, *, vault=None) -> Path` in `core.py`:
      exact-id lookup, external_id dedupe check first (design.md
      decision 3), then filename derivation (section 3) against the
      vacancy's `documents/` directory, then atomic write of
      frontmatter + content (`overwrite=False`), then
      `reindex(vault=vault_root)` before returning.
- [x] 4.8 Run 4.1-4.6 green against the implementation. (`pytest
      tests/test_core.py -k add_document` → 6 passed)

## 5. core.py: append_note() — tests, then implementation

- [x] 5.1 Write `tests/test_core.py`: `append_note` on a vacancy with
      no existing notes creates one file whose body equals the given
      text.
- [x] 5.2 Write `tests/test_core.py`: a second `append_note` call on
      the same vacancy creates a new file and leaves the first file's
      bytes unchanged.
- [x] 5.3 Write `tests/test_core.py`: two `append_note` calls with the
      same explicit `date` produce two distinct files, neither
      overwriting the other.
- [x] 5.4 Write `tests/test_core.py`: after `append_note` returns, a
      `search` call in the same process (pre-built, fresh index) against
      text from the note returns it as a hit.
- [x] 5.5 Implemented `append_note(vacancy_id, text, date=None, *,
      vault=None) -> Path` in `core.py` as a thin call into
      `add_document` with `kind=DocumentKind.NOTE`, a fixed
      `title="Note"` (`NOTE_TITLE`), and `content=text` — no duplicated
      filename-derivation logic (design.md decision 2). `date` defaults
      to today's local calendar day.
- [x] 5.6 Run 5.1-5.4 green against the implementation. (`pytest
      tests/test_core.py -k append_note` → 4 passed)

## 6. core.py: set_status() — tests, then implementation

- [x] 6.1 Write `tests/test_core.py`: a permitted forward transition
      (e.g. `applied` -> `screening`) updates the vacancy's stored
      status and the returned `StatusChange` reflects it.
- [x] 6.2 Write `tests/test_core.py`: a backward transition without
      `force` raises a typed error naming both the current and
      requested status, and the vacancy's stored status is unchanged.
- [x] 6.3 Write `tests/test_core.py`: the same backward transition with
      `force=True` succeeds.
- [x] 6.4 Write `tests/test_core.py`: calling `set_status` with the
      vacancy's current status is a no-op — no file modified, returned
      `StatusChange` reports no change — regardless of `force`.
- [x] 6.5 Write `tests/test_core.py`: an invalid status string raises a
      typed error whose message lists every valid `Status` value.
- [x] 6.6 Write `tests/test_core.py`: two sequential status changes on
      the same vacancy leave both entries present in the status-history
      block, in order.
- [x] 6.7 Write `tests/test_core.py`: `stage_note` is byte-identical
      (read back as the same string) before and after a `set_status`
      call, for a vacancy whose `stage_note` is non-empty.
- [x] 6.8 Write `tests/test_core.py`: a vacancy at `found` transitioned
      to `applied` without an `applied_date` argument raises a typed
      error and leaves the vacancy's stored status at `found`.
- [x] 6.9 Write `tests/test_core.py`: the same transition with an
      explicit `applied_date` succeeds and the vacancy's stored
      `applied_date` equals the value given.
- [x] 6.10 Write `tests/test_core.py`: reading `vacancy.md`'s full text
      before and after a `set_status` call, the only differing/added
      lines are the `status` field, the `## Status History` heading (on
      a vacancy's first status change), history entry lines, and blank
      separator lines the history block introduces — every other
      frontmatter field and body line is byte-identical (the stage 1
      round-trip guarantee).
- [x] 6.11 Write `tests/test_core.py` (embedding-marked): for a vacancy
      with an indexed document, record that document's vector before a
      `set_status` call, reopening the table afterward (mirroring
      `index.search.search`'s own open-fresh-each-call pattern, since a
      held-open `Table` object doesn't observe writes another
      connection made) — the document's row reports the new status and
      its vector is identical to the recorded one.
- [x] 6.12 Write `tests/test_core.py`: `set_status` given a
      `vacancy_id` matching no vacancy raises a typed not-found error.
- [x] 6.13 Implemented `StatusChange` and `set_status(vacancy_id,
      new_status, note=None, applied_date=None, *, force=False,
      vault=None) -> StatusChange` in `core.py`: same-status no-op check
      first, then `STATUS_TRANSITIONS` lookup (raising unless permitted
      or `force`), then the off-`found`-requires-`applied_date` check
      (`_resolve_applied_date`, also clearing `applied_date` on a forced
      transition back to `found`, per the model's own rule), then an
      atomic rewrite of `vacancy.md` — mutating the parsed
      `CommentedMap` in place (only `status`/`applied_date` keys
      touched) and re-validating via `Vacancy(**metadata)` before
      writing, so untouched fields keep their original ruamel
      formatting — with the status-history block appended per design.md
      decision 6, then `reindex(vault=vault_root)` before returning.
      Added `InvalidStatusValueError`, `InvalidStatusTransitionError`,
      `MissingAppliedDateError`, `InvalidVacancyDataError`.
- [x] 6.14 Run 6.1-6.12 green against the implementation. (`pytest
      tests/test_core.py -k set_status` → 12 passed)

## 7. core.py: reindex() — tests, then implementation

Implemented ahead of sections 4-6/8 since every other write function
calls it as its last step.

- [x] 7.1 Write `tests/test_core.py`: `reindex()` against an already
      fresh index reports nothing added, changed, or deleted.
- [x] 7.2 Write `tests/test_core.py`: `reindex(force=True)` against a
      fresh index reports every row re-embedded.
- [x] 7.3 Write `tests/test_core.py`: `reindex()` after a vault change
      made outside of `core.py`'s write functions (e.g. a document
      added by directly writing a file, mirroring stage 3's own tests)
      picks it up.
- [x] 7.4 Implement `reindex(force=False, vault=None) -> IndexReport`
      in `core.py` as a thin wrapper: `build_index(read_vault(vault),
      default_index_path(vault), force=force)` — `vault` added for the
      same explicit-vault testability every other `core.py` function
      already has.
- [x] 7.5 Run 7.1-7.3 green against the implementation. (`pytest
      tests/test_core.py -k reindex` → 3 passed)

## 8. core.py: create_vacancy() — tests, then implementation

- [x] 8.1 Write `tests/test_core.py`: `create_vacancy` for a company
      with no existing directory creates that directory, a
      `_company.md`, and the new vacancy directory + `vacancy.md`.
- [x] 8.2 Write `tests/test_core.py`: `create_vacancy` for a company
      that already has `_company.md` adds a second vacancy under it and
      leaves `_company.md`'s bytes unchanged.
- [x] 8.3 Write `tests/test_core.py`: two `create_vacancy` calls with
      the same `found_date`, company, and an unknown role produce two
      vacancies with distinct ids and both directories exist afterward.
- [x] 8.4 Write `tests/test_core.py`: `create_vacancy` with
      `status=Status.FOUND` and no `applied_date` succeeds (the
      model's own found/no-applied_date rule is satisfied by
      construction).
- [x] 8.5 Write `tests/test_core.py`: `create_vacancy` with a non-`found`
      `status` and no `applied_date` raises a typed error (the model's
      conditional rule surfaced as a typed `core.py` error, not a raw
      `pydantic.ValidationError`), and creates no vacancy for that
      company.
- [x] 8.6 Write `tests/test_core.py` (embedding-marked): after
      `create_vacancy` returns, `list_vacancies()` in the same process
      includes the new vacancy, and a `search` call against its role
      text returns it as a hit — no separate `reindex` call.
- [x] 8.7 Implemented `create_vacancy(company, role, source_url,
      found_date, status, applied_date=None, *, vault=None) -> Path` in
      `core.py`: derive `company_slug` via `ids.slugify`, create the
      company directory/`_company.md` only if `_company.md` is absent,
      mint the vacancy id via `ids.new_vacancy_id` against existing ids
      read fresh from the vault (union'd with any raw subdirectory names
      already on disk under the company directory, defensively), atomic-
      write `vacancy.md` (`overwrite=False` — never overwrites), then
      `reindex(vault=vault_root)` before returning; wraps `Vacancy`
      construction's `pydantic.ValidationError` into `InvalidVacancyDataError`.
- [x] 8.8 Run 8.1-8.6 green against the implementation. (`pytest
      tests/test_core.py -k create_vacancy` → 7 passed, including an
      extra regression test added for a bug caught during review:
      `Status(status)` was evaluated outside the `try`/`except
      ValidationError` block, so an invalid `--status`-style string
      raised a raw `ValueError` instead of `InvalidVacancyDataError` —
      fixed by moving the conversion inside the guarded block and
      catching `ValueError` directly, since `pydantic.ValidationError`
      subclasses it. Full `pytest tests/test_core.py tests/test_models.py`
      → 120 passed; `ruff check`/`ruff format --check` clean on all
      touched files.)

## 9. cli.py: `note` command — tests, then implementation

- [x] 9.1 Write `tests/test_cli.py` (`CliRunner`, hand-built temp vault
      via `_minimal_vault`): `vacancy-radar note <id> "text"` exits 0
      and creates one note file under that vacancy.
- [x] 9.2 Write `tests/test_cli.py`: `note` given a query that
      `core.resolve` finds ambiguous exits non-zero, prints the
      candidates, and creates no file.
- [x] 9.3 Write `tests/test_cli.py`: `note --json` emits valid JSON
      naming the created path.
- [x] 9.4 Implemented `vacancy-radar note <vacancy> <text> [--date]
      [--json]` in `cli.py`: `_resolve_vacancy_or_fail` (candidates ->
      print + exit non-zero, no write - shared by every write command
      that takes a vacancy argument), then `core.append_note`,
      rendering via the shared `_render_write_outcome` helper.
- [x] 9.5 Run 9.1-9.3 green against the implementation. (`pytest
      tests/test_cli.py -k note_command` → 3 passed)

## 10. cli.py: `status set` command — tests, then implementation

- [x] 10.1 Write `tests/test_cli.py`: `vacancy-radar status set <id>
      <status>` for a permitted forward transition exits 0 and updates
      the vacancy.
- [x] 10.2 Write `tests/test_cli.py`: a backward transition without
      `--force` exits non-zero and names both statuses; with `--force`
      it exits 0.
- [x] 10.3 Write `tests/test_cli.py`: moving a `found` vacancy to
      `applied` without `--applied-date` exits non-zero; with
      `--applied-date` it exits 0 and the stored `applied_date` matches.
- [x] 10.4 Write `tests/test_cli.py`: `status set` given an ambiguous
      query exits non-zero and writes nothing.
- [x] 10.5 Write `tests/test_cli.py`: `status set --json` on a same-
      status call emits valid JSON whose outcome indicates no change.
- [x] 10.6 Implemented `vacancy-radar status set <vacancy> <status>
      [--note] [--applied-date] [--force] [--json]` in `cli.py`:
      resolve, then `core.set_status` directly with the raw status
      string — no CLI-side status parsing, since `set_status` already
      raises a typed, permitted-values-listing error for an invalid one
      (duplicating that check in `cli.py` would be exactly the kind of
      business logic design.md decision 1 forbids there) — then render
      the `StatusChange` or `--json`.
- [x] 10.7 Run 10.1-10.5 green against the implementation. (`pytest
      tests/test_cli.py -k status_set` → 6 passed)

## 11. cli.py: `add` command — tests, then implementation

- [x] 11.1 Write `tests/test_cli.py`: `vacancy-radar add <id> --kind
      note --title "..." --date ... --file <path>` exits 0 and creates
      a document whose content matches the file.
- [x] 11.2 Write `tests/test_cli.py`: the same invocation with `--stdin`
      instead of `--file`, piping content via `runner.invoke(...,
      input=...)`, creates a document whose content matches what was
      piped.
- [x] 11.3 Write `tests/test_cli.py`: `add` with an `--external-id`
      that already matches a filed document exits 0, creates no new
      file, and (with `--json`) reports the existing path.
- [x] 11.4 Write `tests/test_cli.py`: `add` given an ambiguous vacancy
      query exits non-zero and writes nothing.
- [x] 11.5 Write `tests/test_cli.py`: `add --json` on a fresh filing
      emits valid JSON naming the created path.
- [x] 11.6 Implemented `vacancy-radar add <vacancy> --kind --title --date
      [--file|--stdin] [--external-id] [--json]` in `cli.py`: resolve,
      read content from `--file` or stdin (`_read_document_content` -
      typed error if neither/both given; this is I/O plumbing, not
      business logic), call `core.add_document`. The created-vs-
      existing outcome for `--json` is derived by comparing
      `core.get_vacancy(...).documents` counts before and after the
      call (`_document_count`) rather than reimplementing
      `add_document`'s internal external_id-dedupe rule in `cli.py` -
      pure observation via an existing read-half function, not new
      business logic.
- [x] 11.7 Run 11.1-11.5 green against the implementation. (`pytest
      tests/test_cli.py -k add_command` → 5 passed)

## 12. cli.py: `new` command — tests, then implementation

- [x] 12.1 Write `tests/test_cli.py`: `vacancy-radar new --company
      --role --url --found-date` exits 0, creates the vacancy (and
      company directory, if new), and the vacancy is listed by a
      follow-up `vacancy-radar list --json` in the same invocation
      sequence (temp vault).
- [x] 12.2 Write `tests/test_cli.py`: `new --status <non-found>`
      without `--applied-date` exits non-zero (mirrors 8.5/10.3's
      conditional rule at the CLI boundary); the same call with
      `--applied-date` exits 0 — `new` exposes `--applied-date`, per
      design.md decision 7's reasoning (same call as `status set`'s).
- [x] 12.3 Write `tests/test_cli.py`: `new --json` emits valid JSON
      naming the created vacancy's id and path.
- [x] 12.4 Implemented `vacancy-radar new --company --role --url
      --found-date [--status] [--applied-date] [--json]` in `cli.py`:
      parse dates, call `core.create_vacancy` with the raw status
      string (same reasoning as 10.6 - `create_vacancy` already raises
      a typed error for an invalid one), render the created vacancy or
      `--json`. The JSON's `id` field is read off the returned path's
      parent directory name - a structural fact `vault/paths.py`'s own
      convention guarantees (vacancy directory name == vacancy id), not
      a derived business decision made in `cli.py`.
- [x] 12.5 Run 12.1-12.3 green against the implementation. (`pytest
      tests/test_cli.py -k new_command` → 3 passed)

## 13. cli.py: `reindex` command — tests, then implementation

- [x] 13.1 Write `tests/test_cli.py`: `vacancy-radar reindex` against a
      vault whose index needs no changes exits 0 and reports zero
      added/changed/deleted.
- [x] 13.2 Write `tests/test_cli.py`: `vacancy-radar reindex --force`
      exits 0 and reports every row re-embedded.
- [x] 13.3 Write `tests/test_cli.py`: `reindex --json` emits valid
      JSON matching `IndexReport`'s fields.
- [x] 13.4 Implemented `vacancy-radar reindex [--force] [--json]` in
      `cli.py` over `core.reindex`, rendering via `dataclasses.asdict`
      (mirroring `search`'s own hit-rendering pattern) or a plain
      summary line.
- [x] 13.5 Run 13.1-13.3 green against the implementation. (`pytest
      tests/test_cli.py -k reindex_command` → 3 passed)

## 14. Cross-cutting CLI and failure-atomicity tests

- [x] 14.1 Write `tests/test_cli.py`: for `note`, `status set`, `add`,
      and `new`, a situation forcing a typed `core.py` error (nonexistent
      vacancy id for the first three; an invalid `source_url` for `new`,
      exercising the section 8 fix) exits non-zero and creates no file
      (parametrized over all four commands, comparing the vault's full
      file set before/after).
- [x] 14.2 Write `tests/test_cli.py`: every write command's `--json`
      success case (already covered per-command in sections 9-13) plus
      a parametrized typed-error-with-`--json` case for `note`, `status
      set`, and `add` confirming stdout is empty on error (`_fail` never
      reaches `_print_json` — matches `cli-read`'s existing convention:
      errors go to stderr, not stdout, `--json` or not).
- [x] 14.3 Write `tests/test_core.py`: a write interrupted partway
      (monkeypatched `os.replace` failure, per section 3) leaves the
      vault's file set exactly as it was before the call — run this once
      each for `append_note`, `add_document`, and `set_status`.
- [x] 14.4 Write `tests/test_core.py`: running the full sequence
      `create_vacancy` -> `append_note` -> `set_status` ->
      `add_document` against one hand-built vault never removes any file
      that existed before the sequence started (`set(files before) <=
      set(files after)`).
- [x] 14.5 Run 14.1-14.4 green (already passed given sections 3-13's
      implementations; this section is a consolidated cross-check, not
      new command logic). Full suite: `pytest tests/ -q` → 418 passed;
      `ruff check`/`ruff format --check` clean across `src/` and
      `tests/`.

## 15. Docs

- [x] 15.1 Added a README "Writing" subsection (under "Usage")
      documenting `note`, `status set`, `add`, `new`, and `reindex`,
      each with a working example invocation verified against a copy of
      the fixture vault: notes derived filenames, `add --external-id`
      idempotency, and `--json` following the same stable-contract
      convention as the read commands. Fixed the read section's
      `openspec/changes/cli-read/...` path in passing to its actual
      archived location (`openspec/changes/archive/2026-08-06-cli-read/
      design.md`) - noticed while editing the adjacent paragraph, not a
      change this stage's scope required, but a one-line drive-by fix
      rather than leaving a broken link untouched next to new text.
- [x] 15.2 No `CHANGELOG.md` exists in this repo yet (checked before
      writing per the `[Unreleased]`-only-valid-once-a-tag-exists
      convention) - creating one from scratch is a bigger decision than
      this stage warrants, so the eager-reindex/no-delete-path note
      lives in the README's new "Writing" section instead (see 15.1),
      not a new CHANGELOG file.
