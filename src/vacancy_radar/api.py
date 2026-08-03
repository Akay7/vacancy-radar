"""FastAPI app: /analyze, /similar, /ingest (upload UI), /healthz.

M1 scaffold — only /healthz was live initially. /similar, /analyze, and the /ui/analyze +
/ingest upload flow are all implemented now. The original M1 stub, a bare `POST /ingest/vacancy`
taking a `vacancy_folder` path string, was removed (never implemented, never returned anything
but 501) in favor of the real upload flow at GET /ingest + POST /ui/ingest/draft +
POST /ui/ingest/confirm (specs/006-vacancy-upload), matching the existing /ui/analyze
naming convention rather than reusing that original path.
"""

import json
import os
import shutil
import uuid
from pathlib import Path

import yaml
from fastapi import Depends, FastAPI, Form, HTTPException, Request, UploadFile
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from pydantic import ValidationError

from vacancy_radar import documents
from vacancy_radar import ingest as ingest_lib
from vacancy_radar.chroma_store import ChromaStore
from vacancy_radar.embedder import Embedder, SentenceTransformersEmbedder
from vacancy_radar.filter_rules import load_filter_rules
from vacancy_radar.grounding import enforce
from vacancy_radar.llm.base import LLMProvider, LLMProviderError
from vacancy_radar.llm.claude import ClaudeProvider
from vacancy_radar.llm.ollama import OllamaProvider
from vacancy_radar.models import Report, SimilarVacancy, VacancyRecord
from vacancy_radar.retriever import Retriever

PENDING_UPLOADS_DIR = Path(".cache/pending-uploads")
SUPPORTED_UPLOAD_EXTENSIONS = {".pdf", ".docx", ".png", ".jpg", ".jpeg", ".txt", ".md"}

# Resolved relative to this module's own location, not the process's current working
# directory — correct regardless of how/where the installed package ends up on disk
# (specs/005-minimal-ui/research.md #6).
BASE_DIR = Path(__file__).resolve().parent

app = FastAPI(title="Vacancy Radar", version="0.1.0")
app.mount("/static", StaticFiles(directory=BASE_DIR / "static"), name="static")
templates = Jinja2Templates(directory=BASE_DIR / "templates")


def get_chroma_store() -> ChromaStore:
    return ChromaStore(ingest_lib.CHROMA_PATH)


def get_embedder() -> Embedder:
    return SentenceTransformersEmbedder()


def get_retriever(
    store: ChromaStore = Depends(get_chroma_store),
    embedder: Embedder = Depends(get_embedder),
) -> Retriever:
    """Composed from get_chroma_store()/get_embedder() so POST /ui/ingest/confirm can write to
    (and /similar, /analyze read from) the exact same store — overriding just those two
    dependencies in tests keeps every route consistent without also overriding get_retriever
    (specs/006-vacancy-upload)."""
    return Retriever(store=store, embedder=embedder)


def get_vacancy_dir() -> Path:
    return Path(os.environ.get("VACANCY_DIR", "data/example/vacancies"))


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


@app.get("/ingest")
def ingest_page(request: Request):
    return templates.TemplateResponse(request, "ingest.html", {})


@app.post("/ui/ingest/draft")
def ingest_draft(
    request: Request,
    file: UploadFile,
    llm_provider: LLMProvider = Depends(get_llm_provider),
):
    filename = file.filename or ""
    suffix = Path(filename).suffix.lower()
    if not filename or suffix not in SUPPORTED_UPLOAD_EXTENSIONS:
        message = (
            "Unsupported file type. Please upload an image (.png/.jpg/.jpeg), PDF, DOCX, or "
            "plain text (.txt/.md) file."
        )
        return templates.TemplateResponse(request, "_error.html", {"message": message})

    token = uuid.uuid4().hex
    staging_dir = PENDING_UPLOADS_DIR / token
    staging_dir.mkdir(parents=True, exist_ok=True)
    staged_path = staging_dir / filename
    staged_path.write_bytes(file.file.read())

    # Images have no local text extraction (specs/007-vision-drafting removed OCR) — the LLM
    # reads the image bytes directly instead, so extract_text() is never called for them.
    image_bytes: bytes | None = None
    image_media_type: str | None = None
    if suffix in documents.IMAGE_EXTENSIONS:
        image_bytes = staged_path.read_bytes()
        image_media_type = documents.IMAGE_MEDIA_TYPES[suffix]
        document_text = ""
    else:
        document_text = documents.extract_text(staged_path)

    draft = None
    message = None
    if not document_text and image_bytes is None:
        message = (
            "Couldn't read any text from this document — fill in every field manually below."
        )
    else:
        try:
            draft = llm_provider.draft_vacancy_metadata(
                document_text, image_bytes=image_bytes, image_media_type=image_media_type
            )
        except (LLMProviderError, ValidationError, json.JSONDecodeError):
            if image_bytes is not None:
                message = (
                    "Your configured LLM backend couldn't read this image directly — "
                    "image-based drafting isn't available with the current setup. Fill in "
                    "every field manually below, or switch to a vision-capable model."
                )
            else:
                message = (
                    "Automatic drafting didn't work — fill in every field manually below."
                )

    return templates.TemplateResponse(
        request,
        "_ingest_draft.html",
        {
            "draft": draft,
            "message": message,
            "upload_token": token,
            "original_filename": filename,
        },
    )


@app.post("/ui/ingest/confirm")
def ingest_confirm(
    request: Request,
    upload_token: str = Form(...),
    original_filename: str = Form(...),
    # Not `Form(...)` (required): FastAPI treats an empty-string submission as a *missing*
    # field for required Form params and raises a raw 422 before this handler ever runs —
    # which would break this route's "always render HTML" contract. Defaulting to "" and
    # validating explicitly below keeps every rejection a rendered, friendly message.
    company: str = Form(""),
    position: str = Form(""),
    date: str = Form(""),
    outcome: str = Form(""),
    vacancy_dir: Path = Depends(get_vacancy_dir),
    store: ChromaStore = Depends(get_chroma_store),
    embedder: Embedder = Depends(get_embedder),
):
    def result(message: str, success: bool):
        return templates.TemplateResponse(
            request, "_ingest_result.html", {"message": message, "success": success}
        )

    if not (company.strip() and position.strip() and date.strip() and outcome.strip()):
        return result("Please fill in every field before saving.", success=False)

    try:
        record = VacancyRecord(company=company, position=position, date=date, outcome=outcome)
    except ValidationError:
        return result(
            "Please check the company/position/date fields — they couldn't be saved as "
            "entered.",
            success=False,
        )

    staging_dir = PENDING_UPLOADS_DIR / upload_token
    staged_path = staging_dir / original_filename
    if not staged_path.is_file():
        return result(
            "This upload has expired or was already saved — please upload the document again.",
            success=False,
        )

    key = ingest_lib.natural_key(record)
    folder = vacancy_dir / key
    if folder.exists():
        return result(
            f"A vacancy already exists at '{key}'. Edit the date/company/position if this is "
            "a different posting, or resolve the existing folder manually.",
            success=False,
        )

    sources_dir = folder / "sources"
    sources_dir.mkdir(parents=True)
    (folder / "vacancy.yaml").write_text(
        yaml.safe_dump(
            {"company": company, "position": position, "date": date, "outcome": outcome},
            sort_keys=False,
        )
    )
    shutil.move(str(staged_path), str(sources_dir / original_filename))
    staging_dir.rmdir()

    summary = ingest_lib.ingest_vacancies(vacancy_dir, store=store, embedder=embedder)
    conflict = next(
        (c for c in summary.vacancies_conflicting if c.natural_key == key), None
    )
    if conflict:
        return result(
            f"Saved to disk, but '{key}' conflicts with another folder already using the same "
            f"date/company/position: {', '.join(conflict.folders)}. Resolve the conflict by "
            "hand (edit or remove one of them), then run `vacancy-radar sync`.",
            success=False,
        )

    return result(f"Saved vacancy '{key}' — it's already searchable.", success=True)


@app.post("/similar", response_model=list[SimilarVacancy])
def similar(
    jd_text: str, retriever: Retriever = Depends(get_retriever)
) -> list[SimilarVacancy]:
    if not jd_text.strip():
        raise HTTPException(status_code=422, detail="jd_text must not be empty")
    return retriever.query_similar_vacancies(jd_text)
