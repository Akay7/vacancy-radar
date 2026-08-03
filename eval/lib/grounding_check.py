"""Grounding enforcement check (User Story 1, specs/004-eval-harness).

Feeds curated CandidateReport-shaped fixtures directly into `grounding.enforce()` and checks
whether each flag/draft-sentence's `expect_grounded` label matches enforce()'s actual keep/drop
decision — the constitution-mandated grounding regression gate (Principle II, non-negotiable).
No ingestion, no embedding model, no LLM involved (research.md #2).
"""

from collections import Counter
from pathlib import Path

from eval.lib.fixtures import load_jsonl
from eval.lib.report import CheckResult, FixtureFailure
from vacancy_radar import grounding
from vacancy_radar.models import CandidateFlag, CandidateReport, CandidateSentence

GOLDEN_PATH = Path("eval/golden/grounding.jsonl")
# Principle II is non-negotiable — any fabricated claim kept, or genuine claim wrongly
# rejected, is a failing run, not a tunable quality bar.
GROUNDING_MIN_ACCURACY = 1.0


def _build_candidate(row: dict) -> CandidateReport:
    return CandidateReport(
        match_band=row.get("match_band", "good"),
        flags=[
            CandidateFlag(
                label=f["label"],
                severity=f["severity"],
                reason=f["reason"],
                quote=f["quote"],
                source_id=f["source_id"],
            )
            for f in row.get("flags", [])
        ],
        gaps=row.get("gaps", []),
        draft_sentences=[
            CandidateSentence(text=s["text"], quote=s["quote"], source_id=s["source_id"])
            for s in row.get("draft_sentences", [])
        ],
    )


def run(golden_path: Path = GOLDEN_PATH) -> CheckResult:
    rows = load_jsonl(golden_path)
    if not rows:
        return CheckResult(name="grounding", status="skipped")

    failures: list[FixtureFailure] = []
    correct = 0
    graded = 0

    for row in rows:
        fixture_id = row.get("id", "<unknown>")
        sources: dict[str, str] = row.get("sources", {})
        candidate = _build_candidate(row)
        result = grounding.enforce(candidate, sources)
        remaining_citations = Counter((c.quote, c.source_id) for c in result.citations)

        labeled_items = [
            (item, "flag") for item in row.get("flags", [])
        ] + [(item, "draft_sentence") for item in row.get("draft_sentences", [])]

        for item, kind in labeled_items:
            expect_grounded = item["expect_grounded"]
            key = (item["quote"], item["source_id"])

            if item["source_id"] not in sources and expect_grounded:
                failures.append(
                    FixtureFailure(
                        fixture_id=fixture_id,
                        kind="fixture_error",
                        reason=(
                            f"{kind} cites unknown source_id '{item['source_id']}' but is "
                            "labeled expect_grounded=true"
                        ),
                    )
                )
                continue

            actual_kept = remaining_citations[key] > 0
            if actual_kept:
                remaining_citations[key] -= 1

            graded += 1
            if actual_kept == expect_grounded:
                correct += 1
            else:
                failures.append(
                    FixtureFailure(
                        fixture_id=fixture_id,
                        kind="regression",
                        reason=(
                            f"{kind} quote {item['quote']!r} expected "
                            f"expect_grounded={expect_grounded} but enforce() "
                            f"{'kept' if actual_kept else 'dropped'} it"
                        ),
                    )
                )

    accuracy = correct / graded if graded else 0.0
    status = "fail" if failures else "pass"
    return CheckResult(
        name="grounding",
        status=status,
        metrics={"accuracy": accuracy},
        sample_size=graded,
        failures=failures,
    )
