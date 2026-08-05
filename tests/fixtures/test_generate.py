import os
import re
from pathlib import Path

import pytest
from generate import (
    ADJACENT_TECH_TERM,
    DISTINCTIVE_PROPER_NOUN,
    EMAIL_MARKER_PHRASES,
    FIRST_NAMES,
    LAST_NAMES,
    RARE_TECH_TERM,
    REQUIRED_UNKNOWN_ROLE_COUNT,
    SEARCH_FIXTURE_COMPANY_SLUG,
    SEMANTIC_PARAPHRASE_QUERY,
    SEMANTIC_PARAPHRASE_TARGET_DOC_ID,
    SEMANTIC_PARAPHRASE_TARGET_TEXT,
    SYNTHETIC_COMPANY_NAMES,
    VAULT_MARKER_DIRNAME,
    generate_vault,
    write_broken_fixtures,
    write_search_fixtures,
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


def test_generated_vault_has_marker_directory(
    tmp_path_factory: pytest.TempPathFactory,
) -> None:
    vault = _generate(tmp_path_factory, "marker")

    assert (vault / VAULT_MARKER_DIRNAME).is_dir()


def test_at_least_one_takehome_document_is_non_markdown(
    tmp_path_factory: pytest.TempPathFactory,
) -> None:
    vault = _generate(tmp_path_factory, "non-markdown-takehome")

    non_markdown_files = [p for p in vault.glob("*/*/documents/*") if p.suffix != ".md"]
    assert non_markdown_files

    for path in non_markdown_files:
        # It must not be parseable as frontmatter - no leading delimiter.
        assert not path.read_bytes().startswith(b"---\n")


def test_scale_override_produces_a_larger_vault(
    tmp_path_factory: pytest.TempPathFactory,
) -> None:
    default_vault = _generate(tmp_path_factory, "default-scale")
    default_vacancies = _load_vacancies(default_vault)

    scaled_output = tmp_path_factory.mktemp("large-scale")
    generate_vault(scaled_output, seed=SEED, min_companies=60, max_companies=60)
    scaled_vacancies = _load_vacancies(scaled_output)

    assert len(scaled_vacancies) > len(default_vacancies)


def test_scale_override_does_not_touch_committed_fixture(
    tmp_path_factory: pytest.TempPathFactory,
) -> None:
    committed_vault = Path(__file__).parent / "vault"
    before = {
        rel: (committed_vault / rel).read_bytes()
        for rel in (
            p.relative_to(committed_vault)
            for p in committed_vault.rglob("*")
            if p.is_file()
        )
    }

    scaled_output = tmp_path_factory.mktemp("scale-no-touch")
    generate_vault(scaled_output, seed=SEED, min_companies=30, max_companies=30)

    after = {
        rel: (committed_vault / rel).read_bytes()
        for rel in (
            p.relative_to(committed_vault)
            for p in committed_vault.rglob("*")
            if p.is_file()
        )
    }
    assert before == after


def test_broken_mode_preserves_healthy_tree_files(
    tmp_path_factory: pytest.TempPathFactory,
) -> None:
    healthy_only = _generate(tmp_path_factory, "healthy-only")

    healthy_plus_broken = tmp_path_factory.mktemp("healthy-plus-broken")
    generate_vault(healthy_plus_broken, seed=SEED)
    write_broken_fixtures(healthy_plus_broken)

    healthy_files = sorted(
        p.relative_to(healthy_only) for p in healthy_only.rglob("*") if p.is_file()
    )
    for rel in healthy_files:
        assert (healthy_plus_broken / rel).read_bytes() == (
            healthy_only / rel
        ).read_bytes()


MIN_DUPLICATE_ID_PATHS = 2


def test_broken_mode_adds_malformed_fixtures(
    tmp_path_factory: pytest.TempPathFactory,
) -> None:
    vault = tmp_path_factory.mktemp("broken")
    generate_vault(vault, seed=SEED)
    write_broken_fixtures(vault)

    known_statuses = {s.value for s in Status}
    unparseable: list[Path] = []
    unknown_status_found = False
    duplicate_ids: dict[str, list[Path]] = {}

    for path in vault.glob("*/*/vacancy.md"):
        if not os.access(path, os.R_OK):
            continue
        try:
            metadata, _ = parse(path.read_text(encoding="utf-8"))
        except Exception:  # noqa: BLE001 - any parse failure counts here
            unparseable.append(path)
            continue
        status = metadata.get("status")
        if status is not None and status not in known_statuses:
            unknown_status_found = True
        vacancy_id = metadata.get("id")
        if vacancy_id:
            duplicate_ids.setdefault(vacancy_id, []).append(path)

    assert unparseable
    assert unknown_status_found
    assert any(len(paths) >= MIN_DUPLICATE_ID_PATHS for paths in duplicate_ids.values())

    unreadable = [p for p in vault.glob("*/*/vacancy.md") if not os.access(p, os.R_OK)]
    assert unreadable
    for path in unreadable:
        path.chmod(0o644)  # restore so pytest's tmp_path cleanup can remove it

    orphan_dirs = [
        p for p in vault.glob("*/*/documents") if not (p.parent / "vacancy.md").exists()
    ]
    assert orphan_dirs


# --- Search fixtures (stage 4) ----------------------------------------------


def _generate_with_search_fixtures(
    tmp_path_factory: pytest.TempPathFactory, name: str
) -> Path:
    vault = _generate(tmp_path_factory, name)
    write_search_fixtures(vault)
    return vault


def _all_document_bodies(vault: Path) -> dict[Path, str]:
    bodies = {}
    for doc_path in vault.glob("*/*/documents/*.md"):
        _, body = parse(doc_path.read_text(encoding="utf-8"))
        bodies[doc_path] = body
    return bodies


def test_distinctive_proper_noun_appears_in_exactly_one_document(
    tmp_path_factory: pytest.TempPathFactory,
) -> None:
    vault = _generate_with_search_fixtures(tmp_path_factory, "proper-noun")

    matches = [
        path
        for path, body in _all_document_bodies(vault).items()
        if DISTINCTIVE_PROPER_NOUN in body
    ]

    assert len(matches) == 1


def test_rare_term_and_adjacent_term_live_in_different_documents(
    tmp_path_factory: pytest.TempPathFactory,
) -> None:
    vault = _generate_with_search_fixtures(tmp_path_factory, "rare-term")
    bodies = _all_document_bodies(vault)

    rare_docs = [path for path, body in bodies.items() if RARE_TECH_TERM in body]
    adjacent_docs = [
        path for path, body in bodies.items() if ADJACENT_TECH_TERM in body
    ]

    assert rare_docs
    assert adjacent_docs
    assert set(rare_docs).isdisjoint(adjacent_docs)
    for path in rare_docs:
        assert ADJACENT_TECH_TERM not in bodies[path]
    for path in adjacent_docs:
        assert RARE_TECH_TERM not in bodies[path]


def test_search_fixture_company_is_present(
    tmp_path_factory: pytest.TempPathFactory,
) -> None:
    vault = _generate_with_search_fixtures(tmp_path_factory, "company-present")

    assert (vault / SEARCH_FIXTURE_COMPANY_SLUG / "_company.md").is_file()


def test_paraphrase_target_document_exists_with_expected_text(
    tmp_path_factory: pytest.TempPathFactory,
) -> None:
    vault = _generate_with_search_fixtures(tmp_path_factory, "paraphrase-target")
    bodies = _all_document_bodies(vault)

    matching = [
        body
        for path, body in bodies.items()
        if path.stem == SEMANTIC_PARAPHRASE_TARGET_DOC_ID
    ]

    assert matching == [SEMANTIC_PARAPHRASE_TARGET_TEXT]


_WORD_RE = re.compile(r"[A-Za-z']+")
_STOPWORDS = {
    "a",
    "an",
    "the",
    "and",
    "or",
    "but",
    "is",
    "are",
    "was",
    "were",
    "be",
    "in",
    "on",
    "at",
    "to",
    "of",
    "for",
    "with",
    "each",
    "other",
    "their",
    "how",
    "did",
    "do",
    "when",
    "during",
    "throughout",
    "many",
}


def _content_words(text: str) -> set[str]:
    return {w.lower() for w in _WORD_RE.findall(text)} - _STOPWORDS


def test_paraphrase_query_shares_no_content_words_with_its_target() -> None:
    target_words = _content_words(SEMANTIC_PARAPHRASE_TARGET_TEXT)
    query_words = _content_words(SEMANTIC_PARAPHRASE_QUERY)

    assert target_words
    assert query_words
    assert target_words.isdisjoint(query_words)
