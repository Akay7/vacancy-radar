import contextlib
import io
import sys
from pathlib import Path
from typing import TYPE_CHECKING

from vacancy_radar import frontmatter
from vacancy_radar.index.extract import extract_to_sidecar
from vacancy_radar.vault.hashing import content_hash
from vacancy_radar.vault.paths import sidecar_path_for

if TYPE_CHECKING:
    from vacancy_radar.vault.reader import VaultWarning

_FIXTURES_DIR = Path(__file__).resolve().parent.parent / "fixtures"
if str(_FIXTURES_DIR) not in sys.path:
    sys.path.insert(0, str(_FIXTURES_DIR))

from pdfs import (  # noqa: E402
    write_encrypted_pdf,
    write_malformed_pdf,
    write_scanned_pdf,
    write_valid_pdf,
)

# --- Section 5: eligibility and successful extraction ---------------------


def test_py_source_gets_no_sidecar(tmp_path: Path) -> None:
    source = tmp_path / "solution.py"
    source.write_text("print('hello')\n", encoding="utf-8")
    warnings: list[VaultWarning] = []

    result = extract_to_sidecar(source, warnings)

    assert result is None
    assert not sidecar_path_for(source).exists()
    assert warnings == []


def test_zip_source_gets_no_sidecar(tmp_path: Path) -> None:
    source = tmp_path / "submission.zip"
    source.write_bytes(b"PK\x03\x04fake zip bytes")
    warnings: list[VaultWarning] = []

    result = extract_to_sidecar(source, warnings)

    assert result is None
    assert not sidecar_path_for(source).exists()
    assert warnings == []


def test_valid_pdf_extraction_writes_sidecar_with_text(tmp_path: Path) -> None:
    source = tmp_path / "spec.pdf"
    write_valid_pdf(source)
    warnings: list[VaultWarning] = []

    result = extract_to_sidecar(source, warnings)

    assert result == sidecar_path_for(source)
    assert result is not None
    metadata, body = frontmatter.parse(result.read_text(encoding="utf-8"))

    assert metadata["extracted_from"] == "spec.pdf"
    assert metadata["source_hash"] == f"sha256:{content_hash(source)}"
    assert metadata["extractor"].startswith("pypdf")
    assert metadata["extracted_at"]
    assert metadata["manually_corrected"] is False
    assert body.strip()
    assert warnings == []


# --- Section 6: regeneration gating ----------------------------------------


def test_reextracting_with_unchanged_source_hash_is_a_noop(tmp_path: Path) -> None:
    source = tmp_path / "spec.pdf"
    write_valid_pdf(source)
    warnings: list[VaultWarning] = []
    extract_to_sidecar(source, warnings)
    sidecar_path = sidecar_path_for(source)
    before = sidecar_path.read_bytes()

    result = extract_to_sidecar(source, warnings)

    assert result == sidecar_path
    assert sidecar_path.read_bytes() == before


def test_changed_source_hash_regenerates_the_sidecar(tmp_path: Path) -> None:
    source = tmp_path / "spec.pdf"
    write_valid_pdf(source, text="A" * 300)
    warnings: list[VaultWarning] = []
    extract_to_sidecar(source, warnings)
    sidecar_path = sidecar_path_for(source)
    first_hash = content_hash(source)

    write_valid_pdf(source, text="B" * 300)
    second_hash = content_hash(source)
    assert second_hash != first_hash

    extract_to_sidecar(source, warnings)

    metadata, _ = frontmatter.parse(sidecar_path.read_text(encoding="utf-8"))
    assert metadata["source_hash"] == f"sha256:{second_hash}"


def test_manually_corrected_sidecar_is_never_regenerated(tmp_path: Path) -> None:
    source = tmp_path / "spec.pdf"
    write_valid_pdf(source, text="A" * 300)
    sidecar_path = sidecar_path_for(source)
    warnings: list[VaultWarning] = []
    extract_to_sidecar(source, warnings)

    metadata, _ = frontmatter.parse(sidecar_path.read_text(encoding="utf-8"))
    metadata["manually_corrected"] = True
    corrected_body = "Hand-verified extracted text."
    sidecar_path.write_text(
        frontmatter.serialize(metadata, corrected_body), encoding="utf-8"
    )
    corrected_bytes = sidecar_path.read_bytes()

    write_valid_pdf(source, text="B" * 300)  # source_hash now stale
    warnings = []
    result = extract_to_sidecar(source, warnings)

    assert result == sidecar_path
    assert sidecar_path.read_bytes() == corrected_bytes
    assert any(w.kind == "stale_sidecar" for w in warnings)


# --- Section 7: failure modes -----------------------------------------------


def test_encrypted_pdf_writes_empty_sidecar_plus_warning(tmp_path: Path) -> None:
    source = tmp_path / "locked.pdf"
    write_encrypted_pdf(source)
    warnings: list[VaultWarning] = []

    result = extract_to_sidecar(source, warnings)

    assert result is not None
    _, body = frontmatter.parse(result.read_text(encoding="utf-8"))
    assert body.strip() == ""
    assert any(w.kind == "encrypted_pdf" for w in warnings)


def test_malformed_pdf_writes_empty_sidecar_plus_warning(tmp_path: Path) -> None:
    source = tmp_path / "broken.pdf"
    write_malformed_pdf(source)
    warnings: list[VaultWarning] = []

    result = extract_to_sidecar(source, warnings)

    assert result is not None
    _, body = frontmatter.parse(result.read_text(encoding="utf-8"))
    assert body.strip() == ""
    assert any(w.kind == "malformed_pdf" for w in warnings)


def test_scanned_pdf_writes_empty_sidecar_plus_warning(tmp_path: Path) -> None:
    source = tmp_path / "scan.pdf"
    write_scanned_pdf(source)
    warnings: list[VaultWarning] = []

    result = extract_to_sidecar(source, warnings)

    assert result is not None
    _, body = frontmatter.parse(result.read_text(encoding="utf-8"))
    assert body.strip() == ""
    assert any(w.kind == "empty_extraction" for w in warnings)


def test_pdf_under_200_chars_is_treated_as_extraction_failed(tmp_path: Path) -> None:
    source = tmp_path / "short.pdf"
    write_valid_pdf(source, text="Too short.")
    warnings: list[VaultWarning] = []

    result = extract_to_sidecar(source, warnings)

    assert result is not None
    _, body = frontmatter.parse(result.read_text(encoding="utf-8"))
    assert body.strip() == ""
    assert any(w.kind == "empty_extraction" for w in warnings)


def test_hand_corrected_scanned_sidecar_is_left_untouched(tmp_path: Path) -> None:
    source = tmp_path / "scan.pdf"
    write_scanned_pdf(source)
    sidecar_path = sidecar_path_for(source)
    warnings: list[VaultWarning] = []
    extract_to_sidecar(source, warnings)

    metadata, _ = frontmatter.parse(sidecar_path.read_text(encoding="utf-8"))
    metadata["manually_corrected"] = True
    sidecar_path.write_text(
        frontmatter.serialize(metadata, "Hand-typed text from the scan."),
        encoding="utf-8",
    )
    corrected_bytes = sidecar_path.read_bytes()

    result = extract_to_sidecar(source, [])

    assert result == sidecar_path
    assert sidecar_path.read_bytes() == corrected_bytes


def test_no_output_on_stdout_or_stderr_during_failing_extractions(
    tmp_path: Path,
) -> None:
    encrypted = tmp_path / "locked.pdf"
    malformed = tmp_path / "broken.pdf"
    scanned = tmp_path / "scan.pdf"
    write_encrypted_pdf(encrypted)
    write_malformed_pdf(malformed)
    write_scanned_pdf(scanned)

    out, err = io.StringIO(), io.StringIO()
    with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
        for source in (encrypted, malformed, scanned):
            extract_to_sidecar(source, [])

    assert out.getvalue() == ""
    assert err.getvalue() == ""
