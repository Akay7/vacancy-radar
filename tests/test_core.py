import sys
from datetime import date, datetime, timedelta
from pathlib import Path

import pytest

from vacancy_radar import core, frontmatter
from vacancy_radar.config import VaultNotConfiguredError
from vacancy_radar.index import search as index_search
from vacancy_radar.index.build import build_index
from vacancy_radar.index.search import SearchMode
from vacancy_radar.index.store import default_index_path, get_index_handle
from vacancy_radar.models import (
    UNKNOWN_ROLE,
    Company,
    Document,
    DocumentKind,
    Status,
    Vacancy,
)
from vacancy_radar.vault.paths import VAULT_MARKER_DIRNAME
from vacancy_radar.vault.reader import VaultSnapshot, read_vault

FIXTURE_VAULT = Path(__file__).resolve().parent / "fixtures" / "vault"

_FIXTURES_DIR = Path(__file__).resolve().parent / "fixtures"
if str(_FIXTURES_DIR) not in sys.path:
    sys.path.insert(0, str(_FIXTURES_DIR))

from pdfs import write_malformed_pdf, write_valid_pdf  # noqa: E402

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
        "resume",
    }


# --- Section 1b (vault-init change): init_vault() --------------------------


def test_init_vault_creates_marker_under_new_path(tmp_path: Path) -> None:
    target = tmp_path / "nested" / "new-vault"

    result = core.init_vault(target)

    assert target.is_dir()
    assert (target / VAULT_MARKER_DIRNAME).is_dir()
    assert result.created is True
    assert result.path == target.resolve()


def test_init_vault_adds_marker_to_existing_directory_without_touching_contents(
    tmp_path: Path,
) -> None:
    target = tmp_path / "existing"
    target.mkdir()
    (target / "unrelated.txt").write_text("keep me", encoding="utf-8")

    result = core.init_vault(target)

    assert (target / VAULT_MARKER_DIRNAME).is_dir()
    assert (target / "unrelated.txt").read_text(encoding="utf-8") == "keep me"
    assert result.created is True


def test_init_vault_is_a_noop_on_already_initialized_vault(tmp_path: Path) -> None:
    target = tmp_path / "vault"
    _init_vault(target)
    marker = target / VAULT_MARKER_DIRNAME
    before_mtime = marker.stat().st_mtime_ns

    result = core.init_vault(target)

    assert result.created is False
    assert marker.stat().st_mtime_ns == before_mtime


def test_init_vault_rejects_a_file_target(tmp_path: Path) -> None:
    target = tmp_path / "not-a-directory"
    target.write_text("x", encoding="utf-8")

    with pytest.raises(core.VaultTargetIsAFileError):
        core.init_vault(target)

    assert target.read_text(encoding="utf-8") == "x"
    assert target.is_file()


def test_init_vault_explicit_path_overrides_vault_path(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    env_target = tmp_path / "env"
    explicit_target = tmp_path / "explicit"
    monkeypatch.setenv("VAULT_PATH", str(env_target))

    result = core.init_vault(explicit_target)

    assert result.path == explicit_target.resolve()
    assert not env_target.exists()


def test_init_vault_falls_back_to_vault_path(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    env_target = tmp_path / "env"
    monkeypatch.setenv("VAULT_PATH", str(env_target))

    result = core.init_vault()

    assert result.path == env_target.resolve()
    assert (env_target / VAULT_MARKER_DIRNAME).is_dir()


def test_init_vault_raises_typed_error_when_neither_present(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("VAULT_PATH", raising=False)

    with pytest.raises(VaultNotConfiguredError):
        core.init_vault()


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


# --- Section 3 (stage 7 write half): atomic write / filename derivation ----


def test_atomic_write_creates_file_with_exact_content_and_no_temp_left(
    tmp_path: Path,
) -> None:
    target = tmp_path / "a.md"

    core._atomic_write(target, "hello", overwrite=False)  # noqa: SLF001

    assert target.read_text(encoding="utf-8") == "hello"
    assert list(tmp_path.iterdir()) == [target]


def test_atomic_write_overwrite_false_refuses_an_existing_path(tmp_path: Path) -> None:
    target = tmp_path / "a.md"
    target.write_text("original", encoding="utf-8")

    with pytest.raises(core.DocumentAlreadyExistsError):
        core._atomic_write(target, "new", overwrite=False)  # noqa: SLF001

    assert target.read_text(encoding="utf-8") == "original"


def test_atomic_write_overwrite_true_replaces_existing_content(tmp_path: Path) -> None:
    target = tmp_path / "vacancy.md"
    target.write_text("original", encoding="utf-8")

    core._atomic_write(target, "updated", overwrite=True)  # noqa: SLF001

    assert target.read_text(encoding="utf-8") == "updated"


_SIMULATED_REPLACE_FAILURE = "simulated replace failure"


def test_atomic_write_new_file_failure_leaves_target_absent(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    target = tmp_path / "a.md"

    def _boom(*_args: object, **_kwargs: object) -> None:
        raise OSError(_SIMULATED_REPLACE_FAILURE)

    # A new file is published by hard link, falling back to an exclusive
    # claim + replace; fail both so the whole publish fails.
    monkeypatch.setattr(core.os, "link", _boom)
    monkeypatch.setattr(core.os, "replace", _boom)

    with pytest.raises(OSError, match=_SIMULATED_REPLACE_FAILURE):
        core._atomic_write(target, "hello", overwrite=False)  # noqa: SLF001

    assert not target.exists()
    # The temp file is cleaned up on a caught failure; nothing is left
    # behind at all (a stronger guarantee than "dot-prefixed and
    # invisible", which is the fallback for an uncatchable crash - see
    # design.md decision 9's risk note).
    assert list(tmp_path.iterdir()) == []


def test_atomic_write_update_failure_leaves_prior_content_intact(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    target = tmp_path / "vacancy.md"
    target.write_text("original", encoding="utf-8")

    def _boom(*_args: object, **_kwargs: object) -> None:
        raise OSError(_SIMULATED_REPLACE_FAILURE)

    monkeypatch.setattr(core.os, "replace", _boom)

    with pytest.raises(OSError, match=_SIMULATED_REPLACE_FAILURE):
        core._atomic_write(target, "updated", overwrite=True)  # noqa: SLF001

    assert target.read_text(encoding="utf-8") == "original"


def test_ensure_within_vault_raises_for_path_outside_vault(tmp_path: Path) -> None:
    vault = tmp_path / "vault"
    vault.mkdir()
    outside = tmp_path / "outside.md"

    with pytest.raises(core.PathOutsideVaultError):
        core._ensure_within_vault(vault, outside)  # noqa: SLF001


def test_ensure_within_vault_does_not_raise_for_contained_path(tmp_path: Path) -> None:
    vault = tmp_path / "vault"
    inside = vault / "acme" / "v1" / "documents" / "note.md"
    inside.parent.mkdir(parents=True)

    core._ensure_within_vault(vault, inside)  # noqa: SLF001 - must not raise


def test_derive_document_filename_uses_date_kind_and_slugified_title(
    tmp_path: Path,
) -> None:
    name = core._derive_document_filename(  # noqa: SLF001
        tmp_path, date(2026, 1, 2), DocumentKind.EMAIL, "Recruiter Follow-Up!"
    )

    assert name == "2026-01-02-email-recruiter-follow-up.md"


def test_derive_document_filename_suffixes_on_collision(tmp_path: Path) -> None:
    base = "2026-01-02-note-note"
    (tmp_path / f"{base}.md").write_text("x", encoding="utf-8")

    name = core._derive_document_filename(  # noqa: SLF001
        tmp_path, date(2026, 1, 2), DocumentKind.NOTE, "Note"
    )

    assert name == f"{base}-2.md"


def test_derive_document_filename_second_collision_uses_next_suffix(
    tmp_path: Path,
) -> None:
    base = "2026-01-02-note-note"
    (tmp_path / f"{base}.md").write_text("x", encoding="utf-8")
    (tmp_path / f"{base}-2.md").write_text("x", encoding="utf-8")

    name = core._derive_document_filename(  # noqa: SLF001
        tmp_path, date(2026, 1, 2), DocumentKind.NOTE, "Note"
    )

    assert name == f"{base}-3.md"


def test_derive_document_filename_title_with_path_separators_stays_safe(
    tmp_path: Path,
) -> None:
    name = core._derive_document_filename(  # noqa: SLF001
        tmp_path, date(2026, 1, 2), DocumentKind.EMAIL, "../../etc/passwd"
    )

    assert "/" not in name
    assert ".." not in name
    assert (tmp_path / name).resolve().parent == tmp_path.resolve()


def test_derive_document_filename_blank_title_falls_back_to_untitled(
    tmp_path: Path,
) -> None:
    name = core._derive_document_filename(  # noqa: SLF001
        tmp_path, date(2026, 1, 2), DocumentKind.NOTE, "..."
    )

    assert name == "2026-01-02-note-untitled.md"


def test_derive_document_filename_raises_when_suffix_attempts_exhausted(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(core, "_MAX_FILENAME_SUFFIX_ATTEMPTS", 3)
    base = "2026-01-02-note-note"
    for name in (f"{base}.md", f"{base}-2.md", f"{base}-3.md"):
        (tmp_path / name).write_text("x", encoding="utf-8")

    with pytest.raises(core.DocumentAlreadyExistsError):
        core._derive_document_filename(  # noqa: SLF001
            tmp_path, date(2026, 1, 2), DocumentKind.NOTE, "Note"
        )


# --- Section 7 (stage 7 write half): reindex() ------------------------------


@pytest.mark.embedding
def test_reindex_against_an_already_fresh_index_reports_nothing_changed(
    tmp_path: Path,
) -> None:
    vault = _minimal_built_vault(tmp_path / "vault")
    build_index(read_vault(vault), default_index_path(vault))

    report = core.reindex(vault=vault)

    assert report.added == 0
    assert report.changed == 0
    assert report.deleted == 0


@pytest.mark.embedding
def test_reindex_force_reembeds_every_row(tmp_path: Path) -> None:
    vault = _minimal_built_vault(tmp_path / "vault")
    build_index(read_vault(vault), default_index_path(vault))

    report = core.reindex(force=True, vault=vault)

    assert report.changed + report.added > 0
    assert report.unchanged == 0


@pytest.mark.embedding
def test_reindex_picks_up_a_vault_change_made_outside_core(tmp_path: Path) -> None:
    vault = _minimal_built_vault(tmp_path / "vault")
    build_index(read_vault(vault), default_index_path(vault))

    _write_document(
        vault / "tiny-corp" / "v1",
        Document(
            id="v1-doc2",
            vacancy_id="v1",
            kind=DocumentKind.NOTE,
            title="New note",
            date=date(2026, 1, 9),
        ),
    )

    report = core.reindex(vault=vault)

    assert report.added == 1


@pytest.mark.embedding
def test_reindex_extract_sidecars_true_creates_sidecar_for_eligible_pdf(
    tmp_path: Path,
) -> None:
    vault = _minimal_built_vault(tmp_path / "vault")
    docs_dir = vault / "tiny-corp" / "v1" / "documents"
    pdf_path = docs_dir / "posting.pdf"
    write_valid_pdf(pdf_path)

    core.reindex(extract_sidecars=True, vault=vault)

    sidecar = docs_dir / "posting.pdf.md"
    assert sidecar.is_file()


@pytest.mark.embedding
def test_reindex_default_extract_sidecars_false_creates_no_sidecar(
    tmp_path: Path,
) -> None:
    vault = _minimal_built_vault(tmp_path / "vault")
    docs_dir = vault / "tiny-corp" / "v1" / "documents"
    pdf_path = docs_dir / "posting.pdf"
    write_valid_pdf(pdf_path)

    core.reindex(vault=vault)

    sidecar = docs_dir / "posting.pdf.md"
    assert not sidecar.exists()


@pytest.mark.embedding
def test_reindex_extract_sidecars_true_malformed_pdf_returns_warning_not_crash(
    tmp_path: Path,
) -> None:
    vault = _minimal_built_vault(tmp_path / "vault")
    docs_dir = vault / "tiny-corp" / "v1" / "documents"
    pdf_path = docs_dir / "broken.pdf"
    write_malformed_pdf(pdf_path)

    report = core.reindex(extract_sidecars=True, vault=vault)

    # extract_to_sidecar still writes a sidecar on a failed-but-handled
    # extraction (empty body) - the warning, not a missing sidecar, is
    # what signals the failure.
    sidecar = docs_dir / "broken.pdf.md"
    assert sidecar.is_file()
    _, body = frontmatter.parse(
        sidecar.read_text(encoding="utf-8"), filename=str(sidecar)
    )
    assert body.strip() == ""
    assert any("broken.pdf" in w.message for w in report.warnings)


# --- Section 4 (stage 7 write half): add_document() -------------------------


def test_add_document_creates_a_file_at_the_derived_path(tmp_path: Path) -> None:
    vault = _minimal_built_vault(tmp_path / "vault")

    path = core.add_document(
        "v1",
        DocumentKind.EMAIL,
        "Hello from a recruiter.",
        "Recruiter Email",
        date(2026, 1, 5),
        vault=vault,
    )

    assert path.is_file()
    assert path.parent == vault / "tiny-corp" / "v1" / "documents"
    assert path.name == "2026-01-05-email-recruiter-email.md"
    _, body = frontmatter.parse(path.read_text(encoding="utf-8"))
    assert body == "Hello from a recruiter."


def test_add_document_raises_when_suffix_attempts_exhausted(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    vault = _minimal_built_vault(tmp_path / "vault")
    monkeypatch.setattr(core, "_MAX_FILENAME_SUFFIX_ATTEMPTS", 1)
    docs_dir = vault / "tiny-corp" / "v1" / "documents"
    for name in (
        "2026-01-05-email-recruiter-email.md",
        "2026-01-05-email-recruiter-email-2.md",
    ):
        (docs_dir / name).write_text("x", encoding="utf-8")
    before = sorted(p.name for p in docs_dir.iterdir())

    with pytest.raises(core.DocumentAlreadyExistsError):
        core.add_document(
            "v1",
            DocumentKind.EMAIL,
            "content",
            "Recruiter Email",
            date(2026, 1, 5),
            vault=vault,
        )

    assert sorted(p.name for p in docs_dir.iterdir()) == before


def test_add_document_external_id_dedupe_returns_existing_path_and_writes_nothing(
    tmp_path: Path,
) -> None:
    vault = _minimal_built_vault(tmp_path / "vault")
    first = core.add_document(
        "v1",
        DocumentKind.EMAIL,
        "Thread body.",
        "Thread",
        date(2026, 1, 5),
        external_id="thread-123",
        vault=vault,
    )
    docs_dir = vault / "tiny-corp" / "v1" / "documents"
    before = sorted(p.name for p in docs_dir.iterdir())

    second = core.add_document(
        "v1",
        DocumentKind.EMAIL,
        "Thread body, quoted differently this time.",
        "Thread",
        date(2026, 1, 5),
        external_id="thread-123",
        vault=vault,
    )

    assert second == first
    assert sorted(p.name for p in docs_dir.iterdir()) == before


def test_add_document_different_external_id_creates_a_second_document(
    tmp_path: Path,
) -> None:
    vault = _minimal_built_vault(tmp_path / "vault")
    first = core.add_document(
        "v1",
        DocumentKind.EMAIL,
        "Thread body.",
        "Thread",
        date(2026, 1, 5),
        external_id="thread-123",
        vault=vault,
    )

    second = core.add_document(
        "v1",
        DocumentKind.EMAIL,
        "Thread body.",
        "Thread",
        date(2026, 1, 5),
        external_id="thread-456",
        vault=vault,
    )

    assert second != first
    assert first.is_file()
    assert second.is_file()


@pytest.mark.embedding
def test_add_document_is_searchable_without_a_separate_reindex(tmp_path: Path) -> None:
    vault = _minimal_built_vault(tmp_path / "vault")
    build_index(read_vault(vault), default_index_path(vault))

    core.add_document(
        "v1",
        DocumentKind.EMAIL,
        "A uniquely identifiable phrase about quantum widgets.",
        "Quantum Widgets Email",
        date(2026, 1, 5),
        vault=vault,
    )

    results = core.search("quantum widgets", vault=vault, mode=SearchMode.KEYWORD)

    assert any(h.kind == "email" for h in results.hits)


def test_add_document_nonexistent_vacancy_id_raises_and_creates_no_file(
    tmp_path: Path,
) -> None:
    vault = _minimal_built_vault(tmp_path / "vault")
    docs_dir = vault / "tiny-corp" / "v1" / "documents"
    before = sorted(p.name for p in docs_dir.iterdir())

    with pytest.raises(core.EntityNotFoundError):
        core.add_document(
            "does-not-exist",
            DocumentKind.EMAIL,
            "content",
            "Title",
            date(2026, 1, 5),
            vault=vault,
        )

    assert sorted(p.name for p in docs_dir.iterdir()) == before


# --- Section 5 (stage 7 write half): append_note() --------------------------


def test_append_note_creates_a_file_whose_body_equals_the_given_text(
    tmp_path: Path,
) -> None:
    vault = _minimal_built_vault(tmp_path / "vault")

    path = core.append_note("v1", "Called the recruiter today.", vault=vault)

    assert path.is_file()
    _, body = frontmatter.parse(path.read_text(encoding="utf-8"))
    assert body == "Called the recruiter today."


def test_append_note_second_call_creates_new_file_leaving_first_unchanged(
    tmp_path: Path,
) -> None:
    vault = _minimal_built_vault(tmp_path / "vault")

    first = core.append_note("v1", "First note.", date=date(2026, 2, 1), vault=vault)
    first_bytes_before = first.read_bytes()

    second = core.append_note("v1", "Second note.", date=date(2026, 2, 2), vault=vault)

    assert second != first
    assert first.read_bytes() == first_bytes_before


def test_append_note_two_notes_same_date_produce_two_distinct_files(
    tmp_path: Path,
) -> None:
    vault = _minimal_built_vault(tmp_path / "vault")

    first = core.append_note("v1", "Morning note.", date=date(2026, 2, 1), vault=vault)
    second = core.append_note("v1", "Evening note.", date=date(2026, 2, 1), vault=vault)

    assert first != second
    assert first.is_file()
    assert second.is_file()
    _, first_body = frontmatter.parse(first.read_text(encoding="utf-8"))
    _, second_body = frontmatter.parse(second.read_text(encoding="utf-8"))
    assert first_body == "Morning note."
    assert second_body == "Evening note."


@pytest.mark.embedding
def test_append_note_is_searchable_without_a_separate_reindex(tmp_path: Path) -> None:
    vault = _minimal_built_vault(tmp_path / "vault")
    build_index(read_vault(vault), default_index_path(vault))

    core.append_note(
        "v1", "A uniquely identifiable phrase about zebra migrations.", vault=vault
    )

    results = core.search("zebra migrations", vault=vault, mode=SearchMode.KEYWORD)

    assert any(h.kind == "note" for h in results.hits)


# --- Section 6 (stage 7 write half): set_status() ---------------------------


def _applied_vacancy(vault: Path, vacancy_id: str = "v2", **overrides: object) -> Path:
    fields: dict[str, object] = {
        "status": Status.APPLIED,
        "applied_date": date(2026, 1, 3),
    }
    fields.update(overrides)
    return _write_vacancy(
        vault, "tiny-corp", vacancy_id, _simple_vacancy(vacancy_id, **fields)
    )


def test_set_status_permitted_forward_transition_succeeds(tmp_path: Path) -> None:
    vault = _minimal_built_vault(tmp_path / "vault")
    _applied_vacancy(vault)

    change = core.set_status("v2", "screening", vault=vault)

    assert change.changed is True
    assert change.old_status == Status.APPLIED
    assert change.new_status == Status.SCREENING
    updated = read_vault(vault).vacancies["v2"]
    assert updated.status == Status.SCREENING


def test_set_status_backward_without_force_raises_naming_both_statuses(
    tmp_path: Path,
) -> None:
    vault = _minimal_built_vault(tmp_path / "vault")
    _applied_vacancy(vault, status=Status.INTERVIEW, applied_date=date(2026, 1, 3))

    with pytest.raises(core.InvalidStatusTransitionError) as exc_info:
        core.set_status("v2", "applied", vault=vault)

    message = str(exc_info.value)
    assert "interview" in message
    assert "applied" in message
    assert read_vault(vault).vacancies["v2"].status == Status.INTERVIEW


def test_set_status_backward_with_force_succeeds(tmp_path: Path) -> None:
    vault = _minimal_built_vault(tmp_path / "vault")
    _applied_vacancy(vault, status=Status.INTERVIEW, applied_date=date(2026, 1, 3))

    change = core.set_status("v2", "applied", force=True, vault=vault)

    assert change.changed is True
    assert read_vault(vault).vacancies["v2"].status == Status.APPLIED


def test_set_status_same_status_is_a_no_op(tmp_path: Path) -> None:
    vault = _minimal_built_vault(tmp_path / "vault")
    _applied_vacancy(vault, status=Status.SCREENING, applied_date=date(2026, 1, 3))
    vacancy_path = vault / "tiny-corp" / "v2" / "vacancy.md"
    before = vacancy_path.read_bytes()

    change = core.set_status("v2", "screening", vault=vault)

    assert change.changed is False
    assert change.old_status == change.new_status == Status.SCREENING
    assert vacancy_path.read_bytes() == before


def test_set_status_invalid_status_string_lists_permitted_values(
    tmp_path: Path,
) -> None:
    vault = _minimal_built_vault(tmp_path / "vault")
    _applied_vacancy(vault)

    with pytest.raises(core.InvalidStatusValueError) as exc_info:
        core.set_status("v2", "intervew", vault=vault)

    message = str(exc_info.value)
    for status in Status:
        assert status.value in message


def test_set_status_appends_history_and_preserves_prior_entries(tmp_path: Path) -> None:
    vault = _minimal_built_vault(tmp_path / "vault")
    _applied_vacancy(vault)

    core.set_status("v2", "screening", vault=vault)
    core.set_status("v2", "interview", vault=vault)

    vacancy_path = vault / "tiny-corp" / "v2" / "vacancy.md"
    _, body = frontmatter.parse(vacancy_path.read_text(encoding="utf-8"))
    assert "applied -> screening" in body
    assert "screening -> interview" in body
    assert body.index("applied -> screening") < body.index("screening -> interview")


def test_set_status_leaves_stage_note_byte_identical(tmp_path: Path) -> None:
    vault = _minimal_built_vault(tmp_path / "vault")
    _applied_vacancy(vault, stage_note="Waiting to hear back from the recruiter.")

    core.set_status("v2", "screening", vault=vault)

    updated = read_vault(vault).vacancies["v2"]
    assert updated.stage_note == "Waiting to hear back from the recruiter."


def test_set_status_off_found_without_applied_date_raises(tmp_path: Path) -> None:
    vault = _minimal_built_vault(tmp_path / "vault")
    # v1 (from _minimal_built_vault) is status=found, applied_date=None.

    with pytest.raises(core.MissingAppliedDateError):
        core.set_status("v1", "applied", vault=vault)

    assert read_vault(vault).vacancies["v1"].status == Status.FOUND


def test_set_status_off_found_with_applied_date_succeeds(tmp_path: Path) -> None:
    vault = _minimal_built_vault(tmp_path / "vault")

    change = core.set_status(
        "v1", "applied", applied_date=date(2026, 1, 10), vault=vault
    )

    assert change.changed is True
    updated = read_vault(vault).vacancies["v1"]
    assert updated.status == Status.APPLIED
    assert updated.applied_date == date(2026, 1, 10)


def test_set_status_round_trip_differs_only_in_status_and_history(
    tmp_path: Path,
) -> None:
    vault = _minimal_built_vault(tmp_path / "vault")
    _applied_vacancy(vault, recruiter="Jane Recruiter", tags=["needs_review"])
    vacancy_path = vault / "tiny-corp" / "v2" / "vacancy.md"
    before_lines = vacancy_path.read_text(encoding="utf-8").splitlines()

    core.set_status("v2", "screening", vault=vault)

    after_lines = vacancy_path.read_text(encoding="utf-8").splitlines()
    before_set = set(before_lines)
    after_set = set(after_lines)
    changed_or_added = before_set ^ after_set
    for line in changed_or_added:
        assert line.startswith(("status:", "- ")) or line in ("## Status History", "")


@pytest.mark.embedding
def test_set_status_updates_document_status_without_reembedding_vectors(
    tmp_path: Path,
) -> None:
    vault = _minimal_built_vault(tmp_path / "vault")
    _applied_vacancy(vault)
    _write_document(
        vault / "tiny-corp" / "v2",
        Document(
            id="v2-doc1",
            vacancy_id="v2",
            kind=DocumentKind.EMAIL,
            title="Recruiter Email",
            date=date(2026, 1, 3),
        ),
        body="Some recruiter email body.",
    )
    build_index(read_vault(vault), default_index_path(vault))
    index = get_index_handle(vault)
    before_table = index.connection.open_table("documents")
    before = before_table.search().where("doc_id = 'v2-doc1'").to_arrow().to_pylist()[0]

    core.set_status("v2", "screening", vault=vault)

    # Reopen the table (mirrors index.search.search's own pattern) so this
    # reads the post-write state rather than a pre-write table snapshot.
    after_table = index.connection.open_table("documents")
    after = after_table.search().where("doc_id = 'v2-doc1'").to_arrow().to_pylist()[0]
    assert after["status"] == "screening"
    assert after["vector"] == before["vector"]


def test_set_status_nonexistent_vacancy_id_raises(tmp_path: Path) -> None:
    vault = _minimal_built_vault(tmp_path / "vault")

    with pytest.raises(core.EntityNotFoundError):
        core.set_status("does-not-exist", "applied", vault=vault)


# --- Section 8 (stage 7 write half): create_vacancy() -----------------------


def test_create_vacancy_new_company_creates_directory_and_company_md(
    tmp_path: Path,
) -> None:
    vault = tmp_path / "vault"
    _init_vault(vault)

    path = core.create_vacancy(
        "Acme Corp",
        "Engineer",
        date(2026, 1, 1),
        Status.FOUND,
        source_url="https://jobs.acme.example/1",
        vault=vault,
    )

    assert path.is_file()
    assert (vault / "acme-corp" / "_company.md").is_file()
    assert path.parent.parent == vault / "acme-corp"


def test_create_vacancy_existing_company_leaves_company_md_untouched(
    tmp_path: Path,
) -> None:
    vault = tmp_path / "vault"
    _init_vault(vault)
    core.create_vacancy(
        "Acme Corp",
        "Engineer",
        date(2026, 1, 1),
        Status.FOUND,
        source_url="https://jobs.acme.example/1",
        vault=vault,
    )
    company_md = vault / "acme-corp" / "_company.md"
    before = company_md.read_bytes()

    second_path = core.create_vacancy(
        "Acme Corp",
        "Designer",
        date(2026, 1, 2),
        Status.FOUND,
        source_url="https://jobs.acme.example/2",
        vault=vault,
    )

    assert company_md.read_bytes() == before
    assert second_path.is_file()
    snapshot = read_vault(vault)
    roles = {v.role for v in snapshot.vacancies_for("acme-corp")}
    assert roles == {"Engineer", "Designer"}


def test_create_vacancy_collision_gets_a_distinct_suffixed_id(tmp_path: Path) -> None:
    vault = tmp_path / "vault"
    _init_vault(vault)

    first = core.create_vacancy(
        "Acme Corp",
        UNKNOWN_ROLE,
        date(2026, 1, 1),
        Status.FOUND,
        source_url="https://jobs.acme.example/1",
        vault=vault,
    )
    second = core.create_vacancy(
        "Acme Corp",
        UNKNOWN_ROLE,
        date(2026, 1, 1),
        Status.FOUND,
        source_url="https://jobs.acme.example/2",
        vault=vault,
    )

    assert first != second
    assert first.is_file()
    assert second.is_file()
    snapshot = read_vault(vault)
    assert {v.id for v in snapshot.vacancies_for("acme-corp")} == {
        first.parent.name,
        second.parent.name,
    }


def test_create_vacancy_found_status_with_no_applied_date_succeeds(
    tmp_path: Path,
) -> None:
    vault = tmp_path / "vault"
    _init_vault(vault)

    path = core.create_vacancy(
        "Acme Corp",
        "Engineer",
        date(2026, 1, 1),
        Status.FOUND,
        source_url="https://jobs.acme.example/1",
        vault=vault,
    )

    assert path.is_file()


def test_create_vacancy_non_found_status_without_applied_date_raises(
    tmp_path: Path,
) -> None:
    vault = tmp_path / "vault"
    _init_vault(vault)

    with pytest.raises(core.InvalidVacancyDataError):
        core.create_vacancy(
            "Acme Corp",
            "Engineer",
            date(2026, 1, 1),
            Status.APPLIED,
            source_url="https://jobs.acme.example/1",
            vault=vault,
        )

    snapshot = read_vault(vault)
    assert snapshot.vacancies_for("acme-corp") == []


def test_create_vacancy_invalid_status_string_raises_typed_error(
    tmp_path: Path,
) -> None:
    vault = tmp_path / "vault"
    _init_vault(vault)

    with pytest.raises(core.InvalidVacancyDataError):
        core.create_vacancy(
            "Acme Corp",
            "Engineer",
            date(2026, 1, 1),
            "not-a-real-status",
            source_url="https://jobs.acme.example/1",
            vault=vault,
        )

    snapshot = read_vault(vault)
    assert snapshot.vacancies_for("acme-corp") == []


@pytest.mark.embedding
def test_create_vacancy_is_listed_and_searchable_immediately(tmp_path: Path) -> None:
    vault = tmp_path / "vault"
    _init_vault(vault)
    build_index(read_vault(vault), default_index_path(vault))

    core.create_vacancy(
        "Quokka Systems",
        "Distributed Systems Engineer",
        date(2026, 1, 1),
        Status.FOUND,
        source_url="https://jobs.quokka.example/1",
        vault=vault,
    )

    summaries = core.list_vacancies(vault=vault)
    assert any(s.company == "Quokka Systems" for s in summaries)

    results = core.search(
        "Distributed Systems Engineer", vault=vault, mode=SearchMode.KEYWORD
    )
    assert any(h.company == "Quokka Systems" for h in results.hits)


# --- Section 8b (stage 9): create_vacancy's optional creation fields -------


def test_create_vacancy_stores_optional_fields(tmp_path: Path) -> None:
    vault = tmp_path / "vault"
    _init_vault(vault)

    path = core.create_vacancy(
        "Acme Corp",
        "Engineer",
        date(2026, 1, 1),
        Status.APPLIED,
        source_url="https://jobs.acme.example/1",
        applied_date=date(2026, 1, 2),
        stage_note="Recruiter called, phone screen next week.",
        salary_note="120-140k, quoted verbally",
        recruiter="Jane Recruiter",
        tags=["needs_review", "migrated"],
        vault=vault,
    )

    text = path.read_text(encoding="utf-8")
    metadata, _ = frontmatter.parse(text, filename=str(path))
    assert metadata["stage_note"] == "Recruiter called, phone screen next week."
    assert metadata["salary_note"] == "120-140k, quoted verbally"
    assert metadata["recruiter"] == "Jane Recruiter"
    assert metadata["tags"] == ["needs_review", "migrated"]


def test_create_vacancy_tags_defaults_to_empty_list(tmp_path: Path) -> None:
    vault = tmp_path / "vault"
    _init_vault(vault)

    path = core.create_vacancy(
        "Acme Corp",
        "Engineer",
        date(2026, 1, 1),
        Status.FOUND,
        source_url="https://jobs.acme.example/1",
        vault=vault,
    )

    snapshot = read_vault(vault)
    vacancy_id = path.parent.name
    assert snapshot.vacancies[vacancy_id].tags == []


def test_create_vacancy_optional_str_fields_default_absent(tmp_path: Path) -> None:
    vault = tmp_path / "vault"
    _init_vault(vault)

    path = core.create_vacancy(
        "Acme Corp",
        "Engineer",
        date(2026, 1, 1),
        Status.FOUND,
        source_url="https://jobs.acme.example/1",
        vault=vault,
    )

    text = path.read_text(encoding="utf-8")
    metadata, _ = frontmatter.parse(text, filename=str(path))
    assert "stage_note" not in metadata
    assert "salary_note" not in metadata
    assert "recruiter" not in metadata


# --- Section 8d (optional-vacancy-url): create_vacancy without source_url --


def test_create_vacancy_without_source_url_creates_vacancy_with_none(
    tmp_path: Path,
) -> None:
    vault = tmp_path / "vault"
    _init_vault(vault)

    path = core.create_vacancy(
        "Acme Corp", "Engineer", date(2026, 1, 1), Status.FOUND, vault=vault
    )

    snapshot = read_vault(vault)
    vacancy_id = path.parent.name
    assert snapshot.vacancies[vacancy_id].source_url is None


def test_create_vacancy_with_source_url_still_stores_it(tmp_path: Path) -> None:
    vault = tmp_path / "vault"
    _init_vault(vault)

    path = core.create_vacancy(
        "Acme Corp",
        "Engineer",
        date(2026, 1, 1),
        Status.FOUND,
        source_url="https://jobs.acme.example/1",
        vault=vault,
    )

    snapshot = read_vault(vault)
    vacancy_id = path.parent.name
    assert snapshot.vacancies[vacancy_id].source_url == "https://jobs.acme.example/1"


def test_create_vacancy_invalid_source_url_scheme_still_raises(tmp_path: Path) -> None:
    vault = tmp_path / "vault"
    _init_vault(vault)

    with pytest.raises(core.InvalidVacancyDataError):
        core.create_vacancy(
            "Acme Corp",
            "Engineer",
            date(2026, 1, 1),
            Status.FOUND,
            source_url="ftp://jobs.acme.example/1",
            vault=vault,
        )

    snapshot = read_vault(vault)
    assert snapshot.vacancies_for("acme-corp") == []


# --- Section 8c (stage 9): find_existing() ----------------------------------


def test_find_existing_matches_existing_company(tmp_path: Path) -> None:
    vault = tmp_path / "vault"
    _init_vault(vault)
    core.create_vacancy(
        "Acme Corp",
        "Engineer",
        date(2026, 1, 1),
        Status.FOUND,
        source_url="https://jobs.acme.example/1",
        vault=vault,
    )
    core.create_vacancy(
        "Acme Corp",
        "Designer",
        date(2026, 1, 2),
        Status.FOUND,
        source_url="https://jobs.acme.example/2",
        vault=vault,
    )

    matches = core.find_existing(
        "Acme Corp", "https://jobs.acme.example/does-not-match", vault=vault
    )

    assert {m.role for m in matches} == {"Engineer", "Designer"}


def test_find_existing_empty_for_unknown_company_and_url(tmp_path: Path) -> None:
    vault = tmp_path / "vault"
    _init_vault(vault)
    core.create_vacancy(
        "Acme Corp",
        "Engineer",
        date(2026, 1, 1),
        Status.FOUND,
        source_url="https://jobs.acme.example/1",
        vault=vault,
    )

    matches = core.find_existing(
        "No Such Company", "https://jobs.nowhere.example/1", vault=vault
    )

    assert matches == []


def test_find_existing_never_raises_on_ambiguous_company(tmp_path: Path) -> None:
    vault = tmp_path / "vault"
    _init_vault(vault)
    # Two companies sharing the same display name but distinct slugs -
    # ambiguous at resolve's case-insensitive-name tier (mirrors
    # test_resolve's own widget-us/widget-eu collision fixture).
    # Written directly rather than via create_vacancy, which always
    # slugifies "Widget Inc" to the same slug and so could never
    # produce two distinct companies with an identical display name.
    _write_company(vault, "widget-us", "Widget Inc")
    _write_company(vault, "widget-eu", "Widget Inc")
    _write_vacancy(
        vault,
        "widget-eu",
        "v1",
        _simple_vacancy(
            "v1",
            slug="widget-eu",
            company="Widget Inc",
            role="Designer",
            source_url="https://jobs.widget-eu.example/1",
        ),
    )

    matches = core.find_existing(
        "Widget Inc", "https://jobs.widget-eu.example/1", vault=vault
    )

    # An ambiguous company name never raises; the source_url tier
    # still matches.
    assert any(m.role == "Designer" for m in matches)


def test_find_existing_matches_by_source_url_across_company_spellings(
    tmp_path: Path,
) -> None:
    vault = tmp_path / "vault"
    _init_vault(vault)
    core.create_vacancy(
        "Acme Corp",
        "Engineer",
        date(2026, 1, 1),
        Status.FOUND,
        source_url="https://jobs.acme.example/1",
        vault=vault,
    )

    matches = core.find_existing(
        "Acme Corporation Ltd", "https://jobs.acme.example/1", vault=vault
    )

    assert [m.role for m in matches] == ["Engineer"]


def test_find_existing_does_not_duplicate_a_vacancy_matching_both_tiers(
    tmp_path: Path,
) -> None:
    vault = tmp_path / "vault"
    _init_vault(vault)
    core.create_vacancy(
        "Acme Corp",
        "Engineer",
        date(2026, 1, 1),
        Status.FOUND,
        source_url="https://jobs.acme.example/1",
        vault=vault,
    )

    matches = core.find_existing(
        "Acme Corp", "https://jobs.acme.example/1", vault=vault
    )

    assert len(matches) == 1


# --- Section 8e (optional-vacancy-url): find_existing without source_url --


def test_find_existing_no_source_url_still_matches_by_company(tmp_path: Path) -> None:
    vault = tmp_path / "vault"
    _init_vault(vault)
    core.create_vacancy(
        "Acme Corp", "Engineer", date(2026, 1, 1), Status.FOUND, vault=vault
    )

    matches = core.find_existing("Acme Corp", vault=vault)

    assert {m.role for m in matches} == {"Engineer"}


def test_find_existing_no_source_url_never_false_matches_across_companies(
    tmp_path: Path,
) -> None:
    vault = tmp_path / "vault"
    _init_vault(vault)
    core.create_vacancy(
        "Acme Corp", "Engineer", date(2026, 1, 1), Status.FOUND, vault=vault
    )
    core.create_vacancy(
        "Beta Inc", "Designer", date(2026, 1, 2), Status.FOUND, vault=vault
    )

    matches = core.find_existing("Acme Corp", vault=vault)

    assert {m.role for m in matches} == {"Engineer"}


def test_find_existing_omitting_source_url_never_matches_via_that_tier(
    tmp_path: Path,
) -> None:
    vault = tmp_path / "vault"
    _init_vault(vault)
    core.create_vacancy(
        "Acme Corp", "Engineer", date(2026, 1, 1), Status.FOUND, vault=vault
    )
    core.create_vacancy(
        "Beta Inc", "Designer", date(2026, 1, 2), Status.FOUND, vault=vault
    )

    matches = core.find_existing("No Such Company", vault=vault)

    assert matches == []


def test_find_existing_with_real_source_url_unchanged(tmp_path: Path) -> None:
    vault = tmp_path / "vault"
    _init_vault(vault)
    core.create_vacancy(
        "Acme Corp",
        "Engineer",
        date(2026, 1, 1),
        Status.FOUND,
        source_url="https://jobs.acme.example/1",
        vault=vault,
    )

    matches = core.find_existing(
        "No Such Company", "https://jobs.acme.example/1", vault=vault
    )

    assert {m.role for m in matches} == {"Engineer"}


# --- Section 14: cross-cutting failure-atomicity tests -----------------


def _snapshot_files(vault: Path) -> dict[str, bytes]:
    return {
        str(p.relative_to(vault)): p.read_bytes()
        for p in vault.rglob("*")
        if p.is_file()
    }


def _boom(*_args: object, **_kwargs: object) -> None:
    raise OSError(_SIMULATED_REPLACE_FAILURE)


def test_append_note_interrupted_write_leaves_vault_unchanged(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    vault = _minimal_built_vault(tmp_path / "vault")
    before = _snapshot_files(vault)

    monkeypatch.setattr(core.os, "link", _boom)
    monkeypatch.setattr(core.os, "replace", _boom)

    with pytest.raises(OSError, match=_SIMULATED_REPLACE_FAILURE):
        core.append_note("v1", "text", vault=vault)

    assert _snapshot_files(vault) == before


def test_add_document_interrupted_write_leaves_vault_unchanged(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    vault = _minimal_built_vault(tmp_path / "vault")
    before = _snapshot_files(vault)

    monkeypatch.setattr(core.os, "link", _boom)
    monkeypatch.setattr(core.os, "replace", _boom)

    with pytest.raises(OSError, match=_SIMULATED_REPLACE_FAILURE):
        core.add_document(
            "v1", DocumentKind.EMAIL, "content", "Title", date(2026, 1, 5), vault=vault
        )

    assert _snapshot_files(vault) == before


def test_set_status_interrupted_write_leaves_vault_unchanged(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    vault = _minimal_built_vault(tmp_path / "vault")
    _applied_vacancy(vault)
    before = _snapshot_files(vault)

    monkeypatch.setattr(core.os, "replace", _boom)

    with pytest.raises(OSError, match=_SIMULATED_REPLACE_FAILURE):
        core.set_status("v2", "screening", vault=vault)

    assert _snapshot_files(vault) == before


def test_write_sequence_never_removes_a_preexisting_file(tmp_path: Path) -> None:
    vault = _minimal_built_vault(tmp_path / "vault")
    before = set(_snapshot_files(vault))

    vacancy_path = core.create_vacancy(
        "Acme Corp",
        "Engineer",
        date(2026, 1, 1),
        Status.FOUND,
        source_url="https://jobs.acme.example/1",
        vault=vault,
    )
    vacancy_id = vacancy_path.parent.name
    core.append_note(vacancy_id, "First note.", vault=vault)
    core.set_status(vacancy_id, "applied", applied_date=date(2026, 1, 10), vault=vault)
    core.add_document(
        vacancy_id,
        DocumentKind.EMAIL,
        "Recruiter email body.",
        "Recruiter Email",
        date(2026, 1, 11),
        vault=vault,
    )

    after = _snapshot_files(vault)
    assert before <= set(after)


# --- Section 7 (edit-vacancy-fields): _append_to_section() ------------------

_append_to_section = core._append_to_section  # noqa: SLF001 - the section-aware append this change adds, exercised directly


def test_append_to_section_matches_prior_end_of_body_append() -> None:
    """The status-history block is the body's last section in every file
    this project writes; the section-aware append must not change a byte
    of what the earlier end-of-body append produced for that shape."""
    body = "# Engineer\n\n## Status History\n- 2026-01-01: found -> applied\n"

    appended = _append_to_section(body, core.STATUS_HISTORY_HEADING, ["- new"])

    assert appended == f"{body.rstrip(chr(10))}\n- new\n"


def test_append_to_section_creates_a_missing_section_at_the_end_of_the_body() -> None:
    body = "# Engineer\n\nSome prose.\n"

    appended = _append_to_section(body, core.EDIT_HISTORY_HEADING, ["- entry"])

    assert appended == f"{body}\n{core.EDIT_HISTORY_HEADING}\n- entry\n"


def test_append_to_section_creates_a_missing_section_in_an_empty_body() -> None:
    appended = _append_to_section("", core.EDIT_HISTORY_HEADING, ["- entry"])

    assert appended == f"{core.EDIT_HISTORY_HEADING}\n- entry\n"


def test_append_to_section_inserts_before_a_following_section() -> None:
    body = (
        "# Engineer\n\n"
        "## Status History\n- 2026-01-01: found -> applied\n\n"
        "## Edit History\n- 2026-01-02: role: a -> b\n"
    )

    appended = _append_to_section(
        body, core.STATUS_HISTORY_HEADING, ["- 2026-01-03: applied -> screening"]
    )

    assert appended == (
        "# Engineer\n\n"
        "## Status History\n"
        "- 2026-01-01: found -> applied\n"
        "- 2026-01-03: applied -> screening\n\n"
        "## Edit History\n- 2026-01-02: role: a -> b\n"
    )


def test_append_to_section_with_no_entries_returns_the_body_unchanged() -> None:
    body = "# Engineer\n\n## Edit History\n- 2026-01-02: role: a -> b\n"

    assert _append_to_section(body, core.EDIT_HISTORY_HEADING, []) == body


def test_status_entry_lands_in_its_own_block_when_edit_history_follows(
    tmp_path: Path,
) -> None:
    vault = _minimal_built_vault(tmp_path / "vault")
    _applied_vacancy(vault)
    core.set_status("v2", "screening", vault=vault)
    core.edit_vacancy("v2", recruiter="Anna K.", vault=vault)

    core.set_status("v2", "interview", vault=vault)

    _, body = frontmatter.parse(
        (vault / "tiny-corp" / "v2" / "vacancy.md").read_text(encoding="utf-8")
    )
    status_block, edit_block = _history_blocks(body)
    assert any("screening -> interview" in line for line in status_block)
    assert not any("screening -> interview" in line for line in edit_block)
    assert edit_block == [f"- {_today()}: recruiter: (none) -> Anna K."]


def test_edit_entry_lands_in_its_own_block_when_status_history_precedes(
    tmp_path: Path,
) -> None:
    vault = _minimal_built_vault(tmp_path / "vault")
    _applied_vacancy(vault)
    core.set_status("v2", "screening", vault=vault)

    core.edit_vacancy("v2", recruiter="Anna K.", vault=vault)

    _, body = frontmatter.parse(
        (vault / "tiny-corp" / "v2" / "vacancy.md").read_text(encoding="utf-8")
    )
    status_block, edit_block = _history_blocks(body)
    assert status_block == [f"- {_today()}: applied -> screening"]
    assert edit_block == [f"- {_today()}: recruiter: (none) -> Anna K."]


def _today() -> str:
    return datetime.now().astimezone().date().isoformat()


def _tomorrow() -> date:
    return datetime.now().astimezone().date() + timedelta(days=1)


def _history_blocks(body: str) -> tuple[list[str], list[str]]:
    """The entry lines of the status-history and edit-history blocks."""
    blocks: dict[str, list[str]] = {
        core.STATUS_HISTORY_HEADING: [],
        core.EDIT_HISTORY_HEADING: [],
    }
    current: list[str] | None = None
    for line in body.split("\n"):
        if line.strip() in blocks:
            current = blocks[line.strip()]
        elif line.startswith("## "):
            current = None
        elif current is not None and line.strip():
            current.append(line)
    return blocks[core.STATUS_HISTORY_HEADING], blocks[core.EDIT_HISTORY_HEADING]


# --- Section 7 (edit-vacancy-fields): edit-history entries ------------------


def _edit_entries(vault: Path, vacancy_id: str = "v2") -> list[str]:
    _, body = frontmatter.parse(
        (vault / "tiny-corp" / vacancy_id / "vacancy.md").read_text(encoding="utf-8")
    )
    return _history_blocks(body)[1]


def test_edit_appends_one_entry_per_changed_field(tmp_path: Path) -> None:
    vault = _minimal_built_vault(tmp_path / "vault")
    _applied_vacancy(vault, salary_note="120k")

    core.edit_vacancy(
        "v2",
        source_url="https://new.example/careers/1",
        recruiter="Anna K.",
        salary_note="120k",
        vault=vault,
    )

    entries = _edit_entries(vault)
    assert [entry.split(": ")[1] for entry in entries] == ["source_url", "recruiter"]


def test_edit_entry_names_the_date_and_both_values(tmp_path: Path) -> None:
    vault = _minimal_built_vault(tmp_path / "vault")
    _applied_vacancy(vault)

    core.edit_vacancy("v2", source_url="https://new.example/careers/1", vault=vault)

    expected = (
        f"- {_today()}: source_url: "
        "https://jobs.acme.example/v2 -> https://new.example/careers/1"
    )
    assert _edit_entries(vault) == [expected]


def test_edit_entry_renders_an_absent_old_value_as_none(tmp_path: Path) -> None:
    vault = _minimal_built_vault(tmp_path / "vault")
    _applied_vacancy(vault)

    core.edit_vacancy("v2", recruiter="Anna K.", vault=vault)

    assert _edit_entries(vault) == [f"- {_today()}: recruiter: (none) -> Anna K."]


def test_edit_entry_renders_a_cleared_value_as_none(tmp_path: Path) -> None:
    vault = _minimal_built_vault(tmp_path / "vault")
    _applied_vacancy(vault, recruiter="Anna K.")

    core.edit_vacancy("v2", recruiter=None, vault=vault)

    assert _edit_entries(vault) == [f"- {_today()}: recruiter: Anna K. -> (none)"]


def test_edit_entry_for_a_multi_line_value_is_one_line(tmp_path: Path) -> None:
    vault = _minimal_built_vault(tmp_path / "vault")
    _applied_vacancy(vault)

    core.edit_vacancy("v2", stage_note="first line\nsecond line\nthird", vault=vault)

    entries = _edit_entries(vault)
    assert len(entries) == 1
    assert (
        entries[0] == f"- {_today()}: stage_note: (none) -> first line [+2 more lines]"
    )


def test_a_value_shaped_like_a_history_entry_does_not_forge_one(
    tmp_path: Path,
) -> None:
    vault = _minimal_built_vault(tmp_path / "vault")
    _applied_vacancy(vault)

    core.edit_vacancy(
        "v2", stage_note="real note\n- 2020-01-01: role: forged -> forged", vault=vault
    )

    entries = _edit_entries(vault)
    assert len(entries) == 1
    assert "forged" not in entries[0]


def test_edit_preserves_prior_edit_history_entries(tmp_path: Path) -> None:
    vault = _minimal_built_vault(tmp_path / "vault")
    _applied_vacancy(vault)

    core.edit_vacancy("v2", recruiter="Anna K.", vault=vault)
    core.edit_vacancy("v2", salary_note="120k", vault=vault)

    entries = _edit_entries(vault)
    assert [entry.split(": ")[1] for entry in entries] == ["recruiter", "salary_note"]


def test_first_edit_creates_the_block_preserving_preceding_body(
    tmp_path: Path,
) -> None:
    vault = _minimal_built_vault(tmp_path / "vault")
    _applied_vacancy(vault)
    vacancy_path = vault / "tiny-corp" / "v2" / "vacancy.md"
    _, body_before = frontmatter.parse(vacancy_path.read_text(encoding="utf-8"))
    assert core.EDIT_HISTORY_HEADING not in body_before

    core.edit_vacancy("v2", recruiter="Anna K.", vault=vault)

    _, body_after = frontmatter.parse(vacancy_path.read_text(encoding="utf-8"))
    assert body_after.startswith(body_before)
    assert core.EDIT_HISTORY_HEADING in body_after


def test_a_no_op_edit_creates_no_edit_history_block(tmp_path: Path) -> None:
    vault = _minimal_built_vault(tmp_path / "vault")
    _applied_vacancy(vault, recruiter="Anna K.")
    vacancy_path = vault / "tiny-corp" / "v2" / "vacancy.md"
    before = vacancy_path.read_bytes()

    core.edit_vacancy("v2", recruiter="Anna K.", vault=vault)

    assert vacancy_path.read_bytes() == before
    assert core.EDIT_HISTORY_HEADING not in vacancy_path.read_text(encoding="utf-8")


# --- Section 7 (edit-vacancy-fields): edit_vacancy() ------------------------


def test_edit_vacancy_sets_each_editable_field(tmp_path: Path) -> None:
    vault = _minimal_built_vault(tmp_path / "vault")
    _applied_vacancy(vault)
    edits: dict[str, object] = {
        "source_url": "https://new.example/careers/1",
        "role": "Staff Engineer",
        "stage_note": "Waiting on the recruiter.",
        "salary_note": "120-140k",
        "recruiter": "Anna K.",
        "external_id": "ext-42",
        "tags": ["remote", "python"],
        "found_date": date(2026, 1, 2),
        "applied_date": date(2026, 1, 4),
    }

    for field, value in edits.items():
        result = core.edit_vacancy("v2", vault=vault, **{field: value})
        assert result.changed is True, field
        assert result.changed_fields == (field,)

    updated = read_vault(vault).vacancies["v2"]
    for field, value in edits.items():
        assert getattr(updated, field) == value


def test_edit_vacancy_rejects_uneditable_fields_as_keyword_arguments(
    tmp_path: Path,
) -> None:
    vault = _minimal_built_vault(tmp_path / "vault")
    _applied_vacancy(vault)
    vacancy_path = vault / "tiny-corp" / "v2" / "vacancy.md"
    before = vacancy_path.read_bytes()

    for field, value in (
        ("status", Status.OFFER),
        ("company", "Other Corp"),
        ("company_slug", "other-corp"),
        ("id", "v99"),
    ):
        with pytest.raises(TypeError):
            core.edit_vacancy("v2", vault=vault, **{field: value})

    assert vacancy_path.read_bytes() == before


def test_edit_vacancy_leaves_omitted_fields_untouched(tmp_path: Path) -> None:
    vault = _minimal_built_vault(tmp_path / "vault")
    _applied_vacancy(vault, recruiter="Anna K.", salary_note="120k")

    core.edit_vacancy("v2", source_url="https://new.example/careers/1", vault=vault)

    updated = read_vault(vault).vacancies["v2"]
    assert updated.recruiter == "Anna K."
    assert updated.salary_note == "120k"
    assert updated.source_url == "https://new.example/careers/1"


def test_edit_vacancy_clears_a_nullable_field_given_as_none(tmp_path: Path) -> None:
    vault = _minimal_built_vault(tmp_path / "vault")
    _applied_vacancy(vault, recruiter="Anna K.")

    core.edit_vacancy("v2", recruiter=None, vault=vault)

    metadata, _ = frontmatter.parse(
        (vault / "tiny-corp" / "v2" / "vacancy.md").read_text(encoding="utf-8")
    )
    assert "recruiter" not in metadata
    assert read_vault(vault).vacancies["v2"].recruiter is None


def test_edit_vacancy_unset_is_distinguishable_from_none(tmp_path: Path) -> None:
    vault = _minimal_built_vault(tmp_path / "vault")
    _applied_vacancy(vault, recruiter="Anna K.")

    omitted = core.edit_vacancy("v2", vault=vault)
    assert omitted.changed is False
    assert read_vault(vault).vacancies["v2"].recruiter == "Anna K."

    cleared = core.edit_vacancy("v2", recruiter=None, vault=vault)
    assert cleared.changed is True
    assert read_vault(vault).vacancies["v2"].recruiter is None


def test_edit_vacancy_applies_several_fields_in_one_call(tmp_path: Path) -> None:
    vault = _minimal_built_vault(tmp_path / "vault")
    _applied_vacancy(vault)

    result = core.edit_vacancy(
        "v2",
        source_url="https://new.example/careers/1",
        recruiter="Anna K.",
        tags=["remote"],
        vault=vault,
    )

    assert set(result.changed_fields) == {"source_url", "recruiter", "tags"}
    updated = read_vault(vault).vacancies["v2"]
    assert updated.source_url == "https://new.example/careers/1"
    assert updated.recruiter == "Anna K."
    assert updated.tags == ["remote"]
    assert [entry.split(": ")[1] for entry in _edit_entries(vault)] == [
        "source_url",
        "recruiter",
        "tags",
    ]


def test_edit_vacancy_writes_nothing_when_one_field_is_invalid(tmp_path: Path) -> None:
    vault = _minimal_built_vault(tmp_path / "vault")
    _applied_vacancy(vault)
    vacancy_path = vault / "tiny-corp" / "v2" / "vacancy.md"
    before = vacancy_path.read_bytes()

    with pytest.raises(core.InvalidVacancyDataError):
        core.edit_vacancy(
            "v2", recruiter="Anna K.", source_url="ftp://example.com/x", vault=vault
        )

    assert vacancy_path.read_bytes() == before


@pytest.mark.parametrize(
    ("edit", "expected_in_message"),
    [
        ({"source_url": "ftp://example.com/x"}, "source_url"),
        ({"role": "   "}, "role"),
        ({"applied_date": None}, "applied_date"),
        ({"found_date": date(2026, 1, 4)}, "found_date"),
        ({"found_date": _tomorrow()}, "found_date"),
    ],
)
def test_edit_vacancy_rejects_invalid_data(
    tmp_path: Path, edit: dict[str, object], expected_in_message: str
) -> None:
    vault = _minimal_built_vault(tmp_path / "vault")
    _applied_vacancy(vault)
    vacancy_path = vault / "tiny-corp" / "v2" / "vacancy.md"
    before = vacancy_path.read_bytes()

    with pytest.raises(core.InvalidVacancyDataError) as exc_info:
        core.edit_vacancy("v2", vault=vault, **edit)

    assert expected_in_message in str(exc_info.value)
    assert vacancy_path.read_bytes() == before


def test_edit_vacancy_result_names_only_the_fields_that_changed(
    tmp_path: Path,
) -> None:
    vault = _minimal_built_vault(tmp_path / "vault")
    _applied_vacancy(vault, recruiter="Anna K.")

    result = core.edit_vacancy(
        "v2",
        recruiter="Anna K.",
        source_url="https://new.example/careers/1",
        vault=vault,
    )

    assert result.changed is True
    assert result.changed_fields == ("source_url",)
    (change,) = result.changes
    assert change.old == "https://jobs.acme.example/v2"
    assert change.new == "https://new.example/careers/1"


def test_edit_vacancy_with_no_fields_is_a_no_op(tmp_path: Path) -> None:
    vault = _minimal_built_vault(tmp_path / "vault")
    _applied_vacancy(vault)
    vacancy_path = vault / "tiny-corp" / "v2" / "vacancy.md"
    before = vacancy_path.read_bytes()

    result = core.edit_vacancy("v2", vault=vault)

    assert result.changed is False
    assert result.changes == ()
    assert vacancy_path.read_bytes() == before


def test_edit_vacancy_reapplying_the_same_values_is_a_no_op(tmp_path: Path) -> None:
    vault = _minimal_built_vault(tmp_path / "vault")
    _applied_vacancy(vault)
    vacancy_path = vault / "tiny-corp" / "v2" / "vacancy.md"

    core.edit_vacancy("v2", recruiter="Anna K.", vault=vault)
    after_first = vacancy_path.read_bytes()
    result = core.edit_vacancy("v2", recruiter="Anna K.", vault=vault)

    assert result.changed is False
    assert vacancy_path.read_bytes() == after_first


def test_edit_vacancy_empty_tags_equals_an_absent_tags_field(tmp_path: Path) -> None:
    vault = _minimal_built_vault(tmp_path / "vault")
    _applied_vacancy(vault)
    vacancy_path = vault / "tiny-corp" / "v2" / "vacancy.md"
    before = vacancy_path.read_bytes()

    result = core.edit_vacancy("v2", tags=[], vault=vault)

    assert result.changed is False
    assert vacancy_path.read_bytes() == before


def test_edit_vacancy_no_op_does_not_reindex(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    vault = _minimal_built_vault(tmp_path / "vault")
    _applied_vacancy(vault)
    calls: list[object] = []
    monkeypatch.setattr(core, "reindex", lambda **kwargs: calls.append(kwargs))

    core.edit_vacancy("v2", vault=vault)
    core.edit_vacancy("v2", recruiter=None, vault=vault)

    assert calls == []


def test_edit_vacancy_unknown_id_raises_without_writing(tmp_path: Path) -> None:
    vault = _minimal_built_vault(tmp_path / "vault")
    _applied_vacancy(vault)
    before = _snapshot_files(vault)

    with pytest.raises(core.EntityNotFoundError):
        core.edit_vacancy("no-such-vacancy", recruiter="Anna K.", vault=vault)

    assert _snapshot_files(vault) == before


def test_edit_vacancy_preserves_every_untouched_line(tmp_path: Path) -> None:
    vault = _minimal_built_vault(tmp_path / "vault")
    vacancy_dir = _applied_vacancy(vault, recruiter="Anna K.")
    vacancy_path = vacancy_dir / "vacancy.md"
    text = vacancy_path.read_text(encoding="utf-8")
    metadata, _body = frontmatter.parse(text)
    vacancy_path.write_text(
        frontmatter.serialize(metadata, "# Engineer\n\nHand-written prose.\n"),
        encoding="utf-8",
    )
    before = vacancy_path.read_text(encoding="utf-8").split("\n")

    core.edit_vacancy("v2", recruiter="Bob", vault=vault)

    after = vacancy_path.read_text(encoding="utf-8").split("\n")
    changed = [line for line in after if line not in before]
    assert all(
        line.startswith(("recruiter:", "- ")) or line == core.EDIT_HISTORY_HEADING
        for line in changed
    ), changed
    assert "Hand-written prose." in after


def test_edit_vacancy_does_not_rewrite_the_role_heading(tmp_path: Path) -> None:
    vault = _minimal_built_vault(tmp_path / "vault")
    _applied_vacancy(vault)

    core.edit_vacancy("v2", role="Staff Engineer", vault=vault)

    _, body = frontmatter.parse(
        (vault / "tiny-corp" / "v2" / "vacancy.md").read_text(encoding="utf-8")
    )
    assert body.startswith("# Engineer\n")
    assert read_vault(vault).vacancies["v2"].role == "Staff Engineer"


def test_edit_vacancy_leaves_id_directory_and_status_alone(tmp_path: Path) -> None:
    vault = _minimal_built_vault(tmp_path / "vault")
    _applied_vacancy(vault, status=Status.SCREENING)
    vacancy_path = vault / "tiny-corp" / "v2" / "vacancy.md"

    core.edit_vacancy(
        "v2", found_date=date(2026, 1, 2), role="Staff Engineer", vault=vault
    )

    assert vacancy_path.exists()
    updated = read_vault(vault).vacancies["v2"]
    assert updated.id == "v2"
    assert updated.status == Status.SCREENING
    assert updated.found_date == date(2026, 1, 2)


def test_edited_role_is_searchable_without_a_separate_reindex(tmp_path: Path) -> None:
    vault = _minimal_built_vault(tmp_path / "vault")
    _applied_vacancy(vault, role=UNKNOWN_ROLE)
    build_index(read_vault(vault), default_index_path(vault))

    core.edit_vacancy("v2", role="Zebra Migration Specialist", vault=vault)

    results = core.search("Zebra Migration", vault=vault, mode=SearchMode.KEYWORD)
    assert any(hit.vacancy_id == "v2" for hit in results.hits)


def test_edited_field_is_visible_to_get_vacancy_immediately(tmp_path: Path) -> None:
    vault = _minimal_built_vault(tmp_path / "vault")
    _applied_vacancy(vault)
    build_index(read_vault(vault), default_index_path(vault))

    core.edit_vacancy("v2", source_url="https://new.example/careers/1", vault=vault)

    assert core.get_vacancy("v2", vault=vault).source_url == (
        "https://new.example/careers/1"
    )


# --- Section 7 (edit-vacancy-fields): resolve_field_edits() -----------------


def test_resolve_field_edits_drops_ungiven_values_and_maps_clears() -> None:
    resolved = core.resolve_field_edits(
        {"recruiter": "Anna K.", "salary_note": None}, ["source-url"]
    )

    assert resolved == {"recruiter": "Anna K.", "source_url": None}


def test_resolve_field_edits_rejects_an_uneditable_field_name() -> None:
    for field in ("status", "company", "id", "not_a_field"):
        with pytest.raises(core.UneditableFieldError) as exc_info:
            core.resolve_field_edits({}, [field])
        message = str(exc_info.value)
        assert field in message
        for editable in core.EDITABLE_FIELDS:
            assert editable in message


def test_resolve_field_edits_rejects_clearing_a_non_nullable_field() -> None:
    for field in ("role", "found_date", "tags"):
        with pytest.raises(core.NotNullableFieldError) as exc_info:
            core.resolve_field_edits({}, [field])
        assert field in str(exc_info.value)


def test_resolve_field_edits_rejects_setting_and_clearing_one_field() -> None:
    with pytest.raises(core.ConflictingEditError) as exc_info:
        core.resolve_field_edits({"recruiter": "Anna K."}, ["recruiter"])

    assert "recruiter" in str(exc_info.value)


# --- Section 8 (resolve-write-target-vacancy): resolve_vacancy() ------------


def _one_vacancy_company(vault: Path) -> Path:
    _init_vault(vault)
    _write_company(vault, "tiny-corp", "Tiny Corp")
    _write_vacancy(vault, "tiny-corp", "v1", _simple_vacancy("v1", slug="tiny-corp"))
    return vault


def test_resolve_vacancy_exact_id_returns_that_id(tmp_path: Path) -> None:
    vault = _one_vacancy_company(tmp_path / "vault")

    assert core.resolve_vacancy("v1", vault=vault) == "v1"


def test_resolve_vacancy_exact_company_slug_returns_its_only_vacancy(
    tmp_path: Path,
) -> None:
    vault = _one_vacancy_company(tmp_path / "vault")

    assert core.resolve_vacancy("tiny-corp", vault=vault) == "v1"


def test_resolve_vacancy_company_display_name_returns_its_only_vacancy(
    tmp_path: Path,
) -> None:
    vault = _one_vacancy_company(tmp_path / "vault")

    assert core.resolve_vacancy("TINY CORP", vault=vault) == "v1"


def test_resolve_vacancy_fuzzy_company_name_returns_its_only_vacancy(
    tmp_path: Path,
) -> None:
    vault = _one_vacancy_company(tmp_path / "vault")

    assert core.resolve_vacancy("Tiny", vault=vault) == "v1"


def test_resolve_vacancy_exact_id_short_circuits_the_company_tiers(
    tmp_path: Path,
) -> None:
    vault = tmp_path / "vault"
    _init_vault(vault)
    _write_company(vault, "wondercorp", "Wonder Co")
    _write_company(vault, "other-corp", "Other Corp")
    _write_vacancy(
        vault, "other-corp", "v1", _simple_vacancy("Wonder Co", slug="other-corp")
    )
    _write_vacancy(vault, "wondercorp", "v2", _simple_vacancy("v2", slug="wondercorp"))

    assert core.resolve_vacancy("Wonder Co", vault=vault) == "Wonder Co"


def test_resolve_vacancy_company_with_several_vacancies_raises_naming_both(
    tmp_path: Path,
) -> None:
    vault = tmp_path / "vault"
    _init_vault(vault)
    _write_company(vault, "tiny-corp", "Tiny Corp")
    _write_vacancy(vault, "tiny-corp", "v1", _simple_vacancy("v1", slug="tiny-corp"))
    _write_vacancy(vault, "tiny-corp", "v2", _simple_vacancy("v2", slug="tiny-corp"))

    with pytest.raises(core.AmbiguousVacancyError) as exc_info:
        core.resolve_vacancy("Tiny Corp", vault=vault)

    assert set(exc_info.value.vacancy_ids) == {"v1", "v2"}
    assert exc_info.value.company_slug == "tiny-corp"
    message = str(exc_info.value)
    assert "v1" in message
    assert "v2" in message


def test_resolve_vacancy_company_with_no_vacancies_raises(tmp_path: Path) -> None:
    vault = tmp_path / "vault"
    _init_vault(vault)
    _write_company(vault, "tiny-corp", "Tiny Corp")

    with pytest.raises(core.EntityNotFoundError):
        core.resolve_vacancy("Tiny Corp", vault=vault)


def test_resolve_vacancy_ambiguous_company_query_raises_before_narrowing(
    tmp_path: Path,
) -> None:
    vault = tmp_path / "vault"
    _init_vault(vault)
    _write_company(vault, "widget-us", "Widget Inc")
    _write_company(vault, "widget-eu", "Widget Inc")
    _write_vacancy(vault, "widget-us", "v1", _simple_vacancy("v1", slug="widget-us"))

    with pytest.raises(core.AmbiguousEntityError) as exc_info:
        core.resolve_vacancy("widget inc", vault=vault)

    assert {c.slug for c in exc_info.value.candidates} == {"widget-us", "widget-eu"}


def test_resolve_vacancy_no_match_raises(tmp_path: Path) -> None:
    vault = _one_vacancy_company(tmp_path / "vault")

    with pytest.raises(core.EntityNotFoundError):
        core.resolve_vacancy("zzz-nonexistent-zzz", vault=vault)


def test_resolve_still_returns_a_company_for_a_one_vacancy_company(
    tmp_path: Path,
) -> None:
    vault = _one_vacancy_company(tmp_path / "vault")

    resolution = core.resolve("Tiny Corp", vault=vault)

    assert resolution.company_slug == "tiny-corp"
    assert resolution.vacancy_id is None


def test_resolve_vacancy_modifies_no_file(tmp_path: Path) -> None:
    vault = _one_vacancy_company(tmp_path / "vault")
    before = _snapshot_files(vault)

    core.resolve_vacancy("Tiny Corp", vault=vault)
    with pytest.raises(core.EntityNotFoundError):
        core.resolve_vacancy("zzz-nonexistent-zzz", vault=vault)

    assert _snapshot_files(vault) == before


# --- add-resume-tracking: resume field, filter, and stats ------------------


def _vacancy_text(vault: Path, vacancy_id: str, slug: str = "tiny-corp") -> str:
    return (vault / slug / vacancy_id / "vacancy.md").read_text(encoding="utf-8")


def test_create_vacancy_stores_resume_trimmed(tmp_path: Path) -> None:
    vault = tmp_path / "vault"
    _init_vault(vault)

    path = core.create_vacancy(
        "Acme Corp",
        "Engineer",
        date(2026, 1, 1),
        Status.APPLIED,
        applied_date=date(2026, 1, 2),
        resume="  backend-v2 ",
        vault=vault,
    )

    metadata, _ = frontmatter.parse(path.read_text(encoding="utf-8"), filename="x")
    assert metadata["resume"] == "backend-v2"


def test_create_vacancy_without_resume_has_no_resume_key(tmp_path: Path) -> None:
    vault = tmp_path / "vault"
    _init_vault(vault)

    path = core.create_vacancy(
        "Acme Corp", "Engineer", date(2026, 1, 1), Status.FOUND, vault=vault
    )

    metadata, _ = frontmatter.parse(path.read_text(encoding="utf-8"), filename="x")
    assert "resume" not in metadata


def test_create_vacancy_rejects_a_blank_resume_and_writes_nothing(
    tmp_path: Path,
) -> None:
    vault = tmp_path / "vault"
    _init_vault(vault)
    before = _snapshot_files(vault)

    with pytest.raises(core.InvalidVacancyDataError):
        core.create_vacancy(
            "Acme Corp",
            "Engineer",
            date(2026, 1, 1),
            Status.FOUND,
            resume="   ",
            vault=vault,
        )

    assert _snapshot_files(vault) == before


def test_edit_vacancy_sets_then_clears_resume_with_history(tmp_path: Path) -> None:
    vault = _minimal_built_vault(tmp_path / "vault")
    _applied_vacancy(vault)

    core.edit_vacancy("v2", resume="backend-v2", vault=vault)
    assert read_vault(vault).vacancies["v2"].resume == "backend-v2"
    assert "resume: (none) -> backend-v2" in _vacancy_text(vault, "v2")

    core.edit_vacancy("v2", resume=None, vault=vault)
    assert read_vault(vault).vacancies["v2"].resume is None
    assert "resume: backend-v2 -> (none)" in _vacancy_text(vault, "v2")


def test_edit_vacancy_rejects_a_whitespace_resume_and_leaves_vault(
    tmp_path: Path,
) -> None:
    vault = _minimal_built_vault(tmp_path / "vault")
    _applied_vacancy(vault)
    before = _vacancy_text(vault, "v2")

    with pytest.raises(core.InvalidVacancyDataError):
        core.edit_vacancy("v2", resume="   ", vault=vault)

    assert _vacancy_text(vault, "v2") == before


def test_edit_vacancy_restating_the_same_resume_is_a_no_op(tmp_path: Path) -> None:
    vault = _minimal_built_vault(tmp_path / "vault")
    _applied_vacancy(vault, resume="backend-v2")
    before = _vacancy_text(vault, "v2")

    result = core.edit_vacancy("v2", resume=" backend-v2 ", vault=vault)

    assert result.changed is False
    assert _vacancy_text(vault, "v2") == before


def test_resolve_field_edits_accepts_resume_and_clear_resume() -> None:
    assert core.resolve_field_edits({"resume": "a"}) == {"resume": "a"}
    assert core.resolve_field_edits({}, clear=["resume"]) == {"resume": None}


def test_set_status_with_resume_stores_it_and_records_edit_history(
    tmp_path: Path,
) -> None:
    vault = _minimal_built_vault(tmp_path / "vault")
    _write_vacancy(vault, "tiny-corp", "v3", _simple_vacancy("v3"))

    core.set_status(
        "v3",
        "applied",
        applied_date=date(2026, 1, 5),
        resume="backend-v2",
        vault=vault,
    )

    assert read_vault(vault).vacancies["v3"].resume == "backend-v2"
    text = _vacancy_text(vault, "v3")
    assert "## Edit History" in text
    assert "resume: (none) -> backend-v2" in text


def test_set_status_without_resume_leaves_stored_resume_and_history(
    tmp_path: Path,
) -> None:
    vault = _minimal_built_vault(tmp_path / "vault")
    _applied_vacancy(vault, resume="backend-v2")

    core.set_status("v2", "screening", vault=vault)

    assert read_vault(vault).vacancies["v2"].resume == "backend-v2"
    assert "## Edit History" not in _vacancy_text(vault, "v2")


def test_set_status_with_unchanged_resume_adds_no_edit_history(tmp_path: Path) -> None:
    vault = _minimal_built_vault(tmp_path / "vault")
    _applied_vacancy(vault, resume="backend-v2")

    core.set_status("v2", "screening", resume="backend-v2", vault=vault)

    assert "## Edit History" not in _vacancy_text(vault, "v2")


def test_set_status_same_status_with_resume_changes_nothing(tmp_path: Path) -> None:
    vault = _minimal_built_vault(tmp_path / "vault")
    _applied_vacancy(vault)
    before = _vacancy_text(vault, "v2")

    change = core.set_status("v2", "applied", resume="backend-v2", vault=vault)

    assert change.changed is False
    assert _vacancy_text(vault, "v2") == before


def test_set_status_invalid_resume_writes_nothing(tmp_path: Path) -> None:
    vault = _minimal_built_vault(tmp_path / "vault")
    _applied_vacancy(vault)
    before = _vacancy_text(vault, "v2")

    with pytest.raises(core.InvalidVacancyDataError):
        core.set_status("v2", "screening", resume="a\nb", vault=vault)

    assert _vacancy_text(vault, "v2") == before


def test_set_status_round_trip_with_resume_differs_only_in_expected_lines(
    tmp_path: Path,
) -> None:
    vault = _minimal_built_vault(tmp_path / "vault")
    _applied_vacancy(vault, recruiter="Jane Recruiter", tags=["needs_review"])
    before_lines = set(_vacancy_text(vault, "v2").splitlines())

    core.set_status("v2", "screening", resume="backend-v2", vault=vault)

    after_lines = set(_vacancy_text(vault, "v2").splitlines())
    for line in before_lines ^ after_lines:
        assert line.startswith(("status:", "resume:", "- ")) or line in (
            "## Status History",
            "## Edit History",
            "",
        )


def test_summaries_and_detail_report_resume(tmp_path: Path) -> None:
    vault = _minimal_built_vault(tmp_path / "vault")
    _applied_vacancy(vault, "v2", resume="backend-v2")

    summaries = {s.id: s for s in core.list_vacancies(vault=vault)}

    assert summaries["v2"].resume == "backend-v2"
    assert summaries["v1"].resume is None
    assert core.get_vacancy("v2", vault=vault).resume == "backend-v2"
    assert core.get_vacancy("v1", vault=vault).resume is None


def test_list_vacancies_resume_filter_matches_case_and_whitespace_insensitively(
    tmp_path: Path,
) -> None:
    vault = _minimal_built_vault(tmp_path / "vault")
    _applied_vacancy(vault, "v2", resume="Backend-V2")
    _applied_vacancy(vault, "v3", resume="backend-v1")
    _applied_vacancy(vault, "v4", status=Status.INTERVIEW, resume="backend-v2")

    matched = core.list_vacancies(resume=" backend-v2 ", vault=vault)
    combined = core.list_vacancies(
        resume="backend-v2", status=[Status.INTERVIEW], vault=vault
    )

    assert {s.id for s in matched} == {"v2", "v4"}
    assert [s.id for s in combined] == ["v4"]


def _stats_vault(tmp_path: Path) -> Path:
    vault = _minimal_built_vault(tmp_path / "vault")  # v1: found, no resume
    _applied_vacancy(vault, "a1", resume="backend-v2")
    _applied_vacancy(vault, "a2", status=Status.INTERVIEW, resume="Backend-V2")
    _applied_vacancy(vault, "a3", status=Status.REJECTED, resume="backend-v2")
    _applied_vacancy(vault, "b1", resume="backend-v1")
    _applied_vacancy(vault, "n1")
    _write_vacancy(
        vault,
        "tiny-corp",
        "f1",
        _simple_vacancy("f1", resume="backend-v2"),
    )
    return vault


def test_resume_stats_counts_applications_per_resume_and_status(
    tmp_path: Path,
) -> None:
    vault = _stats_vault(tmp_path)

    rows = {r.resume: r for r in core.resume_stats(vault=vault)}

    v2 = rows["backend-v2"]
    assert v2.applications == 3  # noqa: PLR2004
    assert v2.by_status == {
        Status.APPLIED: 1,
        Status.INTERVIEW: 1,
        Status.REJECTED: 1,
    }
    assert v2.advanced == 1
    assert v2.advance_rate == pytest.approx(1 / 3)
    assert rows["backend-v1"].applications == 1
    assert rows["backend-v1"].advanced == 0


def test_resume_stats_has_a_no_resume_row_and_totals_add_up(tmp_path: Path) -> None:
    vault = _stats_vault(tmp_path)

    rows = core.resume_stats(vault=vault)

    assert rows[-1].resume is None
    assert rows[-1].applications == 1
    applied_count = 5  # a1-a3, b1, n1; the found vacancies are excluded
    assert sum(r.applications for r in rows) == applied_count


def test_resume_stats_omits_the_no_resume_row_when_every_application_has_one(
    tmp_path: Path,
) -> None:
    vault = _minimal_built_vault(tmp_path / "vault")
    _applied_vacancy(vault, "a1", resume="a")

    assert [r.resume for r in core.resume_stats(vault=vault)] == ["a"]


def test_resume_stats_orders_by_count_then_label_with_no_resume_last(
    tmp_path: Path,
) -> None:
    vault = _minimal_built_vault(tmp_path / "vault")
    _applied_vacancy(vault, "a1", resume="a")
    for index in range(3):
        _applied_vacancy(vault, f"b{index}", resume="b")
    _applied_vacancy(vault, "n1")
    _applied_vacancy(vault, "c1", resume="c")

    assert [r.resume for r in core.resume_stats(vault=vault)] == ["b", "a", "c", None]


def test_resume_stats_since_filters_on_applied_date(tmp_path: Path) -> None:
    vault = _minimal_built_vault(tmp_path / "vault")
    _applied_vacancy(vault, "a1", resume="a", applied_date=date(2026, 1, 10))
    _applied_vacancy(vault, "a2", resume="a", applied_date=date(2026, 3, 1))

    rows = core.resume_stats(since=date(2026, 2, 1), vault=vault)

    assert [(r.resume, r.applications) for r in rows] == [("a", 1)]


def test_resume_stats_with_no_applications_is_empty(tmp_path: Path) -> None:
    vault = _minimal_built_vault(tmp_path / "vault")

    assert core.resume_stats(vault=vault) == []


def test_resume_stats_does_not_touch_the_index(tmp_path: Path) -> None:
    vault = _stats_vault(tmp_path)

    core.resume_stats(vault=vault)

    assert not default_index_path(vault).exists()
