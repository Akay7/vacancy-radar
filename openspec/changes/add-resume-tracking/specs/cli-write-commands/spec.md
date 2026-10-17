## MODIFIED Requirements

### Requirement: edit exposes one option per editable field
`vacancy-radar edit <vacancy>` SHALL expose one option per field
`core.edit_vacancy` accepts — `--source-url`, `--role`, `--stage-note`,
`--salary-note`, `--recruiter`, `--external-id`, `--tags`,
`--found-date`, `--applied-date`, `--resume` — and SHALL expose no
option for `id`, `status`, `company`, or `company_slug`.

#### Scenario: an option given sets that field
- **WHEN** `vacancy-radar edit <vacancy> --recruiter "Anna K."` is run
- **THEN** the command exits 0 and the vacancy's `recruiter` is
  `"Anna K."`

#### Scenario: several options are applied in one invocation
- **WHEN** `vacancy-radar edit <vacancy> --source-url <url>
  --recruiter "Anna K."` is run
- **THEN** the command exits 0 and both fields carry their new values

#### Scenario: no status option is exposed
- **WHEN** `vacancy-radar edit --help` is inspected
- **THEN** it lists no option for setting `status`, `company`, or `id`

#### Scenario: --resume sets the resume
- **WHEN** `vacancy-radar edit <vacancy> --resume backend-v2` is run
- **THEN** the command exits 0 and the vacancy's `resume` is
  `"backend-v2"`

#### Scenario: --clear resume removes it
- **GIVEN** a vacancy with a `resume`
- **WHEN** `vacancy-radar edit <vacancy> --clear resume` is run
- **THEN** the command exits 0 and `resume` is absent from the
  vacancy's frontmatter

## ADDED Requirements

### Requirement: status set accepts the resume used
`vacancy-radar status set <vacancy> <status>` SHALL accept an optional
`--resume LABEL` and pass it through to `set_status`.

#### Scenario: applying with --resume records it
- **GIVEN** a vacancy at status `found`
- **WHEN** `vacancy-radar status set <vacancy> applied --applied-date
  2026-10-01 --resume backend-v2` is run
- **THEN** the command exits 0, the vacancy's status is `applied`, and
  its `resume` is `"backend-v2"`

### Requirement: new accepts the resume used
`vacancy-radar new` SHALL accept an optional `--resume LABEL` and pass
it through to `create_vacancy`.

#### Scenario: creating an applied vacancy with --resume records it
- **WHEN** `vacancy-radar new` is run with `--status applied`,
  `--applied-date`, and `--resume backend-v2`
- **THEN** the command exits 0 and the created vacancy's `resume` is
  `"backend-v2"`
