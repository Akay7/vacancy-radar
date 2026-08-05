## 1. Setup

- [x] 1.1 Add `ruamel.yaml` and `text-unidecode` as runtime dependencies
      in `pyproject.toml`; `uv sync --all-groups`

## 2. Frontmatter I/O: tests, then implementation

- [x] 2.1 Write `tests/test_frontmatter.py`: parsing a valid file then
      serializing it reproduces the original text byte for byte
      (key order, body whitespace)
- [x] 2.2 Write `tests/test_frontmatter.py`: text with no frontmatter
      delimiter raises `MissingFrontmatterError`
- [x] 2.3 Write `tests/test_frontmatter.py`: unparseable YAML raises
      `MalformedFrontmatterError` that identifies the file
- [x] 2.4 Write `tests/test_frontmatter.py`: a body line consisting of
      `---` is not treated as a delimiter, and the file still
      round-trips byte for byte
- [x] 2.5 Run tests, confirm they fail (module doesn't exist yet)
- [x] 2.6 Implement `src/vacancy_radar/frontmatter.py`:
      `MissingFrontmatterError`, `MalformedFrontmatterError`, `parse`,
      `serialize`, using `ruamel.yaml`'s round-trip mode (`YAML(typ="rt")`)
- [x] 2.7 Re-run 2.1–2.4 and confirm they pass

## 3. Vacancy identity (ids.py): tests, then implementation

- [x] 3.1 Write `tests/test_ids.py`: `slugify` produces readable ascii
      (never hex/percent escapes) for the placeholder inputs
      `"Ромашка"`, `"Widget & Sons"`, `"Acme Inc."`, `"Šaltinis Studija"`
- [x] 3.2 Write `tests/test_ids.py`: `new_vacancy_id` is deterministic
      for identical inputs and does not mutate the `existing_ids` set
      it's given
- [x] 3.3 Write `tests/test_ids.py`: id format is
      `{YYYY-MM-DD}-{company_slug}-{role_slug}`, and lexical sort of
      minted ids matches chronological sort of their `found_date`s
- [x] 3.4 Write `tests/test_ids.py`: identical `(found_date,
      company_slug, role, existing_ids)` inputs — standing in for the
      same file at two different paths — yield the identical id,
      since neither `new_vacancy_id` nor `Vacancy` construction takes
      a path argument
- [x] 3.5 Write `tests/test_ids.py`: a migration-shaped batch of
      several vacancies sharing `found_date` and `company_slug`, all
      `UNKNOWN_ROLE`, resolves to unique ids with sequential numeric
      suffixes (`-2`, `-3`, ...) when each minted id is added to
      `existing_ids` before the next call
- [x] 3.6 Write `tests/test_ids.py`: a role slug longer than
      `MAX_ROLE_SLUG_LENGTH` truncates deterministically (same input,
      same truncated output, repeatedly)
- [x] 3.7 Run tests, confirm they fail (module doesn't exist yet)
- [x] 3.8 Implement `src/vacancy_radar/ids.py`: `slugify` (via
      `text_unidecode.unidecode` + lowercase + collapse
      non-alphanumeric runs to hyphens + strip), `MAX_ROLE_SLUG_LENGTH`,
      `new_vacancy_id` (pure function, numeric-suffix collision
      resolution, no filesystem access)
- [x] 3.9 Re-run 3.1–3.6 and confirm they pass

## 4. Vault model — enums and sentinel: tests, then implementation

- [x] 4.1 Write `tests/test_models.py`: every one of the eight `Status`
      values parses; parsing is case-insensitive; output is canonical
      lowercase; an unrecognized value raises a validation error
      listing the permitted values
- [x] 4.2 Write `tests/test_models.py`: each `DocumentKind` member
      (`posting`, `email`, `note`, `takehome`) parses
- [x] 4.3 Run tests, confirm they fail (module doesn't exist yet)
- [x] 4.4 Implement `src/vacancy_radar/models.py`: `UNKNOWN_ROLE`
      sentinel, `Status` enum (8 values), `DocumentKind` enum
- [x] 4.5 Re-run 4.1–4.2 and confirm they pass

## 5. Vault model — Vacancy mandatory & conditional fields: tests, then implementation

- [x] 5.1 Write `tests/test_models.py`: omitting any one of `id`,
      `company`, `company_slug`, `role`, `source_url`, `status`, or
      `found_date` raises a validation error naming that field
- [x] 5.2 Write `tests/test_models.py`: `source_url` with a scheme
      other than `http`/`https` is rejected
- [x] 5.3 Write `tests/test_models.py`: a `Vacancy` with every optional
      field absent parses successfully
- [x] 5.4 Write `tests/test_models.py`: `status` other than `found`
      with no `applied_date` raises a validation error explaining the
      rule
- [x] 5.5 Write `tests/test_models.py`: `status` `found` with an
      `applied_date` present raises a validation error
- [x] 5.6 Write `tests/test_models.py`: `status` `found` with no
      `applied_date` parses successfully
- [x] 5.7 Run tests, confirm they fail
- [x] 5.8 Implement `Vacancy`'s mandatory fields, the `source_url`
      http/https validator, and the named model-level validator
      (`_check_applied_date_matches_status`, `@model_validator(mode="after")`)
      for the conditional `applied_date` rule
- [x] 5.9 Re-run 5.1–5.6 and confirm they pass

## 6. Vault model — date coherence & role: tests, then implementation

- [x] 6.1 Write `tests/test_models.py`: `applied_date` earlier than
      `found_date` is rejected
- [x] 6.2 Write `tests/test_models.py`: `found_date` in the future is
      rejected
- [x] 6.3 Write `tests/test_models.py`: `applied_date` equal to
      `found_date` is valid
- [x] 6.4 Write `tests/test_models.py`: date fields parse equivalently
      from ISO strings and from `date` objects
- [x] 6.5 Write `tests/test_models.py`: empty or whitespace-only `role`
      is rejected
- [x] 6.6 Write `tests/test_models.py`: `role` `"unknown"` parses
      successfully
- [x] 6.7 Write `tests/test_models.py`: `role_is_placeholder` is `True`
      for `"unknown"`, `"Unknown"`, `" UNKNOWN "`
- [x] 6.8 Write `tests/test_models.py`: `role_is_placeholder` is
      `False` for other non-empty values, including `"developer"`
- [x] 6.9 Run tests, confirm they fail
- [x] 6.10 Implement the date-coherence model validator, the `role`
      non-empty validator, and the `role_is_placeholder`
      `@computed_field`
- [x] 6.11 Re-run 6.1–6.8 and confirm they pass

## 7. Vault model — preservation, ordering, Document, Company: tests, then implementation

- [x] 7.1 Write `tests/test_models.py`: `stage_note` round-trips
      exactly, including newlines, emoji, and mixed Cyrillic/Latin text
- [x] 7.2 Write `tests/test_models.py`: `company` (non-ascii placeholder,
      e.g. `"Незабудка Банк"`) and `company_slug` (ascii) both
      round-trip intact and independently
- [x] 7.3 Write `tests/test_models.py`: a list of vacancies with
      distinct `applied_date` values sorts descending by `applied_date`
- [x] 7.4 Write `tests/test_models.py`: `found`-status vacancies
      (no `applied_date`) sort as if `found_date` were their sort key
- [x] 7.5 Write `tests/test_models.py`: vacancies with equal sort dates
      keep their relative input order (stable sort)
- [x] 7.6 Write `tests/test_models.py`: a `Document` constructs with
      `id`, `vacancy_id`, `kind`, `title`, `date`, and optional
      `external_id`
- [x] 7.7 Write `tests/test_models.py`: a `Company` constructs with
      `slug`, `name`, `domains`, `recruiters`, `notes`
- [x] 7.8 Run tests, confirm they fail
- [x] 7.9 Implement the remaining `Vacancy` optional fields
      (`stage_note`, `salary_note`, `recruiter`, `external_id`,
      `tags`), the vacancy ordering key/helper, `Document`, and
      `Company`
- [x] 7.10 Re-run 7.1–7.7 and confirm they pass

## 8. Fixture generator: tests, then implementation

- [x] 8.1 Write `tests/fixtures/test_generate.py`: running the
      generator twice with the same seed (into two separate output
      locations) produces byte-identical trees, file for file
- [x] 8.2 Write `tests/fixtures/test_generate.py`: every `Status`
      value appears on at least one generated vacancy
- [x] 8.3 Write `tests/fixtures/test_generate.py`: at least two
      companies each have vacancies whose `found_date`s fall in
      different calendar years
- [x] 8.4 Write `tests/fixtures/test_generate.py`: at least three
      generated vacancies have `role_is_placeholder` `True` and
      `needs_review` in `tags`
- [x] 8.5 Write `tests/fixtures/test_generate.py`: at least one
      generated company's `name` is non-ascii
- [x] 8.6 Write `tests/fixtures/test_generate.py`: generated companies,
      recruiters, and email bodies are drawn only from the generator's
      own synthetic data pools (no real-entity leakage by construction)
- [x] 8.7 Run tests, confirm they fail (generator doesn't exist yet)
- [x] 8.8 Implement `tests/fixtures/generate.py`: seeded synthetic data
      pools (12–20 companies incl. non-ascii names, plausible recruiter
      names, email bodies), distribution guarantees for the scenarios
      above, ids minted via `new_vacancy_id`, files written via
      `frontmatter.serialize`
- [x] 8.9 Re-run 8.1–8.6 and confirm they pass
- [x] 8.10 Run the generator with a fixed, documented seed against
      `tests/fixtures/vault/` and commit the output

## 9. Verification

- [x] 9.1 `uv sync --all-groups && uv run pytest && uv run ruff check .`
      passes
- [x] 9.2 `uv run ruff format --check .` passes
- [x] 9.3 Confirm no `print()` calls exist anywhere under `src/`
- [x] 9.4 Re-run the fixture generator with its documented seed and
      confirm `tests/fixtures/vault/` shows no diff (committed output
      matches regeneration)
