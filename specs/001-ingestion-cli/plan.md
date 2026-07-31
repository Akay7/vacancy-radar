# Implementation Plan: Ingestion CLI

**Branch**: `001-ingestion-cli` | **Date**: 2026-07-31 | **Spec**: [spec.md](./spec.md)

**Input**: Feature specification from `/specs/001-ingestion-cli/spec.md`

**Note**: This template is filled in by the `/speckit-plan` command; its definition describes the execution workflow.

## Summary

Implement the three CLI subcommands already stubbed in `cli.py` (`ingest`, `sync`, `reindex`)
so that CV bullets and vacancy folders become queryable Chroma collections. `ingest`/`sync`
share one upsert path keyed by natural key (vacancy folders) or full-replace (CV bullets),
tracked via a local per-file staleness manifest; `reindex` deletes the local cache and
rebuilds it from source, also serving as the recovery path for the embedding-model/schema
compat-stamp check already defined in `compat.py`.

## Technical Context

**Language/Version**: Python 3.11 (per `pyproject.toml` `requires-python`/`target-version`)

**Primary Dependencies**: `chromadb` (embedded/persistent client), `sentence-transformers`
(via existing `Embedder` ABC in `embedder.py`), `pyyaml` (vacancy.yaml parsing), `pydantic`
(schema validation), `langchain-text-splitters` (chunking posting/correspondence markdown),
`argparse` (existing `cli.py` subparsers)

**Storage**: Chroma embedded/persistent store at `.cache/chroma` (gitignored, per `compat.py`);
a local JSON ingest manifest (per-file content hash + chunk ids) alongside it for staleness
detection — also disposable/regenerable, never committed

**Testing**: `pytest` + `httpx` (existing dev deps); new tests under `tests/`, matching the
existing flat `tests/test_*.py` convention (no `contract/`/`integration/`/`unit/` split)

**Target Platform**: Linux, run either bare (`vacancy-radar` console script) or inside the
existing Docker image/compose service; must work identically in both

**Project Type**: Single project (CLI + library) — extends the existing `src/vacancy_radar/`
package, no new top-level project

**Performance Goals**: Not a target for this feature (Constitution IV); correctness and
idempotency of upserts matter more than throughput at the project's stated scale

**Constraints**: Fully offline-capable (local embeddings only, per Constitution I/III); MUST
NOT modify or delete any file under `CV_DIR`/`VACANCY_DIR` (source is git-tracked, cache is
not, per Constitution VI); MUST NOT commit or bake `data/user/` content into the image

**Scale/Scope**: Single user, low hundreds to low thousands of vacancy folders and CV bullets
over a job search (per README's stated scale)

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

| Principle | Check | Result |
|---|---|---|
| I. Local-First & Private by Default | Reads only from user-supplied `CV_DIR`/`VACANCY_DIR`; writes only to local `.cache/`; no network calls added | PASS |
| II. Grounded Generation (NON-NEGOTIABLE) | Not applicable to ingestion itself (no generated claims here); this feature's metadata tagging (FR-003) is what later makes `/analyze` grounding possible | PASS (N/A to this feature's own output) |
| III. Pluggable, Provider-Agnostic LLM | Ingestion uses the existing `Embedder` ABC, not `LLMProvider`; no provider-specific branching introduced | PASS |
| IV. Simplicity & Right-Sized Infra (YAGNI) | Chroma stays embedded (no server); CV bullets use full-replace instead of building incremental-upsert machinery for a small, rarely-changing file (per clarified FR-012) | PASS |
| V. Test & Lint Gates | Plan requires `ruff` clean + `pytest` coverage for ingest/sync/reindex and the manifest/validation logic before considered done | PASS (enforced in tasks) |
| VI. Regenerable Derived State | This feature *is* the regenerate-from-source path; `reindex` deletes `.cache/chroma` and rebuilds, upserts are natural-key-keyed, never content-hash-keyed | PASS |

No violations — Complexity Tracking table is not needed.

**Post-Design re-check** (after Phase 1 data-model.md/contracts/quickstart.md): the manifest
(`.cache/ingest-manifest.json`), `ChromaStore` wrapper, and CV full-replace design introduce no
new external services, no new network calls, and no persisted personal data beyond what
already lived in `.cache/chroma` — all six gates above still PASS unchanged.

## Project Structure

### Documentation (this feature)

```text
specs/[###-feature]/
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
├── cli.py              # existing — wires ingest/sync/reindex subcommands to the functions below
├── ingest.py            # existing stubs (ingest_experience_bullets, ingest_vacancies) — implemented here
├── embedder.py          # existing Embedder ABC / SentenceTransformersEmbedder — implemented here
├── compat.py            # existing CompatStamp/needs_reindex — wired into ingest/sync/reindex here
├── models.py             # existing Pydantic schemas — add VacancyRecord (vacancy.yaml schema)
├── chroma_store.py       # NEW — thin wrapper: get_or_create_collection, upsert, delete, count
└── manifest.py            # NEW — per-file content-hash manifest for sync staleness detection

tests/
├── test_api.py           # existing, unchanged
├── test_ingest.py         # NEW — ingest_experience_bullets / ingest_vacancies unit tests
├── test_manifest.py        # NEW — staleness hash cache behavior
└── test_cli_ingest.py       # NEW — CLI-level: ingest/sync/reindex against data/example/

data/example/
└── ...                    # populated with a handful of sanitized CV bullets + vacancy folders
                            # so tests and README examples have real fixture data to ingest
```

**Structure Decision**: Single project (Option 1), extending the existing flat
`src/vacancy_radar/` package and flat `tests/` directory — no new top-level project, no
`contract/`/`integration/`/`unit/` test subdivision, matching the scaffold as it stands today.

## Complexity Tracking

> **Fill ONLY if Constitution Check has violations that must be justified**

No violations — table not needed.
