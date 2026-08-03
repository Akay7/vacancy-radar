from eval.lib.metrics import mrr, precision_at_k, recall_at_k, wilson_score_interval


def test_recall_at_k_counts_expected_ids_found_in_top_k():
    assert recall_at_k(["a", "b"], ["a", "x", "y"], k=3) == 0.5


def test_recall_at_k_is_one_when_all_expected_ids_present():
    assert recall_at_k(["a", "b"], ["b", "a", "z"], k=3) == 1.0


def test_recall_at_k_ignores_results_beyond_k():
    assert recall_at_k(["a"], ["x", "y", "a"], k=2) == 0.0


def test_recall_at_k_is_zero_for_no_expected_ids():
    assert recall_at_k([], ["a", "b"], k=3) == 0.0


def test_mrr_averages_reciprocal_rank_of_first_hit():
    expected = [["a"], ["b"]]
    retrieved = [["x", "a"], ["b", "y"]]
    # query 1: first hit at rank 2 -> 1/2; query 2: first hit at rank 1 -> 1/1
    assert mrr(expected, retrieved) == (0.5 + 1.0) / 2


def test_mrr_is_zero_for_a_query_with_no_hit():
    expected = [["a"]]
    retrieved = [["x", "y"]]
    assert mrr(expected, retrieved) == 0.0


def test_mrr_is_zero_for_no_queries():
    assert mrr([], []) == 0.0


def test_precision_at_k_all_top_k_relevant():
    assert precision_at_k(["a", "b", "c"], ["a", "b", "c"], k=3) == 1.0


def test_precision_at_k_none_relevant():
    assert precision_at_k(["a"], ["x", "y", "z"], k=3) == 0.0


def test_precision_at_k_mixed():
    assert precision_at_k(["a", "b"], ["a", "x", "y"], k=3) == 1 / 3


def test_precision_at_k_uses_actual_result_count_not_k_when_fewer_returned():
    # only 1 result came back (e.g. nothing else passed a similarity threshold) — dividing by
    # the actual count, not k, means this isn't penalized as if 2 slots were wrong answers
    assert precision_at_k(["a"], ["a"], k=3) == 1.0


def test_precision_at_k_is_zero_for_no_results():
    assert precision_at_k(["a"], [], k=3) == 0.0


def test_wilson_score_interval_is_tight_and_high_for_all_successes():
    lower, upper = wilson_score_interval(successes=10, n=10)
    assert lower > 0.65
    assert upper == 1.0


def test_wilson_score_interval_is_wide_and_centered_near_half_for_mixed_results():
    lower, upper = wilson_score_interval(successes=5, n=10)
    assert lower < 0.4
    assert upper > 0.6
    # a 50/50 split should straddle 0.5 roughly symmetrically
    assert abs((lower + upper) / 2 - 0.5) < 0.05


def test_wilson_score_interval_bounds_are_within_zero_and_one():
    lower, upper = wilson_score_interval(successes=3, n=3)
    assert 0.0 <= lower <= upper <= 1.0


def test_wilson_score_interval_handles_zero_sample_size():
    assert wilson_score_interval(successes=0, n=0) == (0.0, 1.0)
