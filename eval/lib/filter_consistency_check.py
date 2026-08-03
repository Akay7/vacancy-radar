"""Filter-rule citation consistency check (User Story 4, specs/004-eval-harness).

A narrower slice of the same grounding-enforcement path as grounding_check.py, focused
specifically on `source_id="filter-rules"` citations: a real violation must be reliably kept,
a fabricated one reliably rejected. Reported with a confidence interval, not a bare
percentage, since golden sets here are necessarily small (research.md #4).
"""

from pathlib import Path

from eval.lib import metrics
from eval.lib.fixtures import load_jsonl
from eval.lib.report import CheckResult, FixtureFailure
from vacancy_radar import grounding
from vacancy_radar.models import CandidateFlag, CandidateReport

GOLDEN_PATH = Path("eval/golden/filter-consistency.jsonl")
# Principle II is non-negotiable — same zero-tolerance policy as grounding_check.py.
FILTER_CONSISTENCY_MIN_ACCURACY = 1.0


def run(golden_path: Path = GOLDEN_PATH) -> CheckResult:
    rows = load_jsonl(golden_path)
    if not rows:
        return CheckResult(name="filter_consistency", status="skipped")

    failures: list[FixtureFailure] = []
    correct = 0
    graded = 0

    for row in rows:
        fixture_id = row["id"]
        flag_data = row["flag"]
        expect_grounded = row["expect_grounded"]

        if flag_data["source_id"] != "filter-rules":
            failures.append(
                FixtureFailure(
                    fixture_id=fixture_id,
                    kind="fixture_error",
                    reason=(
                        "flag source_id must be 'filter-rules', got "
                        f"'{flag_data['source_id']}' — belongs in grounding.jsonl instead"
                    ),
                )
            )
            continue

        sources = {"filter-rules": row["filter_rules_text"]}
        candidate = CandidateReport(
            match_band="good",
            flags=[CandidateFlag(**flag_data)],
            gaps=[],
            draft_sentences=[],
        )
        result = grounding.enforce(candidate, sources)
        actual_kept = len(result.flags) == 1

        graded += 1
        if actual_kept == expect_grounded:
            correct += 1
        else:
            failures.append(
                FixtureFailure(
                    fixture_id=fixture_id,
                    kind="regression",
                    reason=(
                        f"expected expect_grounded={expect_grounded} but enforce() "
                        f"{'kept' if actual_kept else 'dropped'} it"
                    ),
                )
            )

    accuracy = correct / graded if graded else 0.0
    ci_lower, ci_upper = metrics.wilson_score_interval(correct, graded)
    status = "fail" if failures else "pass"
    return CheckResult(
        name="filter_consistency",
        status=status,
        metrics={"accuracy": accuracy, "ci_lower": ci_lower, "ci_upper": ci_upper},
        sample_size=graded,
        failures=failures,
    )
