"""Lock-free concurrent writes (the lock-free-vault-writes change's
concurrent-writes and reindexing specs): no-clobber creates, compare-
before-replace for `vacancy.md`, and a best-effort post-write index
refresh - from threads of one process, from several processes, and
through the MCP server."""

import asyncio
import contextlib
import errno
import logging
import os
import subprocess
import sys
import tempfile
import threading
from collections.abc import Callable, Iterator
from datetime import date
from pathlib import Path

import lancedb
import pyarrow as pa
import pytest

from vacancy_radar import core, frontmatter, mcp_server
from vacancy_radar.index.build import IndexReport
from vacancy_radar.index.search import SearchMode
from vacancy_radar.models import (
    UNKNOWN_ROLE,
    Company,
    DocumentKind,
    Status,
    Vacancy,
)
from vacancy_radar.vault.paths import VAULT_MARKER_DIRNAME
from vacancy_radar.vault.reader import read_vault

# --- Helpers (self-contained per file, like test_core.py's) --------------


def _init_vault(vault: Path) -> None:
    (vault / VAULT_MARKER_DIRNAME).mkdir(parents=True, exist_ok=True)


def _write_company(vault: Path, slug: str, name: str) -> None:
    (vault / slug).mkdir(parents=True, exist_ok=True)
    metadata = Company(slug=slug, name=name).model_dump(mode="json", exclude_none=True)
    (vault / slug / "_company.md").write_text(
        frontmatter.serialize(metadata, ""), encoding="utf-8"
    )


def _write_vacancy(vault: Path, vacancy_id: str, status: Status) -> Path:
    vacancy = Vacancy(
        id=vacancy_id,
        company="Tiny Corp",
        company_slug="tiny-corp",
        role="Engineer",
        status=status,
        found_date=date(2026, 1, 1),
        applied_date=None if status is Status.FOUND else date(2026, 1, 3),
    )
    vacancy_dir = vault / "tiny-corp" / vacancy_id
    vacancy_dir.mkdir(parents=True, exist_ok=True)
    metadata = vacancy.model_dump(
        mode="json", exclude={"role_is_placeholder"}, exclude_none=True
    )
    path = vacancy_dir / "vacancy.md"
    path.write_text(frontmatter.serialize(metadata, "# Engineer\n"), encoding="utf-8")
    return path


def _vault(tmp_path: Path, vacancy_ids: tuple[str, ...] = ("v1",)) -> Path:
    """Not indexed; the first write builds the index."""
    vault = tmp_path / "vault"
    _init_vault(vault)
    _write_company(vault, "tiny-corp", "Tiny Corp")
    for vacancy_id in vacancy_ids:
        _write_vacancy(vault, vacancy_id, Status.FOUND)
    return vault


def _run_concurrently(calls: list[Callable[[], object]]) -> list[object]:
    """Start every call at once (a barrier), return each one's result or
    the exception it raised, in order."""
    barrier = threading.Barrier(len(calls))
    results: list[object] = [None] * len(calls)

    def worker(index: int, call: Callable[[], object]) -> None:
        barrier.wait()
        try:
            results[index] = call()
        except Exception as exc:  # noqa: BLE001 - reported to the test
            results[index] = exc

    threads = [
        threading.Thread(target=worker, args=(i, call)) for i, call in enumerate(calls)
    ]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()
    return results


def _no_exceptions(results: list[object]) -> None:
    errors = [r for r in results if isinstance(r, BaseException)]
    assert not errors, errors


_CONFLICT = RuntimeError(
    "lance error: Retryable commit conflict for version 7: This Rewrite "
    "transaction was preempted by concurrent transaction Update at version 7. "
    "Please retry."
)


@pytest.fixture
def no_backoff(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(core.time, "sleep", lambda _seconds: None)


# --- No-clobber publish (tasks 2.2, 2.3) ----------------------------------


def test_publish_falls_back_when_hard_links_are_unsupported(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    def _no_links(*_args: object, **_kwargs: object) -> None:
        raise PermissionError(errno.EPERM, os.strerror(errno.EPERM))

    monkeypatch.setattr(core.os, "link", _no_links)
    target = tmp_path / "a.md"
    existing = tmp_path / "b.md"
    existing.write_text("original", encoding="utf-8")

    core._atomic_write(target, "hello", overwrite=False)  # noqa: SLF001
    with pytest.raises(core.DocumentAlreadyExistsError):
        core._atomic_write(existing, "new", overwrite=False)  # noqa: SLF001

    assert target.read_text(encoding="utf-8") == "hello"
    assert existing.read_text(encoding="utf-8") == "original"
    assert sorted(p.name for p in tmp_path.iterdir()) == ["a.md", "b.md"]


def test_publish_never_clobbers_a_file_created_after_the_existence_check(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    target = tmp_path / "a.md"
    real_link = os.link

    def _other_writer_wins(src: str, dst: str) -> None:
        Path(dst).write_text("other writer", encoding="utf-8")
        real_link(src, dst)

    monkeypatch.setattr(core.os, "link", _other_writer_wins)

    with pytest.raises(core.DocumentAlreadyExistsError):
        core._atomic_write(target, "mine", overwrite=False)  # noqa: SLF001

    assert target.read_text(encoding="utf-8") == "other writer"
    assert list(tmp_path.iterdir()) == [target]


@contextlib.contextmanager
def _preempt_link_to(
    monkeypatch: pytest.MonkeyPatch, name: str, content: str
) -> Iterator[None]:
    """The first time a file named `name` is published, another writer
    creates it just before - the race the publish must survive."""
    real_link = os.link
    fired = False

    def _link(src: str, dst: str) -> None:
        nonlocal fired
        if not fired and Path(dst).name == name:
            fired = True
            Path(dst).write_text(content, encoding="utf-8")
        real_link(src, dst)

    monkeypatch.setattr(core.os, "link", _link)
    yield
    assert fired


# --- Retrying the name or id (tasks 2.4, 2.5) -----------------------------


def test_add_document_takes_the_next_name_when_another_writer_wins(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    vault = _vault(tmp_path)
    derived = "2026-01-05-note-note.md"

    with _preempt_link_to(monkeypatch, derived, "other writer"):
        path = core.append_note("v1", "mine", date(2026, 1, 5), vault=vault)

    assert path.name == "2026-01-05-note-note-2.md"
    _, body = frontmatter.parse(path.read_text(encoding="utf-8"))
    assert body.strip() == "mine"
    assert (path.parent / derived).read_text(encoding="utf-8") == "other writer"


def test_create_vacancy_mints_the_next_id_when_another_writer_wins(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    vault = _vault(tmp_path)
    snapshot_ids = set(read_vault(vault).vacancies)

    with _preempt_link_to(monkeypatch, "vacancy.md", "other writer"):
        path = core.create_vacancy(
            "Tiny Corp", "Staff Engineer", date(2026, 2, 1), Status.FOUND, vault=vault
        )

    winner = next(
        p
        for p in (vault / "tiny-corp").glob("*/vacancy.md")
        if p.read_text(encoding="utf-8") == "other writer"
    )
    assert path != winner
    metadata, _ = frontmatter.parse(path.read_text(encoding="utf-8"))
    assert metadata["id"] == path.parent.name
    assert metadata["id"] not in snapshot_ids


def test_create_vacancy_keeps_a_company_file_created_concurrently(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    vault = tmp_path / "vault"
    _init_vault(vault)

    with _preempt_link_to(monkeypatch, "_company.md", "other writer"):
        path = core.create_vacancy(
            "New Co", UNKNOWN_ROLE, date(2026, 2, 1), Status.FOUND, vault=vault
        )

    assert path.is_file()
    assert (vault / "new-co" / "_company.md").read_text(
        encoding="utf-8"
    ) == "other writer"


def test_create_vacancy_with_invalid_input_writes_nothing(tmp_path: Path) -> None:
    vault = tmp_path / "vault"
    _init_vault(vault)

    with pytest.raises(core.InvalidVacancyDataError):
        core.create_vacancy(
            "New Co", "Engineer", date(2026, 2, 1), "not-a-status", vault=vault
        )

    assert not (vault / "new-co").exists()


# --- Compare-before-replace (tasks 3.1-3.3) ------------------------------


def test_replace_if_unchanged_replaces_when_unchanged(tmp_path: Path) -> None:
    path = tmp_path / "vacancy.md"
    path.write_text("before", encoding="utf-8")

    core._replace_if_unchanged(path, "before", "after")  # noqa: SLF001

    assert path.read_text(encoding="utf-8") == "after"
    assert list(tmp_path.iterdir()) == [path]


def test_replace_if_unchanged_refuses_when_changed(tmp_path: Path) -> None:
    path = tmp_path / "vacancy.md"
    path.write_text("changed by someone", encoding="utf-8")

    with pytest.raises(core.ConcurrentModificationError):
        core._replace_if_unchanged(path, "before", "after")  # noqa: SLF001

    assert path.read_text(encoding="utf-8") == "changed by someone"
    assert list(tmp_path.iterdir()) == [path]


_OTHER_WRITER_LINE = "Edited by another writer."


@contextlib.contextmanager
def _other_writer_edits_first(
    monkeypatch: pytest.MonkeyPatch, path: Path
) -> Iterator[None]:
    """Just before the first compare-before-replace, another writer
    appends a line to `path` - after this call has read it."""
    real = core._temp_file_beside  # noqa: SLF001
    fired = False

    @contextlib.contextmanager
    def _hooked(target: Path, text: str) -> Iterator[Path]:
        nonlocal fired
        if not fired and target == path:
            fired = True
            with path.open("a", encoding="utf-8") as handle:
                handle.write(f"\n{_OTHER_WRITER_LINE}\n")
        with real(target, text) as tmp:
            yield tmp

    monkeypatch.setattr(core, "_temp_file_beside", _hooked)
    yield
    assert fired


def test_set_status_refuses_a_concurrently_changed_vacancy_then_retry_succeeds(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    vault = _vault(tmp_path)
    path = vault / "tiny-corp" / "v1" / "vacancy.md"

    with _other_writer_edits_first(monkeypatch, path):
        with pytest.raises(core.ConcurrentModificationError):
            core.set_status("v1", "applied", applied_date=date(2026, 1, 3), vault=vault)
        after_other_writer = path.read_bytes()
    assert _OTHER_WRITER_LINE.encode() in after_other_writer

    core.set_status("v1", "applied", applied_date=date(2026, 1, 3), vault=vault)

    text = path.read_text(encoding="utf-8")
    assert _OTHER_WRITER_LINE in text
    assert read_vault(vault).vacancies["v1"].status is Status.APPLIED


def test_edit_vacancy_refuses_a_concurrently_changed_vacancy_then_retry_succeeds(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    vault = _vault(tmp_path)
    path = vault / "tiny-corp" / "v1" / "vacancy.md"

    with _other_writer_edits_first(monkeypatch, path):
        with pytest.raises(core.ConcurrentModificationError):
            core.edit_vacancy("v1", salary_note="100k", vault=vault)
        after_other_writer = path.read_bytes()
    assert _OTHER_WRITER_LINE.encode() in after_other_writer

    core.edit_vacancy("v1", salary_note="100k", vault=vault)

    assert _OTHER_WRITER_LINE in path.read_text(encoding="utf-8")
    assert read_vault(vault).vacancies["v1"].salary_note == "100k"


# --- Index refresh (tasks 4.1-4.4) ---------------------------------------


def test_is_retryable_conflict_matches_a_real_lancedb_conflict() -> None:
    """Pins `_is_retryable_conflict` to what LanceDB actually raises, so
    a wording change fails here rather than silently disabling retries."""
    directory = tempfile.mkdtemp()
    schema = pa.schema([("doc_id", pa.string()), ("text", pa.string())])
    lancedb.connect(directory).create_table("t", schema=schema)
    caught: list[BaseException] = []

    def contend(worker: int) -> None:
        table = lancedb.connect(directory).open_table("t")
        for step in range(15):
            try:
                table.merge_insert(
                    "doc_id"
                ).when_matched_update_all().when_not_matched_insert_all().execute(
                    [{"doc_id": str(step % 3), "text": f"{worker}-{step}"}]
                )
                table.optimize()
            except Exception as exc:  # noqa: BLE001 - collected for the assertion
                caught.append(exc)

    _run_concurrently([lambda w=w: contend(w) for w in range(6)])

    assert caught, "no conflict provoked; raise the contention"
    assert all(core._is_retryable_conflict(exc) for exc in caught), caught  # noqa: SLF001


def test_reindex_retries_a_transient_conflict(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, no_backoff: None
) -> None:
    del no_backoff
    vault = _vault(tmp_path)
    report = IndexReport(
        added=0, changed=0, deleted=0, unchanged=0, skipped=0, elapsed=0.0
    )
    calls = 0

    def _build(*_args: object, **_kwargs: object) -> IndexReport:
        nonlocal calls
        calls += 1
        if calls == 1:
            raise _CONFLICT
        return report

    monkeypatch.setattr(core, "build_index", _build)

    assert core.reindex(vault=vault) is report
    assert calls == 2  # noqa: PLR2004


def test_reindex_raises_a_persistent_conflict(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, no_backoff: None
) -> None:
    del no_backoff
    vault = _vault(tmp_path)

    def _build(*_args: object, **_kwargs: object) -> IndexReport:
        raise _CONFLICT

    monkeypatch.setattr(core, "build_index", _build)

    with pytest.raises(RuntimeError, match="Retryable commit conflict"):
        core.reindex(vault=vault)


_DISK_FULL = "disk full"


def test_reindex_does_not_retry_other_errors(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    vault = _vault(tmp_path)
    calls = 0

    def _build(*_args: object, **_kwargs: object) -> IndexReport:
        nonlocal calls
        calls += 1
        raise RuntimeError(_DISK_FULL)

    monkeypatch.setattr(core, "build_index", _build)

    with pytest.raises(RuntimeError, match=_DISK_FULL):
        core.reindex(vault=vault)
    assert calls == 1


def test_a_write_succeeds_and_warns_when_the_index_stays_contended(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
    no_backoff: None,
) -> None:
    del no_backoff
    vault = _vault(tmp_path)
    core.reindex(vault=vault)
    real_build = core.build_index

    def _build(*_args: object, **_kwargs: object) -> IndexReport:
        raise _CONFLICT

    monkeypatch.setattr(core, "build_index", _build)

    with caplog.at_level(logging.WARNING, logger=core.__name__):
        path = core.append_note("v1", "zephyrine contention note", vault=vault)

    assert path.is_file()
    assert "stale until the next reindex" in caplog.text

    monkeypatch.setattr(core, "build_index", real_build)
    results = core.search("zephyrine", mode=SearchMode.KEYWORD, vault=vault)
    assert results.freshness_warning is not None


def test_racing_first_builds_all_succeed(tmp_path: Path) -> None:
    vault = _vault(tmp_path)

    results = _run_concurrently([lambda: core.reindex(vault=vault)] * 4)

    _no_exceptions(results)


# --- Concurrency (tasks 5.1-5.6, and the no-lock requirement) ------------


def test_a_slow_write_does_not_block_another_write(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    vault = _vault(tmp_path, ("v1", "v2"))
    core.reindex(vault=vault)
    real_build = core.build_index
    release = threading.Event()
    first_refresh_started = threading.Event()

    def _build(*args: object, **kwargs: object) -> IndexReport:
        if not first_refresh_started.is_set():
            first_refresh_started.set()
            assert release.wait(timeout=30)
        return real_build(*args, **kwargs)  # type: ignore[arg-type]

    monkeypatch.setattr(core, "build_index", _build)

    slow = threading.Thread(target=lambda: core.append_note("v1", "slow", vault=vault))
    slow.start()
    try:
        assert first_refresh_started.wait(timeout=30)
        fast = core.append_note("v2", "fast", vault=vault)
        assert fast.is_file()
        assert slow.is_alive()
    finally:
        release.set()
        slow.join()


def test_parallel_notes_on_the_same_day_all_survive(tmp_path: Path) -> None:
    vault = _vault(tmp_path)
    texts = [f"parallel note {i}" for i in range(8)]

    results = _run_concurrently(
        [
            lambda t=t: core.append_note("v1", t, date(2026, 3, 1), vault=vault)
            for t in texts
        ]
    )

    _no_exceptions(results)
    paths = [Path(str(r)) for r in results]
    assert len(set(paths)) == len(texts)
    for text, path in zip(texts, paths, strict=True):
        _, body = frontmatter.parse(path.read_text(encoding="utf-8"))
        assert body.strip() == text


def test_parallel_creates_of_the_same_vacancy_get_distinct_ids(tmp_path: Path) -> None:
    vault = tmp_path / "vault"
    _init_vault(vault)

    results = _run_concurrently(
        [
            lambda: core.create_vacancy(
                "Race Co", "Engineer", date(2026, 3, 1), Status.FOUND, vault=vault
            )
        ]
        * 4
    )

    _no_exceptions(results)
    assert len({Path(str(r)).parent.name for r in results}) == 4  # noqa: PLR2004
    assert len(list((vault / "race-co").glob("*/vacancy.md"))) == 4  # noqa: PLR2004
    assert (vault / "race-co" / "_company.md").is_file()


def test_concurrent_status_change_and_edit_fail_only_cleanly(
    tmp_path: Path,
) -> None:
    """The spec's residual: both calls can pass the compare before
    either renames, so one successful change may be lost. What must
    hold is that each call succeeds or raises the typed error, and the
    file stays a valid vacancy carrying at least one of the changes."""
    vault = _vault(tmp_path)
    core.reindex(vault=vault)

    status_result, edit_result = _run_concurrently(
        [
            lambda: core.set_status(
                "v1", "applied", applied_date=date(2026, 1, 3), vault=vault
            ),
            lambda: core.edit_vacancy("v1", salary_note="100k", vault=vault),
        ]
    )

    for result in (status_result, edit_result):
        if isinstance(result, BaseException):
            assert isinstance(result, core.ConcurrentModificationError), result
    vacancy = read_vault(vault).vacancies["v1"]
    assert vacancy.status is Status.APPLIED or vacancy.salary_note == "100k"


def test_racing_refiles_of_one_source_lose_nothing(tmp_path: Path) -> None:
    vault = _vault(tmp_path)

    def refile(i: int) -> Path:
        return core.add_document(
            "v1",
            DocumentKind.EMAIL,
            f"copy {i}",
            "Thread",
            date(2026, 3, 1),
            external_id="thread-1",
            vault=vault,
        )

    results = _run_concurrently([lambda i=i: refile(i) for i in range(4)])

    _no_exceptions(results)
    snapshot = read_vault(vault)
    with_id = {
        snapshot.document_paths[d.id]
        for d in snapshot.documents_for("v1")
        if d.external_id == "thread-1"
    }
    assert 1 <= len(with_id) <= 4  # noqa: PLR2004
    assert {Path(str(r)) for r in results} <= with_id

    docs_before = sorted((vault / "tiny-corp" / "v1" / "documents").iterdir())
    assert refile(99) in with_id
    assert sorted((vault / "tiny-corp" / "v1" / "documents").iterdir()) == docs_before


def test_reads_never_fail_during_concurrent_writes(tmp_path: Path) -> None:
    vault = _vault(tmp_path, ("v1", "v2"))
    core.reindex(vault=vault)
    done = threading.Event()

    def read_until_done() -> int:
        reads = 0
        while not done.is_set() or reads == 0:
            core.list_vacancies(vault=vault)
            core.get_vacancy("v1", vault=vault)
            reads += 1
        return reads

    def write_then_finish() -> None:
        try:
            for i in range(4):
                core.append_note("v1", f"note {i}", vault=vault)
                core.append_note("v2", f"note {i}", vault=vault)
        finally:
            done.set()

    results = _run_concurrently([read_until_done, read_until_done, write_then_finish])

    _no_exceptions(results)


_APPEND_NOTES_SCRIPT = """
import sys
from pathlib import Path
from vacancy_radar import core
vault, tag = Path(sys.argv[1]), sys.argv[2]
for i in range(3):
    core.append_note("v1", f"quokkaprocess {tag} note {i}", vault=vault)
# Skip interpreter teardown: a native crash (SIGSEGV) at exit, after all
# work is done, predates lock-free writes and happens without any
# concurrency (~1 in 20 runs); this test is about the writes.
import os
os._exit(0)
"""


def test_writers_in_separate_processes_share_a_vault(tmp_path: Path) -> None:
    vault = _vault(tmp_path)
    core.reindex(vault=vault)

    processes = [
        subprocess.Popen(  # noqa: S603 - fixed interpreter and script
            [sys.executable, "-c", _APPEND_NOTES_SCRIPT, str(vault), tag],
            stderr=subprocess.PIPE,
            text=True,
        )
        for tag in ("alpha", "beta")
    ]
    for process in processes:
        _, stderr = process.communicate(timeout=300)
        assert process.returncode == 0, stderr

    notes = [
        d for d in read_vault(vault).documents_for("v1") if d.kind is DocumentKind.NOTE
    ]
    assert len(notes) == 6  # noqa: PLR2004

    core.reindex(vault=vault)
    results = core.search(
        "quokkaprocess", mode=SearchMode.KEYWORD, limit=20, vault=vault
    )
    assert len({hit.doc_id for hit in results.hits}) == 6  # noqa: PLR2004
    assert results.freshness_warning is None


def test_no_lock_file_is_created(tmp_path: Path) -> None:
    vault = _vault(tmp_path)
    temp_dir = Path(tempfile.gettempdir())
    before = set(temp_dir.glob("vacancy-radar-*.lock"))

    core.append_note("v1", "no lock", vault=vault)

    assert set(temp_dir.glob("vacancy-radar-*.lock")) == before
    assert not list(vault.rglob("*.lock"))


# --- Through the MCP server (task 5.7) -----------------------------------


def test_concurrent_write_tools_through_the_mcp_server_all_succeed(
    tmp_path: Path,
) -> None:
    vault = _vault(tmp_path, ("v1", "v2"))
    core.reindex(vault=vault)
    server = mcp_server.build_server(vault)

    async def fire() -> list[object]:
        return await asyncio.gather(
            server.call_tool("append_note", {"vacancy_id": "v1", "text": "mcp one"}),
            server.call_tool("append_note", {"vacancy_id": "v1", "text": "mcp two"}),
            server.call_tool("append_note", {"vacancy_id": "v2", "text": "mcp three"}),
            server.call_tool(
                "set_status",
                {
                    "vacancy_id": "v2",
                    "new_status": "applied",
                    "applied_date": "2026-01-03",
                },
            ),
            server.call_tool(
                "create_vacancy",
                {
                    "company": "Tiny Corp",
                    "role": "Designer",
                    "found_date": "2026-03-01",
                    "status": "found",
                },
            ),
        )

    asyncio.run(fire())

    # Read note files from disk: same-day notes on v1 and v2 share a
    # filename stem, and the vault reader keys documents by stem.
    note_bodies = {
        frontmatter.parse(p.read_text(encoding="utf-8"))[1].strip()
        for p in vault.glob("tiny-corp/*/documents/*.md")
    }
    assert {"mcp one", "mcp two", "mcp three"} <= note_bodies
    snapshot = read_vault(vault)
    assert snapshot.vacancies["v2"].status is Status.APPLIED
    assert any(v.role == "Designer" for v in snapshot.vacancies.values())
