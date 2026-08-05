"""Presentation-only snippet extraction for search results.

Deterministic and pure: given the same `text`/`query`/`has_keyword_match`
it always returns the same string, and it never reads from or writes
back into the ranking path - `search.py` calls this strictly after a
mode's ordering (and, for hybrid, fusion) is already final, so nothing
here can ever change which hit ranks where.
"""

import re

SNIPPET_MAX_CHARS = 200
"""The maximum length of an extracted snippet, in Unicode codepoints
(`str` characters, not bytes) - slicing a Python `str` by index always
lands on a whole codepoint, so this bound can never split a multi-byte
UTF-8 character."""

_HALF_WINDOW = SNIPPET_MAX_CHARS // 2

_WORD_RE = re.compile(r"\S+")


def extract_snippet(text: str, query: str, *, has_keyword_match: bool) -> str:
    """A short window of `text` around the first literal (case-
    insensitive) occurrence of one of `query`'s terms, or `text`'s
    opening when there's no such occurrence - including whenever
    `has_keyword_match` is `False` (a semantic-only hit, where a
    literal match - if any - is coincidental, not what the hit is
    actually about)."""
    match_index = _first_term_index(text, query) if has_keyword_match else None
    if match_index is None:
        return text[:SNIPPET_MAX_CHARS]
    return _window_around(text, match_index)


def _first_term_index(text: str, query: str) -> int | None:
    lowered = text.lower()
    best: int | None = None
    for term in _WORD_RE.findall(query.lower()):
        index = lowered.find(term)
        if index != -1 and (best is None or index < best):
            best = index
    return best


def _window_around(text: str, index: int) -> str:
    start = max(0, index - _HALF_WINDOW)
    end = min(len(text), start + SNIPPET_MAX_CHARS)
    start = max(0, end - SNIPPET_MAX_CHARS)
    return text[start:end]
