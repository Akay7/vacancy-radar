## MODIFIED Requirements

### Requirement: optional write tool parameters are genuinely optional
A write tool parameter SHALL stay optional in the tool's schema
whenever it is optional in `core.py`'s own signature, and omitting it
SHALL produce the same `core.py` call as passing `core.py`'s own
default for that parameter.

#### Scenario: omitting append_note's date matches core's own default
- **GIVEN** `core.append_note` is mocked
- **WHEN** the `append_note` tool is called with no `date` argument
- **THEN** `core.append_note` is called with `date=None`, letting
  `core.append_note` resolve today's local date itself, exactly as an
  unset `date` already behaves when calling `core.append_note` directly

#### Scenario: omitting add_document's external_id matches core's own default
- **GIVEN** `core.add_document` is mocked
- **WHEN** the `add_document` tool is called with no `external_id`
  argument
- **THEN** `core.add_document` is called with `external_id=None`

#### Scenario: omitting create_vacancy's optional fields matches core's own defaults
- **GIVEN** `core.create_vacancy` is mocked
- **WHEN** the `create_vacancy` tool is called with no `source_url`,
  `applied_date`, `stage_note`, `salary_note`, `recruiter`, or `tags`
  argument
- **THEN** `core.create_vacancy` is called with `source_url=None`,
  `applied_date=None`, `stage_note=None`, `salary_note=None`,
  `recruiter=None`, `tags=None` — exactly what each parameter already
  defaults to when calling `core.create_vacancy` directly

### Requirement: create_vacancy's tool description states the import conventions a caller must apply itself
The `create_vacancy` tool's description SHALL state, in terms a
calling model can act on without consulting other documentation: that
`role` should be `"unknown"` when no title is available and such
vacancies should be tagged `needs_review`; that `found_date` may be
synthesized from `applied_date` when the source has no found date, and
such records should be tagged `migrated`; that `source_url` may be
omitted when the source has no link at all (e.g. a recruiter sent only
a PDF attachment, no posting URL); and that the caller should check
for an existing vacancy (e.g. via `find_existing`, passing just
`company` when there is no `source_url` to check against) before
creating, since the tool itself does not deduplicate.

#### Scenario: The tool description states the unknown-role convention
- **WHEN** the `create_vacancy` tool's description is inspected
- **THEN** it contains the words `unknown` and `needs_review` in a
  sentence describing when to use them together

#### Scenario: The tool description states the synthesized-found_date convention
- **WHEN** the `create_vacancy` tool's description is inspected
- **THEN** it contains the words `found_date`, `applied_date`, and
  `migrated` in a sentence describing when to synthesize the former
  from the latter and tag the result

#### Scenario: The tool description states the check-before-create convention
- **WHEN** the `create_vacancy` tool's description is inspected
- **THEN** it states that the tool does not deduplicate and that the
  caller should check for an existing vacancy first

#### Scenario: The tool description states the no-source_url convention
- **WHEN** the `create_vacancy` tool's description is inspected
- **THEN** it states that `source_url` may be omitted when the source
  has no link, naming a PDF-only recruiter message as an example

## ADDED Requirements

### Requirement: create_vacancy tool's source_url parameter is optional
Calling the `create_vacancy` tool with no `source_url` argument SHALL
create a vacancy with no `source_url`, exercised end to end through
the tool against a real vault.

#### Scenario: Omitting source_url through the tool creates a vacancy with none
- **WHEN** the `create_vacancy` tool is called with no `source_url`
  argument and otherwise valid arguments
- **THEN** the tool call succeeds and the created vacancy has no
  `source_url`
