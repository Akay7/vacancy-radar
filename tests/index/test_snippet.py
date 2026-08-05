from vacancy_radar.index.snippet import SNIPPET_MAX_CHARS, extract_snippet


def test_literal_match_snippet_contains_the_matched_term() -> None:
    text = (
        "Some opening filler text that goes on for a while before the "
        "important part where ClickHouse is mentioned, followed by more "
        "trailing text after it."
    )

    snippet = extract_snippet(text, "ClickHouse", has_keyword_match=True)

    assert "clickhouse" in snippet.lower()


def test_match_is_case_insensitive() -> None:
    text = "This document discusses CLICKHOUSE at length in its body."

    snippet = extract_snippet(text, "clickhouse", has_keyword_match=True)

    assert "clickhouse" in snippet.lower()


def test_no_keyword_match_falls_back_to_opening() -> None:
    text = "The opening sentence of a document. " + "Filler content. " * 50

    snippet = extract_snippet(text, "irrelevant query", has_keyword_match=False)

    assert snippet == text[:SNIPPET_MAX_CHARS]


def test_no_literal_occurrence_falls_back_to_opening_even_with_keyword_match() -> None:
    text = "The opening sentence of a document with no literal query terms in it."

    snippet = extract_snippet(text, "zzznomatchzzz", has_keyword_match=True)

    assert snippet == text[:SNIPPET_MAX_CHARS]


def test_snippet_is_bounded_in_length() -> None:
    text = "word " * 500

    snippet = extract_snippet(text, "word", has_keyword_match=True)

    assert len(snippet) <= SNIPPET_MAX_CHARS


def test_snippet_from_multibyte_text_stays_within_bounds_and_is_valid_utf8() -> None:
    text = (
        ("Собеседование прошло 🎯 отлично " * 30)
        + "distinctive_term"
        + (" ещё немного текста 🎯 после совпадения " * 30)
    )

    snippet = extract_snippet(text, "distinctive_term", has_keyword_match=True)

    assert len(snippet) <= SNIPPET_MAX_CHARS
    encoded = snippet.encode("utf-8")
    assert encoded.decode("utf-8") == snippet


def test_extract_snippet_is_deterministic() -> None:
    text = "Repeatable text mentioning ClickHouse for a deterministic snippet test."

    first = extract_snippet(text, "ClickHouse", has_keyword_match=True)
    second = extract_snippet(text, "ClickHouse", has_keyword_match=True)

    assert first == second
