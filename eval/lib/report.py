"""Shared result shapes for every eval check, and the markdown rendering of an eval run.

Every check module (grounding_check.py, retrieval_check.py, similar_check.py,
filter_consistency_check.py) returns a single CheckResult; run_eval.py collects them into an
EvalReport and prints render_markdown(report)'s output.
"""

from dataclasses import dataclass, field
from typing import Literal

FixtureFailureKind = Literal["regression", "fixture_error"]
CheckStatus = Literal["pass", "fail", "skipped"]


@dataclass
class FixtureFailure:
    fixture_id: str
    kind: FixtureFailureKind
    reason: str


@dataclass
class CheckResult:
    name: str
    status: CheckStatus
    metrics: dict[str, float] = field(default_factory=dict)
    sample_size: int = 0
    failures: list[FixtureFailure] = field(default_factory=list)


@dataclass
class EvalReport:
    checks: list[CheckResult]
    overall_status: Literal["pass", "fail"]


def _status_symbol(status: CheckStatus) -> str:
    return {"pass": "✓ PASS", "fail": "✗ FAIL", "skipped": "– SKIPPED"}[status]


def render_markdown(report: EvalReport) -> str:
    lines = [
        "| Check | Status | Sample Size | Metrics |",
        "|---|---|---|---|",
    ]
    for check in report.checks:
        metrics = ", ".join(f"{k}={v:.3f}" for k, v in check.metrics.items()) or "-"
        lines.append(
            f"| {check.name} | {_status_symbol(check.status)} | {check.sample_size} | {metrics} |"
        )

    for check in report.checks:
        if not check.failures:
            continue
        lines.append("")
        lines.append(f"### {check.name} failures")
        for failure in check.failures:
            lines.append(f"- `{failure.fixture_id}` ({failure.kind}): {failure.reason}")

    lines.append("")
    lines.append(f"**Overall: {_status_symbol(report.overall_status)}**")
    return "\n".join(lines)
