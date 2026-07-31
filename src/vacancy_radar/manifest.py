"""Local, disposable staleness manifest for incremental `sync`.

Maps each ingested vacancy source file to its last-seen content hash and the Chroma chunk
ids it produced, so `sync` can skip files that haven't changed. Deleted by `reindex` along
with the Chroma store — never the source of truth, never committed (see .gitignore).
"""

import hashlib
import json
from dataclasses import asdict, dataclass, field
from pathlib import Path

from vacancy_radar.compat import CURRENT_STAMP, CompatStamp

MANIFEST_PATH = Path(".cache/ingest-manifest.json")


@dataclass
class FileEntry:
    content_hash: str
    chunk_ids: list[str]


@dataclass
class IngestManifest:
    compat_stamp: CompatStamp = field(default_factory=lambda: CURRENT_STAMP)
    files: dict[str, FileEntry] = field(default_factory=dict)


def content_hash(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def load(path: Path = MANIFEST_PATH) -> IngestManifest:
    if not path.exists():
        return IngestManifest()
    raw = json.loads(path.read_text())
    stamp = CompatStamp(**raw.get("compat_stamp", {}))
    files = {rel: FileEntry(**entry) for rel, entry in raw.get("files", {}).items()}
    return IngestManifest(compat_stamp=stamp, files=files)


def save(manifest: IngestManifest, path: Path = MANIFEST_PATH) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "compat_stamp": asdict(manifest.compat_stamp),
        "files": {rel: asdict(entry) for rel, entry in manifest.files.items()},
    }
    path.write_text(json.dumps(payload, indent=2))


def delete(path: Path = MANIFEST_PATH) -> None:
    path.unlink(missing_ok=True)
