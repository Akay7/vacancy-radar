## 1. core.resolve_vacancy

- [x] 1.1 Add `AmbiguousVacancyError` to `core.py`, carrying the company slug and the candidate vacancy ids as attributes and naming every id in its message
- [x] 1.2 Implement `resolve_vacancy(query, vault=None) -> str`: one `read_vault` snapshot, `_resolve` for the tiers, then narrow — vacancy id returns directly, company candidates raise `AmbiguousEntityError`, a resolved company narrows to its single vacancy, zero vacancies or no match raise `EntityNotFoundError`, several raise `AmbiguousVacancyError`
- [x] 1.3 Confirm `resolve` itself is untouched and no existing caller of it changes
- [x] 1.4 Tests in `tests/test_core.py`: each tier resolves to a single id (exact id, exact slug, display name in mixed case, unambiguous fuzzy name)
- [x] 1.5 Tests: the id tier short-circuits the company tiers for an id that also fuzzy-matches a company name
- [x] 1.6 Tests: a two-vacancy company raises `AmbiguousVacancyError` naming both ids and exposing them as an attribute; an empty company and an unmatched query raise `EntityNotFoundError`; a two-company query raises `AmbiguousEntityError` carrying both candidates
- [x] 1.7 Test: `resolve` still returns a company (with `vacancy_id` `None`) for a one-vacancy company's name, and `resolve_vacancy` modifies no file in the vault

## 2. CLI write commands

- [x] 2.1 Reduce `cli.py`'s `_resolve_vacancy_or_fail` to a `try/except` over `core.resolve_vacancy`, rendering company candidates via `_render_candidates` and routing every other typed error through `_fail`
- [x] 2.2 Tests in `tests/test_cli.py`: `note`, `status set`, `edit`, and `add` each operate on the right vacancy when given a one-vacancy company's display name
- [x] 2.3 Tests: a two-vacancy company exits non-zero, names both ids, and writes nothing; an empty company exits non-zero and writes nothing
- [x] 2.4 Test: the existing two-company ambiguity case still exits non-zero printing both companies

## 3. Documentation and verification

- [x] 3.1 Update the README's Writing section, which already claims a vacancy argument may be a company name — make the single-vacancy narrowing and its failure modes explicit
- [x] 3.2 Add a CHANGELOG entry under `[Unreleased]` (Fixed)
- [x] 3.3 Run `uv run pytest`, `ruff check`, and `ruff format --check`; fix anything they flag
- [x] 3.4 Run `openspec validate resolve-write-target-vacancy`
- [x] 3.5 Note for archive order: this change's `cli-write-commands` delta already includes `edit` in both modified requirements, so it converges with the unarchived `edit-vacancy-fields` delta whichever archives second
