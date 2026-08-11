import json
import re
import shutil
import sys
from datetime import date
from pathlib import Path

import pytest
from typer.testing import CliRunner

import vacancy_radar
from vacancy_radar import frontmatter
from vacancy_radar.cli import app
from vacancy_radar.index.build import build_index
from vacancy_radar.index.store import default_index_path
from vacancy_radar.models import Company, Document, DocumentKind, Status, Vacancy
from vacancy_radar.vault.paths import VAULT_MARKER_DIRNAME
from vacancy_radar.vault.reader import read_vault

runner = CliRunner()

FIXTURE_VAULT = Path(__file__).resolve().parent / "fixtures" / "vault"

_ENV_WIDE = {"COLUMNS": "400", "LINES": "50"}
"""Widens Rich's rendering width for table-output assertions, so a long
vacancy id or company name never gets column-wrapped mid-string."""

_ANSI_ESCAPE = re.compile(r"\x1b\[[0-9;]*m")


def plain(output: str) -> str:
    """Strip ANSI styling so substring assertions see the literal text.

    Whether Rich colors its output depends on the environment, not on us -
    it stays off under a plain `pytest` run but switches on under
    `FORCE_COLOR` or a terminal-backed runner. Colored, Rich's option
    highlighter renders `--source-url` as three separately styled spans,
    so the substring is simply absent. `NO_COLOR` is not a fix: it drops
    the color but keeps the bold spans, and the text stays fragmented.

    Negative assertions are the reason this matters. `"--status" not in
    output` passes unconditionally against fragmented text, so an
    unstripped assertion would keep passing even if the option it forbids
    came back.
    """
    return _ANSI_ESCAPE.sub("", output)


_FIXTURES_DIR = Path(__file__).resolve().parent / "fixtures"
if str(_FIXTURES_DIR) not in sys.path:
    sys.path.insert(0, str(_FIXTURES_DIR))

from generate import generate_vault, write_broken_fixtures  # noqa: E402
from pdfs import write_encrypted_pdf, write_malformed_pdf, write_valid_pdf  # noqa: E402

SEED = 20260101


def _broken_vault(tmp_path_factory: pytest.TempPathFactory, name: str) -> Path:
    vault = tmp_path_factory.mktemp(name)
    generate_vault(vault, seed=SEED)
    write_broken_fixtures(vault)
    return vault


# --- Ad hoc single-vacancy vault helpers, for staleness/ambiguity fixtures -


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
    vacancy_id: str, slug: str = "tiny-corp", **overrides: object
) -> Vacancy:
    fields: dict[str, object] = {
        "id": vacancy_id,
        "company": "Tiny Corp",
        "company_slug": slug,
        "role": "Engineer",
        "source_url": f"https://jobs.{slug}.example/{vacancy_id}",
        "status": Status.FOUND,
        "found_date": date(2026, 1, 1),
    }
    fields.update(overrides)
    return Vacancy(**fields)  # type: ignore[arg-type]


def _minimal_vault(vault: Path) -> Path:
    """A tiny hand-built vault (marker + one company + one vacancy) -
    small and fast, unlike a copy of the full fixture vault. Mirrors
    `tests/test_core.py`'s `_minimal_built_vault`; write-command tests
    build their own index only when a test actually needs one (most
    don't - they check exit code and file creation, not search)."""
    _init_vault(vault)
    _write_company(vault, "tiny-corp", "Tiny Corp")
    _write_vacancy(vault, "tiny-corp", "v1", _simple_vacancy("v1"))
    return vault


@pytest.fixture(scope="module")
def built_fixture_vault(tmp_path_factory: pytest.TempPathFactory) -> Path:
    """A copy of the committed fixture vault with a fresh index built
    over it - built once and reused read-only by this module's search/
    doctor tests. Building is the slow, embedding-marked part."""
    vault = tmp_path_factory.mktemp("cli-built-fixture-vault")
    shutil.copytree(FIXTURE_VAULT, vault, dirs_exist_ok=True)
    build_index(read_vault(vault), default_index_path(vault))
    return vault


# --- version / help / unknown command (pre-existing) ------------------------


def test_version_flag_exits_zero_and_prints_version() -> None:
    result = runner.invoke(app, ["--version"])

    assert result.exit_code == 0
    assert vacancy_radar.__version__ in result.output


def test_no_args_prints_usage_and_exits_zero() -> None:
    result = runner.invoke(app, [])

    assert result.exit_code == 0
    assert "Usage" in result.output


def test_unknown_command_exits_non_zero() -> None:
    result = runner.invoke(app, ["bogus-command"])

    assert result.exit_code != 0


# --- Section 9: list command -------------------------------------------


def test_list_command_with_no_options_prints_a_row_per_vacancy() -> None:
    snapshot = read_vault(FIXTURE_VAULT)

    result = runner.invoke(
        app,
        ["list", "--limit", str(len(snapshot.vacancies))],
        env={**_ENV_WIDE, "VAULT_PATH": str(FIXTURE_VAULT)},
    )

    assert result.exit_code == 0
    for vacancy_id in snapshot.vacancies:
        assert vacancy_id in result.output


def test_list_command_status_option_restricts_output() -> None:
    snapshot = read_vault(FIXTURE_VAULT)
    target_status = next(iter(snapshot.vacancies.values())).status
    expected_ids = {
        v.id for v in snapshot.vacancies.values() if v.status == target_status
    }
    other_ids = {v.id for v in snapshot.vacancies.values() if v.status != target_status}

    result = runner.invoke(
        app,
        ["list", "--status", target_status.value, "--limit", "1000"],
        env={**_ENV_WIDE, "VAULT_PATH": str(FIXTURE_VAULT)},
    )

    assert result.exit_code == 0
    for vacancy_id in expected_ids:
        assert vacancy_id in result.output
    for vacancy_id in other_ids:
        assert vacancy_id not in result.output


def test_list_command_json_emits_valid_json_array_with_no_rich_formatting() -> None:
    result = runner.invoke(
        app,
        ["list", "--json", "--limit", "1000"],
        env={"VAULT_PATH": str(FIXTURE_VAULT)},
    )

    assert result.exit_code == 0
    payload = json.loads(result.output)
    assert isinstance(payload, list)
    assert payload
    assert "\x1b[" not in result.output


def test_list_command_with_no_vault_configured_names_vault_path(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("VAULT_PATH", raising=False)

    result = runner.invoke(app, ["list"])

    assert result.exit_code != 0
    assert "VAULT_PATH" in result.output


# --- Section 10: show command -------------------------------------------


def test_show_command_on_vacancy_id_renders_vacancy_detail() -> None:
    snapshot = read_vault(FIXTURE_VAULT)
    vacancy_id = next(iter(snapshot.vacancies))

    result = runner.invoke(
        app, ["show", vacancy_id], env={**_ENV_WIDE, "VAULT_PATH": str(FIXTURE_VAULT)}
    )

    assert result.exit_code == 0
    assert snapshot.vacancies[vacancy_id].role in result.output


def test_show_command_on_company_name_renders_company_dossier() -> None:
    snapshot = read_vault(FIXTURE_VAULT)
    company = next(iter(snapshot.companies.values()))

    result = runner.invoke(
        app, ["show", company.slug], env={**_ENV_WIDE, "VAULT_PATH": str(FIXTURE_VAULT)}
    )

    assert result.exit_code == 0
    assert company.name in result.output


def test_show_command_on_ambiguous_query_exits_non_zero_and_lists_candidates(
    tmp_path: Path,
) -> None:
    vault = tmp_path / "vault"
    _init_vault(vault)
    _write_company(vault, "widget-us", "Widget Inc")
    _write_company(vault, "widget-eu", "Widget Inc")

    result = runner.invoke(app, ["show", "widget inc"], env={"VAULT_PATH": str(vault)})

    assert result.exit_code != 0
    assert "widget-us" in result.output
    assert "widget-eu" in result.output


def test_show_command_json_on_vacancy_and_company_are_tagged() -> None:
    snapshot = read_vault(FIXTURE_VAULT)
    vacancy_id = next(iter(snapshot.vacancies))
    company_slug = next(iter(snapshot.companies))

    vacancy_result = runner.invoke(
        app, ["show", vacancy_id, "--json"], env={"VAULT_PATH": str(FIXTURE_VAULT)}
    )
    company_result = runner.invoke(
        app, ["show", company_slug, "--json"], env={"VAULT_PATH": str(FIXTURE_VAULT)}
    )

    assert json.loads(vacancy_result.output)["kind"] == "vacancy"
    assert json.loads(company_result.output)["kind"] == "company"


def test_show_command_on_nonexistent_query_exits_non_zero_with_message() -> None:
    result = runner.invoke(
        app,
        ["show", "zzz-totally-nonexistent-zzz"],
        env={"VAULT_PATH": str(FIXTURE_VAULT)},
    )

    assert result.exit_code != 0
    assert result.output.strip()


# --- Section 11: search command (embedding-marked: needs a built index) ----


@pytest.mark.embedding
def test_search_command_prints_hits(built_fixture_vault: Path) -> None:
    result = runner.invoke(
        app,
        ["search", "Engineer", "--mode", "keyword", "--limit", "5"],
        env={**_ENV_WIDE, "VAULT_PATH": str(built_fixture_vault)},
    )

    assert result.exit_code == 0


@pytest.mark.embedding
def test_search_command_company_option_is_forwarded(built_fixture_vault: Path) -> None:
    snapshot = read_vault(built_fixture_vault)
    slug = next(iter(snapshot.companies))

    result = runner.invoke(
        app,
        [
            "search",
            "Engineer",
            "--mode",
            "keyword",
            "--company",
            slug,
            "--limit",
            "50",
            "--json",
        ],
        env={"VAULT_PATH": str(built_fixture_vault)},
    )

    assert result.exit_code == 0
    payload = json.loads(result.output)
    assert all(hit["company_slug"] == slug for hit in payload["hits"])


@pytest.mark.embedding
def test_search_command_scores_prints_ranks_and_fused_score(
    built_fixture_vault: Path,
) -> None:
    result = runner.invoke(
        app,
        ["search", "Engineer", "--mode", "hybrid", "--scores", "--limit", "5"],
        env={**_ENV_WIDE, "VAULT_PATH": str(built_fixture_vault)},
    )

    assert result.exit_code == 0
    assert "keyword_rank" in result.output
    assert "semantic_rank" in result.output


@pytest.mark.embedding
def test_search_command_json_emits_valid_json_with_no_rich_formatting(
    built_fixture_vault: Path,
) -> None:
    result = runner.invoke(
        app,
        ["search", "Engineer", "--mode", "keyword", "--json"],
        env={"VAULT_PATH": str(built_fixture_vault)},
    )

    assert result.exit_code == 0
    payload = json.loads(result.output)
    assert "hits" in payload
    assert "\x1b[" not in result.output


# --- Section 12: doctor command ------------------------------------------


@pytest.mark.embedding
def test_doctor_command_on_healthy_vault_with_fresh_index_exits_zero(
    built_fixture_vault: Path,
) -> None:
    result = runner.invoke(
        app, ["doctor"], env={"VAULT_PATH": str(built_fixture_vault)}
    )

    assert result.exit_code == 0


def test_doctor_command_on_broken_vault_exits_non_zero_and_lists_warnings(
    tmp_path_factory: pytest.TempPathFactory,
) -> None:
    vault = _broken_vault(tmp_path_factory, "doctor-broken")

    result = runner.invoke(app, ["doctor"], env={**_ENV_WIDE, "VAULT_PATH": str(vault)})

    assert result.exit_code != 0
    for marker in (
        "broken-yaml-vacancy",
        "unreadable-vacancy",
        "duplicate-vacancy-id",
        "orphan-vacancy",
    ):
        assert marker in result.output

    # Restore permissions so pytest's tmp_path cleanup can remove it.
    unreadable_path = (
        vault / "unreadable-vault-corp" / "unreadable-vacancy" / "vacancy.md"
    )
    unreadable_path.chmod(0o644)


@pytest.mark.embedding
def test_doctor_command_reports_stale_index_without_failing_alone(
    tmp_path: Path,
) -> None:
    vault = tmp_path / "vault"
    _init_vault(vault)
    _write_company(vault, "tiny-corp", "Tiny Corp")
    vacancy_dir = _write_vacancy(vault, "tiny-corp", "v1", _simple_vacancy("v1"))
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
    build_index(read_vault(vault), default_index_path(vault))
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

    result = runner.invoke(app, ["doctor"], env={"VAULT_PATH": str(vault)})

    assert result.exit_code == 0
    assert "build_index" in result.output


def test_doctor_command_with_no_vault_configured_names_vault_path(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("VAULT_PATH", raising=False)

    result = runner.invoke(app, ["doctor"])

    assert result.exit_code != 0
    assert "VAULT_PATH" in result.output


def test_doctor_command_json_emits_valid_json() -> None:
    result = runner.invoke(
        app, ["doctor", "--json"], env={"VAULT_PATH": str(FIXTURE_VAULT)}
    )

    payload = json.loads(result.output)
    assert "vault_path" in payload


# --- Section 13: public eval command, replacing _eval ------------------


def test_eval_command_is_listed_in_help_output_and_underscore_eval_is_not() -> None:
    result = runner.invoke(app, ["--help"])

    assert result.exit_code == 0
    assert "eval" in result.output
    assert "_eval" not in result.output


def test_underscore_eval_is_now_an_unknown_command() -> None:
    result = runner.invoke(app, ["_eval"])

    assert result.exit_code != 0


@pytest.mark.embedding
def test_eval_command_runs_the_full_sweep_and_prints_a_markdown_report() -> None:
    result = runner.invoke(app, ["eval"])

    assert result.exit_code == 0
    assert "| mode | vector_weight | fusion | category | recall@5 | MRR | n |" in (
        result.output
    )
    assert "overall" in result.output


# --- Section 9: note command -------------------------------------------


def test_note_command_creates_one_note_file(tmp_path: Path) -> None:
    vault = _minimal_vault(tmp_path / "vault")

    result = runner.invoke(
        app, ["note", "v1", "Called the recruiter."], env={"VAULT_PATH": str(vault)}
    )

    assert result.exit_code == 0
    docs_dir = vault / "tiny-corp" / "v1" / "documents"
    assert list(docs_dir.iterdir())


def test_note_command_ambiguous_query_exits_nonzero_and_writes_nothing(
    tmp_path: Path,
) -> None:
    vault = tmp_path / "vault"
    _init_vault(vault)
    _write_company(vault, "widget-us", "Widget Inc")
    _write_company(vault, "widget-eu", "Widget Inc")

    result = runner.invoke(
        app, ["note", "widget inc", "text"], env={"VAULT_PATH": str(vault)}
    )

    assert result.exit_code != 0
    assert "widget-us" in result.output or "widget-us" in result.stderr
    assert not (vault / "widget-us").exists() or not any(
        (vault / "widget-us").rglob("documents/*")
    )
    assert not (vault / "widget-eu").exists() or not any(
        (vault / "widget-eu").rglob("documents/*")
    )


def test_note_command_json_names_the_created_path(tmp_path: Path) -> None:
    vault = _minimal_vault(tmp_path / "vault")

    result = runner.invoke(
        app,
        ["note", "v1", "Called the recruiter.", "--json"],
        env={"VAULT_PATH": str(vault)},
    )

    assert result.exit_code == 0
    payload = json.loads(result.output)
    assert payload["outcome"] == "created"
    assert Path(payload["path"]).is_file()


# --- Section 10: status set command -------------------------------------


def test_status_set_permitted_forward_transition_exits_zero(tmp_path: Path) -> None:
    vault = _minimal_vault(tmp_path / "vault")

    result = runner.invoke(
        app,
        ["status", "set", "v1", "applied", "--applied-date", "2026-01-05"],
        env={"VAULT_PATH": str(vault)},
    )

    assert result.exit_code == 0
    assert read_vault(vault).vacancies["v1"].status == Status.APPLIED


def test_status_set_backward_without_force_exits_nonzero_names_both_statuses(
    tmp_path: Path,
) -> None:
    vault = _minimal_vault(tmp_path / "vault")
    runner.invoke(
        app,
        ["status", "set", "v1", "applied", "--applied-date", "2026-01-05"],
        env={"VAULT_PATH": str(vault)},
    )

    result = runner.invoke(
        app, ["status", "set", "v1", "found"], env={"VAULT_PATH": str(vault)}
    )
    assert result.exit_code != 0
    assert "applied" in result.output
    assert "found" in result.output

    forced = runner.invoke(
        app, ["status", "set", "v1", "found", "--force"], env={"VAULT_PATH": str(vault)}
    )
    assert forced.exit_code == 0
    assert read_vault(vault).vacancies["v1"].status == Status.FOUND


def test_status_set_off_found_requires_applied_date_option(tmp_path: Path) -> None:
    vault = _minimal_vault(tmp_path / "vault")

    missing = runner.invoke(
        app, ["status", "set", "v1", "applied"], env={"VAULT_PATH": str(vault)}
    )
    assert missing.exit_code != 0

    given = runner.invoke(
        app,
        ["status", "set", "v1", "applied", "--applied-date", "2026-02-01"],
        env={"VAULT_PATH": str(vault)},
    )
    assert given.exit_code == 0
    assert read_vault(vault).vacancies["v1"].applied_date == date(2026, 2, 1)


def test_status_set_ambiguous_query_exits_nonzero_and_writes_nothing(
    tmp_path: Path,
) -> None:
    vault = tmp_path / "vault"
    _init_vault(vault)
    _write_company(vault, "widget-us", "Widget Inc")
    _write_company(vault, "widget-eu", "Widget Inc")

    result = runner.invoke(
        app, ["status", "set", "widget inc", "applied"], env={"VAULT_PATH": str(vault)}
    )

    assert result.exit_code != 0


def test_status_set_json_same_status_reports_unchanged(tmp_path: Path) -> None:
    vault = _minimal_vault(tmp_path / "vault")

    result = runner.invoke(
        app, ["status", "set", "v1", "found", "--json"], env={"VAULT_PATH": str(vault)}
    )

    assert result.exit_code == 0
    payload = json.loads(result.output)
    assert payload["outcome"] == "unchanged"


# --- Section 11: add command ---------------------------------------------


def test_add_command_from_file_creates_a_document_with_matching_content(
    tmp_path: Path,
) -> None:
    vault = _minimal_vault(tmp_path / "vault")
    source = tmp_path / "source.txt"
    source.write_text("Email body from a file.", encoding="utf-8")

    result = runner.invoke(
        app,
        [
            "add",
            "v1",
            "--kind",
            "email",
            "--title",
            "Recruiter Email",
            "--date",
            "2026-01-05",
            "--file",
            str(source),
        ],
        env={"VAULT_PATH": str(vault)},
    )

    assert result.exit_code == 0
    docs_dir = vault / "tiny-corp" / "v1" / "documents"
    created = next(docs_dir.glob("2026-01-05-email-*.md"))
    _, body = frontmatter.parse(created.read_text(encoding="utf-8"))
    assert body == "Email body from a file."


def test_add_command_stdin_creates_a_document_with_piped_content(
    tmp_path: Path,
) -> None:
    vault = _minimal_vault(tmp_path / "vault")

    result = runner.invoke(
        app,
        [
            "add",
            "v1",
            "--kind",
            "email",
            "--title",
            "Recruiter Email",
            "--date",
            "2026-01-05",
            "--stdin",
        ],
        input="Email body from stdin.",
        env={"VAULT_PATH": str(vault)},
    )

    assert result.exit_code == 0
    docs_dir = vault / "tiny-corp" / "v1" / "documents"
    created = next(docs_dir.glob("2026-01-05-email-*.md"))
    _, body = frontmatter.parse(created.read_text(encoding="utf-8"))
    assert body == "Email body from stdin."


def test_add_command_file_non_utf8_exits_cleanly_not_with_traceback(
    tmp_path: Path,
) -> None:
    vault = _minimal_vault(tmp_path / "vault")
    pdf = tmp_path / "posting.pdf"
    write_valid_pdf(pdf)

    result = runner.invoke(
        app,
        [
            "add",
            "v1",
            "--kind",
            "posting",
            "--title",
            "Posting",
            "--date",
            "2026-01-05",
            "--file",
            str(pdf),
        ],
        env={"VAULT_PATH": str(vault)},
    )

    assert result.exit_code != 0
    assert result.exception is None or isinstance(result.exception, SystemExit)
    assert "posting.pdf" in result.output
    assert "Traceback" not in result.output


def test_add_command_file_non_utf8_error_names_the_pdf_workaround(
    tmp_path: Path,
) -> None:
    vault = _minimal_vault(tmp_path / "vault")
    pdf = tmp_path / "posting.pdf"
    write_valid_pdf(pdf)

    result = runner.invoke(
        app,
        [
            "add",
            "v1",
            "--kind",
            "posting",
            "--title",
            "Posting",
            "--date",
            "2026-01-05",
            "--file",
            str(pdf),
        ],
        env={"VAULT_PATH": str(vault)},
    )

    assert "documents/" in result.output
    assert "reindex --extract-sidecars" in result.output


def test_add_command_stdin_non_utf8_exits_cleanly_not_with_traceback(
    tmp_path: Path,
) -> None:
    vault = _minimal_vault(tmp_path / "vault")

    result = runner.invoke(
        app,
        [
            "add",
            "v1",
            "--kind",
            "email",
            "--title",
            "Recruiter Email",
            "--date",
            "2026-01-05",
            "--stdin",
        ],
        input=b"\xff\xfe not valid utf-8 at all",
        env={"VAULT_PATH": str(vault)},
    )

    assert result.exit_code != 0
    assert "not valid" in result.output.lower() or "utf-8" in result.output.lower()
    assert "Traceback" not in result.output


def test_add_command_external_id_dedupe_reports_existing_and_creates_no_file(
    tmp_path: Path,
) -> None:
    vault = _minimal_vault(tmp_path / "vault")
    args = [
        "add",
        "v1",
        "--kind",
        "email",
        "--title",
        "Thread",
        "--date",
        "2026-01-05",
        "--external-id",
        "thread-123",
        "--stdin",
    ]
    first = runner.invoke(
        app, [*args, "--json"], input="first pass", env={"VAULT_PATH": str(vault)}
    )
    assert first.exit_code == 0
    first_payload = json.loads(first.output)
    docs_dir = vault / "tiny-corp" / "v1" / "documents"
    before = sorted(p.name for p in docs_dir.iterdir())

    second = runner.invoke(
        app, [*args, "--json"], input="second pass", env={"VAULT_PATH": str(vault)}
    )

    assert second.exit_code == 0
    second_payload = json.loads(second.output)
    assert second_payload["outcome"] == "existing"
    assert second_payload["path"] == first_payload["path"]
    assert sorted(p.name for p in docs_dir.iterdir()) == before


def test_add_command_ambiguous_query_exits_nonzero_and_writes_nothing(
    tmp_path: Path,
) -> None:
    vault = tmp_path / "vault"
    _init_vault(vault)
    _write_company(vault, "widget-us", "Widget Inc")
    _write_company(vault, "widget-eu", "Widget Inc")

    result = runner.invoke(
        app,
        [
            "add",
            "widget inc",
            "--kind",
            "email",
            "--title",
            "Thread",
            "--date",
            "2026-01-05",
            "--stdin",
        ],
        input="body",
        env={"VAULT_PATH": str(vault)},
    )

    assert result.exit_code != 0


def test_add_command_json_on_fresh_filing_names_created_path(tmp_path: Path) -> None:
    vault = _minimal_vault(tmp_path / "vault")

    result = runner.invoke(
        app,
        [
            "add",
            "v1",
            "--kind",
            "email",
            "--title",
            "Recruiter Email",
            "--date",
            "2026-01-05",
            "--stdin",
            "--json",
        ],
        input="body",
        env={"VAULT_PATH": str(vault)},
    )

    assert result.exit_code == 0
    payload = json.loads(result.output)
    assert payload["outcome"] == "created"
    assert Path(payload["path"]).is_file()


# --- Section 11b (vault-init change): init command -------------------------


def test_init_on_new_path_reports_created(tmp_path: Path) -> None:
    target = tmp_path / "new-vault"

    result = runner.invoke(app, ["init", str(target)])

    assert result.exit_code == 0
    output = plain(result.output)
    assert "created" in output
    assert str(target) in output
    assert (target / VAULT_MARKER_DIRNAME).is_dir()


def test_init_on_already_initialized_vault_exits_zero_and_reports_no_error(
    tmp_path: Path,
) -> None:
    vault = tmp_path / "vault"
    _init_vault(vault)

    result = runner.invoke(app, ["init", str(vault)])

    assert result.exit_code == 0
    assert "already initialized" in result.output


def test_init_json_reports_created(tmp_path: Path) -> None:
    target = tmp_path / "new-vault"

    result = runner.invoke(app, ["init", str(target), "--json"])

    assert result.exit_code == 0
    payload = json.loads(result.output)
    assert payload["outcome"] == "created"
    assert payload["path"] == str(target.resolve())


def test_init_json_reports_already_initialized_outcome(tmp_path: Path) -> None:
    vault = tmp_path / "vault"
    _init_vault(vault)

    result = runner.invoke(app, ["init", str(vault), "--json"])

    assert result.exit_code == 0
    payload = json.loads(result.output)
    assert payload["outcome"] == "already initialized"


def test_init_omitted_path_falls_back_to_vault_path_env(tmp_path: Path) -> None:
    target = tmp_path / "env-vault"

    result = runner.invoke(app, ["init"], env={"VAULT_PATH": str(target)})

    assert result.exit_code == 0
    assert (target / VAULT_MARKER_DIRNAME).is_dir()


def test_list_succeeds_against_a_freshly_initialized_vault(tmp_path: Path) -> None:
    target = tmp_path / "new-vault"

    init_result = runner.invoke(app, ["init", str(target)])
    assert init_result.exit_code == 0

    list_result = runner.invoke(
        app, ["list", "--json"], env={"VAULT_PATH": str(target)}
    )

    assert list_result.exit_code == 0
    assert json.loads(list_result.output) == []


# --- Section 12: new command ----------------------------------------------


def test_new_command_creates_vacancy_and_is_listed_afterward(tmp_path: Path) -> None:
    vault = tmp_path / "vault"
    _init_vault(vault)

    result = runner.invoke(
        app,
        [
            "new",
            "--company",
            "Acme Corp",
            "--role",
            "Engineer",
            "--url",
            "https://jobs.acme.example/1",
            "--found-date",
            "2026-01-01",
        ],
        env={"VAULT_PATH": str(vault)},
    )

    assert result.exit_code == 0
    listing = runner.invoke(app, ["list", "--json"], env={"VAULT_PATH": str(vault)})
    assert listing.exit_code == 0
    rows = json.loads(listing.output)
    assert any(row["company"] == "Acme Corp" for row in rows)


def test_new_command_without_url_creates_vacancy_with_no_source_url(
    tmp_path: Path,
) -> None:
    vault = tmp_path / "vault"
    _init_vault(vault)

    result = runner.invoke(
        app,
        [
            "new",
            "--company",
            "Acme Corp",
            "--role",
            "Engineer",
            "--found-date",
            "2026-01-01",
            "--json",
        ],
        env={"VAULT_PATH": str(vault)},
    )
    assert result.exit_code == 0
    vacancy_id = json.loads(result.output)["id"]

    detail = runner.invoke(
        app, ["show", vacancy_id, "--json"], env={"VAULT_PATH": str(vault)}
    )
    assert detail.exit_code == 0
    payload = json.loads(detail.output)
    assert payload["source_url"] is None


def test_new_command_with_url_still_works(tmp_path: Path) -> None:
    vault = tmp_path / "vault"
    _init_vault(vault)

    result = runner.invoke(
        app,
        [
            "new",
            "--company",
            "Acme Corp",
            "--role",
            "Engineer",
            "--url",
            "https://jobs.acme.example/1",
            "--found-date",
            "2026-01-01",
            "--json",
        ],
        env={"VAULT_PATH": str(vault)},
    )
    assert result.exit_code == 0
    vacancy_id = json.loads(result.output)["id"]

    detail = runner.invoke(
        app, ["show", vacancy_id, "--json"], env={"VAULT_PATH": str(vault)}
    )
    assert detail.exit_code == 0
    payload = json.loads(detail.output)
    assert payload["source_url"] == "https://jobs.acme.example/1"


def test_new_command_non_found_status_without_applied_date_exits_nonzero(
    tmp_path: Path,
) -> None:
    vault = tmp_path / "vault"
    _init_vault(vault)

    result = runner.invoke(
        app,
        [
            "new",
            "--company",
            "Acme Corp",
            "--role",
            "Engineer",
            "--url",
            "https://jobs.acme.example/1",
            "--found-date",
            "2026-01-01",
            "--status",
            "applied",
        ],
        env={"VAULT_PATH": str(vault)},
    )

    assert result.exit_code != 0

    with_date = runner.invoke(
        app,
        [
            "new",
            "--company",
            "Acme Corp",
            "--role",
            "Engineer",
            "--url",
            "https://jobs.acme.example/1",
            "--found-date",
            "2026-01-01",
            "--status",
            "applied",
            "--applied-date",
            "2026-01-05",
        ],
        env={"VAULT_PATH": str(vault)},
    )
    assert with_date.exit_code == 0


def test_new_command_json_names_created_id_and_path(tmp_path: Path) -> None:
    vault = tmp_path / "vault"
    _init_vault(vault)

    result = runner.invoke(
        app,
        [
            "new",
            "--company",
            "Acme Corp",
            "--role",
            "Engineer",
            "--url",
            "https://jobs.acme.example/1",
            "--found-date",
            "2026-01-01",
            "--json",
        ],
        env={"VAULT_PATH": str(vault)},
    )

    assert result.exit_code == 0
    payload = json.loads(result.output)
    assert payload["outcome"] == "created"
    assert "id" in payload
    assert Path(payload["path"]).is_file()


# --- Section 13: reindex command -------------------------------------------


def test_reindex_command_against_fresh_index_reports_zero_changes(
    tmp_path: Path,
) -> None:
    vault = _minimal_vault(tmp_path / "vault")
    build_index(read_vault(vault), default_index_path(vault))

    result = runner.invoke(app, ["reindex"], env={"VAULT_PATH": str(vault)})

    assert result.exit_code == 0
    output = plain(result.output)
    assert "added=0" in output
    assert "changed=0" in output


def test_reindex_command_force_reports_every_row_reembedded(tmp_path: Path) -> None:
    vault = _minimal_vault(tmp_path / "vault")
    build_index(read_vault(vault), default_index_path(vault))

    result = runner.invoke(app, ["reindex", "--force"], env={"VAULT_PATH": str(vault)})

    assert result.exit_code == 0
    assert "unchanged=0" in plain(result.output)


def test_reindex_command_json_matches_index_report_fields(tmp_path: Path) -> None:
    vault = _minimal_vault(tmp_path / "vault")
    build_index(read_vault(vault), default_index_path(vault))

    result = runner.invoke(app, ["reindex", "--json"], env={"VAULT_PATH": str(vault)})

    assert result.exit_code == 0
    payload = json.loads(result.output)
    assert set(payload) == {
        "added",
        "changed",
        "deleted",
        "unchanged",
        "skipped",
        "elapsed",
        "warnings",
    }


def test_reindex_extract_sidecars_flag_creates_sidecar(tmp_path: Path) -> None:
    vault = _minimal_vault(tmp_path / "vault")
    docs_dir = vault / "tiny-corp" / "v1" / "documents"
    docs_dir.mkdir(parents=True, exist_ok=True)
    write_valid_pdf(docs_dir / "posting.pdf")

    result = runner.invoke(
        app, ["reindex", "--extract-sidecars"], env={"VAULT_PATH": str(vault)}
    )

    assert result.exit_code == 0
    assert (docs_dir / "posting.pdf.md").is_file()


def test_reindex_without_flag_creates_no_sidecar(tmp_path: Path) -> None:
    vault = _minimal_vault(tmp_path / "vault")
    docs_dir = vault / "tiny-corp" / "v1" / "documents"
    docs_dir.mkdir(parents=True, exist_ok=True)
    write_valid_pdf(docs_dir / "posting.pdf")

    result = runner.invoke(app, ["reindex"], env={"VAULT_PATH": str(vault)})

    assert result.exit_code == 0
    assert not (docs_dir / "posting.pdf.md").exists()


def test_reindex_plain_text_output_includes_extraction_warning(tmp_path: Path) -> None:
    vault = _minimal_vault(tmp_path / "vault")
    docs_dir = vault / "tiny-corp" / "v1" / "documents"
    docs_dir.mkdir(parents=True, exist_ok=True)
    write_malformed_pdf(docs_dir / "broken.pdf")

    result = runner.invoke(
        app, ["reindex", "--extract-sidecars"], env={"VAULT_PATH": str(vault)}
    )

    assert result.exit_code == 0
    assert "broken.pdf" in result.output


def test_reindex_plain_text_output_includes_encrypted_pdf_warning(
    tmp_path: Path,
) -> None:
    # Scope note (tasks.md 2.4): a true `vanished_source` warning needs a
    # snapshot that's gone stale between read_vault and build_index - not
    # reachable through this CLI's black-box invocation, since
    # core.reindex always reads fresh immediately before building.
    # encrypted_pdf is a second, distinct warning kind extraction
    # actually produces, still proving the plain-text branch prints
    # whatever IndexReport.warnings carries rather than special-casing
    # one warning kind.
    vault = _minimal_vault(tmp_path / "vault")
    docs_dir = vault / "tiny-corp" / "v1" / "documents"
    docs_dir.mkdir(parents=True, exist_ok=True)
    write_encrypted_pdf(docs_dir / "locked.pdf")

    result = runner.invoke(
        app, ["reindex", "--extract-sidecars"], env={"VAULT_PATH": str(vault)}
    )

    assert result.exit_code == 0
    assert "locked.pdf" in result.output


def test_reindex_json_warnings_field_populated_on_extraction_failure(
    tmp_path: Path,
) -> None:
    vault = _minimal_vault(tmp_path / "vault")
    docs_dir = vault / "tiny-corp" / "v1" / "documents"
    docs_dir.mkdir(parents=True, exist_ok=True)
    write_malformed_pdf(docs_dir / "broken.pdf")

    result = runner.invoke(
        app,
        ["reindex", "--extract-sidecars", "--json"],
        env={"VAULT_PATH": str(vault)},
    )

    assert result.exit_code == 0
    payload = json.loads(result.output)
    assert set(payload) == {
        "added",
        "changed",
        "deleted",
        "unchanged",
        "skipped",
        "elapsed",
        "warnings",
    }
    assert payload["warnings"]
    # Each warning serializes as its str(VaultWarning) repr, not a
    # structured {kind, message, paths} object - dataclasses.asdict
    # doesn't know how to recurse into a pydantic BaseModel nested in a
    # dataclass field, so json.dumps's `default=` fallback stringifies
    # it whole. Pre-existing behavior, unchanged by this change (which
    # only touches the plain-text branch) - asserting the real shape
    # here rather than the structured one originally assumed.
    assert any("broken.pdf" in w for w in payload["warnings"])


# --- Section 14: cross-cutting write-command tests --------------------------


@pytest.mark.parametrize(
    "args",
    [
        ["note", "does-not-exist", "text"],
        ["status", "set", "does-not-exist", "applied"],
        [
            "add",
            "does-not-exist",
            "--kind",
            "email",
            "--title",
            "T",
            "--date",
            "2026-01-01",
            "--stdin",
        ],
        [
            "new",
            "--company",
            "Acme",
            "--role",
            "Eng",
            "--url",
            "not-a-url",
            "--found-date",
            "2026-01-01",
        ],
    ],
)
def test_write_command_typed_error_exits_nonzero_and_creates_no_file(
    tmp_path: Path, args: list[str]
) -> None:
    vault = _minimal_vault(tmp_path / "vault")
    before = sorted(str(p.relative_to(vault)) for p in vault.rglob("*") if p.is_file())

    result = runner.invoke(app, args, input="body", env={"VAULT_PATH": str(vault)})

    assert result.exit_code != 0
    after = sorted(str(p.relative_to(vault)) for p in vault.rglob("*") if p.is_file())
    assert after == before


@pytest.mark.parametrize(
    "args",
    [
        ["note", "does-not-exist", "text", "--json"],
        ["status", "set", "does-not-exist", "applied", "--json"],
        [
            "add",
            "does-not-exist",
            "--kind",
            "email",
            "--title",
            "T",
            "--date",
            "2026-01-01",
            "--stdin",
            "--json",
        ],
    ],
)
def test_write_command_json_error_case_emits_no_stdout_json(
    tmp_path: Path, args: list[str]
) -> None:
    vault = _minimal_vault(tmp_path / "vault")

    result = runner.invoke(app, args, input="body", env={"VAULT_PATH": str(vault)})

    assert result.exit_code != 0
    # The error path (_fail) never reaches _print_json - matches cli-read's
    # existing convention (Error: ... on stderr, nothing structured on stdout).
    assert result.stdout.strip() == ""


# --- Section 15 (edit-vacancy-fields): edit command -------------------------


def _edited_vault(vault: Path, **overrides: object) -> Path:
    """`_minimal_vault` with v1 already applied, so `applied_date` and
    the nullable fields an edit test needs are present."""
    _init_vault(vault)
    _write_company(vault, "tiny-corp", "Tiny Corp")
    fields: dict[str, object] = {
        "status": Status.APPLIED,
        "applied_date": date(2026, 1, 3),
    }
    fields.update(overrides)
    _write_vacancy(vault, "tiny-corp", "v1", _simple_vacancy("v1", **fields))
    return vault


def test_edit_sets_a_single_field_and_exits_zero(tmp_path: Path) -> None:
    vault = _edited_vault(tmp_path / "vault")

    result = runner.invoke(
        app,
        ["edit", "v1", "--recruiter", "Anna K."],
        env={"VAULT_PATH": str(vault)},
    )

    assert result.exit_code == 0
    assert read_vault(vault).vacancies["v1"].recruiter == "Anna K."


def test_edit_sets_several_fields_in_one_invocation(tmp_path: Path) -> None:
    vault = _edited_vault(tmp_path / "vault")

    result = runner.invoke(
        app,
        [
            "edit",
            "v1",
            "--source-url",
            "https://new.example/careers/1",
            "--recruiter",
            "Anna K.",
        ],
        env={"VAULT_PATH": str(vault)},
    )

    assert result.exit_code == 0
    updated = read_vault(vault).vacancies["v1"]
    assert updated.source_url == "https://new.example/careers/1"
    assert updated.recruiter == "Anna K."


def test_edit_help_exposes_no_status_company_or_id_option() -> None:
    result = runner.invoke(app, ["edit", "--help"], env=_ENV_WIDE)

    assert result.exit_code == 0
    output = plain(result.output)
    assert "--status" not in output
    assert "--company" not in output
    assert "--id" not in output
    for option in ("--source-url", "--role", "--tags", "--clear"):
        assert option in output


def test_edit_clear_removes_a_nullable_field(tmp_path: Path) -> None:
    vault = _edited_vault(tmp_path / "vault", recruiter="Anna K.")

    result = runner.invoke(
        app, ["edit", "v1", "--clear", "recruiter"], env={"VAULT_PATH": str(vault)}
    )

    assert result.exit_code == 0
    metadata, _ = frontmatter.parse(
        (vault / "tiny-corp" / "v1" / "vacancy.md").read_text(encoding="utf-8")
    )
    assert "recruiter" not in metadata


def test_edit_clear_repeats_for_several_fields(tmp_path: Path) -> None:
    vault = _edited_vault(tmp_path / "vault", recruiter="Anna K.", salary_note="120k")

    result = runner.invoke(
        app,
        ["edit", "v1", "--clear", "recruiter", "--clear", "salary-note"],
        env={"VAULT_PATH": str(vault)},
    )

    assert result.exit_code == 0
    updated = read_vault(vault).vacancies["v1"]
    assert updated.recruiter is None
    assert updated.salary_note is None


@pytest.mark.parametrize(
    ("args", "expected_in_output"),
    [
        (["--clear", "status"], "status"),
        (["--clear", "role"], "role"),
        (["--recruiter", "Anna K.", "--clear", "recruiter"], "recruiter"),
    ],
)
def test_edit_rejects_bad_clear_requests(
    tmp_path: Path, args: list[str], expected_in_output: str
) -> None:
    vault = _edited_vault(tmp_path / "vault", recruiter="Bob")
    vacancy_path = vault / "tiny-corp" / "v1" / "vacancy.md"
    before = vacancy_path.read_bytes()

    result = runner.invoke(
        app, ["edit", "v1", *args], env={**_ENV_WIDE, "VAULT_PATH": str(vault)}
    )

    assert result.exit_code != 0
    assert expected_in_output in result.output
    assert vacancy_path.read_bytes() == before


def test_edit_malformed_date_option_exits_nonzero(tmp_path: Path) -> None:
    vault = _edited_vault(tmp_path / "vault")
    vacancy_path = vault / "tiny-corp" / "v1" / "vacancy.md"
    before = vacancy_path.read_bytes()

    result = runner.invoke(
        app,
        ["edit", "v1", "--found-date", "11-08-2026"],
        env={**_ENV_WIDE, "VAULT_PATH": str(vault)},
    )

    assert result.exit_code != 0
    assert "--found-date" in plain(result.output)
    assert vacancy_path.read_bytes() == before


def test_edit_invalid_source_url_exits_nonzero(tmp_path: Path) -> None:
    vault = _edited_vault(tmp_path / "vault")
    vacancy_path = vault / "tiny-corp" / "v1" / "vacancy.md"
    before = vacancy_path.read_bytes()

    result = runner.invoke(
        app,
        ["edit", "v1", "--source-url", "ftp://example.com/x"],
        env={"VAULT_PATH": str(vault)},
    )

    assert result.exit_code != 0
    assert vacancy_path.read_bytes() == before


def test_edit_ambiguous_vacancy_query_writes_nothing(tmp_path: Path) -> None:
    vault = tmp_path / "vault"
    _init_vault(vault)
    _write_company(vault, "widget-us", "Widget Inc")
    _write_company(vault, "widget-eu", "Widget Inc")

    result = runner.invoke(
        app,
        ["edit", "widget inc", "--recruiter", "Anna K."],
        env={**_ENV_WIDE, "VAULT_PATH": str(vault)},
    )

    assert result.exit_code != 0
    assert "widget-us" in result.output
    assert "widget-eu" in result.output


def test_edit_tags_replaces_the_list(tmp_path: Path) -> None:
    vault = _edited_vault(tmp_path / "vault", tags=["remote", "python"])

    result = runner.invoke(
        app, ["edit", "v1", "--tags", "onsite"], env={"VAULT_PATH": str(vault)}
    )

    assert result.exit_code == 0
    assert read_vault(vault).vacancies["v1"].tags == ["onsite"]


def test_edit_empty_tags_value_empties_the_list(tmp_path: Path) -> None:
    vault = _edited_vault(tmp_path / "vault", tags=["remote"])

    result = runner.invoke(
        app, ["edit", "v1", "--tags", ""], env={"VAULT_PATH": str(vault)}
    )

    assert result.exit_code == 0
    assert read_vault(vault).vacancies["v1"].tags == []


def test_edit_json_reports_the_changed_fields(tmp_path: Path) -> None:
    vault = _edited_vault(tmp_path / "vault")

    result = runner.invoke(
        app,
        ["edit", "v1", "--recruiter", "Anna K.", "--json"],
        env={"VAULT_PATH": str(vault)},
    )

    assert result.exit_code == 0
    payload = json.loads(result.output)
    assert payload["outcome"] == "changed"
    assert payload["vacancy_id"] == "v1"
    assert payload["changed_fields"] == ["recruiter"]


def test_edit_json_reports_a_no_op(tmp_path: Path) -> None:
    vault = _edited_vault(tmp_path / "vault")

    result = runner.invoke(
        app, ["edit", "v1", "--json"], env={"VAULT_PATH": str(vault)}
    )

    assert result.exit_code == 0
    payload = json.loads(result.output)
    assert payload["outcome"] == "unchanged"
    assert payload["changed_fields"] == []


def test_edit_plain_output_names_each_changed_field(tmp_path: Path) -> None:
    vault = _edited_vault(tmp_path / "vault", recruiter="Bob")

    result = runner.invoke(
        app,
        ["edit", "v1", "--recruiter", "Anna K."],
        env={**_ENV_WIDE, "VAULT_PATH": str(vault)},
    )

    assert result.exit_code == 0
    assert "v1" in result.output
    assert "recruiter" in result.output
    assert "Bob" in result.output
    assert "Anna K." in result.output


def test_edit_plain_output_reports_a_no_op_as_unchanged(tmp_path: Path) -> None:
    vault = _edited_vault(tmp_path / "vault")

    result = runner.invoke(
        app, ["edit", "v1"], env={**_ENV_WIDE, "VAULT_PATH": str(vault)}
    )

    assert result.exit_code == 0
    assert "unchanged" in result.output


def test_edit_unknown_vacancy_exits_nonzero(tmp_path: Path) -> None:
    vault = _edited_vault(tmp_path / "vault")

    result = runner.invoke(
        app,
        ["edit", "does-not-exist", "--recruiter", "Anna K."],
        env={**_ENV_WIDE, "VAULT_PATH": str(vault)},
    )

    assert result.exit_code != 0


# --- Section 16 (resolve-write-target-vacancy): company-name arguments ------


def _one_vacancy_company_vault(vault: Path) -> Path:
    """A company with exactly one vacancy - the case a write command's
    vacancy argument may name by company instead of by id."""
    _init_vault(vault)
    _write_company(vault, "tiny-corp", "Tiny Corp")
    _write_vacancy(
        vault,
        "tiny-corp",
        "v1",
        _simple_vacancy("v1", status=Status.APPLIED, applied_date=date(2026, 1, 3)),
    )
    return vault


def _two_vacancy_company_vault(vault: Path) -> Path:
    _one_vacancy_company_vault(vault)
    _write_vacancy(
        vault,
        "tiny-corp",
        "v2",
        _simple_vacancy("v2", status=Status.APPLIED, applied_date=date(2026, 1, 4)),
    )
    return vault


def test_note_accepts_a_one_vacancy_company_by_name(tmp_path: Path) -> None:
    vault = _one_vacancy_company_vault(tmp_path / "vault")

    result = runner.invoke(
        app,
        ["note", "Tiny Corp", "Called the recruiter."],
        env={**_ENV_WIDE, "VAULT_PATH": str(vault)},
    )

    assert result.exit_code == 0
    assert list((vault / "tiny-corp" / "v1" / "documents").glob("*.md"))


def test_status_set_accepts_a_one_vacancy_company_by_fuzzy_name(
    tmp_path: Path,
) -> None:
    vault = _one_vacancy_company_vault(tmp_path / "vault")

    result = runner.invoke(
        app,
        ["status", "set", "Tiny", "screening"],
        env={**_ENV_WIDE, "VAULT_PATH": str(vault)},
    )

    assert result.exit_code == 0
    assert read_vault(vault).vacancies["v1"].status == Status.SCREENING


def test_edit_accepts_a_one_vacancy_company_by_name(tmp_path: Path) -> None:
    vault = _one_vacancy_company_vault(tmp_path / "vault")

    result = runner.invoke(
        app,
        ["edit", "Tiny Corp", "--recruiter", "Anna K."],
        env={**_ENV_WIDE, "VAULT_PATH": str(vault)},
    )

    assert result.exit_code == 0
    assert read_vault(vault).vacancies["v1"].recruiter == "Anna K."


def test_add_accepts_a_one_vacancy_company_by_name(tmp_path: Path) -> None:
    vault = _one_vacancy_company_vault(tmp_path / "vault")

    result = runner.invoke(
        app,
        [
            "add",
            "Tiny Corp",
            "--kind",
            "email",
            "--title",
            "Recruiter reply",
            "--date",
            "2026-01-16",
            "--stdin",
        ],
        env={**_ENV_WIDE, "VAULT_PATH": str(vault)},
        input="Email body.\n",
    )

    assert result.exit_code == 0
    assert list((vault / "tiny-corp" / "v1" / "documents").glob("*.md"))


@pytest.mark.parametrize(
    "args",
    [
        ["note", "Tiny Corp", "A note."],
        ["status", "set", "Tiny Corp", "screening"],
        ["edit", "Tiny Corp", "--recruiter", "Anna K."],
    ],
)
def test_write_commands_reject_a_company_with_several_vacancies(
    tmp_path: Path, args: list[str]
) -> None:
    vault = _two_vacancy_company_vault(tmp_path / "vault")
    before = {p: p.read_bytes() for p in vault.rglob("*") if p.is_file()}

    result = runner.invoke(app, args, env={**_ENV_WIDE, "VAULT_PATH": str(vault)})

    assert result.exit_code != 0
    assert "v1" in result.output
    assert "v2" in result.output
    assert {p: p.read_bytes() for p in vault.rglob("*") if p.is_file()} == before


def test_write_commands_reject_a_company_with_no_vacancies(tmp_path: Path) -> None:
    vault = tmp_path / "vault"
    _init_vault(vault)
    _write_company(vault, "tiny-corp", "Tiny Corp")
    before = {p: p.read_bytes() for p in vault.rglob("*") if p.is_file()}

    result = runner.invoke(
        app,
        ["note", "Tiny Corp", "A note."],
        env={**_ENV_WIDE, "VAULT_PATH": str(vault)},
    )

    assert result.exit_code != 0
    assert {p: p.read_bytes() for p in vault.rglob("*") if p.is_file()} == before


def test_write_commands_still_reject_an_ambiguous_company_query(
    tmp_path: Path,
) -> None:
    vault = tmp_path / "vault"
    _init_vault(vault)
    _write_company(vault, "widget-us", "Widget Inc")
    _write_company(vault, "widget-eu", "Widget Inc")
    _write_vacancy(vault, "widget-us", "v1", _simple_vacancy("v1", slug="widget-us"))
    _write_vacancy(vault, "widget-eu", "v2", _simple_vacancy("v2", slug="widget-eu"))

    result = runner.invoke(
        app,
        ["note", "widget inc", "A note."],
        env={**_ENV_WIDE, "VAULT_PATH": str(vault)},
    )

    assert result.exit_code != 0
    assert "widget-us" in result.output
    assert "widget-eu" in result.output
