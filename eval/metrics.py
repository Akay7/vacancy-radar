"""recall@k and MRR over expected vs. retrieved document ids.

Both metrics treat an empty `expected` as trivially satisfied (`1.0`),
regardless of what was retrieved - there is nothing to find, so nothing
can be missed. That is what lets a `negative`-category query (no
relevant document exists) score `1.0` "when nothing relevant is
returned," without either metric judging what irrelevant results *were*
returned - that's a precision question, out of scope here (see
design.md).
"""

from collections.abc import Sequence


def recall_at_k(expected: Sequence[str], retrieved: Sequence[str], k: int) -> float:
    """The fraction of `expected`'s document ids present among
    `retrieved`'s first `k` entries.

    `1.0` when `expected` is empty - trivially satisfied, regardless of
    `retrieved`. `0.0`, not a `ZeroDivisionError`, when `retrieved` is
    empty and `expected` is not.
    """
    if not expected:
        return 1.0
    top_k = set(retrieved[:k])
    hits = sum(1 for doc_id in expected if doc_id in top_k)
    return hits / len(expected)


def mrr(expected: Sequence[str], retrieved: Sequence[str]) -> float:
    """`1 / rank` of the first entry in `retrieved` whose id appears in
    `expected` (1-based rank), or `0.0` if none does.

    `1.0` when `expected` is empty - trivially satisfied, regardless of
    `retrieved`, mirroring `recall_at_k`'s empty-expectation rule.
    """
    if not expected:
        return 1.0
    expected_set = set(expected)
    for rank, doc_id in enumerate(retrieved, start=1):
        if doc_id in expected_set:
            return 1 / rank
    return 0.0
