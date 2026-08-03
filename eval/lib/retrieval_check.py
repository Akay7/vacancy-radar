"""Experience-bullet retrieval recall/MRR check (User Story 2, specs/004-eval-harness).

Ingests eval's own dedicated CV fixture into a disposable, eval-only Chroma index (never the
maintainer's real `.cache/chroma` or `CV_DIR`, FR-008) and queries it exactly the way
`/analyze` does via `Retriever.query_bullets()`, using the real local embedding model by
default (research.md #1) — a fake is only substituted in this module's own unit tests.
"""

from pathlib import Path

from eval.lib import metrics
from eval.lib.fixtures import load_jsonl
from eval.lib.report import CheckResult, FixtureFailure
from vacancy_radar import ingest
from vacancy_radar.chroma_store import ChromaStore
from vacancy_radar.embedder import Embedder, SentenceTransformersEmbedder
from vacancy_radar.retriever import Retriever

GOLDEN_PATH = Path("eval/golden/bullets.jsonl")
FIXTURES_CV_DIR = Path("eval/golden/fixtures/cv")
EVAL_CHROMA_PATH = ".cache/eval-chroma"
TOP_K = 5
# Calibrated against the real bge-small-en-v1.5 model on eval/golden/fixtures/cv (tasks.md T017).
BULLET_RECALL_AT_5_MIN = 0.8


def run(
    golden_path: Path = GOLDEN_PATH,
    fixtures_cv_dir: Path = FIXTURES_CV_DIR,
    chroma_path: str = EVAL_CHROMA_PATH,
    store: ChromaStore | None = None,
    embedder: Embedder | None = None,
) -> CheckResult:
    rows = load_jsonl(golden_path)
    if not rows:
        return CheckResult(name="bullet_retrieval", status="skipped")

    store = store or ChromaStore(chroma_path)
    embedder = embedder or SentenceTransformersEmbedder()
    bullet_count = ingest.ingest_experience_bullets(fixtures_cv_dir, store=store, embedder=embedder)
    existing_ids = {f"bullet-{i}" for i in range(bullet_count)}
    retriever = Retriever(store=store, embedder=embedder)

    failures: list[FixtureFailure] = []
    expected_lists: list[list[str]] = []
    retrieved_lists: list[list[str]] = []

    for row in rows:
        fixture_id = row["id"]
        expected_ids = row["expected_bullet_ids"]
        missing = [eid for eid in expected_ids if eid not in existing_ids]
        if missing:
            failures.append(
                FixtureFailure(
                    fixture_id=fixture_id,
                    kind="fixture_error",
                    reason=f"expected bullet id(s) {missing} were never ingested",
                )
            )
            continue

        results = retriever.query_bullets(row["query"], top_k=TOP_K)
        retrieved_ids = [r["id"] for r in results]
        recall = metrics.recall_at_k(expected_ids, retrieved_ids, TOP_K)
        if recall < 1.0:
            missing_ids = [eid for eid in expected_ids if eid not in retrieved_ids]
            failures.append(
                FixtureFailure(
                    fixture_id=fixture_id,
                    kind="regression",
                    reason=f"expected bullet id(s) {missing_ids} not found in top-{TOP_K}",
                )
            )
        expected_lists.append(expected_ids)
        retrieved_lists.append(retrieved_ids)

    has_fixture_error = any(f.kind == "fixture_error" for f in failures)
    if not expected_lists:
        return CheckResult(
            name="bullet_retrieval", status="fail", sample_size=0, failures=failures
        )

    avg_recall = sum(
        metrics.recall_at_k(exp, ret, TOP_K)
        for exp, ret in zip(expected_lists, retrieved_lists, strict=True)
    ) / len(expected_lists)
    mrr_score = metrics.mrr(expected_lists, retrieved_lists)

    status = "fail" if has_fixture_error or avg_recall < BULLET_RECALL_AT_5_MIN else "pass"
    return CheckResult(
        name="bullet_retrieval",
        status=status,
        metrics={f"recall@{TOP_K}": avg_recall, "mrr": mrr_score},
        sample_size=len(expected_lists),
        failures=failures,
    )
