## 1. Survey and fixture scaffolding

- [x] 1.1 Confirm no hidden `_search` command exists (`git grep -n
      '"_search"' src/`) — per design.md's Context, only `_eval` exists
      to remove/replace. Note the result in the PR/commit description
      if it disagrees with this survey.
- [x] 1.2 Create `tests/test_core.py` importing `FIXTURE_VAULT = Path(...)
      / "tests" / "fixtures" / "vault"`, following the constant-per-file
      convention already used in `tests/vault/test_reader.py` and
      `tests/index/test_search.py` — no shared pytest fixture.
- [x] 1.3 Add small ad hoc vault-building helpers local to
      `tests/test_core.py` (mirroring `tests/vault/test_reader.py`'s
      `_init_vault`/`_simple_vacancy`/`_write_vacancy` pattern) for the
      handful of scenarios the committed fixture vault doesn't already
      shape: an id/company-slug collision, a company directory with
      vacancies but no `_company.md`, and a vacancy with zero
      documents. Do not modify `tests/fixtures/generate.py` or the
      committed `tests/fixtures/vault/` tree for these — build them at
      `tmp_path` per test, same as the existing `missing_company`
      resilience test does.

## 2. core.py: Resolution model and resolve() — tests, then implementation

- [x] 2.1 Write `tests/test_core.py`: an exact vacancy id resolves to
      that vacancy and `candidates` is empty.
- [x] 2.2 Write `tests/test_core.py`: an exact `company_slug` resolves
      to that company.
- [x] 2.3 Write `tests/test_core.py`: a company display name differing
      only in case resolves to that company.
- [x] 2.4 Write `tests/test_core.py`: `"Acme"` resolves to `acme-corp`
      against the fixture vault's `"Acme Corp"` when unambiguous.
- [x] 2.5 Write `tests/test_core.py`: a query matching two companies
      (construct two companies whose names both fuzzy/case-insensitive
      match one query, at `tmp_path`) returns both as `candidates` and
      resolves to neither.
- [x] 2.6 Write `tests/test_core.py`: a query matching nothing returns
      an empty `Resolution` (no resolved entity, no candidates), and no
      exception is raised.
- [x] 2.7 Write `tests/test_core.py`, using the 1.3 id/slug-collision
      fixture: a query equal to both a vacancy id and (closely)
      matching a different company's name resolves to the vacancy,
      proving exact-id beats company tiers.
- [x] 2.8 Implement `Resolution` (resolved entity — vacancy id, company
      slug, or neither — plus `candidates`) and `resolve(query, vault=
      None)` in `src/vacancy_radar/core.py`: exact id, then exact
      `company_slug`, then unique case-insensitive company-name match,
      then `difflib.get_close_matches` over company display names —
      each tier stopping only on an unambiguous single match, per
      design.md decision 3.
- [x] 2.9 Run 2.1-2.7 green against the implementation.

## 3. core.py: list_vacancies() — tests, then implementation

- [x] 3.1 Write `tests/test_core.py`: no filters returns every vacancy
      in the fixture vault up to the default limit.
- [x] 3.2 Write `tests/test_core.py`: `status` given two values returns
      their union.
- [x] 3.3 Write `tests/test_core.py`: `company` restricts to that
      company's vacancies only.
- [x] 3.4 Write `tests/test_core.py`: `since` excludes vacancies applied
      earlier than it.
- [x] 3.5 Write `tests/test_core.py`: `needs_review=True` returns
      exactly the vacancies tagged `needs_review` in the fixture vault.
- [x] 3.6 Write `tests/test_core.py`, using a `tmp_path` vault built so
      one vacancy has an old `applied_date` but a recent document, and
      another has no documents since applying: `stale_days` excludes
      the first and includes the second.
- [x] 3.7 Write `tests/test_core.py`: `sort='activity'` orders results
      by `last_activity` descending, and two vacancies with an equal
      `last_activity` (construct at `tmp_path`) appear in the same
      relative order across repeated calls.
- [x] 3.8 Write `tests/test_core.py`: no `VacancySummary` in any result
      carries a document body or a document path.
- [x] 3.9 Implement `VacancySummary` and `list_vacancies(status=None,
      company=None, since=None, stale_days=None, needs_review=False,
      limit=50, sort='activity', vault=None)` in `core.py`, composing
      `read_vault` and `VaultSnapshot.last_activity`/`vacancies_for` —
      no document text touched.
- [x] 3.10 Run 3.1-3.8 green against the implementation.

## 4. core.py: get_company() — tests, then implementation

- [x] 4.1 Write `tests/test_core.py`: a fixture-vault company with
      several vacancies returns all of them, including its oldest and
      newest.
- [x] 4.2 Write `tests/test_core.py`: `recruiters` and `domains` on the
      returned dossier match that company's `_company.md`.
- [x] 4.3 Write `tests/test_core.py`, using the 1.3 no-`_company.md`
      fixture: `get_company` still returns that company's vacancies,
      with a warning naming the missing file, and does not raise.
- [x] 4.4 Write `tests/test_core.py`: for a company with several
      vacancies each with documents, the dossier reports per-vacancy
      document counts and no document body appears anywhere in it.
- [x] 4.5 Implement `CompanyDossier` and `get_company(name, vault=
      None)` in `core.py`: resolves `name` via `resolve`, gathers
      `VaultSnapshot.vacancies_for`, reads `_company.md` fields when
      present, counts documents per vacancy without reading their text.
- [x] 4.6 Run 4.1-4.4 green against the implementation.

## 5. core.py: get_vacancy() — tests, then implementation

- [x] 5.1 Write `tests/test_core.py`: documents on a fixture-vault
      vacancy with several documents of differing dates are ordered
      date-ascending, each with title and path.
- [x] 5.2 Write `tests/test_core.py`: `stage_note` on the returned
      detail equals the vacancy's stored `stage_note` exactly.
- [x] 5.3 Write `tests/test_core.py`, using the 1.3 zero-document
      fixture: `get_vacancy` succeeds with an empty documents list.
- [x] 5.4 Write `tests/test_core.py`: no document body appears in a
      `VacancyDetail` for a vacancy with documents.
- [x] 5.5 Implement `VacancyDetail` and `get_vacancy(id_or_query, vault=
      None)` in `core.py`: resolves via `resolve`, returns frontmatter
      fields, `stage_note` verbatim, and `VaultSnapshot.documents_for`
      as path/title/kind/date rows.
- [x] 5.6 Run 5.1-5.4 green against the implementation.

## 6. core.py: read_document() — tests, then implementation

- [x] 6.1 Write `tests/test_core.py`: a valid path inside the fixture
      vault returns that file's full text.
- [x] 6.2 Write `tests/test_core.py`: a path resolving outside the
      vault raises a typed error.
- [x] 6.3 Write `tests/test_core.py`: a path using `..` segments to
      escape the vault raises the same typed error.
- [x] 6.4 Write `tests/test_core.py`: a nonexistent path inside the
      vault raises a typed error naming that path.
- [x] 6.5 Implement `DocumentContent`, `DocumentNotFoundError`,
      `PathOutsideVaultError` (or one shared typed-error hierarchy) and
      `read_document(path, vault=None)` in `core.py`, reusing
      `vault.paths.is_within` for containment — never a bespoke check.
- [x] 6.6 Run 6.1-6.4 green against the implementation.

## 7. core.py: index-freshness check — tests, then implementation

- [x] 7.1 Write `tests/test_core.py`, using a `tmp_path` vault: build
      the index, then add a new document to the vault without
      rebuilding; the freshness check reports a warning naming the
      count of vault documents missing from the index.
- [x] 7.2 Write `tests/test_core.py`: the same stale setup does not
      raise — the check returns a warning (or `None` when fresh),
      never an exception.
- [x] 7.3 Implement the freshness check (e.g. `_index_freshness(vault,
      index) -> IndexFreshnessWarning | None`, non-underscored if
      shared across modules per design.md decision 4) in `core.py`,
      comparing a fresh `read_vault` hash set against the index
      table's `doc_id`/`content_hash` columns.
- [x] 7.4 Run 7.1-7.2 green against the implementation.

## 8. core.py: search() wrapper — tests, then implementation

- [x] 8.1 Write `tests/test_core.py`: `core.search` against a built,
      fresh index returns the same hits `index.search.search` would
      for identical arguments.
- [x] 8.2 Write `tests/test_core.py`, using 7.1's stale setup: `core.
      search` returns hits plus a staleness warning naming the missing
      count.
- [x] 8.3 Write `tests/test_core.py`: the stale case does not raise.
- [x] 8.4 Implement `core.search(query, *, vault=None, mode=None,
      company=None, status=None, limit=None, vector_weight=None, ...)`
      in `core.py`: resolves the vault/index handle, delegates to
      `index.search.search` unchanged, attaches the section 7 freshness
      warning to the result.
- [x] 8.5 Run 8.1-8.3 green against the implementation.

## 9. cli.py: `list` command — tests, then implementation

- [x] 9.1 Write `tests/test_cli.py` (`CliRunner`): `vacancy-radar
      list` against `VAULT_PATH=<fixture vault>` with no options exits
      0 and prints a row per vacancy.
- [x] 9.2 Write `tests/test_cli.py`: `--status`, `--company`, `--since`,
      `--needs-review`, `--stale-days` each restrict output the same
      way their `core.list_vacancies` counterpart does (spot-check one
      filter combination, not the full matrix already covered by
      section 3's core tests).
- [x] 9.3 Write `tests/test_cli.py`: `list --json` exits 0 and stdout
      is a single valid JSON array containing no Rich table characters
      or ANSI codes.
- [x] 9.4 Write `tests/test_cli.py`: `list` run with `VAULT_PATH` unset
      and no explicit path exits non-zero and names `VAULT_PATH`.
- [x] 9.5 Implement `vacancy-radar list` in `cli.py`: Typer options
      matching `list_vacancies`'s parameters, a Rich table renderer, a
      `--json` branch that serializes `VacancySummary` rows directly —
      no filtering/sorting logic in the command body (design.md
      decision 1).
- [x] 9.6 Run 9.1-9.4 green against the implementation.

## 10. cli.py: `show` command — tests, then implementation

- [x] 10.1 Write `tests/test_cli.py`: `show <id>` on an existing
      vacancy id exits 0 and renders that vacancy's detail.
- [x] 10.2 Write `tests/test_cli.py`: `show <name>` on a query that
      resolves to exactly one company exits 0 and renders that
      company's dossier.
- [x] 10.3 Write `tests/test_cli.py`: `show <query>` on an ambiguous
      query exits non-zero and lists the candidates.
- [x] 10.4 Write `tests/test_cli.py`: `show --json` on a vacancy and on
      a company each emit valid JSON tagged with which kind resolved.
- [x] 10.5 Implement `vacancy-radar show` in `cli.py`: calls `core.
      resolve`, branches only on which field of the `Resolution` came
      back (not on re-deriving vacancy-vs-company logic), calls
      `get_vacancy`/`get_company` accordingly, renders via Rich or
      `--json`.
- [x] 10.6 Run 10.1-10.4 green against the implementation.

## 11. cli.py: `search` command — tests, then implementation

- [x] 11.1 Write `tests/test_cli.py`: `search <query>` against the
      fixture vault's built index exits 0 and prints hits.
- [x] 11.2 Write `tests/test_cli.py`: `--mode`, `--company`, `--status`,
      `--limit` are each forwarded (spot-check one each).
- [x] 11.3 Write `tests/test_cli.py`: `search <query> --scores` prints
      each hit's keyword rank, semantic rank, and fused score.
- [x] 11.4 Write `tests/test_cli.py`: `search --json` emits valid JSON
      with no Rich formatting.
- [x] 11.5 Implement `vacancy-radar search` in `cli.py` over `core.
      search`, rendering hits as a Rich table (with an optional scores
      column under `--scores`) or `--json`.
- [x] 11.6 Run 11.1-11.4 green against the implementation.

## 12. cli.py: `doctor` command — tests, then implementation

- [x] 12.1 Write `tests/test_cli.py`: `doctor` against the healthy
      fixture vault with a freshly built index exits 0.
- [x] 12.2 Write `tests/test_cli.py`, using `generate_vault` +
      `write_broken_fixtures` at `tmp_path` (mirroring `tests/vault/
      test_reader.py`'s `_broken_vault` helper): `doctor` exits
      non-zero and lists each of the stage 2 warnings (malformed
      frontmatter, unreadable file, duplicate vacancy id, orphan
      documents directory).
- [x] 12.3 Write `tests/test_cli.py`, using section 7's stale-index
      setup: `doctor` names the staleness, names the command that
      rebuilds the index, and this alone does not make the exit code
      non-zero.
- [x] 12.4 Write `tests/test_cli.py`: `doctor` run with `VAULT_PATH`
      unset exits non-zero and names `VAULT_PATH`.
- [x] 12.5 Implement `vacancy-radar doctor` in `cli.py`: vault path,
      marker presence, index presence/freshness (section 7's check),
      embedding-model availability, and every `VaultWarning` from
      `read_vault`, rendered as Rich or `--json`.
- [x] 12.6 Run 12.1-12.4 green against the implementation.

## 13. cli.py: public `eval` command, removing `_eval`

- [x] 13.1 Write `tests/test_cli.py`: `vacancy-radar --help` lists
      `eval` and does not list `_eval`.
- [x] 13.2 Write `tests/test_cli.py`: `vacancy-radar _eval` is now an
      unknown command (non-zero exit).
- [x] 13.3 Write `tests/test_cli.py` (marked `embedding`, replacing the
      existing `test_eval_command_runs_the_full_sweep_and_prints_a_
      markdown_report`): `vacancy-radar eval` exits 0 and prints the
      same markdown report shape.
- [x] 13.4 Implement `vacancy-radar eval` in `cli.py`: same body as the
      former `eval_command`/`_eval`, registered as a public, visible
      command named `eval`; delete the old `_eval` command and its
      `hidden=True` registration.
- [x] 13.5 Delete or update the now-obsolete
      `test_eval_command_is_absent_from_help_output` and old `_eval`
      tests in `tests/test_cli.py` to match 13.1-13.3.
- [x] 13.6 Run 13.1-13.3 green against the implementation.

## 14. Cross-cutting CLI contract tests

- [x] 14.1 Write `tests/test_cli.py`: for `list`, `show`, `search`, and
      `doctor`, a situation forcing a typed `core.py` error (e.g.
      `show` on a nonexistent id with `--json` off) exits non-zero with
      a descriptive message.
- [x] 14.2 Write `tests/test_cli.py`: every `--json`-supporting command
      run with `--json` produces stdout that `json.loads` parses
      without error.
- [x] 14.3 Run 14.1-14.2 green (should already pass given sections
      9-13's implementations; this section is a consolidated
      cross-check, not new command logic).

## 15. Docs

- [x] 15.1 Update README.md's "Retrieval evaluation" section: replace
      `uv run vacancy-radar _eval` / "private; the public `eval`
      command lands at stage 6" with the now-public `uv run
      vacancy-radar eval`.
- [x] 15.2 Add a short README "Usage" addition (or new section)
      documenting `list`, `show`, `search`, and `doctor`, each with one
      example invocation and a note that `--json` is a stable,
      documented contract per design.md decision 5.
