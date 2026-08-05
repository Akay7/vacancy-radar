## 1. Fixture generator: broken mode, marker, non-markdown doc, scale override

- [x] 1.1 Write `tests/fixtures/test_generate.py`: `--broken` mode
      output contains every file the non-broken run produces,
      unchanged
- [x] 1.2 Write `tests/fixtures/test_generate.py`: `--broken` mode
      additionally writes a `vacancy.md` with unparseable YAML, a
      `vacancy.md` with an unknown status, an unreadable file, two
      `vacancy.md` files sharing an id, and a `documents/` directory
      with no `vacancy.md`
- [x] 1.3 Write `tests/fixtures/test_generate.py`: the generated vault
      has a `.vacancy-radar/` marker directory at its root
- [x] 1.4 Write `tests/fixtures/test_generate.py`: at least one
      `takehome`-kind document is written as a non-markdown file, not
      `.md`/frontmatter
- [x] 1.5 Write `tests/fixtures/test_generate.py`: `generate_vault`
      called with company-count-range overrides produces a
      correspondingly larger vault in a temp directory, and does not
      touch `tests/fixtures/vault/`
- [x] 1.6 Run tests, confirm they fail (behavior doesn't exist yet)
- [x] 1.7 Implement the `.vacancy-radar/` marker directory and the
      non-markdown `takehome` document in `_write_vault`
- [x] 1.8 Implement `generate_vault`'s optional
      `min_companies`/`max_companies` override parameters (defaulting
      to the existing module constants)
- [x] 1.9 Implement `--broken` mode: a separate write path that adds
      the malformed-YAML, unknown-status, unreadable-file, duplicate-id,
      and orphan-directory fixtures without touching the healthy tree's
      existing files
- [x] 1.10 Add a `--broken` flag to `generate.py`'s CLI (`argparse`)
- [x] 1.11 Re-run 1.1–1.5 and confirm they pass
- [x] 1.12 Regenerate `tests/fixtures/vault/` with the documented seed
      (non-broken mode) and diff against the currently committed tree:
      confirm only the marker directory and the one non-markdown
      take-home file are new, every other file is byte-identical;
      commit the regenerated tree

## 2. vault/paths.py and containment: tests, then implementation

- [x] 2.1 Write `tests/vault/test_paths.py`: the company-markdown path
      helper matches `_company.md`'s actual location in the fixture
      vault for a known company slug
- [x] 2.2 Write `tests/vault/test_paths.py`: the vacancy-markdown and
      documents-directory helpers match `vacancy.md`'s and
      `documents/`'s actual locations in the fixture vault for a known
      vacancy
- [x] 2.3 Write `tests/vault/test_paths.py`: `is_within` rejects a path
      escaping the vault root via `..`
- [x] 2.4 Write `tests/vault/test_paths.py`: `is_within` rejects a
      symlink inside the vault whose target resolves outside the vault
      root
- [x] 2.5 Write `tests/vault/test_paths.py`: `is_within` accepts an
      ordinary in-vault path with no symlinks or `..` segments
- [x] 2.6 Write `tests/vault/test_paths.py`: a symlink loop (a
      directory symlinked back to one of its own ancestors) terminates
      traversal instead of recursing without bound
- [x] 2.7 Run tests, confirm they fail (module doesn't exist yet)
- [x] 2.8 Implement `src/vacancy_radar/vault/__init__.py` and
      `src/vacancy_radar/vault/paths.py`: layout constants, path
      helpers, `is_within` (resolve both paths, `is_relative_to`), and
      a directory-walk helper with a visited-real-paths guard against
      symlink loops
- [x] 2.9 Re-run 2.1–2.6 and confirm they pass

## 3. vault/hashing.py: tests, then implementation

- [x] 3.1 Write `tests/vault/test_hashing.py`: `content_hash` is
      unchanged when a file's mtime is touched but content is not
- [x] 3.2 Write `tests/vault/test_hashing.py`: `content_hash` changes
      when a single byte in the file changes
- [x] 3.3 Write `tests/vault/test_hashing.py`: two files with identical
      content hash identically
- [x] 3.4 Run tests, confirm they fail (module doesn't exist yet)
- [x] 3.5 Implement `src/vacancy_radar/vault/hashing.py`: `content_hash`
      (sha256 over file bytes, read in chunks, no mtime/size/inode
      access)
- [x] 3.6 Re-run 3.1–3.3 and confirm they pass

## 4. config.py: tests, then implementation

- [x] 4.1 Write `tests/test_config.py`: an explicit path argument
      overrides `VAULT_PATH`
- [x] 4.2 Write `tests/test_config.py`: `VAULT_PATH` is used when no
      argument is given
- [x] 4.3 Write `tests/test_config.py`: neither present raises
      `VaultNotConfiguredError`
- [x] 4.4 Write `tests/test_config.py`: a path that exists but has no
      `.vacancy-radar/` marker raises `VaultNotFoundError` naming what
      was expected
- [x] 4.5 Write `tests/test_config.py`: a nonexistent path raises
      `VaultNotFoundError`
- [x] 4.6 Write `tests/test_config.py`: a path pointing at a file, not
      a directory, raises `VaultNotFoundError`
- [x] 4.7 Write `tests/test_config.py`: the resolved path is absolute
      even when the input was relative
- [x] 4.8 Run tests, confirm they fail (module doesn't exist yet)
- [x] 4.9 Implement `src/vacancy_radar/config.py`: `VaultNotConfiguredError`,
      `VaultNotFoundError`, `resolve_vault_path(explicit: Path | str |
      None = None) -> Path` — precedence, absolute resolution,
      existence/directory/marker checks; document the MCP-roots seam
      in a docstring
- [x] 4.10 Re-run 4.1–4.7 and confirm they pass

## 5. vault/reader.py — traversal and counts: tests, then implementation

- [x] 5.1 Write `tests/vault/test_reader.py`: reading the fixture vault
      yields vacancy/document/company counts matching an independent
      walk of the fixture tree
- [x] 5.2 Write `tests/vault/test_reader.py`: a vacancy's snapshot key
      is its frontmatter `id`, not its directory name
- [x] 5.3 Write `tests/vault/test_reader.py`: documents are attributed
      to the vacancy whose `documents/` directory contains them
- [x] 5.4 Write `tests/vault/test_reader.py`: a company directory with
      `_company.md` and no vacancies parses, and `vacancies_for` its
      slug returns an empty list
- [x] 5.5 Write `tests/vault/test_reader.py`: a non-markdown file in a
      `documents/` directory is registered as a `Document` by path,
      with no frontmatter-parse warning
- [x] 5.6 Write `tests/vault/test_reader.py`: dotfiles, `.git/`,
      `.index/`, and the `.vacancy-radar/` marker directory are skipped
      entirely (no snapshot entries, no warnings)
- [x] 5.7 Run tests, confirm they fail (module doesn't exist yet)
- [x] 5.8 Implement `src/vacancy_radar/vault/reader.py`: directory walk
      over the fixture-vault layout (using `vault/paths.py`), parsing
      `_company.md` into `Company`, `vacancy.md` into `Vacancy`,
      `documents/*.md` into `Document`, non-markdown `documents/*` into
      path-only `Document`s; skip rules for dotfiles/`.git`/`.index`/marker
- [x] 5.9 Re-run 5.1–5.6 and confirm they pass

## 6. vault/reader.py — resilience: tests, then implementation

- [x] 6.1 Write `tests/vault/test_reader.py`: (using `--broken`
      fixtures) unparseable YAML in `vacancy.md` produces a warning
      naming the file, excludes that vacancy, and every other vacancy
      still loads
- [x] 6.2 Write `tests/vault/test_reader.py`: an unknown `status`
      produces a warning and excludes that vacancy
- [x] 6.3 Write `tests/vault/test_reader.py`: an unreadable file
      produces a warning, not a crash — `read_vault` still returns
- [x] 6.4 Write `tests/vault/test_reader.py`: two `vacancy.md` files
      sharing an id produce one deterministic survivor in
      `snapshot.vacancies` and a warning naming both paths
- [x] 6.5 Write `tests/vault/test_reader.py`: a `documents/` directory
      with no `vacancy.md` produces an orphan warning naming the
      directory, and its documents are not attributed to any vacancy
- [x] 6.6 Write `tests/vault/test_reader.py`: a vacancy whose
      `company_slug` has no `_company.md` still loads, with a warning
      naming the missing company
- [x] 6.7 Run tests, confirm they fail
- [x] 6.8 Implement warning collection: `VaultWarning` (frozen model:
      kind, message, path(s)) and the per-failure-mode try/except
      branches in the traversal from section 5, with no `print()`/
      logging call anywhere in `src/`
- [x] 6.9 Re-run 6.1–6.6 and confirm they pass

## 7. vault/reader.py — hashing, change detection, VaultSnapshot immutability

- [x] 7.1 Write `tests/vault/test_reader.py`: reading the same
      unchanged vault twice produces identical `hashes` mappings
- [x] 7.2 Write `tests/vault/test_reader.py`: editing one file between
      two reads changes exactly that file's entry in the hash map
- [x] 7.3 Write `tests/vault/test_reader.py`: mutating an exposed
      `VaultSnapshot` collection (e.g. assigning into `.vacancies`)
      raises rather than silently succeeding
- [x] 7.4 Run tests, confirm they fail
- [x] 7.5 Implement `VaultSnapshot` as frozen (Pydantic `frozen=True`)
      with `MappingProxyType`-wrapped `vacancies`/`documents`/
      `companies`/`hashes`; wire `content_hash` (section 3) into the
      traversal, one call per file
- [x] 7.6 Re-run 7.1–7.3 and confirm they pass

## 8. vault/reader.py — derived accessors: tests, then implementation

- [x] 8.1 Write `tests/vault/test_reader.py`: `last_activity` returns
      the most recent document date when documents exist
- [x] 8.2 Write `tests/vault/test_reader.py`: `last_activity` falls
      back to `applied_date` when a vacancy has no documents
- [x] 8.3 Write `tests/vault/test_reader.py`: `last_activity` falls
      back to `found_date` for a `found`-status vacancy with no
      documents
- [x] 8.4 Write `tests/vault/test_reader.py`: `documents_for` returns
      documents in ascending date order
- [x] 8.5 Write `tests/vault/test_reader.py`: same-date documents keep
      a stable relative order across repeated calls
- [x] 8.6 Run tests, confirm they fail
- [x] 8.7 Implement `documents_for`, `vacancies_for`, `last_activity` on
      `VaultSnapshot`
- [x] 8.8 Re-run 8.1–8.5 and confirm they pass

## 9. Performance

- [x] 9.1 Write `tests/vault/test_reader.py` (marked slow if the
      project has such a marker convention, else plain): generating a
      ~700-vacancy vault via the scale override and calling
      `read_vault` on it completes within a few seconds
- [x] 9.2 Write `tests/vault/test_reader.py`: instrument
      `content_hash` call counts (e.g. monkeypatch) and confirm every
      file in the ~700-vacancy vault is hashed exactly once
- [x] 9.3 Run tests, confirm they fail if applicable, then pass once
      section 7's traversal/hashing wiring is in place (no separate
      implementation expected here beyond what sections 5–7 already
      built; this section only adds the scale test)

## 10. Verification

- [x] 10.1 `uv sync --all-groups && uv run pytest && uv run ruff check .`
       passes
- [x] 10.2 `uv run ruff format --check .` passes
- [x] 10.3 Confirm no `print()` calls exist anywhere under `src/`
- [x] 10.4 Confirm no `lancedb`/`fastembed` imports anywhere in the
       change
- [x] 10.5 Re-run the fixture generator (non-broken) with its
       documented seed and confirm `tests/fixtures/vault/` shows no
       diff (matches what was committed in section 1)
- [x] 10.6 Confirm no function added in this change writes, moves, or
       deletes a file under a vault path (read-only review of
       `config.py` and `vault/*.py`)
