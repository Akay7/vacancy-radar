"""Content-based change detection.

`content_hash` never reads mtime, size, or inode: git checkouts and
sync tools rewrite those on every checkout, and a false-positive change
signal would re-embed the whole corpus for nothing.
"""

import hashlib
from pathlib import Path

_CHUNK_SIZE = 1024 * 1024  # 1 MiB


def content_hash(path: Path) -> str:
    """The sha256 hex digest of `path`'s full byte content."""
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(_CHUNK_SIZE), b""):
            digest.update(chunk)
    return digest.hexdigest()
