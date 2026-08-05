from pathlib import Path

import pytest
from generate import (
    EMAIL_MARKER_PHRASES,
    FIRST_NAMES,
    LAST_NAMES,
    REQUIRED_UNKNOWN_ROLE_COUNT,
    SYNTHETIC_COMPANY_NAMES,
    generate_vault,
)

from vacancy_radar.frontmatter import parse
from vacancy_radar.models import Company, DocumentKind, Status, Vacancy

SEED = 20260101
MIN_COMPANIES_SPANNING_YEARS = 2


def _generate(tmp_path_factory: pytest.TempPathFactory, name: str) -> Path:
    output = tmp_path_factory.mktemp(name)
    generate_vault(output, seed=SEED)
    return output


def _load_vacancies(vault_dir: Path) -> list[Vacancy]:
    vacancies = []
    for vacancy_file in sorted(vault_dir.glob("*/*/vacancy.md")):
        metadata, _ = parse(vacancy_file.read_text(encoding="utf-8"))
        vacancies.append(Vacancy(**metadata))
    return vacancies


def _load_companies(vault_dir: Path) -> list[Company]:
    companies = []
    for company_file in sorted(vault_dir.glob("*/_company.md")):
        metadata, _ = parse(company_file.read_text(encoding="utf-8"))
        companies.append(Company(**metadata))
    return companies


def test_same_seed_produces_byte_identical_trees(
    tmp_path_factory: pytest.TempPathFactory,
) -> None:
    first = _generate(tmp_path_factory, "first")
    second = _generate(tmp_path_factory, "second")

    first_files = sorted(p.relative_to(first) for p in first.rglob("*") if p.is_file())
    second_files = sorted(
        p.relative_to(second) for p in second.rglob("*") if p.is_file()
    )
    assert first_files == second_files
    assert first_files

    for rel in first_files:
        assert (first / rel).read_bytes() == (second / rel).read_bytes()


def test_every_status_value_appears(tmp_path_factory: pytest.TempPathFactory) -> None:
    vault = _generate(tmp_path_factory, "statuses")
    vacancies = _load_vacancies(vault)

    statuses_present = {v.status for v in vacancies}
    assert statuses_present == set(Status)


def test_at_least_two_companies_span_different_calendar_years(
    tmp_path_factory: pytest.TempPathFactory,
) -> None:
    vault = _generate(tmp_path_factory, "years")
    vacancies = _load_vacancies(vault)

    years_by_company: dict[str, set[int]] = {}
    for vacancy in vacancies:
        years_by_company.setdefault(vacancy.company_slug, set()).add(
            vacancy.found_date.year
        )

    companies_spanning_years = [
        slug
        for slug, years in years_by_company.items()
        if len(years) >= MIN_COMPANIES_SPANNING_YEARS
    ]
    assert len(companies_spanning_years) >= MIN_COMPANIES_SPANNING_YEARS


def test_at_least_three_vacancies_are_unknown_role_and_flagged(
    tmp_path_factory: pytest.TempPathFactory,
) -> None:
    vault = _generate(tmp_path_factory, "unknown-role")
    vacancies = _load_vacancies(vault)

    flagged = [v for v in vacancies if v.role_is_placeholder]
    assert len(flagged) >= REQUIRED_UNKNOWN_ROLE_COUNT
    for vacancy in flagged:
        assert "needs_review" in vacancy.tags


def test_at_least_one_company_name_is_non_ascii(
    tmp_path_factory: pytest.TempPathFactory,
) -> None:
    vault = _generate(tmp_path_factory, "non-ascii")
    companies = _load_companies(vault)

    assert any(not company.name.isascii() for company in companies)


def test_generated_content_is_drawn_only_from_synthetic_pools(
    tmp_path_factory: pytest.TempPathFactory,
) -> None:
    vault = _generate(tmp_path_factory, "synthetic")
    companies = _load_companies(vault)
    vacancies = _load_vacancies(vault)

    for company in companies:
        assert company.name in SYNTHETIC_COMPANY_NAMES
        for recruiter in company.recruiters:
            first, _, last = recruiter.partition(" ")
            assert first in FIRST_NAMES
            assert last in LAST_NAMES

    for vacancy_file in sorted(vault.glob("*/*/documents/*.md")):
        metadata, body = parse(vacancy_file.read_text(encoding="utf-8"))
        if metadata.get("kind") == DocumentKind.EMAIL.value:
            assert any(phrase in body for phrase in EMAIL_MARKER_PHRASES)

    assert vacancies  # sanity: the loop above ran against real data
