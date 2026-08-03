"""FastAPI app: /analyze /similar /ingest/vacancy /healthz.

M1 scaffold — only /healthz is live initially. /similar (M3) and /analyze (M4) are
implemented; /ingest/vacancy is still wired but not implemented (M2 — CLI ingestion is the
only ingestion path so far); it returns 501 rather than 404 so the API surface is stable from
day one for anything that starts integrating against it early.
"""

import json
import os
from pathlib import Path

from fastapi import Depends, FastAPI, Form, HTTPException, Request
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from pydantic import ValidationError

from vacancy_radar.filter_rules import load_filter_rules
from vacancy_radar.grounding import enforce
from vacancy_radar.llm.base import LLMProvider, LLMProviderError
from vacancy_radar.llm.claude import ClaudeProvider
from vacancy_radar.llm.ollama import OllamaProvider
from vacancy_radar.models import Report, SimilarVacancy
from vacancy_radar.retriever import Retriever

# Resolved relative to this module's own location, not the process's current working
# directory — correct regardless of how/where the installed package ends up on disk
# (specs/005-minimal-ui/research.md #6).
BASE_DIR = Path(__file__).resolve().parent

app = FastAPI(title="Vacancy Radar", version="0.1.0")
app.mount("/static", StaticFiles(directory=BASE_DIR / "static"), name="static")
templates = Jinja2Templates(directory=BASE_DIR / "templates")


def get_retriever() -> Retriever:
    return Retriever()


def get_llm_provider() -> LLMProvider:
    if os.environ.get("LLM_PROVIDER", "claude") == "ollama":
        return OllamaProvider(
            model=os.environ.get("OLLAMA_MODEL", "qwen3:8b"),
            host=os.environ.get("OLLAMA_HOST", "http://localhost:11434"),
        )
    return ClaudeProvider()


@app.get("/healthz")
def healthz() -> dict[str, str]:
    return {"status": "ok"}


def run_analysis(jd_text: str, retriever: Retriever, llm_provider: LLMProvider) -> Report:
    """Shared orchestration behind both `POST /analyze` (JSON) and `POST /ui/analyze` (HTML).

    Assumes `jd_text` is already validated as non-empty by the caller — the two routes render
    that failure differently (a 422 vs. an HTML validation message), so it isn't handled here.
    May raise `LLMProviderError`, `ValidationError`, or `json.JSONDecodeError`, which each
    caller also handles/renders differently (specs/005-minimal-ui/research.md #3).
    """
    bullets = [(b["id"], b["text"]) for b in retriever.query_bullets(jd_text)]
    similar = retriever.query_similar_vacancies(jd_text)
    filter_rules_text = load_filter_rules()

    sources = dict(bullets)
    if filter_rules_text.strip():
        sources["filter-rules"] = filter_rules_text

    candidate = llm_provider.analyze(jd_text, bullets, filter_rules_text)
    grounded = enforce(candidate, sources)

    return Report(
        score=candidate.match_band,
        flags=grounded.flags,
        gaps=grounded.gaps,
        similar=similar,
        draft_paragraph=grounded.draft_paragraph,
        draft_sentences=grounded.draft_sentences,
        citations=grounded.citations,
    )


@app.post("/analyze", response_model=Report)
def analyze(
    jd_text: str,
    retriever: Retriever = Depends(get_retriever),
    llm_provider: LLMProvider = Depends(get_llm_provider),
) -> Report:
    if not jd_text.strip():
        raise HTTPException(status_code=422, detail="jd_text must not be empty")

    try:
        return run_analysis(jd_text, retriever, llm_provider)
    except (LLMProviderError, ValidationError, json.JSONDecodeError) as exc:
        raise HTTPException(status_code=502, detail=f"LLM backend error: {exc}") from exc


@app.get("/")
def index(request: Request):
    return templates.TemplateResponse(request, "index.html", {})


@app.post("/ui/analyze")
def ui_analyze(
    request: Request,
    jd_text: str = Form(...),
    retriever: Retriever = Depends(get_retriever),
    llm_provider: LLMProvider = Depends(get_llm_provider),
):
    if not jd_text.strip():
        message = "Paste a job posting before submitting."
        return templates.TemplateResponse(request, "_error.html", {"message": message})

    try:
        report = run_analysis(jd_text, retriever, llm_provider)
    except (LLMProviderError, ValidationError, json.JSONDecodeError):
        message = (
            "The analysis backend is unavailable right now. Check your LLM_PROVIDER "
            "configuration and try again."
        )
        return templates.TemplateResponse(request, "_error.html", {"message": message})

    return templates.TemplateResponse(request, "_report.html", {"report": report})


@app.post("/similar", response_model=list[SimilarVacancy])
def similar(
    jd_text: str, retriever: Retriever = Depends(get_retriever)
) -> list[SimilarVacancy]:
    if not jd_text.strip():
        raise HTTPException(status_code=422, detail="jd_text must not be empty")
    return retriever.query_similar_vacancies(jd_text)


@app.post("/ingest/vacancy")
def ingest_vacancy(vacancy_folder: str) -> dict[str, str]:
    raise HTTPException(status_code=501, detail="Not implemented yet — see M2 in the roadmap")
