from eval.lib.report import CheckResult, EvalReport, FixtureFailure, render_markdown


def test_render_markdown_shows_check_name_status_size_and_metrics():
    report = EvalReport(
        checks=[
            CheckResult(
                name="grounding",
                status="pass",
                metrics={"accuracy": 1.0},
                sample_size=10,
            )
        ],
        overall_status="pass",
    )
    output = render_markdown(report)
    assert "grounding" in output
    assert "PASS" in output
    assert "10" in output
    assert "accuracy=1.000" in output


def test_render_markdown_lists_failing_fixtures_with_kind_and_reason():
    report = EvalReport(
        checks=[
            CheckResult(
                name="bullets",
                status="fail",
                metrics={"recall@5": 0.5},
                sample_size=2,
                failures=[
                    FixtureFailure(
                        fixture_id="bullets-001", kind="regression", reason="missing bullet-2"
                    ),
                    FixtureFailure(
                        fixture_id="bullets-002",
                        kind="fixture_error",
                        reason="bullet-999 was never ingested",
                    ),
                ],
            )
        ],
        overall_status="fail",
    )
    output = render_markdown(report)
    assert "bullets-001" in output
    assert "regression" in output
    assert "missing bullet-2" in output
    assert "bullets-002" in output
    assert "fixture_error" in output
    assert "FAIL" in output


def test_render_markdown_shows_overall_status():
    report = EvalReport(checks=[], overall_status="pass")
    output = render_markdown(report)
    assert "Overall" in output
    assert "PASS" in output
