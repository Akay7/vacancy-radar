"""Ascii slugs and deterministic vacancy id minting.

No filesystem access here — ids are derived purely from the values a
caller supplies, never from a path. See design.md for why: a vacancy's
identity must survive its containing file or directory being renamed.
"""

import re
from datetime import date

from text_unidecode import unidecode

MAX_ROLE_SLUG_LENGTH = 50

_APOSTROPHES = re.compile("['\u2018\u2019`]")  # ascii ' + smart quotes + backtick
_NON_ALNUM_RUN = re.compile(r"[^a-z0-9]+")


def slugify(text: str) -> str:
    """Transliterate `text` into a readable, stable ascii slug."""
    ascii_text = unidecode(text)
    ascii_text = _APOSTROPHES.sub("", ascii_text).lower()
    return _NON_ALNUM_RUN.sub("-", ascii_text).strip("-")


def new_vacancy_id(
    found_date: date,
    company_slug: str,
    role: str,
    existing_ids: set[str],
) -> str:
    """Mint a deterministic `{date}-{company_slug}-{role_slug}` id.

    Pure function: never mutates `existing_ids`. When the base id
    collides with `existing_ids`, appends the lowest unused numeric
    suffix (`-2`, `-3`, ...).
    """
    role_slug = slugify(role)[:MAX_ROLE_SLUG_LENGTH]
    base = f"{found_date.isoformat()}-{company_slug}-{role_slug}"

    if base not in existing_ids:
        return base

    suffix = 2
    while f"{base}-{suffix}" in existing_ids:
        suffix += 1
    return f"{base}-{suffix}"
