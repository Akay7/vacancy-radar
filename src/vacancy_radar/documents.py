"""Local, offline text extraction for vacancy source documents (specs/006-vacancy-upload).

Every format is handled by a single-purpose, local library — no cloud OCR/vision API
(Constitution I). `extract_text()` never raises for an unreadable/empty document; it returns
"" so callers can degrade gracefully to manual entry (FR-008) rather than treating extraction
failure as fatal.

Images have no local extraction at all (specs/007-vision-drafting removed local OCR
entirely) — a vision-capable `LLMProvider` reads image bytes directly instead
(`llm/draft_vacancy_metadata`); `extract_text()` returns "" for them like any other
unsupported input.
"""

from pathlib import Path

from docx import Document
from pypdf import PdfReader

IMAGE_EXTENSIONS = {".png", ".jpg", ".jpeg"}
IMAGE_MEDIA_TYPES = {".png": "image/png", ".jpg": "image/jpeg", ".jpeg": "image/jpeg"}


def _extract_pdf(path: Path) -> str:
    try:
        reader = PdfReader(str(path))
    except Exception:
        return ""
    return "\n".join(page.extract_text() or "" for page in reader.pages).strip()


def _extract_docx(path: Path) -> str:
    try:
        document = Document(str(path))
    except Exception:
        return ""
    return "\n".join(p.text for p in document.paragraphs).strip()


def extract_text(path: Path) -> str:
    """Best-effort text extraction, dispatched by file extension.

    Returns "" for an unsupported/unreadable/empty document rather than raising — extraction
    failure must never block logging a vacancy (FR-008). Images always return "" — there is no
    local extraction for them (see module docstring).
    """
    suffix = path.suffix.lower()
    if suffix == ".pdf":
        return _extract_pdf(path)
    if suffix == ".docx":
        return _extract_docx(path)
    if suffix in IMAGE_EXTENSIONS:
        return ""
    try:
        return path.read_text().strip()
    except (OSError, UnicodeDecodeError):
        return ""
