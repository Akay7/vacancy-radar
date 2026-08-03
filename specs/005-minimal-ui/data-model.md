# Data Model: Minimal UI

No new persisted or cached state. One additive change to an existing Pydantic model, plus the
in-process shapes the templates render against.

## `DraftSentence` (new)

```python
class DraftSentence(BaseModel):
    text: str
    citation: Citation
```

One grounded sentence of the draft opening paragraph, paired with the citation that grounds it.
`Citation` is the existing `{quote: str, source_id: str}` model from
[[003-analyze-report-generation]] — unchanged.

## `Report` (extended)

```python
class Report(BaseModel):
    score: MatchBand
    flags: list[Flag]
    gaps: list[str]
    similar: list[SimilarVacancy]
    draft_paragraph: str          # unchanged — kept for backward compatibility
    draft_sentences: list[DraftSentence]   # NEW — structured pairing for the UI
    citations: list[Citation]     # unchanged
```

`draft_sentences` is built by `grounding.enforce()` from the same loop that already produces
`draft_paragraph`/`citations` — for each kept `CandidateSentence`, it appends one
`DraftSentence(text=sentence.text, citation=Citation(quote=.., source_id=..))`. Invariant:
`draft_paragraph == " ".join(d.text for d in draft_sentences)` always holds — the two fields are
two views of the same underlying data, kept in sync by construction, not by convention.

`GroundedContent` (the internal dataclass `enforce()` returns, `src/vacancy_radar/grounding.py`)
gains the matching `draft_sentences: list[DraftSentence]` field.

## Template-rendering shapes (not persisted, not new Pydantic models)

The templates render directly against the existing `Report` object (now including
`draft_sentences`) passed into Jinja2's context — no separate view-model layer, since `Report`
already has everything each template needs:

- **`index.html`**: no data — just the paste-JD form.
- **`_report.html`**: iterates `report.flags` (label/severity/reason), `report.gaps`,
  `report.similar` (company/position/outcome/is_duplicate), and `report.draft_sentences`
  (text + citation, rendered inline together) — falls back to a plain "nothing to show yet"
  message when `flags`, `citations`, and `draft_paragraph` are all empty (FR-009).
- **`_error.html`**: a single `message: str` context variable — either the validation message
  ("paste a job posting") or the backend-failure message, chosen by the route, never the raw
  exception text (FR-007 — plain-language, not a stack trace).
