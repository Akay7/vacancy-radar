# Quickstart: `/analyze` Full Report Generation

Validates the feature end-to-end using `data/example/` ([[001-ingestion-cli]]), a running API
server, and — unlike the automated test suite, which fakes the LLM entirely — a real configured
LLM backend, per Constitution V's expectation of a manual pass against the real thing.

## Prerequisites

- `data/example/` ingested: `vacancy-radar ingest`
- API running: `uvicorn vacancy_radar.api:app` (bare) or `docker compose up`
- `.env` has a working `LLM_PROVIDER` configured — either `claude` with a real
  `ANTHROPIC_API_KEY`, or `ollama` with a running local Ollama server
  (`docker compose --profile local up`)
- Optionally: a `data/user/filter-rules.md` with a line or two of personal preferences, to
  exercise FR-007

## Scenario 1 — Grounded assessment with a real gap (User Story 1)

```bash
curl -s -G -X POST "http://localhost:8000/analyze" --data-urlencode "jd_text=$(cat data/example/vacancies/2026-01-15_acme-corp_backend-engineer/sources/posting.md)"
```

**Expected**: `200 OK`; `flags` includes at least one green flag whose `reason` quotes/paraphrases
a real ingested bullet, and `citations` includes that exact quote with a matching `source_id`.
If the posting mentions anything not covered by ingested bullets, `gaps` names it.

## Scenario 2 — Grounded draft paragraph (User Story 2)

Same request as Scenario 1. **Expected**: `draft_paragraph` is non-empty, and every claim in it
can be found verbatim among `citations`' quotes — nothing in the paragraph should read as an
invented achievement, tool, or outcome not covered by a citation.

## Scenario 3 — Cold start: no bullets ingested (User Story 2, Scenario 2 / FR-010)

```bash
rm -rf .cache
curl -s -G -X POST "http://localhost:8000/analyze" --data-urlencode "jd_text=Any job description text."
```

**Expected**: `200 OK`; `draft_paragraph` is `""`, `flags` and `citations` are `[]`, and `gaps`
reflects that nothing could be assessed — not an error, not a fabricated report. Re-run
`vacancy-radar ingest` afterward to restore the index for the remaining scenarios.

## Scenario 4 — Similar vacancies folded in (User Story 3)

```bash
curl -s -G -X POST "http://localhost:8000/analyze" --data-urlencode "jd_text=$(cat data/example/vacancies/2026-01-15_acme-corp_backend-engineer/sources/posting.md)" | python3 -c "import json,sys; print(json.load(sys.stdin)['similar'])"
```

**Expected**: matches what a direct `POST /similar` call with the same `jd_text` would return —
same vacancy, same similarity, same duplicate flag ([[002-similar-retrieval]] Scenario 1/3).

## Scenario 5 — Provider-agnostic structure (Constitution III / SC-004)

Run Scenario 1 once with `LLM_PROVIDER=claude` and once with `LLM_PROVIDER=ollama` (restart the
server between runs after editing `.env`). **Expected**: both responses have the identical JSON
shape (same fields, same types) and both satisfy the same grounding guarantee (every citation
verifiable against `data/example/`) — the actual wording of flags/draft text may differ, but the
structure and grounding rules must not.

## Scenario 6 — Empty JD text rejected (FR-011)

```bash
curl -s -w "\nHTTP %{http_code}\n" -G -X POST "http://localhost:8000/analyze" --data-urlencode "jd_text= "
```

**Expected**: `422 Unprocessable Entity`.

## Scenario 7 — LLM backend unreachable (FR-012)

Temporarily set an invalid `ANTHROPIC_API_KEY` (or stop the local Ollama server if using that
profile), restart the server, and repeat Scenario 1.

**Expected**: `502 Bad Gateway` with a clear message — not a `200` with an empty or
default-looking report, and not an unhandled 500.
