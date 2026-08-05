import pytest
from typer.testing import CliRunner

import vacancy_radar
from vacancy_radar.cli import app

runner = CliRunner()


def test_version_flag_exits_zero_and_prints_version() -> None:
    result = runner.invoke(app, ["--version"])

    assert result.exit_code == 0
    assert vacancy_radar.__version__ in result.output


def test_no_args_prints_usage_and_exits_zero() -> None:
    result = runner.invoke(app, [])

    assert result.exit_code == 0
    assert "Usage" in result.output


def test_unknown_command_exits_non_zero() -> None:
    result = runner.invoke(app, ["bogus-command"])

    assert result.exit_code != 0


def test_eval_command_is_absent_from_help_output() -> None:
    result = runner.invoke(app, ["--help"])

    assert result.exit_code == 0
    assert "_eval" not in result.output


@pytest.mark.embedding
def test_eval_command_runs_the_full_sweep_and_prints_a_markdown_report() -> None:
    result = runner.invoke(app, ["_eval"])

    assert result.exit_code == 0
    assert "| mode | vector_weight | fusion | category | recall@5 | MRR | n |" in (
        result.output
    )
    assert "overall" in result.output
