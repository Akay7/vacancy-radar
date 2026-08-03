"""Similar-vacancy retrieval precision check (User Story 3, specs/004-eval-harness).

Ingests eval's own dedicated vacancy fixture set into a disposable, eval-only Chroma index
(never the maintainer's real `.cache/chroma` or `VACANCY_DIR`, FR-008) and queries it exactly
the way `/similar` does via `Retriever.query_similar_vacancies()`.
"""

from pathlib import Path

from eval.lib import metrics
from eval.lib.fixtures import load_jsonl
from eval.lib.report import CheckResult, FixtureFailure
from vacancy_radar import ingest
from vacancy_radar.chroma_store import ChromaStore
from vacancy_radar.embedder import Embedder, SentenceTransformersEmbedder
from vacancy_radar.retriever import Retriever

GOLDEN_PATH = Path("eval/golden/similar.jsonl")
FIXTURES_VACANCIES_DIR = Path("eval/golden/fixtures/vacancies")
EVAL_CHROMA_PATH = ".cache/eval-chroma"
TOP_K = 3
# Calibrated against the real bge-small-en-v1.5 model on eval/golden/fixtures/vacancies
# (tasks.md T023).
SIMILAR_PRECISION_AT_3_MIN = 0.7


def _existing_natural_keys(vacancies_dir: Path) -> set[str]:
    keys = set()
    for folder in sorted(p for p in vacancies_dir.iterdir() if p.is_dir()):
        record, _reason = ingest.load_vacancy_record(folder)
        if record:
            keys.add(ingest.natural_key(record))
    return keys


def run(
    golden_path: Path = GOLDEN_PATH,
    fixtures_vacancies_dir: Path = FIXTURES_VACANCIES_DIR,
    chroma_path: str = EVAL_CHROMA_PATH,
    store: ChromaStore | None = None,
    embedder: Embedder | None = None,
) -> CheckResult:
    rows = load_jsonl(golden_path)
    if not rows:
        return CheckResult(name="similar_vacancy", status="skipped")

    store = store or ChromaStore(chroma_path)
    embedder = embedder or SentenceTransformersEmbedder()
    ingest.ingest_vacancies(fixtures_vacancies_dir, store=store, embedder=embedder)
    existing_ids = _existing_natural_keys(fixtures_vacancies_dir)
    retriever = Retriever(store=store, embedder=embedder)

    failures: list[FixtureFailure] = []
    precision_scores: list[float] = []

    for row in rows:
        fixture_id = row["id"]
        expected_ids = row["expected_similar_ids"]
        missing = [eid for eid in expected_ids if eid not in existing_ids]
        if missing:
            failures.append(
                FixtureFailure(
                    fixture_id=fixture_id,
                    kind="fixture_error",
                    reason=f"expected vacancy id(s) {missing} were never ingested",
                )
            )
            continue

        matches = retriever.query_similar_vacancies(row["query_posting"], top_k=TOP_K)
        retrieved_ids = [m.vacancy_id for m in matches]
        precision = metrics.precision_at_k(expected_ids, retrieved_ids, TOP_K)
        if precision < 1.0:
            wrong = [rid for rid in retrieved_ids if rid not in expected_ids]
            reason = (
                f"top-{TOP_K} included non-similar vacancy id(s) {wrong}"
                if wrong
                else f"no similar vacancy found among top-{TOP_K} results"
            )
            failures.append(
                FixtureFailure(fixture_id=fixture_id, kind="regression", reason=reason)
            )
        precision_scores.append(precision)

    has_fixture_error = any(f.kind == "fixture_error" for f in failures)
    if not precision_scores:
        return CheckResult(
            name="similar_vacancy", status="fail", sample_size=0, failures=failures
        )

    avg_precision = sum(precision_scores) / len(precision_scores)
    status = "fail" if has_fixture_error or avg_precision < SIMILAR_PRECISION_AT_3_MIN else "pass"
    return CheckResult(
        name="similar_vacancy",
        status=status,
        metrics={f"precision@{TOP_K}": avg_precision},
        sample_size=len(precision_scores),
        failures=failures,
    )
