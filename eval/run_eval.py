"""Runs the four golden sets and writes the results as a markdown table for the README.

Ordered by ground-truth rigor, strongest first (see the eval section of the
maintainer's project plan for the full reasoning):
  1. grounding check       — automated, no golden file needed (cited text ∈ source)
  2. bullet retrieval      — eval/golden/bullets.jsonl (recall@5, MRR)
  3. similar-vacancy       — eval/golden/similar.jsonl (precision@3)
  4. filter-consistency    — eval/golden/filter-consistency.jsonl, reported with
                              sample size + confidence interval, not a bare percentage

Fully local and deterministic — no live LLM call, no network access (specs/004-eval-harness).
"""

import argparse
import sys
from collections.abc import Callable
from pathlib import Path

# Run as `python eval/run_eval.py`, Python puts eval/ (not the repo root) on sys.path[0] — add
# the repo root too so `eval.lib.*` imports resolve the same way they do under pytest (which
# gets the repo root from tests/conftest.py).
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from eval.lib import (  # noqa: E402
    filter_consistency_check,
    grounding_check,
    retrieval_check,
    similar_check,
)
from eval.lib.report import CheckResult, EvalReport, render_markdown  # noqa: E402

# Populated incrementally as each check module is implemented (specs/004-eval-harness/tasks.md).
CHECKS: dict[str, Callable[[], CheckResult]] = {
    "grounding": grounding_check.run,
    "bullets": retrieval_check.run,
    "similar": similar_check.run,
    "filter-consistency": filter_consistency_check.run,
}


def parse_args(argv: list[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Vacancy Radar eval harness")
    parser.add_argument(
        "--check",
        action="append",
        choices=sorted(CHECKS) or ["grounding", "bullets", "similar", "filter-consistency"],
        help="Restrict the run to one or more specific checks (default: all)",
    )
    return parser.parse_args(argv)


def run(check_names: list[str] | None = None) -> EvalReport:
    names = check_names or sorted(CHECKS)
    results = [CHECKS[name]() for name in names if name in CHECKS]
    overall_status = "fail" if any(r.status == "fail" for r in results) else "pass"
    return EvalReport(checks=results, overall_status=overall_status)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    report = run(args.check)
    print(render_markdown(report))
    return 0 if report.overall_status == "pass" else 1


if __name__ == "__main__":
    sys.exit(main())
