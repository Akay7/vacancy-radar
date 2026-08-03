import json
from pathlib import Path

from _fakes import BagOfWordsEmbedder

from eval.lib import filter_consistency_check, grounding_check, retrieval_check, similar_check
from vacancy_radar.chroma_store import ChromaStore


def _write_jsonl(path: Path, rows: list[dict]) -> None:
    path.write_text("\n".join(json.dumps(row) for row in rows) + "\n")


def test_grounding_check_passes_when_every_label_matches(tmp_path: Path):
    golden = tmp_path / "grounding.jsonl"
    _write_jsonl(
        golden,
        [
            {
                "id": "g-001",
                "sources": {"bullet-0": "Built a FastAPI service handling 200 req/s."},
                "match_band": "good",
                "flags": [
                    {
                        "label": "Backend",
                        "severity": "green",
                        "reason": "Built a FastAPI service.",
                        "quote": "Built a FastAPI service handling 200 req/s",
                        "source_id": "bullet-0",
                        "expect_grounded": True,
                    },
                    {
                        "label": "Fabricated",
                        "severity": "green",
                        "reason": "Invented.",
                        "quote": "launched a rocket to Mars",
                        "source_id": "bullet-0",
                        "expect_grounded": False,
                    },
                ],
                "gaps": [],
                "draft_sentences": [],
            }
        ],
    )

    result = grounding_check.run(golden)

    assert result.status == "pass"
    assert result.metrics["accuracy"] == 1.0
    assert result.sample_size == 2
    assert result.failures == []


def test_grounding_check_fails_on_a_mismatched_label(tmp_path: Path):
    golden = tmp_path / "grounding.jsonl"
    _write_jsonl(
        golden,
        [
            {
                "id": "g-002",
                "sources": {"bullet-0": "Built a FastAPI service handling 200 req/s."},
                "match_band": "good",
                "flags": [
                    {
                        "label": "Fabricated",
                        "severity": "green",
                        "reason": "Invented.",
                        "quote": "launched a rocket to Mars",
                        "source_id": "bullet-0",
                        "expect_grounded": True,
                    }
                ],
                "gaps": [],
                "draft_sentences": [],
            }
        ],
    )

    result = grounding_check.run(golden)

    assert result.status == "fail"
    assert len(result.failures) == 1
    assert result.failures[0].fixture_id == "g-002"
    assert result.failures[0].kind == "regression"


def test_grounding_check_reports_unknown_source_labeled_true_as_fixture_error(tmp_path: Path):
    golden = tmp_path / "grounding.jsonl"
    _write_jsonl(
        golden,
        [
            {
                "id": "g-003",
                "sources": {"bullet-0": "Built a FastAPI service handling 200 req/s."},
                "match_band": "good",
                "flags": [
                    {
                        "label": "Bad source",
                        "severity": "red",
                        "reason": "cites a source that doesn't exist",
                        "quote": "anything",
                        "source_id": "bullet-99",
                        "expect_grounded": True,
                    }
                ],
                "gaps": [],
                "draft_sentences": [],
            }
        ],
    )

    result = grounding_check.run(golden)

    assert result.status == "fail"
    assert len(result.failures) == 1
    assert result.failures[0].kind == "fixture_error"
    assert result.sample_size == 0


def test_grounding_check_reports_skipped_for_empty_golden_file(tmp_path: Path):
    golden = tmp_path / "grounding.jsonl"
    golden.write_text("")

    result = grounding_check.run(golden)

    assert result.status == "skipped"


# --- retrieval_check (User Story 2) -----------------------------------------------------


def _cv_fixture(tmp_path: Path) -> Path:
    cv_dir = tmp_path / "cv"
    cv_dir.mkdir()
    (cv_dir / "experience.md").write_text(
        "- Built a FastAPI backend service with async SQLAlchemy\n"
        "- Led a team of five engineers migrating to Kubernetes\n"
        "- Wrote pytest integration tests raising coverage from 40% to 85%\n"
    )
    return cv_dir


def test_retrieval_check_reports_recall_and_mrr(tmp_path: Path):
    golden = tmp_path / "bullets.jsonl"
    _write_jsonl(
        golden,
        [
            {
                "id": "b-001",
                "query": "FastAPI backend service",
                "expected_bullet_ids": ["bullet-0"],
            },
            {
                "id": "b-002",
                "query": "pytest integration tests coverage",
                "expected_bullet_ids": ["bullet-2"],
            },
        ],
    )
    embedder = BagOfWordsEmbedder()
    store = ChromaStore(str(tmp_path / "chroma"))

    result = retrieval_check.run(
        golden_path=golden,
        fixtures_cv_dir=_cv_fixture(tmp_path),
        store=store,
        embedder=embedder,
    )

    assert result.status == "pass"
    assert result.sample_size == 2
    assert result.metrics["recall@5"] == 1.0
    assert result.metrics["mrr"] == 1.0
    assert result.failures == []


def test_retrieval_check_reports_fixture_error_for_never_ingested_bullet_id(tmp_path: Path):
    golden = tmp_path / "bullets.jsonl"
    _write_jsonl(
        golden,
        [{"id": "b-003", "query": "anything", "expected_bullet_ids": ["bullet-999"]}],
    )
    embedder = BagOfWordsEmbedder()
    store = ChromaStore(str(tmp_path / "chroma"))

    result = retrieval_check.run(
        golden_path=golden,
        fixtures_cv_dir=_cv_fixture(tmp_path),
        store=store,
        embedder=embedder,
    )

    assert result.status == "fail"
    assert len(result.failures) == 1
    assert result.failures[0].kind == "fixture_error"


def test_retrieval_check_reports_skipped_for_missing_golden_file(tmp_path: Path):
    result = retrieval_check.run(
        golden_path=tmp_path / "does-not-exist.jsonl",
        fixtures_cv_dir=_cv_fixture(tmp_path),
        store=ChromaStore(str(tmp_path / "chroma")),
        embedder=BagOfWordsEmbedder(),
    )

    assert result.status == "skipped"


# --- similar_check (User Story 3) -------------------------------------------------------


def _vacancy_fixture(tmp_path: Path) -> Path:
    vacancies_dir = tmp_path / "vacancies"
    folder = vacancies_dir / "2026-01-15_acme-corp_backend-engineer"
    (folder / "sources").mkdir(parents=True)
    (folder / "vacancy.yaml").write_text(
        "company: Acme Corp\nposition: Backend Engineer\ndate: 2026-01-15\noutcome: applied\n"
    )
    (folder / "sources" / "posting.md").write_text(
        "Backend Engineer role building Python APIs with PostgreSQL for a growing SaaS company."
    )
    return vacancies_dir


def test_similar_check_reports_precision(tmp_path: Path):
    golden = tmp_path / "similar.jsonl"
    _write_jsonl(
        golden,
        [
            {
                "id": "s-001",
                "query_posting": (
                    "Backend Engineer role building Python APIs with PostgreSQL for a "
                    "growing SaaS company."
                ),
                "expected_similar_ids": ["2026-01-15_acme-corp_backend-engineer"],
            }
        ],
    )
    embedder = BagOfWordsEmbedder()
    store = ChromaStore(str(tmp_path / "chroma"))

    result = similar_check.run(
        golden_path=golden,
        fixtures_vacancies_dir=_vacancy_fixture(tmp_path),
        store=store,
        embedder=embedder,
    )

    assert result.status == "pass"
    assert result.sample_size == 1
    assert result.metrics["precision@3"] == 1.0
    assert result.failures == []


def test_similar_check_reports_fixture_error_for_never_ingested_vacancy_id(tmp_path: Path):
    golden = tmp_path / "similar.jsonl"
    _write_jsonl(
        golden,
        [
            {
                "id": "s-002",
                "query_posting": "Anything",
                "expected_similar_ids": ["2099-01-01_nonexistent-corp_ghost-role"],
            }
        ],
    )
    embedder = BagOfWordsEmbedder()
    store = ChromaStore(str(tmp_path / "chroma"))

    result = similar_check.run(
        golden_path=golden,
        fixtures_vacancies_dir=_vacancy_fixture(tmp_path),
        store=store,
        embedder=embedder,
    )

    assert result.status == "fail"
    assert len(result.failures) == 1
    assert result.failures[0].kind == "fixture_error"


def test_similar_check_reports_skipped_for_missing_golden_file(tmp_path: Path):
    result = similar_check.run(
        golden_path=tmp_path / "does-not-exist.jsonl",
        fixtures_vacancies_dir=_vacancy_fixture(tmp_path),
        store=ChromaStore(str(tmp_path / "chroma")),
        embedder=BagOfWordsEmbedder(),
    )

    assert result.status == "skipped"


# --- filter_consistency_check (User Story 4) --------------------------------------------


def test_filter_consistency_check_passes_when_labels_match(tmp_path: Path):
    golden = tmp_path / "filter-consistency.jsonl"
    _write_jsonl(
        golden,
        [
            {
                "id": "f-001",
                "filter_rules_text": "Must be remote. No on-call rotation.",
                "flag": {
                    "label": "Remote requirement",
                    "severity": "red",
                    "reason": "Posting doesn't mention remote work.",
                    "quote": "Must be remote",
                    "source_id": "filter-rules",
                },
                "expect_grounded": True,
            },
            {
                "id": "f-002",
                "filter_rules_text": "Must be remote. No on-call rotation.",
                "flag": {
                    "label": "Fabricated",
                    "severity": "red",
                    "reason": "Not actually in the filter rules.",
                    "quote": "Must offer unlimited PTO",
                    "source_id": "filter-rules",
                },
                "expect_grounded": False,
            },
        ],
    )

    result = filter_consistency_check.run(golden)

    assert result.status == "pass"
    assert result.metrics["accuracy"] == 1.0
    assert result.sample_size == 2
    assert result.failures == []


def test_filter_consistency_check_fails_on_a_mismatched_label(tmp_path: Path):
    golden = tmp_path / "filter-consistency.jsonl"
    _write_jsonl(
        golden,
        [
            {
                "id": "f-003",
                "filter_rules_text": "Must be remote.",
                "flag": {
                    "label": "Fabricated",
                    "severity": "red",
                    "reason": "Not in the filter rules.",
                    "quote": "Must offer unlimited PTO",
                    "source_id": "filter-rules",
                },
                "expect_grounded": True,
            }
        ],
    )

    result = filter_consistency_check.run(golden)

    assert result.status == "fail"
    assert len(result.failures) == 1
    assert result.failures[0].kind == "regression"


def test_filter_consistency_check_reports_wrong_source_id_as_fixture_error(tmp_path: Path):
    golden = tmp_path / "filter-consistency.jsonl"
    _write_jsonl(
        golden,
        [
            {
                "id": "f-004",
                "filter_rules_text": "Must be remote.",
                "flag": {
                    "label": "Wrong source",
                    "severity": "red",
                    "reason": "This belongs in grounding.jsonl instead.",
                    "quote": "Must be remote",
                    "source_id": "bullet-0",
                },
                "expect_grounded": True,
            }
        ],
    )

    result = filter_consistency_check.run(golden)

    assert result.status == "fail"
    assert len(result.failures) == 1
    assert result.failures[0].kind == "fixture_error"


def test_filter_consistency_check_reports_skipped_for_empty_golden_file(tmp_path: Path):
    golden = tmp_path / "filter-consistency.jsonl"
    golden.write_text("")

    result = filter_consistency_check.run(golden)

    assert result.status == "skipped"
