# cli-read-commands Specification

## Purpose
TBD - created by openspec-sync-specs during change retrieval. Update Purpose after archive.

## Requirements

### Requirement: vacancy-radar list renders filtered vacancies as a table or JSON
`vacancy-radar list` SHALL accept `list_vacancies`'s filters as
options, calling `core.list_vacancies` and rendering the result as a
Rich table by default or as JSON with `--json`.

#### Scenario: list with no options renders every vacancy as a table
- **WHEN** `vacancy-radar list` is run against a healthy fixture vault
  with no options
- **THEN** it exits 0 and prints a table row for each vacancy

#### Scenario: list --json emits a JSON array of vacancy summaries
- **WHEN** `vacancy-radar list --json` is run
- **THEN** it exits 0 and stdout is a single valid JSON array, with no
  Rich formatting

### Requirement: vacancy-radar show auto-detects a vacancy or company via resolve
`vacancy-radar show <query>` SHALL call `core.resolve`, then render a
`VacancyDetail` or `CompanyDossier` depending on what resolved,
without the caller specifying which kind of entity `<query>` names.

#### Scenario: show on a vacancy id renders vacancy detail
- **WHEN** `vacancy-radar show <id>` is run with an existing vacancy's
  id
- **THEN** it exits 0 and renders that vacancy's detail

#### Scenario: show on a company name renders a company dossier
- **WHEN** `vacancy-radar show <name>` is run with a query that
  resolves to exactly one company
- **THEN** it exits 0 and renders that company's dossier

### Requirement: vacancy-radar search exposes mode, filters, limit, and score display
`vacancy-radar search` SHALL accept `--mode`, `--company`, `--status`,
and `--limit` options forwarded to `core.search`, and, given
`--scores`, print each hit's `keyword_rank`, `semantic_rank`, and
fused `score`.

#### Scenario: search --scores prints per-mode ranks alongside the fused score
- **WHEN** `vacancy-radar search <query> --scores` is run in hybrid
  mode
- **THEN** each printed hit shows its keyword rank, semantic rank, and
  fused score

### Requirement: vacancy-radar doctor reports vault health and every warning
`vacancy-radar doctor` SHALL report the vault path, whether the vault
marker is present, whether the index is present and fresh, whether the
embedding model is available, and every warning collected from
`read_vault` and the index-freshness check.

#### Scenario: doctor on a healthy fixture vault exits 0
- **WHEN** `vacancy-radar doctor` is run against the healthy fixture
  vault with a freshly built index
- **THEN** it exits 0

#### Scenario: doctor on a vault with broken fixtures exits non-zero and lists each warning
- **WHEN** `vacancy-radar doctor` is run against a vault including the
  stage 2 broken fixtures (malformed frontmatter, unreadable file,
  duplicate vacancy id, orphan documents directory)
- **THEN** it exits non-zero and its output lists each of those
  warnings

#### Scenario: doctor reports a stale index with the command that fixes it
- **WHEN** `vacancy-radar doctor` is run against a vault whose index is
  missing documents present in the vault
- **THEN** its output names the staleness and the command that rebuilds
  the index, and this alone does not cause a non-zero exit

### Requirement: vacancy-radar eval replaces the hidden _eval command
`vacancy-radar eval` SHALL be a public command running the existing
eval harness (`eval.run.run_eval` over `FULL_SWEEP`) against the
fixture vault and printing its markdown report. The hidden `_eval`
command SHALL no longer exist.

#### Scenario: eval runs the full sweep and prints a markdown report
- **WHEN** `vacancy-radar eval` is run
- **THEN** it exits 0 and prints the same markdown report shape the
  former `_eval` command printed

#### Scenario: eval is visible in --help and _eval is gone
- **WHEN** `vacancy-radar --help` is run
- **THEN** `eval` appears in the command list and `_eval` does not,
  and invoking `vacancy-radar _eval` fails as an unknown command

### Requirement: every command exits 0 on success and non-zero on a typed error
Every command added in this change SHALL exit 0 when its underlying
`core.py` call succeeds, and exit non-zero when it raises a typed
error, printing a message describing the failure.

#### Scenario: Every command exits 0 on success and non-zero on a typed error
- **WHEN** `list`, `show`, `search`, `doctor`, or `eval` is run in a
  situation that raises one of `core.py`'s typed errors
- **THEN** the command exits non-zero and prints a message describing
  the error

### Requirement: --json emits valid JSON with no Rich formatting
Every command supporting `--json` SHALL, when given that flag, print
exactly one valid JSON document to stdout and nothing else — no table
borders, no color codes, no extra lines.

#### Scenario: --json emits valid JSON with no Rich formatting
- **WHEN** any `--json`-supporting command is run with `--json`
- **THEN** stdout parses as valid JSON and contains no Rich table
  characters or ANSI escape codes

### Requirement: a command run with no vault configured names VAULT_PATH
Any command that resolves a vault SHALL, when no vault path is
configured (no explicit path, no `VAULT_PATH` environment variable),
exit non-zero with a message naming `VAULT_PATH`.

#### Scenario: A command run with no vault configured exits non-zero with a message naming VAULT_PATH
- **WHEN** `vacancy-radar list` (or any other vault-resolving command)
  is run with no vault path configured
- **THEN** it exits non-zero and its output names `VAULT_PATH`
