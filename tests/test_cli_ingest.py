import shutil
from pathlib import Path

import pytest
from _fakes import FakeEmbedder

from vacancy_radar import cli, compat, ingest
from vacancy_radar import manifest as manifest_module

EXAMPLE_DIR = Path(__file__).parent.parent / "data" / "example"


@pytest.fixture(autouse=True)
def fake_embedder(monkeypatch):
    monkeypatch.setattr(ingest, "SentenceTransformersEmbedder", FakeEmbedder)


@pytest.fixture
def project_dir(tmp_path, monkeypatch):
    shutil.copytree(EXAMPLE_DIR, tmp_path / "example")
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("CV_DIR", "example")
    monkeypatch.setenv("VACANCY_DIR", "example/vacancies")
    return tmp_path


def test_ingest_command_end_to_end(project_dir, capsys):
    exit_code = cli.main(["ingest"])
    assert exit_code == 0

    captured = capsys.readouterr()
    assert "CV_DIR:      example" in captured.out
    assert "VACANCY_DIR: example/vacancies" in captured.out
    assert "Ingested 8 CV bullets" in captured.out
    assert "Created 2 new vacancies" in captured.out
    assert "Invalid folder" in captured.err
    assert "Conflict" in captured.err


def test_ingest_is_idempotent_across_cli_invocations(project_dir, capsys):
    cli.main(["ingest"])
    capsys.readouterr()
    # Second `ingest` re-embeds everything (non-incremental) but must not duplicate entries —
    # the manifest already knows these natural keys, so they're reported as updated, not created.
    cli.main(["ingest"])
    captured = capsys.readouterr()
    assert "Created 0 new vacancies" in captured.out
    assert "Updated 2 vacancies" in captured.out

    store = ingest.ChromaStore(ingest.CHROMA_PATH)
    assert store.count(ingest.VACANCIES_COLLECTION) == 6


def test_sync_command_incremental(project_dir, capsys):
    cli.main(["ingest"])
    capsys.readouterr()

    new_folder = project_dir / "example" / "vacancies" / "2026-06-01_hooli_swe"
    new_folder.mkdir()
    (new_folder / "vacancy.yaml").write_text(
        "company: Hooli\nposition: SWE\ndate: 2026-06-01\noutcome: applied\n"
    )
    yaml_path = (
        project_dir / "example" / "vacancies" / "2026-01-15_acme-corp_backend-engineer"
        / "vacancy.yaml"
    )
    yaml_path.write_text(yaml_path.read_text().replace("outcome: applied", "outcome: offer"))

    exit_code = cli.main(["sync"])
    assert exit_code == 0
    captured = capsys.readouterr()
    assert "Created 1 new vacancy" in captured.out
    assert "Updated 1 vacancy" in captured.out
    assert "Skipped 1 unchanged vacancy" in captured.out


def test_sync_does_not_clean_up_deleted_folder(project_dir):
    cli.main(["ingest"])
    shutil.rmtree(project_dir / "example" / "vacancies" / "2026-02-03_globex_platform-engineer")

    cli.main(["sync"])

    store = ingest.ChromaStore(ingest.CHROMA_PATH)
    got = store.get_or_create_collection(ingest.VACANCIES_COLLECTION).get(
        ids=["2026-02-03_globex_platform-engineer/vacancy.yaml"]
    )
    assert len(got["ids"]) == 1


def test_sync_after_compat_mismatch_reembeds_everything(project_dir, capsys):
    cli.main(["ingest"])
    capsys.readouterr()

    m = manifest_module.load()
    m.compat_stamp = compat.CompatStamp(embedding_model="different-model", schema_version="1")
    manifest_module.save(m)

    cli.main(["sync"])
    captured = capsys.readouterr()
    assert "Created 0 new vacancies" in captured.out
    assert "Updated 2 vacancies" in captured.out
    assert "Skipped 0 unchanged vacancies" in captured.out


@pytest.mark.parametrize("command", ["ingest", "sync", "reindex"])
def test_command_errors_when_vacancy_dir_missing(project_dir, monkeypatch, capsys, command):
    # Without any vacancy history, the tool can't do anything useful — this is a hard error,
    # unlike a missing CV_DIR (see test_ingest_tolerates_missing_cv_dir).
    monkeypatch.setenv("VACANCY_DIR", "no-such-vacancy-dir")
    exit_code = cli.main([command])
    assert exit_code != 0
    captured = capsys.readouterr()
    assert "VACANCY_DIR" in captured.err
    assert "no-such-vacancy-dir" in captured.err


def test_ingest_tolerates_missing_cv_dir(project_dir, monkeypatch, capsys):
    # A missing CV_DIR is still a legitimate zero-item state (FR-007) — the CLI can still
    # ingest vacancy history without any experience bullets to draw on yet.
    monkeypatch.setenv("CV_DIR", "no-such-cv-dir")
    exit_code = cli.main(["ingest"])
    assert exit_code == 0
    captured = capsys.readouterr()
    assert "Ingested 0 CV bullets" in captured.out


def _hash_tree(root: Path) -> dict[str, str]:
    import hashlib

    return {
        str(p.relative_to(root)): hashlib.sha256(p.read_bytes()).hexdigest()
        for p in sorted(root.rglob("*"))
        if p.is_file()
    }


def test_reindex_matches_fresh_ingest_and_preserves_source(project_dir, capsys):
    cli.main(["ingest"])
    capsys.readouterr()

    source_before = _hash_tree(project_dir / "example")

    exit_code = cli.main(["reindex"])
    assert exit_code == 0
    captured = capsys.readouterr()
    assert "Ingested 8 CV bullets" in captured.out
    assert "Created 2 new vacancies" in captured.out

    source_after = _hash_tree(project_dir / "example")
    assert source_before == source_after
