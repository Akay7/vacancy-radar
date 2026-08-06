from datetime import date, datetime, timedelta
from pathlib import Path

import pytest

from vacancy_radar import core, frontmatter
from vacancy_radar.index import search as index_search
from vacancy_radar.index.build import build_index
from vacancy_radar.index.search import SearchMode
from vacancy_radar.index.store import default_index_path, get_index_handle
from vacancy_radar.models import Company, Document, DocumentKind, Status, Vacancy
from vacancy_radar.vault.paths import VAULT_MARKER_DIRNAME
from vacancy_radar.vault.reader import VaultSnapshot, read_vault

FIXTURE_VAULT = Path(__file__).resolve().parent / "fixtures" / "vault"

# --- Ad hoc vault-building helpers (1.3) -----------------------------------
#
# Mirrors tests/vault/test_reader.py's _init_vault/_simple_vacancy/
# _write_vacancy pattern - self-contained per file, no shared fixture.


def _init_vault(vault: Path) -> None:
    (vault / VAULT_MARKER_DIRNAME).mkdir(parents=True, exist_ok=True)


def _write_company(vault: Path, slug: str, name: str) -> None:
    company_dir = vault / slug
    company_dir.mkdir(parents=True, exist_ok=True)
    company = Company(slug=slug, name=name, domains=[f"{slug}.example"])
    metadata = company.model_dump(mode="json", exclude_none=True)
    (company_dir / "_company.md").write_text(
        frontmatter.serialize(metadata, ""), encoding="utf-8"
    )


def _write_vacancy(vault: Path, slug: str, dirname: str, vacancy: Vacancy) -> Path:
    vacancy_dir = vault / slug / dirname
    vacancy_dir.mkdir(parents=True, exist_ok=True)
    metadata = vacancy.model_dump(
        mode="json", exclude={"role_is_placeholder"}, exclude_none=True
    )
    (vacancy_dir / "vacancy.md").write_text(
        frontmatter.serialize(metadata, f"# {vacancy.role}\n"), encoding="utf-8"
    )
    return vacancy_dir


def _write_document(vacancy_dir: Path, document: Document, body: str = "body") -> None:
    docs_dir = vacancy_dir / "documents"
    docs_dir.mkdir(parents=True, exist_ok=True)
    metadata = document.model_dump(mode="json", exclude_none=True)
    (docs_dir / f"{document.id}.md").write_text(
        frontmatter.serialize(metadata, body), encoding="utf-8"
    )


def _simple_vacancy(
    vacancy_id: str, slug: str = "acme", **overrides: object
) -> Vacancy:
    fields: dict[str, object] = {
        "id": vacancy_id,
        "company": "Acme",
        "company_slug": slug,
        "role": "Engineer",
        "source_url": f"https://jobs.{slug}.example/{vacancy_id}",
        "status": Status.FOUND,
        "found_date": date(2026, 1, 1),
    }
    fields.update(overrides)
    return Vacancy(**fields)  # type: ignore[arg-type]


def _minimal_built_vault(vault: Path) -> Path:
    """A tiny hand-built vault (marker + one company + one vacancy +
    one document) - small so embedding it stays fast, unlike the full
    fixture vault. Not yet indexed; callers build the index."""
    _init_vault(vault)
    _write_company(vault, "tiny-corp", "Tiny Corp")
    vacancy_dir = _write_vacancy(
        vault, "tiny-corp", "v1", _simple_vacancy("v1", slug="tiny-corp")
    )
    _write_document(
        vacancy_dir,
        Document(
            id="v1-doc1",
            vacancy_id="v1",
            kind=DocumentKind.NOTE,
            title="Note",
            date=date(2026, 1, 2),
        ),
    )
    return vault


def _vacancy_summary_fields() -> set[str]:
    return {
        "id",
        "company",
        "role",
        "status",
        "applied_date",
        "last_activity",
        "document_count",
    }


# --- Section 2: resolve() ---------------------------------------------------


def test_resolve_exact_id_matches_that_vacancy() -> None:
    snapshot = read_vault(FIXTURE_VAULT)
    vacancy_id = next(iter(snapshot.vacancies))

    resolution = core.resolve(vacancy_id, vault=FIXTURE_VAULT)

    assert resolution.vacancy_id == vacancy_id
    assert resolution.candidates == ()


def test_resolve_exact_company_slug_matches_that_company() -> None:
    snapshot = read_vault(FIXTURE_VAULT)
    slug = next(iter(snapshot.companies))

    resolution = core.resolve(slug, vault=FIXTURE_VAULT)

    assert resolution.company_slug == slug


def test_resolve_case_insensitive_display_name_matches() -> None:
    snapshot = read_vault(FIXTURE_VAULT)
    company = next(iter(snapshot.companies.values()))

    resolution = core.resolve(company.name.upper(), vault=FIXTURE_VAULT)

    assert resolution.company_slug == company.slug


def test_resolve_fuzzy_acme_matches_acme_corp_when_unambiguous() -> None:
    resolution = core.resolve("Acme", vault=FIXTURE_VAULT)

    assert resolution.company_slug == "acme-corp"


def test_resolve_ambiguous_company_match_returns_both_candidates(
    tmp_path: Path,
) -> None:
    vault = tmp_path / "vault"
    _init_vault(vault)
    _write_company(vault, "widget-us", "Widget Inc")
    _write_company(vault, "widget-eu", "Widget Inc")

    resolution = core.resolve("widget inc", vault=vault)

    assert resolution.vacancy_id is None
    assert resolution.company_slug is None
    assert {c.slug for c in resolution.candidates} == {"widget-us", "widget-eu"}


def test_resolve_returns_empty_resolution_for_no_match() -> None:
    resolution = core.resolve("zzz-nonexistent-zzz", vault=FIXTURE_VAULT)

    assert resolution.vacancy_id is None
    assert resolution.company_slug is None
    assert resolution.candidates == ()


def test_resolve_order_is_exact_id_before_company(tmp_path: Path) -> None:
    vault = tmp_path / "vault"
    _init_vault(vault)
    _write_company(vault, "wondercorp", "Wonder Co")
    _write_company(vault, "other-corp", "Other Corp")
    collider = _simple_vacancy("Wonder Co", slug="other-corp")
    _write_vacancy(vault, "other-corp", "v1", collider)

    resolution = core.resolve("Wonder Co", vault=vault)

    assert resolution.vacancy_id == "Wonder Co"
    assert resolution.company_slug is None


# --- Section 3: list_vacancies() --------------------------------------------


def test_list_vacancies_no_filters_returns_all_vacancies() -> None:
    snapshot = read_vault(FIXTURE_VAULT)
    total = len(snapshot.vacancies)

    summaries = core.list_vacancies(vault=FIXTURE_VAULT, limit=total)

    assert len(summaries) == total
    assert {s.id for s in summaries} == set(snapshot.vacancies)


def test_list_vacancies_status_filter_returns_union() -> None:
    snapshot = read_vault(FIXTURE_VAULT)
    statuses_present = sorted({v.status for v in snapshot.vacancies.values()}, key=str)
    chosen = statuses_present[:2]

    summaries = core.list_vacancies(vault=FIXTURE_VAULT, status=chosen, limit=1000)

    expected_ids = {v.id for v in snapshot.vacancies.values() if v.status in chosen}
    assert summaries
    assert {s.id for s in summaries} == expected_ids


def test_list_vacancies_company_filter_restricts_to_that_company() -> None:
    snapshot = read_vault(FIXTURE_VAULT)
    slug = next(iter(snapshot.companies))

    summaries = core.list_vacancies(vault=FIXTURE_VAULT, company=slug, limit=1000)

    assert summaries
    assert all(snapshot.vacancies[s.id].company_slug == slug for s in summaries)


def test_list_vacancies_since_excludes_earlier_vacancies() -> None:
    snapshot = read_vault(FIXTURE_VAULT)
    effective_dates = sorted(
        (v.applied_date or v.found_date) for v in snapshot.vacancies.values()
    )
    since = effective_dates[len(effective_dates) // 2]
    excluded_ids = {
        v.id
        for v in snapshot.vacancies.values()
        if (v.applied_date or v.found_date) < since
    }
    assert excluded_ids  # sanity: the chosen cutoff actually excludes something

    summaries = core.list_vacancies(vault=FIXTURE_VAULT, since=since, limit=1000)

    assert not ({s.id for s in summaries} & excluded_ids)


def test_list_vacancies_needs_review_returns_exactly_tagged_vacancies() -> None:
    snapshot = read_vault(FIXTURE_VAULT)
    expected = {v.id for v in snapshot.vacancies.values() if "needs_review" in v.tags}
    assert expected  # sanity: the generator guarantees some

    summaries = core.list_vacancies(vault=FIXTURE_VAULT, needs_review=True, limit=1000)

    assert {s.id for s in summaries} == expected


def test_list_vacancies_stale_days_uses_last_activity_not_applied_date(
    tmp_path: Path,
) -> None:
    vault = tmp_path / "vault"
    _init_vault(vault)
    _write_company(vault, "acme", "Acme")
    today = datetime.now().astimezone().date()

    old_applied_recent_doc = _simple_vacancy(
        "old-applied-recent-doc",
        status=Status.APPLIED,
        found_date=today - timedelta(days=400),
        applied_date=today - timedelta(days=395),
    )
    vacancy_dir = _write_vacancy(vault, "acme", "v1", old_applied_recent_doc)
    _write_document(
        vacancy_dir,
        Document(
            id="v1-doc1",
            vacancy_id="old-applied-recent-doc",
            kind=DocumentKind.NOTE,
            title="Recent note",
            date=today - timedelta(days=2),
        ),
    )

    no_recent_activity = _simple_vacancy(
        "no-recent-activity",
        status=Status.APPLIED,
        found_date=today - timedelta(days=400),
        applied_date=today - timedelta(days=395),
    )
    _write_vacancy(vault, "acme", "v2", no_recent_activity)

    summaries = core.list_vacancies(vault=vault, stale_days=30, limit=1000)

    ids = {s.id for s in summaries}
    assert "old-applied-recent-doc" not in ids
    assert "no-recent-activity" in ids


def test_list_vacancies_sort_activity_orders_descending_stable_for_ties(
    tmp_path: Path,
) -> None:
    vault = tmp_path / "vault"
    _init_vault(vault)
    _write_company(vault, "acme", "Acme")
    same_date = date(2026, 1, 5)
    _write_vacancy(vault, "acme", "a", _simple_vacancy("tie-a", found_date=same_date))
    _write_vacancy(vault, "acme", "b", _simple_vacancy("tie-b", found_date=same_date))

    first = core.list_vacancies(vault=vault, sort="activity")
    second = core.list_vacancies(vault=vault, sort="activity")

    tie_ids_first = [s.id for s in first if s.id in ("tie-a", "tie-b")]
    tie_ids_second = [s.id for s in second if s.id in ("tie-a", "tie-b")]
    assert tie_ids_first == ["tie-a", "tie-b"]
    assert tie_ids_first == tie_ids_second


def test_list_vacancies_summaries_contain_no_document_bodies() -> None:
    assert set(core.VacancySummary.model_fields) == _vacancy_summary_fields()


# --- Section 4: get_company() -----------------------------------------------


def _company_with_multiple_vacancies(snapshot: VaultSnapshot) -> str:
    for slug in snapshot.companies:
        if len(snapshot.vacancies_for(slug)) >= 2:  # noqa: PLR2004
            return slug
    pytest.fail("fixture vault has no company with >= 2 vacancies")


def test_get_company_returns_all_vacancies_oldest_and_newest() -> None:
    snapshot = read_vault(FIXTURE_VAULT)
    slug = _company_with_multiple_vacancies(snapshot)
    vacancies = snapshot.vacancies_for(slug)
    dated = sorted(vacancies, key=lambda v: v.applied_date or v.found_date)

    dossier = core.get_company(slug, vault=FIXTURE_VAULT)

    ids = {v.id for v in dossier.vacancies}
    assert dated[0].id in ids
    assert dated[-1].id in ids
    assert len(dossier.vacancies) == len(vacancies)


def test_get_company_recruiters_and_domains_come_from_company_md() -> None:
    snapshot = read_vault(FIXTURE_VAULT)
    company = next(iter(snapshot.companies.values()))

    dossier = core.get_company(company.slug, vault=FIXTURE_VAULT)

    assert dossier.recruiters == company.recruiters
    assert dossier.domains == company.domains


def test_get_company_with_no_company_md_still_returns_vacancies_with_warning(
    tmp_path: Path,
) -> None:
    vault = tmp_path / "vault"
    _init_vault(vault)
    (vault / "no-company-corp").mkdir(parents=True)
    _write_vacancy(
        vault,
        "no-company-corp",
        "v1",
        _simple_vacancy("orphan-v1", slug="no-company-corp"),
    )

    dossier = core.get_company("no-company-corp", vault=vault)

    assert [v.id for v in dossier.vacancies] == ["orphan-v1"]
    assert dossier.warnings


def test_get_company_reports_document_counts_and_no_bodies() -> None:
    snapshot = read_vault(FIXTURE_VAULT)
    slug = _company_with_multiple_vacancies(snapshot)

    dossier = core.get_company(slug, vault=FIXTURE_VAULT)

    assert all(
        v.document_count == len(snapshot.documents_for(v.id)) for v in dossier.vacancies
    )
    assert set(core.VacancySummary.model_fields) == _vacancy_summary_fields()


# --- Section 5: get_vacancy() -----------------------------------------------


def _vacancy_with_varied_document_dates(snapshot: VaultSnapshot) -> str:
    for vacancy_id in snapshot.vacancies:
        docs = snapshot.documents_for(vacancy_id)
        if len({d.date for d in docs}) >= 2:  # noqa: PLR2004
            return vacancy_id
    pytest.fail("fixture vault has no vacancy with documents on differing dates")


def _vacancy_with_stage_note(snapshot: VaultSnapshot) -> str:
    for vacancy_id, vacancy in snapshot.vacancies.items():
        if vacancy.stage_note:
            return vacancy_id
    pytest.fail("fixture vault has no vacancy with a stage_note")


def test_get_vacancy_documents_are_date_ascending_with_titles_and_paths() -> None:
    snapshot = read_vault(FIXTURE_VAULT)
    vacancy_id = _vacancy_with_varied_document_dates(snapshot)

    detail = core.get_vacancy(vacancy_id, vault=FIXTURE_VAULT)

    dates = [d.date for d in detail.documents]
    assert dates == sorted(dates)
    assert all(d.title and d.path for d in detail.documents)


def test_get_vacancy_stage_note_is_verbatim() -> None:
    snapshot = read_vault(FIXTURE_VAULT)
    vacancy_id = _vacancy_with_stage_note(snapshot)

    detail = core.get_vacancy(vacancy_id, vault=FIXTURE_VAULT)

    assert detail.stage_note == snapshot.vacancies[vacancy_id].stage_note


def test_get_vacancy_with_zero_documents_succeeds(tmp_path: Path) -> None:
    vault = tmp_path / "vault"
    _init_vault(vault)
    _write_company(vault, "acme", "Acme")
    _write_vacancy(vault, "acme", "v1", _simple_vacancy("no-docs-vacancy"))

    detail = core.get_vacancy("no-docs-vacancy", vault=vault)

    assert detail.documents == []


def test_vacancy_detail_document_summaries_have_no_body_field() -> None:
    assert set(core.DocumentSummary.model_fields) == {
        "id",
        "title",
        "kind",
        "date",
        "path",
    }


# --- Section 6: read_document() ---------------------------------------------


def test_read_document_returns_full_text_for_valid_vault_path() -> None:
    snapshot = read_vault(FIXTURE_VAULT)
    vacancy_id = next(iter(snapshot.vacancy_paths))
    path = snapshot.vacancy_paths[vacancy_id]

    content = core.read_document(path, vault=FIXTURE_VAULT)

    assert content.text == path.read_text(encoding="utf-8")


def test_read_document_rejects_path_outside_vault(tmp_path: Path) -> None:
    vault = tmp_path / "vault"
    _init_vault(vault)
    outside = tmp_path / "outside.txt"
    outside.write_text("nope", encoding="utf-8")

    with pytest.raises(core.PathOutsideVaultError):
        core.read_document(outside, vault=vault)


def test_read_document_rejects_dotdot_traversal(tmp_path: Path) -> None:
    vault = tmp_path / "vault"
    _init_vault(vault)
    (tmp_path / "outside.txt").write_text("nope", encoding="utf-8")

    with pytest.raises(core.PathOutsideVaultError):
        core.read_document("../outside.txt", vault=vault)


def test_read_document_raises_for_nonexistent_path_inside_vault(tmp_path: Path) -> None:
    vault = tmp_path / "vault"
    _init_vault(vault)

    with pytest.raises(core.DocumentNotFoundError):
        core.read_document("does-not-exist.md", vault=vault)


# --- doctor(): cheap, non-embedding path (no index built) ------------------


def test_doctor_against_healthy_fixture_vault_with_no_index_built() -> None:
    report = core.doctor(vault=FIXTURE_VAULT)

    assert report.vault_warnings == []
    assert report.embedding_model_available is True
    assert report.index_present is False
    assert report.healthy is True


# --- Section 7: index-freshness check (embedding-marked: builds a real index)


@pytest.mark.embedding
def test_index_freshness_reports_missing_document_count(tmp_path: Path) -> None:
    vault = _minimal_built_vault(tmp_path / "vault")
    build_index(read_vault(vault), default_index_path(vault))
    index = get_index_handle(vault)

    vacancy_dir = vault / "tiny-corp" / "v1"
    _write_document(
        vacancy_dir,
        Document(
            id="v1-doc2",
            vacancy_id="v1",
            kind=DocumentKind.NOTE,
            title="New note",
            date=date(2026, 1, 9),
        ),
    )

    warning = core._index_freshness(vault, index)  # noqa: SLF001 - the unit under test

    assert warning is not None
    assert warning.missing_count == 1


@pytest.mark.embedding
def test_index_freshness_does_not_raise_when_stale(tmp_path: Path) -> None:
    vault = _minimal_built_vault(tmp_path / "vault")
    build_index(read_vault(vault), default_index_path(vault))
    index = get_index_handle(vault)

    vacancy_dir = vault / "tiny-corp" / "v1"
    _write_document(
        vacancy_dir,
        Document(
            id="v1-doc2",
            vacancy_id="v1",
            kind=DocumentKind.NOTE,
            title="New note",
            date=date(2026, 1, 9),
        ),
    )

    core._index_freshness(vault, index)  # noqa: SLF001 - must not raise


# --- Section 8: search() wrapper (embedding-marked: builds a real index) ---


@pytest.fixture(scope="module")
def fresh_search_vault(tmp_path_factory: pytest.TempPathFactory) -> Path:
    """A vault holding a fresh index of the committed fixture vault's
    content, built once and reused read-only by this module's tests -
    building is the slow, embedding-marked part."""
    vault_root = tmp_path_factory.mktemp("core-search-vault")
    _init_vault(vault_root)
    build_index(read_vault(FIXTURE_VAULT), default_index_path(vault_root))
    return vault_root


@pytest.mark.embedding
def test_core_search_returns_same_hits_as_index_search(
    fresh_search_vault: Path,
) -> None:
    core_results = core.search(
        "Engineer", vault=fresh_search_vault, mode=SearchMode.KEYWORD, limit=5
    )
    index = get_index_handle(fresh_search_vault)
    raw = index_search.search(index, "Engineer", mode=SearchMode.KEYWORD, limit=5)

    assert [h.doc_id for h in core_results.hits] == [h.doc_id for h in raw.hits]


@pytest.mark.embedding
def test_core_search_attaches_staleness_warning(tmp_path: Path) -> None:
    vault = _minimal_built_vault(tmp_path / "vault")
    build_index(read_vault(vault), default_index_path(vault))
    vacancy_dir = vault / "tiny-corp" / "v1"
    _write_document(
        vacancy_dir,
        Document(
            id="v1-doc2",
            vacancy_id="v1",
            kind=DocumentKind.NOTE,
            title="New note",
            date=date(2026, 1, 9),
        ),
    )

    results = core.search("Note", vault=vault, mode=SearchMode.KEYWORD, limit=5)

    assert results.freshness_warning is not None
    assert results.freshness_warning.missing_count == 1


@pytest.mark.embedding
def test_core_search_does_not_raise_when_stale(tmp_path: Path) -> None:
    vault = _minimal_built_vault(tmp_path / "vault")
    build_index(read_vault(vault), default_index_path(vault))
    vacancy_dir = vault / "tiny-corp" / "v1"
    _write_document(
        vacancy_dir,
        Document(
            id="v1-doc2",
            vacancy_id="v1",
            kind=DocumentKind.NOTE,
            title="New note",
            date=date(2026, 1, 9),
        ),
    )

    core.search("Note", vault=vault, mode=SearchMode.KEYWORD, limit=5)  # must not raise
