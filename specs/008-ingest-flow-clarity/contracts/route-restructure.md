# Route Contract: Path Restructuring

Every route below keeps its existing request/response shape, status codes, and behavior
byte-for-byte — only the URL path changes. `GET /`, `GET /ingest`, and `GET /healthz` are
unchanged and not listed.

| Old path | New path | Kind | Notes |
|---|---|---|---|
| `POST /analyze` | `POST /api/analyze` | JSON | Response model (`Report`), `422`/`502` behavior unchanged |
| `POST /similar` | `POST /api/similar` | JSON | Response model (`list[SimilarVacancy]`), `422` behavior unchanged |
| `POST /ui/analyze` | `POST /analyze` | HTML | Form field (`jd_text`), returned partials (`_report.html`/`_error.html`) unchanged |
| `POST /ui/ingest/draft` | `POST /ingest/draft` | HTML | Multipart `file` field, returned partial (`_ingest_draft.html`) unchanged in shape — gains `step` context value (data-model.md) |
| `POST /ui/ingest/confirm` | `POST /ingest/confirm` | HTML | Form fields unchanged, returned partial (`_ingest_result.html`) unchanged in shape — gains `step` context value |

## Implementation shape

```python
api_router = APIRouter(prefix="/api")

@api_router.post("/analyze", response_model=Report)
def analyze(...): ...

@api_router.post("/similar", response_model=list[SimilarVacancy])
def similar(...): ...

app.include_router(api_router)

@app.post("/analyze")          # was /ui/analyze
def ui_analyze(...): ...

@app.post("/ingest/draft")     # was /ui/ingest/draft
def ingest_draft(...): ...

@app.post("/ingest/confirm")   # was /ui/ingest/confirm
def ingest_confirm(...): ...
```

`run_analysis()`, `get_llm_provider()`, `get_retriever()`, `get_chroma_store()`,
`get_embedder()`, and `get_vacancy_dir()` are all untouched — only the decorator each route
function is registered under changes.

## Consumers that must be updated alongside this change

- `templates/index.html`: form `hx-post` target `/ui/analyze` → `/analyze`.
- `templates/ingest.html`: form `hx-post` target `/ui/ingest/draft` → `/ingest/draft`.
- `templates/_ingest_draft.html`: form `hx-post` target `/ui/ingest/confirm` → `/ingest/confirm`.
- `tests/test_api.py`, `tests/test_ui.py`, `tests/test_ingest_upload.py`: every `client.post(...)`
  call against an old path.
- `README.md`'s endpoint table and Quick Start.
- `CHANGELOG.md`: a `### Changed` entry under the next (unreleased) version — see plan.md's
  Constraints section for why this is the first entry in the project's history where `Changed`
  legitimately applies.
