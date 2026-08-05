## 1. Setup

- [x] 1.1 Add `lancedb`, `fastembed`, `pypdf` as runtime dependencies in
      `pyproject.toml`; `uv sync --all-groups`
- [x] 1.2 Register an `embedding` pytest marker in `pyproject.toml`
      (`[tool.pytest.ini_options] markers = [...]`) for tests that load
      the real embedding model, so CI can cache its download across
      runs instead of per test

## 2. PDF test fixtures (programmatic, not committed)

- [x] 2.1 Write `tests/fixtures/pdfs.py`: `write_valid_pdf(path, text)`
      — a real, unencrypted, single-page PDF containing `text`, built
      via `pypdf.PdfWriter`
- [x] 2.2 Write `tests/fixtures/pdfs.py`: `write_malformed_pdf(path)` —
      a `.pdf`-named file whose bytes are not a valid PDF structure
- [x] 2.3 Write `tests/fixtures/pdfs.py`: `write_encrypted_pdf(path,
      text, password)` — a valid PDF encrypted via
      `PdfWriter.encrypt`
- [x] 2.4 Write `tests/fixtures/pdfs.py`: `write_scanned_pdf(path)` — a
      valid, unencrypted PDF with an embedded image and no text layer
- [x] 2.5 Write `tests/fixtures/test_pdfs.py`: each helper produces a
      file `pypdf.PdfReader` can open without raising (except the
      malformed case, which must raise when read), confirming the
      fixtures are shaped as intended before anything depends on them

## 3. vault/paths.py: sidecar_path_for — tests, then implementation

- [x] 3.1 Write `tests/vault/test_paths.py`: `sidecar_path_for` returns
      the source's full filename plus `.md` (e.g. `spec.pdf` ->
      `spec.pdf.md`)
- [x] 3.2 Write `tests/vault/test_paths.py`: `sidecar_path_for` for
      `notes.pdf` and `notes.docx` (same stem, different extension)
      returns two distinct, non-colliding paths
- [x] 3.3 Run tests, confirm they fail (function doesn't exist yet)
- [x] 3.4 Implement `sidecar_path_for` in `src/vacancy_radar/vault/paths.py`
- [x] 3.5 Re-run 3.1–3.2 and confirm they pass

## 4. vault/reader.py: sidecar recognition — tests, then implementation

- [x] 4.1 Write `tests/vault/test_reader.py`: a source with a
      well-formed matching sidecar registers as exactly one `Document`
      (the source's), with no warning for the sidecar
- [x] 4.2 Write `tests/vault/test_reader.py`: a sidecar's frontmatter
      shape (`extracted_from`, `source_hash`, `extractor`,
      `extracted_at`, `manually_corrected`) never reaches `Document`
      validation and never produces an `invalid_document` warning
- [x] 4.3 Write `tests/vault/test_reader.py`: a sidecar with no
      matching source produces an orphan-sidecar warning and is
      excluded from `documents`
- [x] 4.4 Write `tests/vault/test_reader.py`: a sidecar whose
      `extracted_from` disagrees with its own filename produces a
      mismatch warning and is excluded from `documents`
- [x] 4.5 Write `tests/vault/test_reader.py`: `notes.pdf` and
      `notes.docx` in one `documents/` directory, each with its own
      correctly-named sidecar, both register as independent
      `Document`s, with neither sidecar producing a warning
- [x] 4.6 Write `tests/vault/test_reader.py`: an ordinary `.md`
      `Document` (no `extracted_from` in its frontmatter) is parsed
      exactly as before — this change doesn't alter non-sidecar
      behavior
- [x] 4.7 Run tests, confirm they fail (sidecar recognition doesn't
      exist yet — sidecars currently produce spurious
      `invalid_document` warnings)
- [x] 4.8 Implement sidecar recognition in
      `src/vacancy_radar/vault/reader.py`'s `_read_document`: check for
      `extracted_from` in parsed frontmatter before attempting
      `Document(**metadata)`; branch to orphan/mismatch warnings or
      silent exclusion as appropriate
- [x] 4.9 Re-run 4.1–4.6 and confirm they pass; re-run the full stage 2
      test suite to confirm no regression

## 5. index/extract.py: eligibility and successful extraction — tests, then implementation

- [x] 5.1 Write `tests/index/test_extract.py`: a `.py` source gets no
      sidecar written and `extract_to_sidecar` returns `None`
- [x] 5.2 Write `tests/index/test_extract.py`: a `.zip` source gets no
      sidecar written and `extract_to_sidecar` returns `None`
- [x] 5.3 Write `tests/index/test_extract.py`: extracting a valid PDF
      (via `tests/fixtures/pdfs.write_valid_pdf`) writes a sidecar with
      non-empty text and frontmatter (`extracted_from`, `source_hash`,
      `extractor`, `extracted_at`, `manually_corrected: false`)
      matching the source
- [x] 5.4 Run tests, confirm they fail (module doesn't exist yet)
- [x] 5.5 Implement `src/vacancy_radar/index/extract.py`:
      `extract_to_sidecar(source_path) -> Path | None` — extension
      check (`.pdf` only), `pypdf` text extraction, sidecar frontmatter
      construction, write via `frontmatter.serialize`
- [x] 5.6 Re-run 5.1–5.3 and confirm they pass

## 6. index/extract.py: regeneration gating — tests, then implementation

- [x] 6.1 Write `tests/index/test_extract.py`: re-extracting with an
      unchanged `source_hash` does not rewrite the sidecar (byte-
      identical before and after)
- [x] 6.2 Write `tests/index/test_extract.py`: a changed source (new
      content, new hash) regenerates the sidecar with the new
      `source_hash`
- [x] 6.3 Write `tests/index/test_extract.py`: a sidecar with
      `manually_corrected: true` and a stale `source_hash` is not
      rewritten, and a stale-sidecar warning is reported naming it
- [x] 6.4 Run tests, confirm they fail
- [x] 6.5 Implement hash-gated regeneration and the
      `manually_corrected` guard in `extract_to_sidecar`
- [x] 6.6 Re-run 6.1–6.3 and confirm they pass

## 7. index/extract.py: failure modes — tests, then implementation

- [x] 7.1 Write `tests/index/test_extract.py`: an encrypted PDF (via
      `write_encrypted_pdf`) writes an empty-body sidecar plus a
      warning naming the source, and does not raise
- [x] 7.2 Write `tests/index/test_extract.py`: a malformed PDF (via
      `write_malformed_pdf`) writes an empty-body sidecar plus a
      warning, and does not raise
- [x] 7.3 Write `tests/index/test_extract.py`: a scanned PDF (via
      `write_scanned_pdf`, no text layer) writes an empty-body sidecar
      plus a warning
- [x] 7.4 Write `tests/index/test_extract.py`: a PDF whose extracted
      text is under 200 characters is treated as extraction-failed —
      empty sidecar, warning
- [x] 7.5 Write `tests/index/test_extract.py`: after hand-editing a
      scanned PDF's empty sidecar (body filled in, `manually_corrected:
      true` set), re-running `extract_to_sidecar` leaves it untouched
- [x] 7.6 Write `tests/index/test_extract.py`: calling
      `extract_to_sidecar` on the encrypted, malformed, and scanned
      PDFs with stdout/stderr captured produces no output on either
      stream
- [x] 7.7 Run tests, confirm they fail
- [x] 7.8 Implement the three failure branches (encrypted, malformed,
      under-200-chars) in `extract_to_sidecar`, each producing an
      empty-body sidecar and a returned/collected warning, never a
      raise and never a print
- [x] 7.9 Re-run 7.1–7.6 and confirm they pass

## 8. index/embed.py: lazy loading and dimensionality — tests, then implementation

- [x] 8.1 Write `tests/index/test_embed.py` (marked `embedding`):
      importing `vacancy_radar.index.embed` and
      `vacancy_radar.index.build` does not load a model (instrument the
      underlying model constructor to assert zero calls at import time)
- [x] 8.2 Write `tests/index/test_embed.py` (marked `embedding`): the
      first `embed_texts` call for a model name loads the model; a
      second call with the same name does not reload it
- [x] 8.3 Write `tests/index/test_embed.py` (marked `embedding`):
      returned vectors' length matches the default model's reported
      dimension
- [x] 8.4 Write `tests/index/test_embed.py` (marked `embedding`, may be
      skipped by default if it requires downloading a second model):
      calling `embed_texts` with two different model names returns
      vectors of each model's own dimension
- [x] 8.5 Run tests, confirm they fail (module doesn't exist yet)
- [x] 8.6 Implement `src/vacancy_radar/index/embed.py`: a private
      `dict[str, TextEmbedding]` cache, `DEFAULT_EMBEDDING_MODEL_NAME =
      "BAAI/bge-small-en-v1.5"`, `embed_texts(texts, model_name=...) ->
      list[list[float]]` (batched), `vector_dim(model_name=...) -> int`
- [x] 8.7 Re-run 8.1–8.4 and confirm they pass

## 9. index/schema.py: table shape — tests, then implementation

- [x] 9.1 Write `tests/index/test_schema.py`: the schema's column set
      matches exactly `doc_id, vacancy_id, company_slug, company, role,
      status, kind, title, path, date, found_date, applied_date,
      last_activity, tags, text, content_hash, vector`
- [x] 9.2 Write `tests/index/test_schema.py`: schema construction takes
      a `vector_dim` parameter and the resulting `vector` field has
      that exact fixed-size dimensionality
- [x] 9.3 Run tests, confirm they fail (module doesn't exist yet)
- [x] 9.4 Implement `src/vacancy_radar/index/schema.py`: the table
      schema (LanceDB pydantic model or explicit pyarrow schema),
      parameterized by `vector_dim`
- [x] 9.5 Re-run 9.1–9.2 and confirm they pass

## 10. index/store.py: lazy, path-keyed handle resolution — tests, then implementation

- [x] 10.1 Write `tests/index/test_store.py`: importing the module
      creates no handle (instrument handle creation)
- [x] 10.2 Write `tests/index/test_store.py`: two `get_index_handle`
      calls with the same vault path return the same handle object
- [x] 10.3 Write `tests/index/test_store.py`: `get_index_handle` calls
      with two different vault paths return distinct handles
- [x] 10.4 Write `tests/index/test_store.py`: the default index path
      resolved for a vault has a directory name already excluded from
      `read_vault` traversal (`vault.paths.is_skipped_name`)
- [x] 10.5 Run tests, confirm they fail (module doesn't exist yet)
- [x] 10.6 Implement `src/vacancy_radar/index/store.py`: `IndexHandle`,
      a module-level `dict[Path, IndexHandle]` cache keyed by resolved
      vault path, `get_index_handle(vault_path) -> IndexHandle`,
      default index path `{vault}/.index/`
- [x] 10.7 Re-run 10.1–10.4 and confirm they pass

## 11. index/build.py — building from empty: tests, then implementation

- [x] 11.1 Write `tests/index/test_build.py`: building from an empty
      index over the fixture vault's snapshot produces a row count
      equal to its document count plus its vacancy count
- [x] 11.2 Write `tests/index/test_build.py`: every row's `content_hash`
      matches the snapshot's hash for its `path`
- [x] 11.3 Write `tests/index/test_build.py`: a document row's
      denormalized `company_slug`, `company`, `role`, `status` match
      its parent vacancy
- [x] 11.4 Write `tests/index/test_build.py`: a source with a matching
      sidecar embeds the sidecar's body as `text`
- [x] 11.5 Write `tests/index/test_build.py`: a source with no sidecar
      indexes with `text` derived from its title/filename, not empty
- [x] 11.6 Run tests, confirm they fail (module doesn't exist yet)
- [x] 11.7 Implement `src/vacancy_radar/index/build.py`:
      `IndexReport` (added, changed, deleted, unchanged, skipped,
      elapsed, warnings) and `build_index(snapshot, index_path,
      force=False, extract_sidecars=False) -> IndexReport` — from-empty
      path: compose each row's text (sidecar body, else title/filename
      fallback), embed, write, create FTS index, `optimize()`
- [x] 11.8 Re-run 11.1–11.5 and confirm they pass

## 12. index/build.py — incrementality: tests, then implementation

- [x] 12.1 Write `tests/index/test_build.py`: building twice with no
      filesystem change reports `added == changed == deleted == 0`
- [x] 12.2 Write `tests/index/test_build.py`: editing one document's
      body re-embeds exactly that document (`changed == 1`; its row's
      `content_hash`/`vector` change; every other row's don't)
- [x] 12.3 Write `tests/index/test_build.py`: editing only a vacancy's
      frontmatter re-embeds the vacancy's own row, and updates its
      sibling documents' denormalized `status` column without changing
      their `content_hash`/`vector`
- [x] 12.4 Write `tests/index/test_build.py`: adding one document adds
      exactly one row (`added == 1`)
- [x] 12.5 Write `tests/index/test_build.py`: deleting one document's
      source file removes exactly its row (`deleted == 1`) on the next
      build, using a snapshot taken after the deletion
- [x] 12.6 Write `tests/index/test_build.py`: `force=True` re-embeds
      every row regardless of hash (`changed == total row count`,
      `unchanged == 0`)
- [x] 12.7 Run tests, confirm they fail
- [x] 12.8 Implement the diffing logic: compare snapshot hashes against
      stored `content_hash` per row; embed-and-write new/changed;
      column-only update for documents whose vacancy changed but whose
      own hash didn't; delete rows whose path is absent from the
      snapshot; `force` bypasses the hash comparison entirely
- [x] 12.9 Re-run 12.1–12.6 and confirm they pass

## 13. index/build.py — disposability: tests, then implementation

- [x] 13.1 Write `tests/index/test_build.py`: deleting the index
      directory entirely and rebuilding from the same snapshot
      reproduces the same row count and the same set of `doc_id`s
      recorded before deletion
- [x] 13.2 Run the test, confirm it fails only if disposability is
      actually broken (this should already pass once section 11's
      from-empty build path is correct — treat any failure here as a
      real defect, not a missing-implementation gap)
- [x] 13.3 Fix any divergence found (e.g. non-deterministic row
      ordering or id minting) so the scenario holds
- [x] 13.4 Confirm `.index/` is absent from `git status` after a build
      (already gitignored; verify no change to `.gitignore` is needed)

## 14. index/build.py — FTS: tests, then implementation

- [x] 14.1 Write `tests/index/test_build.py`: the table has a
      full-text index on `text` after the first build
- [x] 14.2 Write `tests/index/test_build.py`: a document added after
      the initial build is returned by an FTS query for a term unique
      to its text, once the second `build_index` call (which runs
      `optimize()`) completes
- [x] 14.3 Write `tests/index/test_build.py`: rebuilding three times
      with no vault changes leaves exactly one row matching a term
      known to match one document — no FTS duplication
- [x] 14.4 Run tests, confirm they fail
- [x] 14.5 Implement FTS index creation on first build and
      `optimize()` after every build (both full and incremental) in
      `build_index`
- [x] 14.6 Re-run 14.1–14.3 and confirm they pass

## 15. index/build.py — resilience: tests, then implementation

- [x] 15.1 Write `tests/index/test_build.py`: a snapshot with
      pre-existing warnings still builds successfully, and those
      warnings appear in the returned `IndexReport.warnings`
- [x] 15.2 Write `tests/index/test_build.py`: a document whose source
      file is deleted after the snapshot is taken but before
      `build_index` reads it does not crash the build; it's counted
      under `IndexReport.skipped` with a warning naming it
- [x] 15.3 Run tests, confirm they fail
- [x] 15.4 Implement warning carry-over from `snapshot.warnings` into
      `IndexReport.warnings`, and a try/except around each row's file
      read that skips-and-warns on a vanished file instead of raising
- [x] 15.5 Re-run 15.1–15.2 and confirm they pass

## 16. Performance

- [x] 16.1 Write `tests/index/test_build.py` (marked `embedding`,
      since it exercises real embedding at scale): building from empty
      over a ~700-vacancy generated vault (stage 2's scale override)
      completes within a few minutes
- [x] 16.2 Write `tests/index/test_build.py` (marked `embedding`): a
      second, no-change `build_index` call over that same large vault
      completes within seconds
- [x] 16.3 Run both, confirm they pass against the implementation from
      sections 11–12 (no separate implementation expected here)

## 17. Verification

- [x] 17.1 `uv sync --all-groups && uv run pytest && uv run ruff check .`
       passes
- [x] 17.2 `uv run ruff format --check .` passes
- [x] 17.3 Confirm no `print()` calls exist anywhere under `src/`
- [x] 17.4 Confirm no `torch`, `sentence-transformers`, or reranker
       dependency was introduced — only `lancedb`, `fastembed`, `pypdf`
       are new in `pyproject.toml`
- [x] 17.5 Confirm the only vault writes anywhere in this change are
       sidecar files, gated behind `extract_sidecars`/direct
       `extract_to_sidecar` calls — no function touches a source file
       or deletes anything in the vault
- [x] 17.6 Confirm `uv run pytest -m "not embedding"` passes without
       requiring network access (mock or stub the embedding model
       where the marker isn't applied), so contributors without a
       cached model can still run the fast suite
- [x] 17.7 Update `.github/workflows/ci.yml` to cache the `fastembed`
       model cache directory, keyed by the configured model name, so
       the model downloads once across CI runs rather than per test
