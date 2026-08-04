"""FastAPI app: /api/analyze, /api/similar (JSON), /, /analyze, /ingest, /ingest/draft,
/ingest/confirm (HTML), /healthz.

M1 scaffold — only /healthz was live initially. The JSON API lives under /api/* and the
browser-facing HTML routes are unprefixed (specs/008-ingest-flow-clarity route restructuring —
previously the JSON routes were unprefixed and the HTML routes carried a /ui/ prefix). The
original M1 stub, a bare `POST /ingest/vacancy` taking a `vacancy_folder` path string, was
removed (never implemented, never returned anything but 501) in favor of the real upload flow at
GET /ingest + POST /ingest/draft + POST /ingest/confirm (specs/006-vacancy-upload).
"""

import json
import os
import shutil
import uuid
from pathlib import Path
from typing import NamedTuple

import yaml
from fastapi import APIRouter, Depends, FastAPI, File, Form, HTTPException, Request, UploadFile
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from langchain.chat_models import init_chat_model
from langchain_core.embeddings import Embeddings
from pydantic import ValidationError

from vacancy_radar import documents
from vacancy_radar import ingest as ingest_lib
from vacancy_radar.chroma_store import ChromaStore
from vacancy_radar.embedder import get_embeddings
from vacancy_radar.filter_rules import load_filter_rules
from vacancy_radar.grounding import enforce
from vacancy_radar.llm.base import LLMProvider, LLMProviderError
from vacancy_radar.llm.config import LLMConfig
from vacancy_radar.models import DraftVacancyMetadata, Report, SimilarVacancy, VacancyRecord
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
api_router = APIRouter(prefix="/api")


def get_chroma_store() -> ChromaStore:
    return ChromaStore(ingest_lib.CHROMA_PATH)


def get_embedder() -> Embeddings:
    return get_embeddings()


def get_retriever(
    store: ChromaStore = Depends(get_chroma_store),
    embedder: Embeddings = Depends(get_embedder),
) -> Retriever:
    """Composed from get_chroma_store()/get_embedder() so POST /ingest/confirm can write to
    (and /api/similar, /api/analyze read from) the exact same store — overriding just those two
    dependencies in tests keeps every route consistent without also overriding get_retriever
    (specs/006-vacancy-upload)."""
    return Retriever(store=store, embedder=embedder)


def get_vacancy_dir() -> Path:
    return Path(os.environ.get("VACANCY_DIR", "data/example/vacancies"))


def get_llm_provider() -> LLMProvider:
    """The only place that decides which `BaseChatModel` `LLMProvider` wraps — `LLMConfig`
    (llm/config.py) is just settings; resolving them into a live chat model is app wiring, not
    config, so it lives here instead."""
    config = LLMConfig()
    if not config.llm_provider or not config.llm_model:
        raise LLMProviderError(
            "LLM_PROVIDER and LLM_MODEL must both be set, e.g. LLM_PROVIDER=anthropic "
            "LLM_MODEL=claude-opus-5 or LLM_PROVIDER=ollama LLM_MODEL=qwen3:8b — see the "
            "README for the full list of supported providers."
        )
    try:
        chat_model = init_chat_model(
            config.llm_model, model_provider=config.llm_provider, base_url=config.llm_base_url
        )
    except (ValueError, ImportError) as exc:
        raise LLMProviderError(
            f"Couldn't initialize LLM_PROVIDER={config.llm_provider!r} "
            f"LLM_MODEL={config.llm_model!r}: {exc}"
        ) from exc
    return LLMProvider(chat_model)


@app.get("/healthz")
def healthz() -> dict[str, str]:
    return {"status": "ok"}


def run_analysis(jd_text: str, retriever: Retriever, llm_provider: LLMProvider) -> Report:
    """Shared orchestration behind both `POST /api/analyze` (JSON) and `POST /analyze` (HTML).

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


@api_router.post("/analyze", response_model=Report)
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
    return templates.TemplateResponse(request, "index.html", {"active_page": "analyze"})


@app.post("/analyze")
def ui_analyze(
    request: Request,
    jd_text: str = Form(""),
    file: UploadFile | None = File(None),
    retriever: Retriever = Depends(get_retriever),
    llm_provider: LLMProvider = Depends(get_llm_provider),
):
    if file is not None and file.filename:
        staged = _stage_and_read_upload(file)
        if isinstance(staged, str):
            return templates.TemplateResponse(request, "_error.html", {"message": staged})

        draft, draft_message = _draft_metadata(staged, llm_provider)
        query_text, report_message = _query_text_for_analysis(staged, llm_provider)

        report = None
        if query_text:
            try:
                report = run_analysis(query_text, retriever, llm_provider)
            except (LLMProviderError, ValidationError, json.JSONDecodeError):
                report_message = (
                    "The analysis backend is unavailable right now. Check your LLM_PROVIDER/"
                    "LLM_MODEL configuration and try again."
                )

        return templates.TemplateResponse(
            request,
            "_report.html",
            {
                "report": report,
                "report_message": report_message,
                "draft": draft,
                "message": draft_message,
                "upload_token": staged.token,
                "original_filename": staged.filename,
                "step": "review" if draft else "error",
            },
        )

    if not jd_text.strip():
        message = "Paste a job posting before submitting."
        return templates.TemplateResponse(request, "_error.html", {"message": message})

    try:
        report = run_analysis(jd_text, retriever, llm_provider)
    except (LLMProviderError, ValidationError, json.JSONDecodeError):
        message = (
            "The analysis backend is unavailable right now. Check your ANTHROPIC_API_KEY "
            "or Ollama configuration and try again."
        )
        return templates.TemplateResponse(request, "_error.html", {"message": message})

    return templates.TemplateResponse(request, "_report.html", {"report": report})


@app.get("/ingest")
def ingest_page(request: Request):
    return templates.TemplateResponse(request, "ingest.html", {"active_page": "ingest"})


class StagedUpload(NamedTuple):
    """A file staged to disk under PENDING_UPLOADS_DIR, plus what was read from it for LLM
    use — shared by POST /ingest/draft and POST /analyze's upload branch
    (specs/009-analyze-and-log-vacancy) so both stage/extract identically."""

    token: str
    filename: str
    document_text: str
    image_bytes: bytes | None
    image_media_type: str | None


def _stage_and_read_upload(file: UploadFile) -> StagedUpload | str:
    """Stages an uploaded file and reads its content for LLM use. Returns a `StagedUpload` on
    success, or a user-facing error message string if the file type isn't supported."""
    filename = file.filename or ""
    suffix = Path(filename).suffix.lower()
    if not filename or suffix not in SUPPORTED_UPLOAD_EXTENSIONS:
        return (
            "Unsupported file type. Please upload an image (.png/.jpg/.jpeg), PDF, DOCX, or "
            "plain text (.txt/.md) file."
        )

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

    return StagedUpload(token, filename, document_text, image_bytes, image_media_type)


def _draft_metadata(
    staged: StagedUpload, llm_provider: LLMProvider
) -> tuple[DraftVacancyMetadata | None, str | None]:
    """Drafts company/position/date from a staged upload, or returns a user-facing message
    explaining why drafting didn't happen — shared by POST /ingest/draft and POST /analyze's
    upload branch (specs/009-analyze-and-log-vacancy)."""
    if not staged.document_text and staged.image_bytes is None:
        return None, (
            "Couldn't read any text from this document — fill in every field manually below."
        )

    try:
        draft = llm_provider.draft_vacancy_metadata(
            staged.document_text,
            image_bytes=staged.image_bytes,
            image_media_type=staged.image_media_type,
        )
        return draft, None
    except (LLMProviderError, ValidationError, json.JSONDecodeError):
        if staged.image_bytes is not None:
            return None, (
                "Your configured LLM backend couldn't read this image directly — "
                "image-based drafting isn't available with the current setup. Fill in "
                "every field manually below, or switch to a vision-capable model."
            )
        return None, "Automatic drafting didn't work — fill in every field manually below."


def _query_text_for_analysis(
    staged: StagedUpload, llm_provider: LLMProvider
) -> tuple[str | None, str | None]:
    """Resolves the text `run_analysis()` should treat as `jd_text` for a staged upload, or a
    user-facing message explaining why analysis can't proceed (specs/009-analyze-and-log-vacancy).

    Non-image uploads already have real text via `documents.extract_text()`. Images have none —
    there's no local OCR (specs/007-vision-drafting) — so `extract_document_text()`'s vision
    transcription is used instead, purely to give retrieval something to embed
    (research.md #2); it never fabricates content, so a failure here surfaces the same way a
    missing document_text does.
    """
    if staged.image_bytes is not None:
        try:
            text = llm_provider.extract_document_text(staged.image_bytes, staged.image_media_type)
            return text, None
        except LLMProviderError:
            return None, (
                "Your configured LLM backend couldn't read this image directly — "
                "image-based analysis isn't available with the current setup."
            )

    if staged.document_text:
        return staged.document_text, None
    return None, "Couldn't read any text from this document to analyze."


@app.post("/ingest/draft")
def ingest_draft(
    request: Request,
    file: UploadFile,
    llm_provider: LLMProvider = Depends(get_llm_provider),
):
    staged = _stage_and_read_upload(file)
    if isinstance(staged, str):
        return templates.TemplateResponse(request, "_error.html", {"message": staged})

    draft, message = _draft_metadata(staged, llm_provider)

    return templates.TemplateResponse(
        request,
        "_ingest_draft.html",
        {
            "draft": draft,
            "message": message,
            "upload_token": staged.token,
            "original_filename": staged.filename,
            "step": "review" if draft else "error",
        },
    )


@app.post("/ingest/confirm")
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
    embedder: Embeddings = Depends(get_embedder),
):
    def result(message: str, success: bool):
        return templates.TemplateResponse(
            request,
            "_ingest_result.html",
            {"message": message, "success": success, "step": "done" if success else "error"},
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


@api_router.post("/similar", response_model=list[SimilarVacancy])
def similar(
    jd_text: str, retriever: Retriever = Depends(get_retriever)
) -> list[SimilarVacancy]:
    if not jd_text.strip():
        raise HTTPException(status_code=422, detail="jd_text must not be empty")
    return retriever.query_similar_vacancies(jd_text)


app.include_router(api_router)
