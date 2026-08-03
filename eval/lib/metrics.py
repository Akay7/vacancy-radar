"""Pure metric functions shared by the retrieval-based and consistency-based eval checks.

No dependency on Chroma, pydantic, or any vacancy_radar module — these operate purely on ids
and counts so they're trivially unit-testable on their own (research.md #4).
"""

import math


def recall_at_k(expected_ids: list[str], retrieved_ids: list[str], k: int) -> float:
    """Fraction of `expected_ids` that appear anywhere in `retrieved_ids[:k]`."""
    if not expected_ids:
        return 0.0
    top_k = set(retrieved_ids[:k])
    hits = sum(1 for expected_id in expected_ids if expected_id in top_k)
    return hits / len(expected_ids)


def mrr(expected_ids_per_query: list[list[str]], retrieved_ids_per_query: list[list[str]]) -> float:
    """Mean reciprocal rank of the first relevant result, across queries."""
    if not expected_ids_per_query:
        return 0.0

    reciprocal_ranks = []
    for expected_ids, retrieved_ids in zip(
        expected_ids_per_query, retrieved_ids_per_query, strict=True
    ):
        expected_set = set(expected_ids)
        rank = next(
            (i + 1 for i, rid in enumerate(retrieved_ids) if rid in expected_set), None
        )
        reciprocal_ranks.append(1.0 / rank if rank else 0.0)

    return sum(reciprocal_ranks) / len(reciprocal_ranks)


def precision_at_k(expected_ids: list[str], retrieved_ids: list[str], k: int) -> float:
    """Fraction of the (up to `k`) actually-returned results that are truly relevant.

    Divides by the number of results actually returned, not by `k` itself, so a query that
    legitimately returns fewer than `k` results (e.g. nothing else passed a similarity
    threshold) isn't penalized as if the missing slots were wrong answers.
    """
    top_k = retrieved_ids[:k]
    if not top_k:
        return 0.0
    expected_set = set(expected_ids)
    hits = sum(1 for rid in top_k if rid in expected_set)
    return hits / len(top_k)


def wilson_score_interval(successes: int, n: int, z: float = 1.96) -> tuple[float, float]:
    """Wilson score confidence interval for a binomial proportion — appropriate at small n."""
    if n == 0:
        return (0.0, 1.0)

    p = successes / n
    denominator = 1 + z**2 / n
    centre = p + z**2 / (2 * n)
    adjustment = z * math.sqrt(p * (1 - p) / n + z**2 / (4 * n**2))

    lower = (centre - adjustment) / denominator
    upper = (centre + adjustment) / denominator
    return (max(0.0, lower), min(1.0, upper))
