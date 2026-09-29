from datetime import date, datetime, timedelta

import pytest
from pydantic import TypeAdapter, ValidationError

from vacancy_radar.models import (
    STATUS_TRANSITIONS,
    TERMINAL_STATUSES,
    Company,
    Document,
    DocumentKind,
    Status,
    Vacancy,
    sort_vacancies,
)

ALL_STATUS_VALUES = [
    "found",
    "applied",
    "screening",
    "take_home",
    "interview",
    "offer",
    "rejected",
    "ghosted",
]

_status_adapter = TypeAdapter(Status)


def test_every_status_value_parses() -> None:
    for value in ALL_STATUS_VALUES:
        assert _status_adapter.validate_python(value) is getattr(Status, value.upper())


def test_unrecognized_status_lists_permitted_values() -> None:
    with pytest.raises(ValidationError) as exc_info:
        _status_adapter.validate_python("bogus")

    message = str(exc_info.value)
    for value in ALL_STATUS_VALUES:
        assert value in message


def test_status_parsing_is_case_insensitive_canonical_lowercase() -> None:
    parsed = _status_adapter.validate_python("Applied")

    assert parsed is Status.APPLIED
    assert str(parsed) == "applied"


def test_document_kind_members_parse() -> None:
    adapter = TypeAdapter(DocumentKind)

    assert adapter.validate_python("posting") is DocumentKind.POSTING
    assert adapter.validate_python("email") is DocumentKind.EMAIL
    assert adapter.validate_python("note") is DocumentKind.NOTE
    assert adapter.validate_python("takehome") is DocumentKind.TAKEHOME


def minimal_vacancy_data(**overrides: object) -> dict:
    data: dict[str, object] = {
        "id": "2026-01-01-acme-developer",
        "company": "Acme Inc.",
        "company_slug": "acme-inc",
        "role": "developer",
        "source_url": "https://example.com/jobs/1",
        "status": Status.FOUND,
        "found_date": date(2026, 1, 1),
    }
    data.update(overrides)
    return data


@pytest.mark.parametrize(
    "missing_field",
    ["id", "company", "company_slug", "role", "status", "found_date"],
)
def test_omitting_a_mandatory_field_is_rejected(missing_field: str) -> None:
    data = minimal_vacancy_data()
    del data[missing_field]

    with pytest.raises(ValidationError) as exc_info:
        Vacancy(**data)

    errors = exc_info.value.errors()
    assert any(missing_field in error["loc"] for error in errors)


def test_source_url_must_be_http_or_https() -> None:
    with pytest.raises(ValidationError):
        Vacancy(**minimal_vacancy_data(source_url="ftp://example.com/job"))


def test_vacancy_omitting_source_url_parses() -> None:
    data = minimal_vacancy_data()
    del data["source_url"]

    vacancy = Vacancy(**data)

    assert vacancy.source_url is None


def test_vacancy_with_valid_source_url_still_stored() -> None:
    vacancy = Vacancy(**minimal_vacancy_data(source_url="https://example.com/jobs/1"))

    assert vacancy.source_url == "https://example.com/jobs/1"


def test_minimal_vacancy_with_no_optional_fields_parses() -> None:
    vacancy = Vacancy(**minimal_vacancy_data())

    assert vacancy.stage_note is None
    assert vacancy.salary_note is None
    assert vacancy.recruiter is None
    assert vacancy.external_id is None
    assert vacancy.tags == []


def test_non_found_status_without_applied_date_is_rejected() -> None:
    with pytest.raises(ValidationError, match="applied_date"):
        Vacancy(**minimal_vacancy_data(status=Status.APPLIED))


def test_found_status_with_applied_date_is_rejected() -> None:
    with pytest.raises(ValidationError):
        Vacancy(
            **minimal_vacancy_data(status=Status.FOUND, applied_date=date(2026, 1, 2))
        )


def test_found_status_with_no_applied_date_parses() -> None:
    vacancy = Vacancy(**minimal_vacancy_data(status=Status.FOUND))

    assert vacancy.status == Status.FOUND
    assert vacancy.applied_date is None


def test_applied_date_before_found_date_is_rejected() -> None:
    with pytest.raises(ValidationError):
        Vacancy(
            **minimal_vacancy_data(
                status=Status.APPLIED,
                found_date=date(2026, 1, 10),
                applied_date=date(2026, 1, 9),
            )
        )


def test_found_date_in_the_future_is_rejected() -> None:
    tomorrow = datetime.now().astimezone().date() + timedelta(days=1)

    with pytest.raises(ValidationError):
        Vacancy(**minimal_vacancy_data(found_date=tomorrow))


def test_applied_date_equal_to_found_date_is_valid() -> None:
    same_day = date(2026, 1, 5)

    vacancy = Vacancy(
        **minimal_vacancy_data(
            status=Status.APPLIED, found_date=same_day, applied_date=same_day
        )
    )

    assert vacancy.applied_date == vacancy.found_date


def test_dates_parse_from_iso_strings_and_date_objects() -> None:
    from_string = Vacancy(**minimal_vacancy_data(found_date="2026-01-01"))
    from_object = Vacancy(**minimal_vacancy_data(found_date=date(2026, 1, 1)))

    assert from_string.found_date == from_object.found_date == date(2026, 1, 1)


@pytest.mark.parametrize("blank_role", ["", "   ", "\t\n"])
def test_empty_or_whitespace_role_is_rejected(blank_role: str) -> None:
    with pytest.raises(ValidationError):
        Vacancy(**minimal_vacancy_data(role=blank_role))


def test_role_unknown_parses() -> None:
    vacancy = Vacancy(**minimal_vacancy_data(role="unknown"))

    assert vacancy.role == "unknown"


@pytest.mark.parametrize("role", ["unknown", "Unknown", " UNKNOWN "])
def test_role_is_placeholder_true_for_unknown_variants(role: str) -> None:
    vacancy = Vacancy(**minimal_vacancy_data(role=role))

    assert vacancy.role_is_placeholder is True


@pytest.mark.parametrize("role", ["developer", "Data Scientist", "unknown role"])
def test_role_is_placeholder_false_for_other_values(role: str) -> None:
    vacancy = Vacancy(**minimal_vacancy_data(role=role))

    assert vacancy.role_is_placeholder is False


def test_stage_note_preserves_exact_text() -> None:
    note = "Первый этап 🎯\nSecond line with Latin and Кириллица mixed.\n"

    vacancy = Vacancy(**minimal_vacancy_data(stage_note=note))

    assert vacancy.stage_note == note


def test_company_and_company_slug_round_trip_independently() -> None:
    vacancy = Vacancy(
        **minimal_vacancy_data(company="Незабудка Банк", company_slug="nezabudka-bank")
    )

    assert vacancy.company == "Незабудка Банк"
    assert vacancy.company_slug == "nezabudka-bank"


def test_vacancies_sort_by_applied_date_descending() -> None:
    early = Vacancy(
        **minimal_vacancy_data(
            id="a",
            status=Status.APPLIED,
            found_date=date(2026, 1, 1),
            applied_date=date(2026, 1, 2),
        )
    )
    late = Vacancy(
        **minimal_vacancy_data(
            id="b",
            status=Status.APPLIED,
            found_date=date(2026, 2, 1),
            applied_date=date(2026, 2, 2),
        )
    )

    assert sort_vacancies([early, late]) == [late, early]


def test_found_vacancies_sort_by_found_date_in_applied_dates_place() -> None:
    found_only = Vacancy(
        **minimal_vacancy_data(id="a", status=Status.FOUND, found_date=date(2026, 3, 1))
    )
    applied = Vacancy(
        **minimal_vacancy_data(
            id="b",
            status=Status.APPLIED,
            found_date=date(2026, 1, 1),
            applied_date=date(2026, 2, 1),
        )
    )

    # found_only's sort key (found_date=2026-03-01) is later than
    # applied's sort key (applied_date=2026-02-01).
    assert sort_vacancies([applied, found_only]) == [found_only, applied]


def test_vacancy_sort_ties_are_stable() -> None:
    same_day = date(2026, 4, 1)
    first = Vacancy(
        **minimal_vacancy_data(
            id="a", status=Status.APPLIED, found_date=same_day, applied_date=same_day
        )
    )
    second = Vacancy(
        **minimal_vacancy_data(
            id="b", status=Status.APPLIED, found_date=same_day, applied_date=same_day
        )
    )

    assert sort_vacancies([first, second]) == [first, second]


def test_document_constructs() -> None:
    document = Document(
        id="doc-1",
        vacancy_id="2026-01-01-acme-developer",
        kind=DocumentKind.EMAIL,
        title="Recruiter follow-up",
        date=date(2026, 1, 3),
    )

    assert document.external_id is None

    with_external = Document(
        id="doc-2",
        vacancy_id="2026-01-01-acme-developer",
        kind=DocumentKind.EMAIL,
        title="Recruiter follow-up",
        date=date(2026, 1, 3),
        external_id="gmail-message-id",
    )
    assert with_external.external_id == "gmail-message-id"


def test_company_constructs() -> None:
    company = Company(
        slug="acme-inc",
        name="Acme Inc.",
        domains=["acme.example"],
        recruiters=["Jane Recruiter"],
        notes="Friendly hiring team.",
    )

    assert company.slug == "acme-inc"
    assert company.domains == ["acme.example"]
    assert company.recruiters == ["Jane Recruiter"]


# --- STATUS_TRANSITIONS (stage 7 write half, section 2) --------------------


def test_status_transitions_has_an_entry_for_every_status() -> None:
    assert set(STATUS_TRANSITIONS) == set(Status)


def test_status_transitions_permits_every_later_pipeline_stage() -> None:
    # found -> every later pipeline status, not only the immediate next one.
    assert STATUS_TRANSITIONS[Status.FOUND] >= {
        Status.APPLIED,
        Status.SCREENING,
        Status.TAKE_HOME,
        Status.INTERVIEW,
        Status.OFFER,
    }
    # screening -> offer skips take_home and interview - a real pipeline
    # does this often enough that it must be permitted without force.
    assert Status.OFFER in STATUS_TRANSITIONS[Status.SCREENING]


def test_status_transitions_permits_terminal_statuses_from_any_active_state() -> None:
    for status in (
        Status.FOUND,
        Status.APPLIED,
        Status.SCREENING,
        Status.TAKE_HOME,
        Status.INTERVIEW,
        Status.OFFER,
    ):
        assert Status.REJECTED in STATUS_TRANSITIONS[status]
        assert Status.GHOSTED in STATUS_TRANSITIONS[status]


def test_status_transitions_terminal_statuses_have_no_unforced_follow_on() -> None:
    # offer is the last pipeline stage, so nothing later remains - but it
    # still reaches rejected/ghosted, like every other active status.
    assert STATUS_TRANSITIONS[Status.OFFER] == TERMINAL_STATUSES
    assert STATUS_TRANSITIONS[Status.REJECTED] == frozenset()
    assert STATUS_TRANSITIONS[Status.GHOSTED] == frozenset()


def test_status_transitions_has_no_self_loops() -> None:
    for status, reachable in STATUS_TRANSITIONS.items():
        assert status not in reachable
