import re

import vacancy_radar


def test_version_is_three_part_numeric_string() -> None:
    assert re.match(r"^\d+\.\d+\.\d+$", vacancy_radar.__version__)
