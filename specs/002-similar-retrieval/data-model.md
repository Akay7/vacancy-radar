# Phase 1 Data Model: `/similar` Retrieval

This feature reads the existing `vacancies` Chroma collection populated by
[[001-ingestion-cli]]; it introduces one new response shape and no new persisted entities.

## SimilarVacancy (response model, extended)

Existing model in `models.py`, extended for this feature.

| Field | Type | Notes |
|---|---|---|
| `vacancy_id` | str | The vacancy's natural key (`YYYY-MM-DD_company-slug_position-slug`, per [[001-ingestion-cli]] data-model.md) |
| `company` | str | Copied from the matched chunk's metadata |
| `position` | str | Renamed from `title` (research.md) — copied from the matched chunk's metadata |
| `outcome` | str | Copied from the matched chunk's metadata |
| `similarity` | float | `1 - cosine_distance`, in roughly [0, 1] for related text (research.md) |
| `excerpt` | str | First 280 characters of the matched posting chunk's stored text, `…`-truncated (research.md, FR-009) |
| `is_duplicate` | bool | `True` when `similarity >= DUPLICATE_SIMILARITY` (0.85), signaling a likely duplicate application (research.md, FR-008) |

**Validation rules**: none beyond type — this is a read-only projection of already-validated
ingested data (vacancy folders were already validated at ingestion time, per
[[001-ingestion-cli]] FR-008).

## Candidate hit (internal, not persisted)

One raw result from a Chroma query against `doc_type=posting` chunks, before grouping.

| Field | Source |
|---|---|
| `chunk_id` | Chroma hit id, e.g. `2026-01-15_acme-corp_backend-engineer/sources/posting.md` |
| `natural_key` | `chunk_id.split("/", 1)[0]` |
| `distance` | Chroma's returned cosine distance |
| `metadata` | Chroma's returned metadata (company/position/date/outcome/doc_type) |
| `document` | Chroma's returned chunk text (source for `excerpt`) |

**Grouping rule** (research.md): among candidate hits sharing the same `natural_key`, keep only
the one with the lowest `distance` (highest similarity) before applying the threshold and
building the final `SimilarVacancy` list.

## Query parameters (internal constants, not user-facing)

| Name | Value | Purpose |
|---|---|---|
| `MIN_SIMILARITY` | 0.6 | Matches below this are omitted entirely (FR-007) |
| `DUPLICATE_SIMILARITY` | 0.85 | Matches at/above this are flagged `is_duplicate=True` (FR-008) |
| `top_k` | 3 (default, per [[001-ingestion-cli]]'s existing `retriever.py` stub signature) | Max results returned |
| over-fetch count | `top_k * 4` (capped at 20) | Candidates fetched from Chroma before grouping (research.md) |
