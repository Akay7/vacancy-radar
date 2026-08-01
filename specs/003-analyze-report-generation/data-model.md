# Phase 1 Data Model: `/analyze` Full Report Generation

This feature reads the `experience_bullets` and `vacancies` collections ([[001-ingestion-cli]],
[[002-similar-retrieval]]) and an optional local filter-rules file; it introduces one changed
public field, two new internal (non-persisted) shapes, and no new persisted storage.

## Report (public response model, changed)

Existing model in `models.py`.

| Field | Type | Change |
|---|---|---|
| `score` | `Literal["strong", "good", "weak", "poor"]` | **Changed** from `float` — a rubric-derived match band (FR-005), not a numeric score (research.md) |
| `flags` | `list[Flag]` | Unchanged shape; only grounded flags survive `grounding.enforce()` |
| `gaps` | `list[str]` | Unchanged; gaps are absence-statements, not subject to citation (spec Assumptions) |
| `similar` | `list[SimilarVacancy]` | Unchanged — reused verbatim from [[002-similar-retrieval]]'s `query_similar_vacancies()` |
| `draft_paragraph` | `str` | Unchanged shape; built by joining only grounded sentences (FR-002/FR-008) — may be empty if nothing was groundable (FR-010) |
| `citations` | `list[Citation]` | Unchanged shape; the flat, validated list of every `(quote, source_id)` pair backing this report's flags and draft paragraph — see below |

**Validation rule**: every `Citation` in `citations` MUST have already passed
`grounding.enforce()` — nothing reaches this list unvalidated. A `Flag`'s `reason` text and the
corresponding sentence in `draft_paragraph` are expected to directly quote or closely paraphrase
their backing citation, so a human reader can see the grounding without cross-referencing
indices; `citations` exists as the structured, programmatically-checkable record of the same
guarantee, not a second independent source of truth.

## CandidateReport (internal, not persisted, not returned to the client)

The raw, pre-validation shape both `ClaudeProvider` and `OllamaProvider` parse their LLM
response into. Lives in `models.py` or `grounding.py` as a plain dataclass/BaseModel — never
serialized to the HTTP response directly.

| Field | Type | Notes |
|---|---|---|
| `match_band` | `Literal["strong","good","weak","poor"]` | Passed through to `Report.score` unchanged — the LLM itself isn't subject to grounding validation for this field (it's a holistic judgment, not a factual claim) |
| `flags` | `list[CandidateFlag]` | Each carries its own unvalidated citation — see below |
| `gaps` | `list[str]` | Passed through to `Report.gaps` unchanged |
| `draft_sentences` | `list[CandidateSentence]` | Each carries its own unvalidated citation |

### CandidateFlag

| Field | Type | Notes |
|---|---|---|
| `label` | str | e.g. "Backend experience" |
| `severity` | `Literal["red","green"]` | |
| `reason` | str | Plain-language justification, expected to quote/paraphrase `quote` |
| `quote` | str | The exact source text the LLM claims backs this flag |
| `source_id` | str | Which retrieved bullet or the filter-rules file this quote is claimed to come from |

### CandidateSentence

| Field | Type | Notes |
|---|---|---|
| `text` | str | One sentence of the draft opening paragraph |
| `quote` | str | The exact source text the LLM claims backs this sentence |
| `source_id` | str | Same `source_id` space as `CandidateFlag` |

## Source registry (internal, built per request, not persisted)

A `dict[str, str]` mapping every valid `source_id` to its full text, built fresh for each
`/analyze` call from that call's own retrieval results — never cached or reused across requests:

| `source_id` pattern | Maps to |
|---|---|
| `bullet-{i}` | One retrieved experience bullet's text (same id scheme `query_bullets()` returns, mirroring [[002-similar-retrieval]]'s chunk-id convention) |
| `filter-rules` | The full contents of the filter-rules file (single entry — the file isn't split into addressable pieces) |

`grounding.enforce()` looks up each `CandidateFlag`/`CandidateSentence`'s `source_id` in this
registry; an unknown `source_id`, or a `quote` that isn't a (whitespace/case-normalized)
substring of the looked-up text, means that flag/sentence is dropped (FR-008).

## FilterRules (not a model — a plain string)

The contents of `data/user/filter-rules.md` (or empty string if the file doesn't exist,
FR-007). Not parsed into structured rules — used as-is, both as prompt context and as the
`filter-rules` entry in the source registry above.

## Cross-references to existing entities

- **CV bullet**, **Vacancy folder**, **Local cache (Chroma collections)** — unchanged from
  [[001-ingestion-cli]]; this feature only reads them.
- **Similar vacancy match** — unchanged from [[002-similar-retrieval]]; `query_similar_vacancies()`
  is called as-is and its output becomes `Report.similar` directly.
