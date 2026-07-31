"""Ingestion: markdown experience bullets + vacancy folders → Chroma.

Upsert, never wipe-and-rebuild:
- Identity key: the vacancy folder's natural key (date+company+position) —
  not a content hash. The folder name IS the key.
- Staleness: a lightweight per-file hash cache (local to this module, not
  user-facing) decides whether an individual file needs re-embedding.
  sources/ and correspondence/ are static once captured; analysis.md and
  vacancy.yaml are the only files that change after creation.
- Every embedded vacancy-folder chunk is tagged with doc_type/company/
  position/date/outcome metadata for retrieval-time filtering.
"""

from pathlib import Path


def ingest_experience_bullets(cv_dir: Path) -> int:
    """Ingest CV/profile markdown bullets into the experience_bullets collection."""
    raise NotImplementedError("M2")


def ingest_vacancies(vacancy_dir: Path) -> int:
    """Walk vacancy_dir/<natural-key-folder>/, upsert changed files into the
    vacancies collection, tagged with retrieval metadata."""
    raise NotImplementedError("M2")
