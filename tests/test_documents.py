from pathlib import Path

from docx import Document
from reportlab.pdfgen import canvas

from vacancy_radar.documents import IMAGE_EXTENSIONS, IMAGE_MEDIA_TYPES, extract_text

KNOWN_TEXT = "Acme Corp Backend Engineer"


def _make_pdf(path: Path, text: str) -> None:
    c = canvas.Canvas(str(path))
    c.drawString(50, 750, text)
    c.save()


def _make_docx(path: Path, text: str) -> None:
    document = Document()
    document.add_paragraph(text)
    document.save(str(path))


def test_image_media_types_covers_every_image_extension():
    assert set(IMAGE_MEDIA_TYPES) == IMAGE_EXTENSIONS


def test_extract_text_from_pdf(tmp_path: Path):
    path = tmp_path / "posting.pdf"
    _make_pdf(path, KNOWN_TEXT)
    assert KNOWN_TEXT in extract_text(path)


def test_extract_text_from_docx(tmp_path: Path):
    path = tmp_path / "posting.docx"
    _make_docx(path, KNOWN_TEXT)
    assert KNOWN_TEXT in extract_text(path)


def test_extract_text_returns_empty_string_for_image(tmp_path: Path):
    path = tmp_path / "posting.png"
    path.write_bytes(b"not a real png, just needs to exist")
    # No local OCR (specs/007-vision-drafting) — vision-capable LLMs read image bytes directly.
    assert extract_text(path) == ""


def test_extract_text_from_plain_text_file(tmp_path: Path):
    path = tmp_path / "posting.txt"
    path.write_text(KNOWN_TEXT)
    assert extract_text(path) == KNOWN_TEXT


def test_extract_text_returns_empty_string_for_missing_file(tmp_path: Path):
    assert extract_text(tmp_path / "does-not-exist.pdf") == ""


def test_extract_text_returns_empty_string_for_corrupted_pdf(tmp_path: Path):
    path = tmp_path / "corrupted.pdf"
    path.write_bytes(b"not actually a pdf")
    assert extract_text(path) == ""
