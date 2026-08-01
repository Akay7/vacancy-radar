"""Ingestion: markdown experience bullets + vacancy folders → Chroma.

Upsert, never wipe-and-rebuild:
- Identity key: the vacancy folder's natural key (date+company+position), computed from
  `vacancy.yaml`'s own fields via a deterministic slug — not a hash of file content, and not
  just the folder name (so two folders whose `vacancy.yaml` describes the same vacancy under
  different folder names are caught as a conflict, FR-009).
- Staleness: a lightweight per-file hash cache (`manifest.py`) decides whether an individual
  file needs re-embedding during `sync`. `ingest` and `reindex` always re-embed everything.
- Every embedded vacancy-folder chunk is tagged with doc_type/company/position/date/outcome
  metadata for retrieval-time filtering.
"""

import re
from dataclasses import dataclass, field
from pathlib import Path

import yaml
from pydantic import ValidationError

from vacancy_radar import compat
from vacancy_radar import manifest as manifest_module
from vacancy_radar.chroma_store import ChromaStore
from vacancy_radar.embedder import Embedder, SentenceTransformersEmbedder
from vacancy_radar.models import VacancyRecord

CHROMA_PATH = ".cache/chroma"
BULLETS_COLLECTION = "experience_bullets"
VACANCIES_COLLECTION = "vacancies"
# Cosine distance gives a bounded, thresholdable similarity score for /similar retrieval
# (see specs/002-similar-retrieval/research.md) — must be set at collection-creation time.
VACANCIES_COLLECTION_METADATA = {"hnsw:space": "cosine"}

NATURAL_KEY_NAME_RE = re.compile(r"^\d{4}-\d{2}-\d{2}_[a-z0-9-]+_[a-z0-9-]+$")
BULLET_LINE_RE = re.compile(r"^\s*[-*+]\s+(.*\S)\s*$")


@dataclass
class InvalidFolder:
    folder: str
    reason: str


@dataclass
class ConflictGroup:
    natural_key: str
    folders: list[str]


@dataclass
class RunSummary:
    bullets_ingested: int = 0
    vacancies_created: int = 0
    vacancies_updated: int = 0
    vacancies_skipped: int = 0
    vacancies_invalid: list[InvalidFolder] = field(default_factory=list)
    vacancies_conflicting: list[ConflictGroup] = field(default_factory=list)


def slugify(text: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", text.strip().lower())
    return slug.strip("-")


def natural_key(record: VacancyRecord) -> str:
    return f"{record.date.isoformat()}_{slugify(record.company)}_{slugify(record.position)}"


def validate_folder_name(folder: Path) -> str | None:
    """Return an error reason if the folder name doesn't match the natural-key convention."""
    if not NATURAL_KEY_NAME_RE.match(folder.name):
        return (
            f"folder name '{folder.name}' doesn't match the "
            "YYYY-MM-DD_company-slug_position-slug convention"
        )
    return None


def load_vacancy_record(folder: Path) -> tuple[VacancyRecord | None, str | None]:
    """Parse and validate folder/vacancy.yaml. Returns (record, None) or (None, reason)."""
    name_error = validate_folder_name(folder)
    if name_error:
        return None, name_error

    yaml_path = folder / "vacancy.yaml"
    if not yaml_path.exists():
        return None, "vacancy.yaml is missing"

    try:
        raw = yaml.safe_load(yaml_path.read_text()) or {}
    except yaml.YAMLError as exc:
        return None, f"vacancy.yaml is not valid YAML: {exc}"

    try:
        record = VacancyRecord.model_validate(raw)
    except ValidationError as exc:
        missing = ", ".join(sorted({str(e["loc"][0]) for e in exc.errors()}))
        return None, f"vacancy.yaml is missing/invalid required field(s): {missing}"

    return record, None


def chunk_vacancy_folder(folder: Path, key: str, record: VacancyRecord) -> list[dict]:
    """Split one vacancy folder into (id, document, metadata) chunks, one per source file."""
    metadata_base = {
        "company": record.company,
        "position": record.position,
        "date": record.date.isoformat(),
        "outcome": record.outcome,
    }
    chunks = [
        {
            "id": f"{key}/vacancy.yaml",
            "document": (folder / "vacancy.yaml").read_text(),
            "metadata": {**metadata_base, "doc_type": "vacancy_meta"},
        }
    ]

    for subdir, doc_type in (("sources", "posting"), ("correspondence", "correspondence")):
        subdir_path = folder / subdir
        if not subdir_path.is_dir():
            continue
        for file_path in sorted(subdir_path.iterdir()):
            if not file_path.is_file():
                continue
            chunks.append(
                {
                    "id": f"{key}/{subdir}/{file_path.name}",
                    "document": file_path.read_text(),
                    "metadata": {**metadata_base, "doc_type": doc_type},
                }
            )

    analysis_path = folder / "analysis.md"
    if analysis_path.is_file():
        chunks.append(
            {
                "id": f"{key}/analysis.md",
                "document": analysis_path.read_text(),
                "metadata": {**metadata_base, "doc_type": "analysis"},
            }
        )

    return chunks


def _parse_bullets(cv_dir: Path) -> list[str]:
    bullets: list[str] = []
    if not cv_dir.is_dir():
        return bullets
    for md_file in sorted(cv_dir.glob("*.md")):
        if md_file.name.lower() == "readme.md":
            continue
        for line in md_file.read_text().splitlines():
            match = BULLET_LINE_RE.match(line)
            if match:
                bullets.append(match.group(1))
    return bullets


def ingest_experience_bullets(
    cv_dir: Path,
    store: ChromaStore | None = None,
    embedder: Embedder | None = None,
) -> int:
    """Full-replace the experience_bullets collection from CV_DIR's markdown bullets (FR-012)."""
    store = store or ChromaStore(CHROMA_PATH)
    embedder = embedder or SentenceTransformersEmbedder()

    bullets = _parse_bullets(Path(cv_dir))
    store.delete_all(BULLETS_COLLECTION)
    if bullets:
        ids = [f"bullet-{i}" for i in range(len(bullets))]
        vectors = embedder.embed(bullets)
        store.upsert(BULLETS_COLLECTION, ids=ids, documents=bullets, embeddings=vectors)
    return len(bullets)


def _discover_vacancy_folders(vacancy_dir: Path) -> list[Path]:
    if not vacancy_dir.is_dir():
        return []
    return sorted(p for p in vacancy_dir.iterdir() if p.is_dir())


def ingest_vacancies(
    vacancy_dir: Path,
    store: ChromaStore | None = None,
    embedder: Embedder | None = None,
    incremental: bool = False,
    ingest_manifest: manifest_module.IngestManifest | None = None,
) -> RunSummary:
    """Upsert vacancy folders into the vacancies collection, keyed by natural key.

    When `incremental` is True, files whose content hash matches the manifest are skipped
    (FR-004); when False (ingest/reindex), every file is re-embedded regardless of the
    manifest (FR-005/FR-010).
    """
    store = store or ChromaStore(CHROMA_PATH)
    embedder = embedder or SentenceTransformersEmbedder()
    ingest_manifest = ingest_manifest if ingest_manifest is not None else manifest_module.load()

    summary = RunSummary()
    folders = _discover_vacancy_folders(Path(vacancy_dir))

    parsed: list[tuple[Path, VacancyRecord]] = []
    for folder in folders:
        record, reason = load_vacancy_record(folder)
        if reason:
            summary.vacancies_invalid.append(InvalidFolder(folder=str(folder), reason=reason))
            continue
        parsed.append((folder, record))

    keys_to_folders: dict[str, list[Path]] = {}
    for folder, record in parsed:
        keys_to_folders.setdefault(natural_key(record), []).append(folder)

    conflicting_keys = {key for key, fs in keys_to_folders.items() if len(fs) > 1}
    for key in sorted(conflicting_keys):
        summary.vacancies_conflicting.append(
            ConflictGroup(natural_key=key, folders=[str(f) for f in keys_to_folders[key]])
        )

    for folder, record in parsed:
        key = natural_key(record)
        if key in conflicting_keys:
            continue

        is_new_key = not any(k.startswith(f"{key}/") for k in ingest_manifest.files)

        chunks = chunk_vacancy_folder(folder, key, record)
        to_embed = []
        folder_changed = False
        for chunk in chunks:
            data = chunk["document"].encode("utf-8")
            digest = manifest_module.content_hash(data)
            existing = ingest_manifest.files.get(chunk["id"])
            unchanged = incremental and existing is not None and existing.content_hash == digest
            if unchanged:
                continue
            to_embed.append(chunk)
            folder_changed = True
            ingest_manifest.files[chunk["id"]] = manifest_module.FileEntry(
                content_hash=digest, chunk_ids=[chunk["id"]]
            )

        if to_embed:
            vectors = embedder.embed([c["document"] for c in to_embed])
            store.upsert(
                VACANCIES_COLLECTION,
                ids=[c["id"] for c in to_embed],
                documents=[c["document"] for c in to_embed],
                embeddings=vectors,
                metadatas=[c["metadata"] for c in to_embed],
                collection_metadata=VACANCIES_COLLECTION_METADATA,
            )

        if is_new_key:
            summary.vacancies_created += 1
        elif folder_changed:
            summary.vacancies_updated += 1
        else:
            summary.vacancies_skipped += 1

    return summary


def run_ingest(cv_dir: Path, vacancy_dir: Path, incremental: bool = False) -> RunSummary:
    """Shared entrypoint for `ingest` (incremental=False) and `sync` (incremental=True).

    Checks the compat stamp first: an embedding-model/schema mismatch forces a full
    (non-incremental) run this time, regardless of the requested mode (research.md).
    """
    ingest_manifest = manifest_module.load()
    effective_incremental = incremental and not compat.needs_reindex(ingest_manifest.compat_stamp)

    bullets_count = ingest_experience_bullets(cv_dir)
    vacancy_summary = ingest_vacancies(
        vacancy_dir, incremental=effective_incremental, ingest_manifest=ingest_manifest
    )
    vacancy_summary.bullets_ingested = bullets_count

    ingest_manifest.compat_stamp = compat.CURRENT_STAMP
    manifest_module.save(ingest_manifest)

    return vacancy_summary


def reindex(cv_dir: Path, vacancy_dir: Path) -> RunSummary:
    """Wipe the local cache and manifest, then rebuild from source (FR-005).

    Wipes via ChromaStore.reset_collection (delete_collection + recreate) rather than
    deleting `.cache/chroma` on disk — see reset_collection's docstring for why.
    """
    store = ChromaStore(CHROMA_PATH)
    store.reset_collection(BULLETS_COLLECTION)
    store.reset_collection(VACANCIES_COLLECTION, metadata=VACANCIES_COLLECTION_METADATA)
    manifest_module.delete()
    return run_ingest(cv_dir, vacancy_dir, incremental=False)
