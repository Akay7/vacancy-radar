from datetime import date

import pytest

from vacancy_radar.ids import MAX_ROLE_SLUG_LENGTH, new_vacancy_id, slugify


@pytest.mark.parametrize(
    ("company_name", "expected_slug"),
    [
        ("Ромашка", "romashka"),
        ("Widget & Sons", "widget-sons"),
        ("Acme Inc.", "acme-inc"),
        ("Šaltinis Studija", "saltinis-studija"),
    ],
)
def test_slugify_produces_readable_ascii_transliteration(
    company_name: str, expected_slug: str
) -> None:
    result = slugify(company_name)

    assert result == expected_slug
    assert result.isascii()
    assert "%" not in result
    assert "\\x" not in result


def test_new_vacancy_id_is_deterministic_and_pure() -> None:
    existing_ids = {"2026-01-01-acme-developer"}
    frozen = frozenset(existing_ids)

    first = new_vacancy_id(date(2026, 2, 1), "acme", "designer", existing_ids)
    second = new_vacancy_id(date(2026, 2, 1), "acme", "designer", existing_ids)

    assert first == second
    assert existing_ids == frozen


def test_new_vacancy_id_format_and_lexical_sort_matches_chronological() -> None:
    triples = [
        (date(2026, 3, 1), "acme", "developer"),
        (date(2024, 1, 15), "beta", "designer"),
        (date(2025, 6, 30), "gamma", "analyst"),
    ]

    ids = [new_vacancy_id(d, slug, role, set()) for d, slug, role in triples]

    for minted_id, (found_date, company_slug, role) in zip(ids, triples, strict=True):
        assert minted_id == f"{found_date.isoformat()}-{company_slug}-{slugify(role)}"

    chronological_order = [
        i for _, i in sorted(zip((d for d, _, _ in triples), ids, strict=True))
    ]
    assert sorted(ids) == chronological_order


def test_id_depends_only_on_frontmatter_content_not_a_path() -> None:
    # The same frontmatter content, as if read from two different paths
    # (e.g. before and after a directory rename), yields the same id.
    args = (date(2026, 4, 1), "acme", "developer")

    id_from_location_a = new_vacancy_id(*args, set())
    id_from_location_b = new_vacancy_id(*args, set())

    assert id_from_location_a == id_from_location_b


def test_collision_batch_resolves_with_sequential_numeric_suffixes() -> None:
    # Migration-shaped: several vacancies found the same day at the same
    # company, all with an undetermined role.
    found_date = date(2026, 5, 1)
    company_slug = "acme"
    role = "unknown"
    batch_size = 5

    existing_ids: set[str] = set()
    minted = []
    for _ in range(batch_size):
        new_id = new_vacancy_id(found_date, company_slug, role, existing_ids)
        minted.append(new_id)
        existing_ids.add(new_id)

    assert len(set(minted)) == batch_size

    base = f"{found_date.isoformat()}-{company_slug}-{slugify(role)}"
    assert minted[0] == base
    assert minted[1:] == [f"{base}-{n}" for n in range(2, batch_size + 1)]


def test_role_slug_truncates_deterministically() -> None:
    long_role = "senior " * 20 + "engineer"

    first = new_vacancy_id(date(2026, 6, 1), "acme", long_role, set())
    second = new_vacancy_id(date(2026, 6, 1), "acme", long_role, set())

    role_segment = first.removeprefix("2026-06-01-acme-")
    assert len(role_segment) <= MAX_ROLE_SLUG_LENGTH
    assert first == second
