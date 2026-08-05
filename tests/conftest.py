"""Puts the repo root on `sys.path` for the whole test session, so
`tests/eval/*.py` can `import eval.*` (a top-level package sibling to
`src/` and `tests/`, not part of the installed `vacancy_radar`
package - see the eval-harness change's design.md) as an ordinary
module-level import, without each test file repeating the same
`sys.path` insertion.

pytest imports every `conftest.py` above a collected test file before
collecting it, so this runs exactly once, before anything under
`tests/` needs it.
"""

import sys
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parent.parent
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))
