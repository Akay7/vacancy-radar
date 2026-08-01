"""Reads the user's optional filter-rules file — personal dealbreakers/preferences.

Analogous to CV_DIR: a plain-text file the user maintains under their own data directory,
used as additional grounding context for /analyze's flags (FR-007). An absent file is a
valid state, not an error — most users won't have one until they choose to write it.
"""

from pathlib import Path

DEFAULT_FILTER_RULES_PATH = Path("data/user/filter-rules.md")


def load_filter_rules(path: Path = DEFAULT_FILTER_RULES_PATH) -> str:
    if not path.is_file():
        return ""
    return path.read_text()
