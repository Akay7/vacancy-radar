# Phase 0 Research: `/similar` Retrieval

No open `NEEDS CLARIFICATION` markers remain in the Technical Context. The decisions below turn
the spec's resolved clarifications (threshold filtering, duplicate flag, excerpt) into concrete
technical choices.

## Decision: Distance metric and similarity score

**Decision**: Explicitly configure the `vacancies` collection with `metadata={"hnsw:space":
"cosine"}` at creation time (in `ChromaStore.get_or_create_collection`, or a dedicated
`ChromaStore.query()` helper), and compute `similarity = 1 - cosine_distance` from Chroma's
returned distances. Bump `compat.CURRENT_STAMP.schema_version` (e.g. `"1"` → `"2"`) so that any
existing `vacancies` collection created under [[001-ingestion-cli]] (which didn't set an
explicit space and so defaults to Chroma's L2 space) gets picked up by the existing compat-stamp
auto-reindex check on the next `ingest`/`sync` and rebuilt under the new space.

**Rationale**: Chroma's HNSW distance space is fixed at collection-creation time and can't be
changed in place; cosine distance is the natural fit for sentence-transformer embeddings and
gives a similarity score in a predictable range for FR-007's threshold. Reusing the existing
compat-stamp mechanism (built in [[001-ingestion-cli]] specifically for "the embedding/schema
changed underneath you") is exactly what it's for — no new migration mechanism needed
(Constitution IV, VI).

**Alternatives considered**: Leaving the default L2 space and thresholding on raw L2 distance —
rejected because L2 distance has no fixed upper bound to normalize against, making a stable,
explainable threshold harder to pick and reason about than a cosine similarity in a bounded range.

## Decision: Minimum similarity threshold

**Decision**: A module-level constant `MIN_SIMILARITY = 0.5` in `retriever.py`. Matches at or
above this cosine similarity are considered meaningful (FR-007); anything below is omitted
entirely, not just down-ranked.

**Rationale**: The spec explicitly defers the exact number to planning (Assumptions). Initially
set to 0.5 as a conservative starting guess, then empirically recalibrated to 0.6 during manual
quickstart validation (`/speckit-implement` T025) against the real `bge-small-en-v1.5` model on
`data/example/`: unrelated postings (entirely different profession) scored 0.47-0.59 cosine
similarity against a backend-engineering posting — clearing the original 0.5 cutoff and
violating SC-002 — while a genuine different-role-same-domain posting scored 0.645 and a
reworded near-duplicate scored 0.88+. 0.6 sits in the gap between the "unrelated" and
"genuinely related" clusters observed in that test. Kept as a single named constant (not a
config file, not an env var) per Constitution IV — trivial to change again in one place if the
eval harness roadmap item finds a better value with more real usage data.

**Alternatives considered**: Making it configurable via an environment variable now — rejected
as premature configuration surface for a single-user tool with no evidence yet that the default
needs tuning per-user (YAGNI, Constitution IV). Also considered: a relative-margin approach
(e.g., only keep matches within some gap of the top score) instead of an absolute cutoff —
rejected as more complex to reason about and unnecessary given the absolute-threshold approach
cleanly separated the two clusters in real testing.

## Decision: Grouping hits by vacancy (natural key)

**Decision**: Query the `vacancies` collection with a `where={"doc_type": "posting"}` filter and
an over-fetch of `n_results = top_k * 4` (capped, e.g. at 20) candidate chunks. Extract each
hit's natural key from its chunk id (`id.split("/", 1)[0]`, per [[001-ingestion-cli]]'s
`{natural_key}/{relative_path}` id scheme). Keep only the best-scoring chunk per natural key,
then apply the similarity threshold, sort, and truncate to `top_k`.

**Rationale**: A vacancy folder can in principle have more than one file under `sources/`
(multiple posting snapshots), each embedded as a separate chunk (per [[001-ingestion-cli]]'s
chunking decision) — without grouping, the same vacancy could appear twice in the results,
contradicting FR-003's "ranked list of vacancies" framing (one entry per vacancy, not per file).
Over-fetching before grouping avoids under-filling `top_k` when several of the best raw hits
belong to the same vacancy.

**Alternatives considered**: Storing one combined chunk per vacancy (concatenating all posting
files) at ingestion time instead of grouping at query time — rejected as a bigger change
reaching back into the already-shipped Ingestion CLI feature for a case (multiple posting
snapshots per folder) that isn't confirmed to be common; grouping at query time is a strictly
additive, contained change.

## Decision: "Effectively the same position" duplicate-flag rule

**Decision**: The pasted JD has no structured company/position of its own — it's raw text, not
a parsed `vacancy.yaml` — so a direct field-equality check isn't available. Instead, flag
`is_duplicate = True` whenever a match's similarity is at or above a second, higher constant
`DUPLICATE_SIMILARITY = 0.85`, on the reasoning that JD text for the same company and
effectively the same position produces near-identical embeddings to the original posting.

**Rationale**: Avoids requiring the caller to supply a structured company/position for the
pasted JD (which the spec never asks for — input is just JD text). A high-similarity-threshold
proxy directly satisfies both of User Story 2's acceptance scenarios (same company+role →
flagged; same company, different role → NOT flagged, since a different role's posting text
won't score above 0.85) without adding a second matching code path, keeping to Constitution IV.

**Alternatives considered**: A separate normalized-string equality check on `company`+`position`
— rejected because the pasted JD text has no separately-supplied company/position for this
endpoint to compare against; extracting those from freeform JD text would require new NLP/LLM
work out of scope for a pure-retrieval feature and would violate Constitution II if done by an
LLM without grounding, or add non-trivial custom logic if done by hand-rolled parsing
(Constitution IV: no reasonable simple alternative exists here, so the similarity-proxy is the
simpler and sufficient mechanism).

## Decision: Excerpt content

**Decision**: The first 280 characters of the matched posting chunk's stored document text
(the same text embedded for that chunk), with a trailing `…` if truncated.

**Rationale**: The chunk's full text is already stored in Chroma (`documents` field) — no
re-reading of the original vacancy folder from disk is needed at query time, keeping this
feature purely a Chroma read. 280 characters is enough to recognize a posting at a glance
without bloating the response (Constitution IV).

**Alternatives considered**: Returning the full posting text — rejected as unnecessarily large
for a "glance to confirm" use case; the user can still open the original vacancy folder for the
full text if needed.

## Decision: `SimilarVacancy` model shape

**Decision**: Rename the existing `title` field to `position` (matching the field name used
everywhere else in the codebase — `VacancyRecord.position`, ingestion metadata, `retriever.py`'s
docstring) and add `excerpt: str` and `is_duplicate: bool`.

**Rationale**: `/analyze` (which will also use `SimilarVacancy` per `Report.similar`) isn't
implemented yet, so there are no real consumers of the current field name to break; fixing the
`title`/`position` naming mismatch now avoids carrying an inconsistency into the next feature.

**Alternatives considered**: Leaving `title` as-is and accepting the naming mismatch — rejected,
free to fix now with zero migration cost.

## Decision: Endpoint signature

**Decision**: Keep `/similar`'s existing signature — `def similar(jd_text: str)` — unchanged
from the M1 stub (a plain scalar parameter, which FastAPI treats as a query parameter absent a
Pydantic body model), now returning `list[SimilarVacancy]` via `response_model`.

**Rationale**: `/analyze`'s stub uses the identical convention (`jd_text: str`); diverging to a
request-body model for only `/similar` would introduce an inconsistency between the two
JD-accepting endpoints for no functional benefit at this stage (Constitution IV).

**Alternatives considered**: Switching to a `Body(...)`-based request model now — rejected as an
unrelated API-shape change better made consistently across both endpoints together, if ever,
not as a side effect of this feature.
