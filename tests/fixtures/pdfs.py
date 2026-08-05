"""Programmatic PDF fixtures for extraction tests.

Built with `pypdf` (already a runtime dependency for extraction
itself) rather than committed as binary blobs - consistent with this
project's preference for seeded/generated fixtures over checked-in
binary assets. None of these are written into the committed
`tests/fixtures/vault/` tree; callers write them into `tmp_path`.
"""

from pathlib import Path

from pypdf import PdfWriter
from pypdf.generic import ContentStream, DictionaryObject, NameObject

MIN_EXTRACTABLE_CHARS = 200


def _add_text_page(
    writer: PdfWriter, text: str, *, width: float = 400, height: float = 400
) -> None:
    """Append a page to `writer` whose content stream draws `text`
    with the standard Helvetica font (no embedding needed - pypdf's
    extractor decodes it via the font's default encoding)."""
    page = writer.add_blank_page(width=width, height=height)

    font = DictionaryObject()
    font[NameObject("/Type")] = NameObject("/Font")
    font[NameObject("/Subtype")] = NameObject("/Type1")
    font[NameObject("/BaseFont")] = NameObject("/Helvetica")
    font_ref = writer._add_object(font)  # noqa: SLF001 - no public API for this

    resources = DictionaryObject()
    font_dict = DictionaryObject()
    font_dict[NameObject("/F1")] = font_ref
    resources[NameObject("/Font")] = font_dict
    page[NameObject("/Resources")] = resources

    escaped = text.replace("\\", r"\\").replace("(", r"\(").replace(")", r"\)")
    stream_data = f"BT /F1 14 Tf 20 {height - 40} Td ({escaped}) Tj ET".encode()
    content = ContentStream(None, writer)
    content.set_data(stream_data)
    page.replace_contents(content)


def write_valid_pdf(path: Path, text: str | None = None) -> None:
    """Write a real, unencrypted, single-page PDF containing `text`
    (extractable by `pypdf`), long enough to clear the
    extraction-succeeded threshold by default."""
    if text is None:
        text = (
            "The candidate should implement a rate limiter that supports "
            "a configurable window and a configurable request budget, and "
            "should include tests covering the boundary conditions, plus a "
            "short written explanation of the chosen eviction strategy."
        )
    writer = PdfWriter()
    _add_text_page(writer, text)
    with path.open("wb") as handle:
        writer.write(handle)


def write_malformed_pdf(path: Path) -> None:
    """Write a `.pdf`-named file whose bytes are not a valid PDF
    structure at all."""
    path.write_bytes(b"this is not a pdf, just garbage bytes pretending to be one")


def write_encrypted_pdf(
    path: Path, text: str | None = None, password: str = "secret"
) -> None:
    """Write a valid PDF, password-encrypted so its content can't be
    read without the password."""
    if text is None:
        text = "This content is behind a password and should never be read."
    writer = PdfWriter()
    _add_text_page(writer, text)
    writer.encrypt(password)
    with path.open("wb") as handle:
        writer.write(handle)


def write_scanned_pdf(path: Path) -> None:
    """Write a valid, unencrypted PDF with no extractable text layer -
    standing in for a scanned page (image only, no text operators in
    its content stream)."""
    writer = PdfWriter()
    page = writer.add_blank_page(width=400, height=400)
    # A path-paint operator with no text (Tj) operators at all: a
    # valid, non-empty content stream that yields zero extractable
    # characters, the same as a real scanned page's image-only stream.
    content = ContentStream(None, writer)
    content.set_data(b"0 0 400 400 re f")
    page.replace_contents(content)
    with path.open("wb") as handle:
        writer.write(handle)
