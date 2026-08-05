from eval.metrics import mrr, recall_at_k


def test_single_expected_document_ranking_first_scores_1() -> None:
    assert recall_at_k(["doc-a"], ["doc-a", "doc-b", "doc-c"], k=5) == 1.0


def test_expected_document_absent_from_top_k_scores_0() -> None:
    retrieved = ["doc-b", "doc-c", "doc-d", "doc-e", "doc-f"]

    assert recall_at_k(["doc-a"], retrieved, k=5) == 0.0


def test_partial_recall_two_of_three_expected_found_in_top_five() -> None:
    expected = ["doc-a", "doc-b", "doc-c"]
    retrieved = ["doc-a", "doc-x", "doc-b", "doc-y", "doc-z"]

    assert recall_at_k(expected, retrieved, k=5) == 2 / 3


def test_recall_at_k_only_considers_the_first_k_entries() -> None:
    expected = ["doc-a"]
    retrieved = ["doc-x", "doc-y", "doc-z", "doc-w", "doc-v", "doc-a"]

    assert recall_at_k(expected, retrieved, k=5) == 0.0


def test_mrr_reflects_the_rank_of_the_first_expected_hit() -> None:
    expected = ["doc-c"]
    retrieved = ["doc-a", "doc-b", "doc-c", "doc-d"]

    assert mrr(expected, retrieved) == 1 / 3


def test_mrr_scores_0_when_no_expected_document_is_retrieved() -> None:
    expected = ["doc-a"]
    retrieved = ["doc-x", "doc-y", "doc-z"]

    assert mrr(expected, retrieved) == 0.0


def test_empty_retrieval_yields_0_for_recall_at_k() -> None:
    assert recall_at_k(["doc-a"], [], k=5) == 0.0


def test_empty_retrieval_yields_0_for_mrr() -> None:
    assert mrr(["doc-a"], []) == 0.0


def test_no_expected_documents_scores_1_for_recall_at_k() -> None:
    assert recall_at_k([], [], k=5) == 1.0
    assert recall_at_k([], ["doc-x", "doc-y"], k=5) == 1.0


def test_no_expected_documents_scores_1_for_mrr() -> None:
    assert mrr([], []) == 1.0
    assert mrr([], ["doc-x", "doc-y"]) == 1.0


def test_mrr_with_multiple_expected_documents_uses_the_earliest_match() -> None:
    expected = ["doc-a", "doc-b"]
    retrieved = ["doc-b", "doc-x", "doc-y", "doc-a"]

    assert mrr(expected, retrieved) == 1 / 1


def test_recall_at_k_with_multiple_expected_does_not_require_all_present() -> None:
    expected = ["doc-a", "doc-b", "doc-missing"]
    retrieved = ["doc-a", "doc-b"]

    assert recall_at_k(expected, retrieved, k=5) == 2 / 3
