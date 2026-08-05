"""Stage 5's retrieval eval harness - a labelled query set, recall@k/MRR
metrics, and a sweep runner across `search()`'s modes, vector weights,
and fusion strategies.

Lives at the repo root, sibling to `src/` and `tests/`, not inside the
installed `vacancy_radar` package - see the eval-harness change's
design.md for why. Not shipped in the built wheel; reachable from a
repo checkout via `vacancy-radar _eval` (private, hidden) or by
importing `eval.run`/`eval.metrics` directly.
"""
