import os
import time
from pathlib import Path

from vacancy_radar.vault.hashing import content_hash


def test_content_hash_stable_when_mtime_changes_but_content_does_not(
    tmp_path: Path,
) -> None:
    file_path = tmp_path / "file.md"
    file_path.write_text("stable content", encoding="utf-8")
    before = content_hash(file_path)

    # Bump mtime without touching content ("touch" with a future time).
    later = time.time() + 5
    os.utime(file_path, (later, later))

    after = content_hash(file_path)

    assert before == after


def test_content_hash_changes_when_a_single_byte_changes(tmp_path: Path) -> None:
    file_path = tmp_path / "file.md"
    file_path.write_text("aaaa", encoding="utf-8")
    before = content_hash(file_path)

    file_path.write_text("aaab", encoding="utf-8")
    after = content_hash(file_path)

    assert before != after


def test_identical_content_hashes_identically(tmp_path: Path) -> None:
    first = tmp_path / "first.md"
    second = tmp_path / "second.md"
    first.write_text("same bytes", encoding="utf-8")
    second.write_text("same bytes", encoding="utf-8")

    assert content_hash(first) == content_hash(second)
