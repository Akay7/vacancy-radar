from concurrent.futures import ThreadPoolExecutor

import pytest

from vacancy_radar.frontmatter import (
    MalformedFrontmatterError,
    MissingFrontmatterError,
    parse,
    serialize,
)

VALID_TEXT = """---
id: acme-2026-01-01-developer
company: Acme Inc.
status: applied
tags:
  - urgent
  - remote
---
# Notes

Some body text here.

- bullet one
- bullet two
"""

NO_DELIMITER_TEXT = """# No frontmatter

Just a body.
"""

MALFORMED_TEXT = """---
key: [unclosed
---
body
"""

BODY_WITH_DASHES_TEXT = """---
id: x
---
Line one

---

Line after dashes
"""


def test_parse_then_serialize_reproduces_original_byte_for_byte() -> None:
    metadata, body = parse(VALID_TEXT)

    assert serialize(metadata, body) == VALID_TEXT


def test_missing_delimiter_raises_missing_frontmatter_error() -> None:
    with pytest.raises(MissingFrontmatterError):
        parse(NO_DELIMITER_TEXT)


def test_malformed_yaml_raises_malformed_frontmatter_error_naming_file() -> None:
    with pytest.raises(MalformedFrontmatterError) as exc_info:
        parse(MALFORMED_TEXT, filename="vault/acme.md")

    assert "vault/acme.md" in str(exc_info.value)


def test_body_dashes_line_is_not_a_delimiter() -> None:
    metadata, body = parse(BODY_WITH_DASHES_TEXT)

    assert "---" in body
    assert serialize(metadata, body) == BODY_WITH_DASHES_TEXT


def test_concurrent_round_trips_from_many_threads_stay_correct() -> None:
    """Regression: a shared module-level `YAML` instance let two threads'
    dumps interleave, wedging its emitter so every later dump in the
    process raised `EmitterError`. No instance may be shared."""

    def round_trip(_: int) -> str:
        metadata, body = parse(VALID_TEXT)
        return serialize(metadata, body)

    with ThreadPoolExecutor(max_workers=16) as pool:
        results = list(pool.map(round_trip, range(2000)))

    assert all(result == VALID_TEXT for result in results)
    # And a later call on this thread still works afterwards.
    assert serialize(*parse(VALID_TEXT)) == VALID_TEXT
