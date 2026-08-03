# Implementation Plan: Vacancy Document Upload

**Branch**: `006-vacancy-upload` | **Date**: 2026-08-03 | **Spec**: [spec.md](spec.md)

**Input**: Feature specification from `/specs/006-vacancy-upload/spec.md`

**Note**: This template is filled in by the `/speckit-plan` command; its definition describes the execution workflow.

## Summary

Add a two-step web upload flow that finally gives this project a real "log a vacancy" screen
(retiring the never-implemented `POST /ingest/vacancy` M1 stub — see research.md #9): upload a
job posting/offer document (image, PDF, DOCX, or plain text) → the system extracts its text locally
and asks the configured `LLMProvider` to draft company/position/date → the maintainer reviews
and edits every field (outcome is always typed by hand) → on confirm, the system writes a real
vacancy folder into `VACANCY_DIR` and immediately upserts it into Chroma by reusing the existing
`ingest_vacancies()` function unchanged. The same local text-extraction capability also lets the
existing CLI/folder-based ingestion path accept image/PDF/DOCX files under `sources/`/
`correspondence/`, not just markdown/text.

A real infra constraint surfaced during planning and was resolved with the user directly:
`docker-compose.yml` currently mounts the user's real data read-only (`./data/user:/data/user:ro`),
which would make it impossible to satisfy Constitution VI (Chroma must never be the only record
of a vacancy) inside the containerized deployment. Per the user's explicit decision, this mount
becomes read-write — the first time this app has ever needed to write to the user's own source
data, done for a concrete, constitutionally-required reason.

## Technical Context

**Language/Version**: Python 3.11 (unchanged).

**Primary Dependencies**: `pypdf` (PDF text-layer extraction), `python-docx` (DOCX text
extraction), `pytesseract` + `Pillow` (image OCR — `pytesseract` is a thin wrapper requiring the
system `tesseract-ocr` binary, a new OS-level dependency, not just a pip package).
`python-multipart` is already a dependency ([[005-minimal-ui]]) and covers the file-upload form
parsing here too. No new LLM SDK — drafting reuses the existing `LLMProvider` abstraction.

**Storage**: A new writable staging area, `.cache/pending-uploads/<token>/` (disposable,
gitignored — `.cache/` already carries this convention), holds an uploaded document between the
"draft" and "confirm" steps of the two-request flow. The confirmed vacancy folder itself is
written into `VACANCY_DIR` — the user's own git-tracked data — using the existing `vacancy.yaml`
format and natural-key folder-naming convention unchanged; no new persisted schema.

**Testing**: `pytest`, same `LLMProvider` dependency-injection pattern used for `/analyze` to
fake the drafting call. Text-extraction functions are tested against small fixtures synthesized
at test time with the same libraries being tested (a few lines of real PDF/DOCX/PNG content,
not hand-curated binary files checked into the repo). Genuine OCR/PDF-rendering quality is
validated once, for real, in the manual quickstart pass — a fake can't stand in for whether
`pytesseract` actually reads a real scanned image correctly.

**Target Platform**: Same Docker/bare deployment as the rest of the project; `Dockerfile` gains
an `apt-get install tesseract-ocr` step; `docker-compose.yml`'s `./data/user` mount changes from
read-only to read-write (see Summary) — `./data/example` stays read-only, since demo/CI fixture
data is never written to.

**Project Type**: Single project — extends the existing FastAPI app exactly as
[[005-minimal-ui]] did, no new service.

**Performance Goals**: Single-document, synchronous request/response for both the draft and
confirm steps — no background job queue, matching the scale of a single-user tool processing a
handful of pages per upload.

**Constraints**: Extraction and drafting must each degrade gracefully to full manual entry if
they fail (FR-008) — neither step may block logging a vacancy. No new dependency on a paid
OCR/vision API — extraction stays fully local (Constitution I). The confirmed record must always
land in git-trackable `VACANCY_DIR` source, never only in Chroma (Constitution VI).

**Scale/Scope**: One new upload screen, two new routes (draft + confirm), one new
`LLMProvider.draft_vacancy_metadata()` method (both providers), one new document-extraction
module, one small extension to the existing folder-based ingestion's chunking logic, and the
two infra changes (Dockerfile, docker-compose.yml) described above.

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

| Principle | Check | Result |
|---|---|---|
| I. Local-First & Private by Default | Extraction (PDF/DOCX/OCR) is fully local, no cloud OCR/vision API; only extracted *text* goes to the already-configured `LLMProvider`, same trust boundary `/analyze` already crosses; confirmed data is written straight into the maintainer's own `VACANCY_DIR`. The `data/user` mount moving to read-write is a deliberate, confirmed widening of write access to the maintainer's *own* data on their *own* machine — not a new external exposure. | PASS |
| II. Grounded Generation (NON-NEGOTIABLE) | Drafted company/position/date aren't a citation-bearing generated narrative like `/analyze`'s report — `grounding.enforce()` doesn't apply. The substitute safeguard is FR-004's mandatory human review before anything is persisted, documented explicitly in spec.md's Assumptions as the deliberate reason this doesn't need an automated citation check. | PASS (documented substitution) |
| III. Pluggable, Provider-Agnostic LLM | New `draft_vacancy_metadata()` method added to the `LLMProvider` ABC, implemented identically by `ClaudeProvider` and `OllamaProvider` — both only ever see plain extracted text (never an image/PDF directly), so there's no vision-only-works-on-Claude asymmetry to begin with. | PASS |
| IV. Simplicity & Right-Sized Infra (YAGNI) | Reuses the existing `ingest_vacancies()` upsert/conflict-detection logic wholesale (write a normal folder to disk, then call the same function again) instead of a parallel single-vacancy ingestion path; no job queue/async infra for a small, synchronous, single-document operation. The one new system dependency (`tesseract-ocr`) is justified directly by FR-001's requirement to accept images. | PASS |
| V. Test & Lint Gates | New routes, the extraction module, and the new `LLMProvider` method all get `pytest` coverage; real format-rendering/OCR quality gets a manual quickstart pass, matching this project's established pattern for anything a fake can't meaningfully stand in for. | PASS |
| VI. Regenerable Derived State | This feature exists specifically to guarantee the confirmed vacancy lands in git-trackable source (`VACANCY_DIR`) *before* Chroma ever sees it (via the existing `ingest_vacancies()` call) — directly reinforcing this principle. The read-only-mount discovery during planning was this principle catching a real design flaw (a vacancy that could otherwise be lost on the next `reindex`) before it shipped. | PASS |

No violations to justify — Complexity Tracking section left empty.

*Re-checked post-Phase 1 (after research.md/data-model.md/contracts/quickstart.md were
written): unchanged — the staging-area design and the reuse of `ingest_vacancies()` both confirm
the table above rather than introduce anything new.*

## Project Structure

### Documentation (this feature)

```text
specs/006-vacancy-upload/
├── plan.md              # This file (/speckit-plan command output)
├── research.md          # Phase 0 output (/speckit-plan command)
├── data-model.md        # Phase 1 output (/speckit-plan command)
├── quickstart.md        # Phase 1 output (/speckit-plan command)
├── contracts/           # Phase 1 output (/speckit-plan command)
└── tasks.md             # Phase 2 output (/speckit-tasks command - NOT created by /speckit-plan)
```

### Source Code (repository root)

```text
src/vacancy_radar/
├── api.py                     # extended: GET /ingest, POST /ui/ingest/draft, POST /ui/ingest/confirm
├── documents.py                # NEW: extract_text(path) -> str, dispatches by extension
├── ingest.py                   # extended: chunk_vacancy_folder() uses documents.extract_text()
│                                # for .pdf/.docx/image extensions instead of assuming .read_text()
├── models.py                   # extended: DraftVacancyMetadata candidate shape
├── llm/
│   ├── base.py                 # extended: LLMProvider.draft_vacancy_metadata() abstract method
│   ├── claude.py               # extended: draft_vacancy_metadata() implementation
│   ├── ollama.py                # extended: draft_vacancy_metadata() implementation
│   └── prompts.py               # extended: build_draft_metadata_prompt() + JSON schema
├── templates/
│   ├── ingest.html              # NEW: upload form page
│   ├── _ingest_draft.html        # NEW: editable draft-review form (hidden upload token)
│   └── _ingest_result.html       # NEW: confirmation / conflict / error result partial
└── static/                      # unchanged from 005 (htmx.min.js, ui.js)

docker-compose.yml               # ./data/user mount: :ro -> read-write (./data/example stays :ro)
Dockerfile                        # + apt-get install tesseract-ocr

tests/
├── test_documents.py            # NEW: extract_text() against small synthesized fixtures
├── test_llm_claude.py            # extended: draft_vacancy_metadata()
├── test_llm_ollama.py            # extended: draft_vacancy_metadata()
├── test_ingest.py                # extended: chunk_vacancy_folder() handles pdf/docx/image sources
└── test_ingest_upload.py         # NEW: draft/confirm route tests
```

**Structure Decision**: Single project (unchanged) — everything lives inside the existing
`src/vacancy_radar` package and the existing FastAPI app, following [[005-minimal-ui]]'s
established pattern exactly (new templates, new routes, no new service). The only structure
changes outside `src/` are the two infra files (`docker-compose.yml`, `Dockerfile`) needed for
the read-write mount and the new system OCR dependency.

## Complexity Tracking

> No violations — this section is intentionally empty; see the Constitution Check table above.
