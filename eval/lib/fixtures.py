"""Golden-set loading: one JSON object per line, per eval/golden/*.jsonl.

A missing or empty golden file is not an error here — it's a signal for the calling check to
report status="skipped" (spec.md's edge case), not to crash the whole harness run.
"""

import json
from pathlib import Path


def load_jsonl(path: Path) -> list[dict]:
    if not path.exists():
        return []
    lines = [line for line in path.read_text().splitlines() if line.strip()]
    return [json.loads(line) for line in lines]
