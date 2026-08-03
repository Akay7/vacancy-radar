# Data Model: Vacancy Document Upload

No new persisted database/schema — the confirmed output is still just a normal
`vacancy.yaml` + `sources/` folder under `VACANCY_DIR`, exactly as [[001-ingestion-cli]] already
defines it. What's new is one small Pydantic model for the LLM-drafted fields, and a filesystem
convention for the transient staging state between the draft and confirm requests.

## `DraftVacancyMetadata` (new)

```python
class DraftVacancyMetadata(BaseModel):
    company: str
    position: str
    date: date  # defaults to today when not determinable from the document (research.md #6)
```

Returned by `LLMProvider.draft_vacancy_metadata(document_text: str) -> DraftVacancyMetadata`.
Deliberately excludes `outcome` — per spec.md's FR-003, outcome is never derived from the
document; the draft-review form always requires the maintainer to set it directly.

Unlike `CandidateReport` ([[003-analyze-report-generation]]), there is no citation/grounding
shape here — see spec.md's Assumptions for why (a handful of short factual fields, human-
reviewed before anything is saved, not a longer generated narrative needing per-claim citation
checking).

## Pending Upload (filesystem convention, not a Python model)

Between the draft and confirm requests, a staged upload is just a directory:

```text
.cache/pending-uploads/<uuid>/<original-filename>
```

- `<uuid>`: a random token, generated at draft time, round-tripped through the rendered form as
  a hidden field — this is the only thing the confirm request needs to relocate the staged file.
- The directory (and its one file) is deleted once `POST /ui/ingest/confirm` successfully moves
  it into the new vacancy folder's `sources/`. An abandoned draft (never confirmed) simply leaves
  this directory behind under `.cache/` — no expiry job (research.md #4).

## `VacancyRecord` *(existing, reused from [[001-ingestion-cli]], unchanged)*

```python
class VacancyRecord(BaseModel):
    company: str
    position: str
    date: date
    outcome: str
```

The confirmed draft (company/position/date from `DraftVacancyMetadata`, possibly edited, plus
the maintainer-provided `outcome`) is written out as exactly this shape into the new folder's
`vacancy.yaml` — this feature produces a `VacancyRecord`, it doesn't change what one is.

## Confirm result (in-process, not persisted)

Two distinct conflict checks, not one — **corrected during implementation**, see
contracts/ingest-upload-routes.md:

1. **Same-key, pre-write guard** (new to this feature): before writing anything, check whether
   `VACANCY_DIR/<natural-key>/` already exists. Since this route uses the natural key directly
   as the folder name, writing into an existing one would silently overwrite it — this is
   checked and rejected *before* any file is touched, not detected afterward.
2. **Cross-folder conflict** (existing, reused unchanged): after a successful write, re-invoking
   `ingest.ingest_vacancies()` ([[001-ingestion-cli]]) still performs its own scan for two
   *differently-named* folders whose `vacancy.yaml` content resolves to the same key — the
   scenario `RunSummary.vacancies_conflicting`/`ConflictGroup` already exist for. This remains
   the safety net for that separate case; it's unrelated to check #1 above.

The confirm route's success/failure result is otherwise derived directly from `RunSummary`:
`vacancies_created == 1` → success, new vacancy folder created and embedded.
