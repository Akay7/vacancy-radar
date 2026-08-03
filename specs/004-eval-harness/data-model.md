# Data Model: Eval Harness

All fixture files are JSON Lines (one JSON object per line); all in-process shapes are Python
`dataclasses` (matching the style of `ingest.py`'s `RunSummary`/`InvalidFolder`) — no new
`pydantic` models are needed since fixtures aren't API input.

## Eval Fixture Set

Four fixture kinds, one file each under `eval/golden/`.

### `grounding.jsonl` (User Story 1)

One line = one grounding scenario, fed straight into `grounding.enforce()`.

```json
{
  "id": "grounding-001",
  "sources": {"bullet-0": "Built a FastAPI service handling 200 req/s with async SQLAlchemy."},
  "match_band": "good",
  "flags": [
    {"label": "Backend", "severity": "green", "reason": "Built a FastAPI service.",
     "quote": "Built a FastAPI service handling 200 req/s", "source_id": "bullet-0",
     "expect_grounded": true},
    {"label": "Fabricated", "severity": "green", "reason": "Invented.",
     "quote": "launched a rocket to Mars", "source_id": "bullet-0",
     "expect_grounded": false}
  ],
  "gaps": ["No Kubernetes experience found in ingested bullets"],
  "draft_sentences": [
    {"text": "I built a FastAPI service.", "quote": "Built a FastAPI service handling 200 req/s",
     "source_id": "bullet-0", "expect_grounded": true}
  ]
}
```

- `sources`: same shape `grounding.enforce()` already takes (`dict[str, str]`).
- `flags[]` / `draft_sentences[]`: identical fields to `CandidateFlag`/`CandidateSentence`
  (`src/vacancy_radar/models.py`) plus one added label field, `expect_grounded: bool` — stripped
  off before constructing the real `CandidateFlag`/`CandidateSentence`/`CandidateReport` objects
  passed into `enforce()`.
- Validation rule: every `flags[].source_id` / `draft_sentences[].source_id` referenced must
  exist as a key in this same line's `sources` object, OR the fixture is intentionally testing
  the unknown-source-id path (in which case `expect_grounded` must be `false`) — a fixture where
  an unknown source id is labeled `expect_grounded: true` is a fixture authoring error, reported
  as a fixture/data error (not a grounding-logic failure) per FR-007.

### `bullets.jsonl` (User Story 2)

One line = one labeled retrieval query, run against the eval's own ingested
`eval/golden/fixtures/cv/` bullets (not the maintainer's real bullets).

```json
{"id": "bullets-001", "query": "Experience building async Python web APIs",
 "expected_bullet_ids": ["bullet-0", "bullet-2"]}
```

- `expected_bullet_ids`: ids as assigned by `ingest.ingest_experience_bullets()`'s existing
  `bullet-{i}` convention over the eval's fixture CV file(s) — positional, so re-ordering or
  editing `eval/golden/fixtures/cv/*.md` requires updating referencing fixtures. A fixture whose
  `expected_bullet_ids` entry doesn't exist among the ids actually produced by ingesting the
  fixture CV data is a fixture/data error (FR-007), not a retrieval miss.

### `similar.jsonl` (User Story 3)

One line = one labeled query posting, run against the eval's own ingested
`eval/golden/fixtures/vacancies/` (not the maintainer's real vacancy history).

```json
{"id": "similar-001", "query_posting": "<full text of a JD, or path to one under fixtures/>",
 "expected_similar_ids": ["2026-01-15_acme-corp_backend-engineer"]}
```

- `expected_similar_ids`: natural keys (same format `ingest.natural_key()` produces) of vacancies
  under `eval/golden/fixtures/vacancies/` that a human has labeled as truly similar to
  `query_posting`. A referenced id absent from the ingested fixture vacancies is a fixture/data
  error (FR-007).
- `query_posting` may be inlined text or a relative path into `fixtures/`; the loader accepts
  either (implementation detail, decided in tasks phase).

### `filter-consistency.jsonl` (User Story 4)

One line = one filter-rule citation scenario. Deliberately narrower than a full
`grounding.jsonl` line: always exactly one candidate flag citing `source_id: "filter-rules"`.

```json
{"id": "filter-001", "filter_rules_text": "Must be remote. No on-call rotation.",
 "flag": {"label": "Remote requirement", "severity": "red",
          "reason": "Posting doesn't mention remote work.",
          "quote": "Must be remote", "source_id": "filter-rules"},
 "expect_grounded": true}
```

- `filter_rules_text`: the exact active filter-rules content for this scenario (each fixture
  supplies its own, rather than sharing one global file, so violation/non-violation cases can
  each control their own ground truth).
- `flag.source_id` MUST be `"filter-rules"` — a fixture with any other `source_id` belongs in
  `grounding.jsonl` instead (fixture authoring error otherwise).

## Eval Report (in-process result of one harness run)

```python
@dataclass
class FixtureFailure:
    fixture_id: str
    kind: Literal["regression", "fixture_error"]
    reason: str

@dataclass
class CheckResult:
    name: str                       # "grounding" | "bullet_retrieval" | "similar_vacancy" | "filter_consistency"
    status: Literal["pass", "fail", "skipped"]
    metrics: dict[str, float]        # e.g. {"recall@5": 0.83, "mrr": 0.71}
    sample_size: int
    failures: list[FixtureFailure]

@dataclass
class EvalReport:
    checks: list[CheckResult]
    overall_status: Literal["pass", "fail"]
```

- `status = "skipped"` when a check's golden file is missing or empty (edge case from spec.md) —
  distinct from `"fail"`, and does NOT by itself flip `overall_status` to `"fail"` (a fresh clone
  with an intentionally-empty new golden file shouldn't hard-fail CI; an existing, previously
  populated golden file going missing is a repo problem the maintainer would notice separately).
- `failures[].kind` distinguishes a genuine quality regression from a fixture/data problem
  (FR-007) — e.g., a fixture referencing a bullet id that was never ingested is `"fixture_error"`,
  while a real expected-relevant bullet failing to appear in top-k is `"regression"`.

## Metric Threshold

Not a data entity so much as named constants alongside each check module (same pattern as
`retriever.py`'s `MIN_SIMILARITY`), e.g. `GROUNDING_MIN_ACCURACY = 1.0`,
`BULLET_RECALL_AT_5_MIN`, `SIMILAR_PRECISION_AT_3_MIN`, `FILTER_CONSISTENCY_MIN_ACCURACY = 1.0` —
exact retrieval-based values calibrated during implementation once real fixture scores are
observed (research.md item 5).
