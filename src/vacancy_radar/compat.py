"""Version-stamp check: triggers an automatic reindex on embedding-model or
schema mismatch, instead of silently serving stale results.

The vector index is a disposable, regenerable cache — never a migration target.
Rebuilding it is `vacancy-radar reindex`: delete .cache/chroma/, re-embed the
git-tracked source. At this project's scale that's seconds, entirely local.
"""

from dataclasses import dataclass


@dataclass(frozen=True)
class CompatStamp:
    embedding_model: str
    schema_version: str


CURRENT_STAMP = CompatStamp(embedding_model="BAAI/bge-small-en-v1.5", schema_version="1")


def needs_reindex(stored_stamp: CompatStamp | None) -> bool:
    return stored_stamp != CURRENT_STAMP
