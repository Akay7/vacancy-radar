"""Index handle resolution, keyed by vault path, created lazily.

Never a module-level singleton: stage 8 may switch vaults at runtime
via MCP roots, and a handle bound at import time would silently keep
querying/writing the first vault's table after that switch.
"""

from dataclasses import dataclass
from pathlib import Path

import lancedb

DEFAULT_INDEX_DIRNAME = ".index"
"""Dot-prefixed: already excluded from `read_vault` traversal
(`vault.paths.is_skipped_name`) and already gitignored."""

_handles: dict[Path, "IndexHandle"] = {}


@dataclass
class IndexHandle:
    """A resolved connection to one vault's disposable index."""

    vault_path: Path
    index_path: Path
    connection: lancedb.DBConnection


def default_index_path(vault_path: Path) -> Path:
    """Where a vault's index lives unless a caller overrides it."""
    return vault_path / DEFAULT_INDEX_DIRNAME


def get_index_handle(vault_path: Path, index_path: Path | None = None) -> IndexHandle:
    """Resolve (creating on first request) the index handle for
    `vault_path`, keyed by its resolved (absolute, symlink-followed)
    form so two different-looking paths to the same vault share one
    handle."""
    resolved_vault = vault_path.resolve()
    if resolved_vault in _handles:
        return _handles[resolved_vault]

    resolved_index_path = (
        index_path if index_path is not None else default_index_path(resolved_vault)
    ).resolve()
    connection = lancedb.connect(resolved_index_path)
    handle = IndexHandle(
        vault_path=resolved_vault,
        index_path=resolved_index_path,
        connection=connection,
    )
    _handles[resolved_vault] = handle
    return handle
