"""Repo root on sys.path so tests can import `eval.lib.*` — `eval/` is a maintainer-tool
script directory (not part of the installed `vacancy_radar` package), so it isn't otherwise
importable the way `vacancy_radar` is via the editable install."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
