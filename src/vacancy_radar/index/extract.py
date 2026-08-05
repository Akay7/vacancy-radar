"""PDF text extraction into git-tracked markdown sidecars.

Eligibility is extension-based (`.pdf` only): the brief describes it as
"code and archives under `takehome/` get no sidecar," but stage 2
shipped a flat `documents/` layout with no `takehome/` subdirectory
(every kind lives together, distinguished by `DocumentKind`, not path)
- see design.md. Extension-based eligibility is behaviorally equivalent
for every case the brief lists and needs no directory-shape assumption.

Every failure mode - encrypted, malformed, too little text - writes an
empty-body sidecar plus a warning, never raises, never prints.
Regeneration is gated on `source_hash`: unchanged, a no-op; changed,
regenerate; changed but `manually_corrected: true`, leave it and warn
that it's stale instead.
"""

import logging
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pypdf
from pypdf import PdfReader

from vacancy_radar import frontmatter
from vacancy_radar.frontmatter import FrontmatterError
from vacancy_radar.vault.hashing import content_hash
from vacancy_radar.vault.paths import sidecar_path_for
from vacancy_radar.vault.reader import VaultWarning

# pypdf logs malformed/encrypted-PDF problems via the stdlib `logging`
# module. With no handler configured anywhere in the process, Python's
# "handler of last resort" writes them straight to stderr. Silence that
# here: every failure this module cares about is reported as a
# VaultWarning instead, never as output on stdout or stderr.
logging.getLogger("pypdf").addHandler(logging.NullHandler())
logging.getLogger("pypdf").propagate = False

ELIGIBLE_SUFFIXES = frozenset({".pdf"})
MIN_EXTRACTABLE_CHARS = 200
EXTRACTOR_NAME = f"pypdf-{pypdf.__version__}"


def extract_to_sidecar(source_path: Path, warnings: list[VaultWarning]) -> Path | None:
    """Extract `source_path`'s text into its sidecar, if eligible.

    Returns the sidecar path on success, on no-op (already up to date),
    and on a failed-but-handled extraction (empty sidecar written).
    Returns `None` only when `source_path` isn't extraction-eligible at
    all (not a `.pdf`). Never raises; every failure becomes an entry
    appended to `warnings`.
    """
    if source_path.suffix.lower() not in ELIGIBLE_SUFFIXES:
        return None

    sidecar_path = sidecar_path_for(source_path)
    current_source_hash = f"sha256:{content_hash(source_path)}"

    existing = _read_existing_sidecar(sidecar_path)
    if existing is not None:
        if existing.get("source_hash") == current_source_hash:
            return sidecar_path
        if existing.get("manually_corrected") is True:
            warnings.append(
                VaultWarning(
                    kind="stale_sidecar",
                    message=(
                        f"{sidecar_path}: source changed but the sidecar is "
                        "manually_corrected; not regenerating"
                    ),
                    paths=(sidecar_path,),
                )
            )
            return sidecar_path

    body = _extract_text(source_path, warnings)
    metadata = {
        "extracted_from": source_path.name,
        "source_hash": current_source_hash,
        "extractor": EXTRACTOR_NAME,
        "extracted_at": datetime.now(UTC).date().isoformat(),
        "manually_corrected": False,
    }
    sidecar_path.write_text(frontmatter.serialize(metadata, body), encoding="utf-8")
    return sidecar_path


def _read_existing_sidecar(sidecar_path: Path) -> dict[str, Any] | None:
    if not sidecar_path.is_file():
        return None
    try:
        text = sidecar_path.read_text(encoding="utf-8")
        metadata, _ = frontmatter.parse(text, filename=str(sidecar_path))
    except (OSError, FrontmatterError):
        return None
    return dict(metadata)


def _extract_text(source_path: Path, warnings: list[VaultWarning]) -> str:
    try:
        reader = PdfReader(source_path)
    except Exception as exc:  # noqa: BLE001 - pypdf raises many error types on malformed input; must never propagate
        warnings.append(
            VaultWarning(
                kind="malformed_pdf",
                message=f"{source_path}: {exc}",
                paths=(source_path,),
            )
        )
        return ""

    if reader.is_encrypted:
        warnings.append(
            VaultWarning(
                kind="encrypted_pdf",
                message=f"{source_path}: password-protected, cannot extract text",
                paths=(source_path,),
            )
        )
        return ""

    try:
        text = "\n".join(page.extract_text() for page in reader.pages)
    except Exception as exc:  # noqa: BLE001 - see above
        warnings.append(
            VaultWarning(
                kind="malformed_pdf",
                message=f"{source_path}: {exc}",
                paths=(source_path,),
            )
        )
        return ""

    if len(text.strip()) < MIN_EXTRACTABLE_CHARS:
        warnings.append(
            VaultWarning(
                kind="empty_extraction",
                message=(
                    f"{source_path}: only {len(text.strip())} extractable "
                    f"characters (minimum {MIN_EXTRACTABLE_CHARS}) - "
                    "treated as a scanned/unextractable PDF"
                ),
                paths=(source_path,),
            )
        )
        return ""

    return text
