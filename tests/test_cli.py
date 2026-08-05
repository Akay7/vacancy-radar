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
