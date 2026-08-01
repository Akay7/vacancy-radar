# API Contract: `POST /analyze`

## Request

Same convention as `/similar` ([[002-similar-retrieval]]'s Endpoint signature decision) and the
existing `/analyze` stub:

```
POST /analyze?jd_text=<pasted job description text>
```

`jd_text` is a required, non-empty (after stripping whitespace) string query parameter.

## Response

`200 OK`, body: `Report` (see data-model.md).

```json
{
  "score": "good",
  "flags": [
    {
      "label": "Backend API experience",
      "severity": "green",
      "reason": "You've built a FastAPI service handling real production load — 'built a FastAPI service handling 200 req/s with async SQLAlchemy and Redis caching.'"
    },
    {
      "label": "Kubernetes",
      "severity": "red",
      "reason": "The posting asks for hands-on Kubernetes experience; no ingested bullet mentions it."
    }
  ],
  "gaps": ["No direct Kubernetes experience found in ingested bullets"],
  "similar": [
    {
      "vacancy_id": "2026-01-15_acme-corp_backend-engineer",
      "company": "Acme Corp",
      "position": "Backend Engineer",
      "outcome": "applied",
      "similarity": 0.87,
      "excerpt": "...",
      "is_duplicate": false
    }
  ],
  "draft_paragraph": "I built a FastAPI service handling 200 req/s with async SQLAlchemy and Redis caching, which lines up closely with this role's core API work.",
  "citations": [
    {"quote": "built a FastAPI service handling 200 req/s with async SQLAlchemy and Redis caching", "source_id": "bullet-2"}
  ]
}
```

An index with no ingested bullets returns `200` with `flags: []`, `draft_paragraph: ""`,
`citations: []`, and `gaps` listing what couldn't be assessed — never a fabricated report
(FR-010, User Story 2 Scenario 2).

## Error responses

- `422 Unprocessable Entity` — `jd_text` missing, empty, or whitespace-only (FR-011), same
  convention as `/similar`.
- `502 Bad Gateway` — the configured LLM backend (Claude or Ollama) is unreachable or
  misconfigured (FR-012) — a clear, actionable error rather than a silently empty or
  default-looking report.

## Cross-cutting

- Read-only: never writes to the Chroma store, the manifest, or any vacancy folder.
- Depends on [[001-ingestion-cli]] having been run (bullets ingested) for a non-empty report,
  and on [[002-similar-retrieval]]'s retrieval logic for the `similar` field — but degrades
  gracefully (FR-010) if bullets are missing entirely.
- Response structure and grounding guarantee are identical regardless of `LLM_PROVIDER`
  (`claude` or `ollama`) — Constitution III.
- Every claim in `flags` and `draft_paragraph` has already passed the shared grounding
  validator (`grounding.enforce()`, research.md) before this response is built — `citations` is
  the checkable record of that, not raw LLM output.
