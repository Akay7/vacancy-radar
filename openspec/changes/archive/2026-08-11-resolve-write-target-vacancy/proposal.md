## Why

`cli-write-commands` requires that `note`, `status set`, `edit`, and `add`
accept a vacancy argument resolving "via `core.resolve`'s full tier order:
exact vacancy id, exact company slug, exact company name, or unambiguous
fuzzy company name". They do not. `core.resolve` returns a `company_slug`
for every company-tier match — correctly, since `show` uses the same call to
decide whether to render a company dossier — and `cli.py`'s
`_resolve_vacancy_or_fail` treats any company-tier resolution as a failure:
`"'tiny corp' resolved to a company, not a vacancy"`, exit 1. So the
documented convenience has never worked for any write command, and nothing
in the test suite covers it.

The gap surfaced while implementing `edit-vacancy-fields`, whose `edit`
command inherits the same helper and the same shortfall.

## What Changes

- New `core.resolve_vacancy(query, vault=None) -> str`: the write commands'
  vacancy-argument resolution, in `core.py` rather than in the CLI. It runs
  `resolve`'s tiers and then narrows a company-tier match to that company's
  single vacancy, raising a typed error when the company has none or more
  than one.
- New `AmbiguousVacancyError`, naming the company and every candidate
  vacancy id, for a company that holds more than one vacancy.
- `cli.py`'s `_resolve_vacancy_or_fail` delegates to it, so `note`,
  `status set`, `edit`, and `add` all gain the behavior at once, and the
  CLI keeps no resolution rule of its own.
- `core.resolve` itself is unchanged: a company query still resolves to a
  company, which is what `show`, `get_company`, and `find_existing` need.

Non-goals: changing `resolve`'s tiers or return shape; teaching the MCP
write tools to accept a query in place of a `vacancy_id` (a model has
`resolve` and `find_existing` for that, and an LLM guessing which vacancy a
company name meant is exactly what the typed error prevents); resolving a
company to a vacancy for read commands, which already render a dossier.

## Capabilities

### New Capabilities
- `write-target-resolution`: `core.resolve_vacancy` — the tier order it
  inherits from `resolve`, the single-vacancy narrowing rule, and the typed
  errors for zero, several, and no match.

### Modified Capabilities
- `cli-write-commands`: the write commands' vacancy-argument requirement
  becomes precise about what a company-name argument does — resolve to that
  company's one vacancy, or fail naming the candidates — and gains scenarios
  that actually exercise it.

## Impact

- `src/vacancy_radar/core.py` — `resolve_vacancy`, `AmbiguousVacancyError`.
- `src/vacancy_radar/cli.py` — `_resolve_vacancy_or_fail` reduced to error
  rendering over the new core call.
- Tests under `tests/test_core.py` and `tests/test_cli.py`.
- No change to `resolve`, the MCP server, the index, or the vault layout.
- Behavioral change for users: a command that exited 1 on a company-name
  argument may now perform the write. That is the documented intent, and it
  still refuses whenever the company holds more than one vacancy.
