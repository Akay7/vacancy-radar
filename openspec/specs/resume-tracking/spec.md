# resume-tracking Specification

## Purpose

Records which resume variant each application was sent with, and
compares variants by how their applications turned out, so that
several resumes — for different positions or as an A/B test of one —
can be judged on evidence instead of memory.

## Requirements

### Requirement: a vacancy may carry a resume label
A vacancy SHALL accept an optional `resume`: a short free-form label
naming the resume variant sent for it. A vacancy without one SHALL
remain valid, and `resume` SHALL be allowed at any status, including
`found`.

#### Scenario: a vacancy with a resume label is valid
- **WHEN** a vacancy is built with `resume="backend-v2"`
- **THEN** it validates and reports `resume` as `"backend-v2"`

#### Scenario: a vacancy without a resume is valid
- **WHEN** a vacancy is built with no `resume`
- **THEN** it validates and reports `resume` as absent

#### Scenario: a resume may be recorded before applying
- **WHEN** a vacancy with status `found` is built with a `resume`
- **THEN** it validates

### Requirement: a resume label is trimmed and must not be blank
A `resume` value SHALL be stored with surrounding whitespace removed.
A value that is empty or whitespace-only, spans more than one line, or
is longer than 64 characters SHALL be rejected, writing nothing.

#### Scenario: surrounding whitespace is trimmed
- **WHEN** a vacancy is created with `resume="  backend-v2 "`
- **THEN** its stored `resume` is `"backend-v2"`

#### Scenario: a whitespace-only resume is rejected
- **WHEN** a vacancy is created or edited with `resume="   "`
- **THEN** the call raises the typed invalid-vacancy-data error and the
  vault is unchanged

#### Scenario: a multi-line resume is rejected
- **WHEN** a vacancy is edited with `resume="a\nb"`
- **THEN** the call raises the typed invalid-vacancy-data error and the
  vault is unchanged

### Requirement: create_vacancy accepts a resume
`create_vacancy` SHALL accept an optional `resume` and store it in the
new vacancy's frontmatter.

#### Scenario: a vacancy created with a resume carries it
- **WHEN** `create_vacancy` is called with `status="applied"`, an
  `applied_date`, and `resume="backend-v2"`
- **THEN** the created vacancy's frontmatter has `resume: backend-v2`

#### Scenario: omitting resume stores none
- **WHEN** `create_vacancy` is called with no `resume`
- **THEN** the created vacancy's frontmatter has no `resume` key

### Requirement: set_status can record the resume used when applying
`set_status` SHALL accept an optional `resume` and, when given, store
it in the same write as the status change. A value that differs from
the stored one SHALL also append an entry to the vacancy's
`## Edit History` block naming the old and new value. When `resume` is
omitted, the stored `resume` SHALL be left as it was.

#### Scenario: applying with a resume stores it
- **GIVEN** a vacancy at status `found`
- **WHEN** `set_status` is called with `new_status="applied"`, an
  `applied_date`, and `resume="backend-v2"`
- **THEN** the vacancy's status is `applied` and its `resume` is
  `"backend-v2"`, and its `## Edit History` block records
  `resume: (none) -> backend-v2`

#### Scenario: omitting resume leaves the stored one alone
- **GIVEN** a vacancy at status `applied` with `resume="backend-v2"`
- **WHEN** `set_status` is called with `new_status="screening"` and no
  `resume`
- **THEN** its `resume` is still `"backend-v2"` and its edit history
  gained no entry

#### Scenario: a same-status call with a resume changes nothing
- **GIVEN** a vacancy already at status `applied`
- **WHEN** `set_status` is called with `new_status="applied"` and a
  `resume`
- **THEN** nothing in the vault is modified, as for any same-status call

### Requirement: summaries and detail report the resume
`VacancySummary` (as returned by `list_vacancies`) and `VacancyDetail`
(as returned by `get_vacancy`) SHALL each report the vacancy's
`resume`, or `null` when none is recorded.

#### Scenario: list_vacancies reports each vacancy's resume
- **GIVEN** a vault with one vacancy carrying `resume="backend-v2"`
  and one carrying none
- **WHEN** `list_vacancies` is called
- **THEN** the first row's `resume` is `"backend-v2"` and the second's
  is `null`

#### Scenario: get_vacancy reports the resume
- **GIVEN** a vacancy carrying `resume="backend-v2"`
- **WHEN** `get_vacancy` is called for it
- **THEN** the result's `resume` is `"backend-v2"`

### Requirement: list_vacancies filters by resume
`list_vacancies(resume=...)` SHALL return only vacancies whose stored
`resume` equals the given label, compared case-insensitively after
trimming, and SHALL combine with every other filter by intersection.

#### Scenario: the filter returns only that resume's vacancies
- **GIVEN** vacancies carrying `backend-v1`, `backend-v2`, and no
  resume
- **WHEN** `list_vacancies` is called with `resume="backend-v2"`
- **THEN** only the `backend-v2` vacancy is returned

#### Scenario: matching ignores case and surrounding whitespace
- **GIVEN** a vacancy carrying `resume="Backend-V2"`
- **WHEN** `list_vacancies` is called with `resume=" backend-v2 "`
- **THEN** that vacancy is returned

#### Scenario: the filter combines with status
- **WHEN** `list_vacancies` is called with `resume="backend-v2"` and
  `status=["interview"]`
- **THEN** every returned vacancy has that resume and status
  `interview`

### Requirement: resume_stats compares resumes by application outcome
`resume_stats` SHALL return one row per distinct resume label, counting
only vacancies that have been applied to (status other than `found`).
Labels SHALL be grouped case-insensitively after trimming and reported
in lower case. Each row SHALL report the number of applications, a
count per status, the number that advanced (currently `screening`,
`take_home`, `interview`, or `offer`), and the advance rate — advanced
divided by applications, or `null` when there are none.

#### Scenario: applications are counted per resume and status
- **GIVEN** three applied vacancies with `backend-v2` — one still
  `applied`, one `interview`, one `rejected` — and one `applied`
  vacancy with `backend-v1`
- **WHEN** `resume_stats` is called
- **THEN** the `backend-v2` row reports 3 applications, 1 each under
  `applied`, `interview`, and `rejected`, 1 advanced, and an advance
  rate of 1/3; the `backend-v1` row reports 1 application and 0
  advanced

#### Scenario: vacancies not yet applied to are not counted
- **GIVEN** a `found` vacancy carrying `resume="backend-v2"`
- **WHEN** `resume_stats` is called
- **THEN** the `backend-v2` row, if present, does not count it

#### Scenario: labels differing only in case are one resume
- **GIVEN** applied vacancies carrying `Backend-V2` and `backend-v2`
- **WHEN** `resume_stats` is called
- **THEN** one row labelled `backend-v2` reports both

### Requirement: resume_stats accounts for applications with no resume
`resume_stats` SHALL include one additional row, with a `null` resume,
counting applied vacancies that carry none, so that the rows' total
applications equals the number of applied vacancies considered. That
row SHALL be omitted when there are no such vacancies.

#### Scenario: unlabelled applications form their own row
- **GIVEN** two applied vacancies with `backend-v2` and one applied
  vacancy with no resume
- **WHEN** `resume_stats` is called
- **THEN** there is a row with `resume` `null` reporting 1 application,
  and the rows' applications sum to 3

#### Scenario: no unlabelled row when every application has a resume
- **GIVEN** every applied vacancy carries a resume
- **WHEN** `resume_stats` is called
- **THEN** no row has a `null` resume

### Requirement: resume_stats can be limited to recent applications
`resume_stats(since=...)` SHALL consider only vacancies whose
`applied_date` is on or after the given date.

#### Scenario: since excludes earlier applications
- **GIVEN** a `backend-v2` application dated 2026-01-10 and another
  dated 2026-03-01
- **WHEN** `resume_stats` is called with `since=2026-02-01`
- **THEN** the `backend-v2` row reports 1 application

### Requirement: resume_stats rows are ordered deterministically
`resume_stats` SHALL order rows by application count descending, then
by label ascending, with the `null`-resume row last.

#### Scenario: more-used resumes come first
- **GIVEN** `a` used for 1 application, `b` for 3, and one unlabelled
  application
- **WHEN** `resume_stats` is called
- **THEN** the rows' resumes are, in order, `b`, `a`, `null`

### Requirement: the comparison is available from the CLI
`vacancy-radar resumes` SHALL print the `resume_stats` rows as a table
and accept `--since` and `--json`, exiting 0 on success and printing a
clear message, not an empty table, when no vacancy has been applied to.

#### Scenario: resumes prints one row per resume
- **GIVEN** a vault with applications under two resumes
- **WHEN** `vacancy-radar resumes` is run
- **THEN** the command exits 0 and its output names both resumes with
  their application counts

#### Scenario: --json emits the same rows
- **WHEN** `vacancy-radar resumes --json` is run
- **THEN** stdout is JSON whose rows equal those of `resume_stats`

#### Scenario: an empty vault says so
- **GIVEN** a vault with no applied vacancy
- **WHEN** `vacancy-radar resumes` is run
- **THEN** the command exits 0 and reports that there are no
  applications to compare

### Requirement: the comparison is available as a read-only MCP tool
The MCP server SHALL expose `resume_stats` as a read-only tool that
delegates to the single `resume_stats` call, taking an optional
`since`, with `readOnlyHint=true` and `openWorldHint=false`.

#### Scenario: the tool delegates to core
- **GIVEN** `core.resume_stats` is mocked to return fixed rows
- **WHEN** the `resume_stats` tool is called with `since="2026-02-01"`
- **THEN** `core.resume_stats` is called exactly once with that date
  and the tool result equals the mocked rows, serialized, unmodified

#### Scenario: the tool is annotated read-only
- **WHEN** the server's `tools/list` response is fetched
- **THEN** `resume_stats` reports `readOnlyHint=true` and
  `openWorldHint=false`

### Requirement: resume tracking does not affect the index
Recording, changing, or clearing a `resume` SHALL NOT require a
reindex, and an index built before this field existed SHALL remain
valid.

#### Scenario: an older index still reports fresh
- **GIVEN** an index built from a vault with no `resume` fields
- **WHEN** a vacancy is edited to carry a `resume`
- **THEN** `search` still works against that index, and the index's
  schema is unchanged
