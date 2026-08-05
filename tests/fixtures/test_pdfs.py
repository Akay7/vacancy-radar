from pathlib import Path

import pytest
from pdfs import (
    MIN_EXTRACTABLE_CHARS,
    write_encrypted_pdf,
    write_malformed_pdf,
    write_scanned_pdf,
    write_valid_pdf,
)
from pypdf import PdfReader
from pypdf.errors import PdfReadError


def test_valid_pdf_is_readable_and_yields_extractable_text(tmp_path: Path) -> None:
    path = tmp_path / "spec.pdf"
    write_valid_pdf(path)

    reader = PdfReader(path)
    text = reader.pages[0].extract_text()

    assert not reader.is_encrypted
    assert len(text) >= MIN_EXTRACTABLE_CHARS


def test_malformed_pdf_raises_when_read(tmp_path: Path) -> None:
    path = tmp_path / "broken.pdf"
    write_malformed_pdf(path)

    with pytest.raises(PdfReadError):
        PdfReader(path)


def test_encrypted_pdf_is_marked_encrypted_and_unreadable_without_password(
    tmp_path: Path,
) -> None:
    path = tmp_path / "locked.pdf"
    write_encrypted_pdf(path, password="hunter2")

    reader = PdfReader(path)

    assert reader.is_encrypted
    with pytest.raises(Exception):  # noqa: B017,PT011 - pypdf's own decrypt-required error
        reader.pages[0].extract_text()


def test_scanned_pdf_is_readable_but_has_no_extractable_text(tmp_path: Path) -> None:
    path = tmp_path / "scan.pdf"
    write_scanned_pdf(path)

    reader = PdfReader(path)
    text = reader.pages[0].extract_text()

    assert not reader.is_encrypted
    assert text == ""
