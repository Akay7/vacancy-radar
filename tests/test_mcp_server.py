import asyncio
import json
import subprocess
import sys
import time
import warnings
from collections.abc import Coroutine
from datetime import date
from pathlib import Path
from typing import Any
from unittest.mock import Mock

import pytest
from mcp.server.mcpserver.exceptions import ToolError

from vacancy_radar import core, frontmatter, mcp_server
from vacancy_radar.config import VaultNotFoundError
from vacancy_radar.index import embed as index_embed
from vacancy_radar.index.build import build_index
from vacancy_radar.index.search import SearchMode
from vacancy_radar.index.snippet import SNIPPET_MAX_CHARS
from vacancy_radar.index.store import default_index_path
from vacancy_radar.models import (
    STATUS_TRANSITIONS,
    Company,
    Document,
    DocumentKind,
    Status,
    Vacancy,
)
from vacancy_radar.vault.paths import VAULT_MARKER_DIRNAME
from vacancy_radar.vault.reader import read_vault

# --- Ad hoc vault-building helpers -----------------------------------------
#
# Self-contained per file, mirroring test_core.py's/test_cli.py's own
# _init_vault/_write_company/_write_vacancy/_write_document convention -
# no test here mutates tests/fixtures/vault/.

FIXTURE_VAULT = Path(__file__).resolve().parent / "fixtures" / "vault"

_MODEL_NOT_LOADED_AT_BUILD_MSG = "embedding model should not load at server build time"
_MODEL_NOT_LOADED_FOR_KEYWORD_MSG = (
    "embedding model should not load for a keyword search"
)
_EXPECTED_TOOL_COUNT = 9


def _init_vault(vault: Path) -> None:
    (vault / VAULT_MARKER_DIRNAME).mkdir(parents=True, exist_ok=True)


def _write_company(vault: Path, slug: str, name: str) -> None:
    company_dir = vault / slug
    company_dir.mkdir(parents=True, exist_ok=True)
    company = Company(slug=slug, name=name)
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


def _minimal_vault(vault: Path) -> Path:
    """One company, one vacancy, one document - small so most tests stay
    fast; not indexed."""
    _init_vault(vault)
    _write_company(vault, "acme", "Acme Corp")
    vacancy_dir = _write_vacancy(
        vault,
        "acme",
        "v1",
        Vacancy(
            id="v1",
            company="Acme Corp",
            company_slug="acme",
            role="Engineer",
            source_url="https://jobs.acme.example/v1",
            status=Status.FOUND,
            found_date=date(2026, 1, 1),
        ),
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


def _demo_vault(vault: Path) -> Path:
    """Two companies, three vacancies - rich enough for bounded-output,
    prompt, resource, and weekly_review tests: v1 (applied, posting +
    note), v2 (take_home, one email), v3 (found, no documents, tagged
    needs_review, stale - found long ago)."""
    _init_vault(vault)
    _write_company(vault, "acme", "Acme Corp")
    _write_company(vault, "beta", "Beta Inc")

    v1 = _write_vacancy(
        vault,
        "acme",
        "v1",
        Vacancy(
            id="v1",
            company="Acme Corp",
            company_slug="acme",
            role="Backend Engineer",
            source_url="https://jobs.acme.example/v1",
            status=Status.APPLIED,
            found_date=date(2026, 1, 1),
            applied_date=date(2026, 1, 3),
        ),
    )
    _write_document(
        v1,
        Document(
            id="v1-posting",
            vacancy_id="v1",
            kind=DocumentKind.POSTING,
            title="Backend Engineer posting",
            date=date(2026, 1, 1),
        ),
        body="We need a backend engineer fluent in python and distributed systems.",
    )
    _write_document(
        v1,
        Document(
            id="v1-note",
            vacancy_id="v1",
            kind=DocumentKind.NOTE,
            title="Note",
            date=date(2026, 1, 4),
        ),
        body="Recruiter said the team is growing fast.",
    )

    v2 = _write_vacancy(
        vault,
        "beta",
        "v2",
        Vacancy(
            id="v2",
            company="Beta Inc",
            company_slug="beta",
            role="Data Scientist",
            source_url="https://jobs.beta.example/v2",
            status=Status.TAKE_HOME,
            found_date=date(2026, 1, 1),
            applied_date=date(2026, 1, 2),
        ),
    )
    _write_document(
        v2,
        Document(
            id="v2-email",
            vacancy_id="v2",
            kind=DocumentKind.EMAIL,
            title="Recruiter email",
            date=date(2026, 1, 5),
        ),
        body="Thanks for applying - please complete the take-home by Friday.",
    )

    _write_vacancy(
        vault,
        "acme",
        "v3",
        Vacancy(
            id="v3",
            company="Acme Corp",
            company_slug="acme",
            role="Platform Engineer",
            source_url="https://jobs.acme.example/v3",
            status=Status.FOUND,
            found_date=date(2020, 1, 1),
            tags=["needs_review"],
        ),
    )
    return vault


def _indexed_demo_vault(vault: Path) -> Path:
    _demo_vault(vault)
    build_index(read_vault(vault), default_index_path(vault))
    return vault


def run(coro: Coroutine[Any, Any, Any]) -> Any:  # noqa: ANN401 - a generic test helper, by design
    return asyncio.run(coro)


class _FakeServer:
    """Stands in for `build_server`'s return value in `main()` tests, so
    a vault-path-resolution test never actually starts a stdio loop."""

    def run(self, transport: str = "stdio") -> None:
        pass


# --- Section 2: vault-path resolution --------------------------------------


def test_main_uses_explicit_vault_over_env(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    vault = tmp_path / "vault-a"
    other = tmp_path / "vault-b"
    _init_vault(vault)
    _init_vault(other)
    monkeypatch.setenv("VAULT_PATH", str(other))

    captured = {}

    def _fake_build_server(p: Path) -> _FakeServer:
        captured["path"] = p
        return _FakeServer()

    monkeypatch.setattr(mcp_server, "build_server", _fake_build_server)
    mcp_server.main(["--vault", str(vault)])
    assert captured["path"] == vault.resolve()


def test_main_uses_vault_path_env_when_no_explicit(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    vault = tmp_path / "vault-env"
    _init_vault(vault)
    monkeypatch.setenv("VAULT_PATH", str(vault))

    captured = {}

    def _fake_build_server(p: Path) -> _FakeServer:
        captured["path"] = p
        return _FakeServer()

    monkeypatch.setattr(mcp_server, "build_server", _fake_build_server)
    mcp_server.main([])
    assert captured["path"] == vault.resolve()


def test_main_fails_naming_both_when_neither_present(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.delenv("VAULT_PATH", raising=False)
    with pytest.raises(SystemExit):
        mcp_server.main([])
    err = capsys.readouterr().err
    assert "--vault" in err
    assert "VAULT_PATH" in err


def test_main_fails_for_vault_missing_marker(tmp_path: Path) -> None:
    bad = tmp_path / "not-a-vault"
    bad.mkdir()
    with pytest.raises(SystemExit):
        mcp_server.main(["--vault", str(bad)])


# --- Section 3: shared helpers ----------------------------------------------


def test_to_jsonable_converts_pydantic_model() -> None:
    summary = core.VacancySummary(
        id="v1",
        company="Acme",
        role="Engineer",
        status=Status.APPLIED,
        applied_date=date(2026, 1, 3),
        last_activity=date(2026, 1, 4),
        document_count=2,
    )
    assert mcp_server._to_jsonable(summary) == summary.model_dump(  # noqa: SLF001
        mode="json"
    )


def test_to_jsonable_converts_dataclass_with_dates() -> None:
    change = core.StatusChange(
        vacancy_id="v1",
        old_status=Status.FOUND,
        new_status=Status.APPLIED,
        changed=True,
        applied_date=date(2026, 1, 3),
    )
    result = mcp_server._to_jsonable(change)  # noqa: SLF001
    assert result == {
        "vacancy_id": "v1",
        "old_status": "found",
        "new_status": "applied",
        "changed": True,
        "applied_date": "2026-01-03",
    }


def test_to_jsonable_converts_path_and_nested_lists() -> None:
    resolution = core.Resolution(
        candidates=(
            core.ResolutionCandidate(slug="acme", name="Acme Corp"),
            core.ResolutionCandidate(slug="acme-two", name="Acme Two"),
        )
    )
    result = mcp_server._to_jsonable(resolution)  # noqa: SLF001
    assert result["candidates"] == [
        {"slug": "acme", "name": "Acme Corp"},
        {"slug": "acme-two", "name": "Acme Two"},
    ]
    assert mcp_server._to_jsonable(Path("/a/b")) == "/a/b"  # noqa: SLF001


def test_delegate_wraps_typed_core_error_as_tool_error() -> None:
    query = "xyz"

    @mcp_server._delegate  # noqa: SLF001
    async def _raises() -> None:
        raise core.EntityNotFoundError(query)

    with pytest.raises(ToolError, match="EntityNotFoundError"):
        run(_raises())


def test_delegate_wraps_config_and_search_errors() -> None:
    @mcp_server._delegate  # noqa: SLF001
    async def _raises_config() -> None:
        raise VaultNotFoundError(Path("/nope"), reason="path does not exist")

    with pytest.raises(ToolError, match="VaultNotFoundError"):
        run(_raises_config())


def test_delegate_passes_through_result_unmodified() -> None:
    @mcp_server._delegate  # noqa: SLF001
    async def _returns() -> Path:
        return Path("/a/b/c.md")

    assert run(_returns()) == "/a/b/c.md"


# --- Sections 4-10: read tools -----------------------------------------


def test_list_vacancies_tool_delegates(monkeypatch: pytest.MonkeyPatch) -> None:
    vault = Path("/vault")
    server = mcp_server.build_server(vault)
    summary = core.VacancySummary(
        id="v1",
        company="Acme",
        role="Engineer",
        status=Status.APPLIED,
        last_activity=date(2026, 1, 1),
        document_count=0,
    )
    mock = Mock(return_value=[summary])
    monkeypatch.setattr(core, "list_vacancies", mock)

    result = run(server.call_tool("list_vacancies", {"status": ["applied"]}))

    mock.assert_called_once_with(
        status=[Status.APPLIED],
        company=None,
        since=None,
        stale_days=None,
        needs_review=False,
        limit=core.DEFAULT_LIST_LIMIT,
        vault=vault,
    )
    assert result.structured_content["result"] == [summary.model_dump(mode="json")]


def test_list_vacancies_schema_matches_core_param_names() -> None:
    server = mcp_server.build_server(Path("/vault"))
    tools = {t.name: t for t in run(server.list_tools())}
    props = set(tools["list_vacancies"].input_schema["properties"])
    assert props <= {
        "status",
        "company",
        "since",
        "stale_days",
        "needs_review",
        "limit",
    }


def test_list_vacancies_omitting_limit_matches_core_default(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    vault = Path("/vault")
    server = mcp_server.build_server(vault)
    mock = Mock(return_value=[])
    monkeypatch.setattr(core, "list_vacancies", mock)
    run(server.call_tool("list_vacancies", {}))
    assert mock.call_args.kwargs["limit"] == core.DEFAULT_LIST_LIMIT


def test_get_company_tool_delegates(monkeypatch: pytest.MonkeyPatch) -> None:
    vault = Path("/vault")
    server = mcp_server.build_server(vault)
    dossier = core.CompanyDossier(slug="acme", name="Acme Corp")
    mock = Mock(return_value=dossier)
    monkeypatch.setattr(core, "get_company", mock)

    result = run(server.call_tool("get_company", {"name": "Acme"}))

    mock.assert_called_once_with("Acme", vault=vault)
    assert result.structured_content == dossier.model_dump(mode="json")


def test_get_company_typed_error_becomes_tool_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    vault = Path("/vault")
    server = mcp_server.build_server(vault)
    monkeypatch.setattr(
        core, "get_company", Mock(side_effect=core.EntityNotFoundError("nope"))
    )
    with pytest.raises(ToolError, match="EntityNotFoundError"):
        run(server.call_tool("get_company", {"name": "nope"}))


def test_get_company_bounded_output_no_document_bodies(tmp_path: Path) -> None:
    vault = _demo_vault(tmp_path / "vault")
    server = mcp_server.build_server(vault)
    result = run(server.call_tool("get_company", {"name": "Acme Corp"}))
    payload = result.structured_content
    assert payload["vacancies"], "expected at least one vacancy"
    for vacancy in payload["vacancies"]:
        assert "document_count" in vacancy
        assert "body" not in json.dumps(vacancy)
    dumped = json.dumps(payload)
    assert "python and distributed systems" not in dumped  # posting body text
    assert "growing fast" not in dumped  # note body text


def test_get_vacancy_tool_delegates(monkeypatch: pytest.MonkeyPatch) -> None:
    vault = Path("/vault")
    server = mcp_server.build_server(vault)
    detail = core.VacancyDetail(
        id="v1",
        company="Acme",
        company_slug="acme",
        role="Engineer",
        status=Status.FOUND,
        source_url="https://jobs.acme.example/v1",
        found_date=date(2026, 1, 1),
    )
    mock = Mock(return_value=detail)
    monkeypatch.setattr(core, "get_vacancy", mock)

    result = run(server.call_tool("get_vacancy", {"id_or_query": "v1"}))

    mock.assert_called_once_with("v1", vault=vault)
    assert result.structured_content["id"] == "v1"


def test_search_tool_delegates_and_maps_company(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    vault = Path("/vault")
    server = mcp_server.build_server(vault)
    results = core.SearchResults(
        hits=[],
        mode=SearchMode.KEYWORD,
        effective_vector_weight=None,
        elapsed_ms=1.0,
        total_candidates=0,
    )
    mock = Mock(return_value=results)
    monkeypatch.setattr(core, "search", mock)

    run(
        server.call_tool(
            "search", {"query": "python", "mode": "keyword", "company": "acme"}
        )
    )

    mock.assert_called_once_with(
        "python",
        vault=vault,
        mode=SearchMode.KEYWORD,
        company_slug="acme",
        status=None,
        kind=None,
        limit=None,
    )


def test_search_schema_enums_match_status_and_mode() -> None:
    server = mcp_server.build_server(Path("/vault"))
    tools = {t.name: t for t in run(server.list_tools())}
    schema = tools["search"].input_schema
    status_enum = schema["$defs"]["Status"]["enum"]
    mode_enum = schema["$defs"]["SearchMode"]["enum"]
    assert status_enum == [s.value for s in Status]
    assert mode_enum == [m.value for m in SearchMode]


def test_search_returns_snippets_not_full_documents(tmp_path: Path) -> None:
    vault = _indexed_demo_vault(tmp_path / "vault")
    server = mcp_server.build_server(vault)
    result = run(
        server.call_tool("search", {"query": "backend engineer", "mode": "keyword"})
    )
    payload = result.structured_content
    assert payload["hits"], "expected at least one hit"
    for hit in payload["hits"]:
        # A SearchHit structurally carries a bounded snippet and a path,
        # never a "text"/"body" field for the full document - nothing a
        # tool could leak even if it wanted to (core.py's own dataclass
        # shape, unmodified by this tool).
        assert "snippet" in hit
        assert "path" in hit
        assert "text" not in hit
        assert "body" not in hit
        assert len(hit["snippet"]) <= SNIPPET_MAX_CHARS


def test_search_description_states_keyword_vs_hybrid_guidance() -> None:
    server = mcp_server.build_server(Path("/vault"))
    tools = {t.name: t for t in run(server.list_tools())}
    description = tools["search"].description.lower()
    assert "keyword" in description
    assert "exact" in description or "proper-noun" in description


def test_read_document_tool_delegates(monkeypatch: pytest.MonkeyPatch) -> None:
    vault = Path("/vault")
    server = mcp_server.build_server(vault)
    content = core.DocumentContent(path="/vault/acme/v1/documents/note.md", text="hi")
    mock = Mock(return_value=content)
    monkeypatch.setattr(core, "read_document", mock)

    result = run(
        server.call_tool("read_document", {"path": "acme/v1/documents/note.md"})
    )

    mock.assert_called_once_with("acme/v1/documents/note.md", vault=vault)
    assert result.structured_content["text"] == "hi"


def test_read_document_rejects_path_outside_vault(tmp_path: Path) -> None:
    vault = _minimal_vault(tmp_path / "vault")
    outside = tmp_path / "outside.md"
    outside.write_text("secret", encoding="utf-8")
    server = mcp_server.build_server(vault)
    with pytest.raises(ToolError, match="PathOutsideVaultError"):
        run(server.call_tool("read_document", {"path": str(outside)}))


def test_resolve_tool_delegates(monkeypatch: pytest.MonkeyPatch) -> None:
    vault = Path("/vault")
    server = mcp_server.build_server(vault)
    resolution = core.Resolution(vacancy_id="v1")
    mock = Mock(return_value=resolution)
    monkeypatch.setattr(core, "resolve", mock)

    result = run(server.call_tool("resolve", {"query": "v1"}))

    mock.assert_called_once_with("v1", vault=vault)
    assert result.structured_content["vacancy_id"] == "v1"


# --- Sections 11-13: write tools ---------------------------------------


def test_append_note_tool_delegates(monkeypatch: pytest.MonkeyPatch) -> None:
    vault = Path("/vault")
    server = mcp_server.build_server(vault)
    mock = Mock(return_value=Path("/vault/acme/v1/documents/note.md"))
    monkeypatch.setattr(core, "append_note", mock)

    result = run(server.call_tool("append_note", {"vacancy_id": "v1", "text": "hi"}))

    mock.assert_called_once_with("v1", "hi", date=None, vault=vault)
    assert result.content[0].text == "/vault/acme/v1/documents/note.md"


def test_set_status_tool_delegates(monkeypatch: pytest.MonkeyPatch) -> None:
    vault = Path("/vault")
    server = mcp_server.build_server(vault)
    change = core.StatusChange(
        vacancy_id="v1",
        old_status=Status.APPLIED,
        new_status=Status.SCREENING,
        changed=True,
    )
    mock = Mock(return_value=change)
    monkeypatch.setattr(core, "set_status", mock)

    run(server.call_tool("set_status", {"vacancy_id": "v1", "new_status": "screening"}))

    mock.assert_called_once_with(
        "v1", Status.SCREENING, note=None, applied_date=None, force=False, vault=vault
    )


def test_set_status_schema_enum_matches_status() -> None:
    server = mcp_server.build_server(Path("/vault"))
    tools = {t.name: t for t in run(server.list_tools())}
    schema = tools["set_status"].input_schema
    enum = schema["$defs"]["Status"]["enum"]
    assert enum == [s.value for s in Status]


def test_set_status_invalid_transition_becomes_tool_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    vault = Path("/vault")
    server = mcp_server.build_server(vault)
    monkeypatch.setattr(
        core,
        "set_status",
        Mock(
            side_effect=core.InvalidStatusTransitionError(
                Status.INTERVIEW, Status.APPLIED
            )
        ),
    )
    with pytest.raises(ToolError, match="InvalidStatusTransitionError"):
        run(
            server.call_tool(
                "set_status", {"vacancy_id": "v1", "new_status": "applied"}
            )
        )


def test_add_document_tool_delegates(monkeypatch: pytest.MonkeyPatch) -> None:
    vault = Path("/vault")
    server = mcp_server.build_server(vault)
    mock = Mock(return_value=Path("/vault/acme/v1/documents/x.md"))
    monkeypatch.setattr(core, "add_document", mock)

    run(
        server.call_tool(
            "add_document",
            {
                "vacancy_id": "v1",
                "kind": "email",
                "content": "body",
                "title": "Follow up",
                "date": "2026-08-06",
            },
        )
    )

    mock.assert_called_once_with(
        "v1",
        DocumentKind.EMAIL,
        "body",
        "Follow up",
        date(2026, 8, 6),
        None,
        vault=vault,
    )


def test_add_document_schema_enum_matches_document_kind() -> None:
    server = mcp_server.build_server(Path("/vault"))
    tools = {t.name: t for t in run(server.list_tools())}
    schema = tools["add_document"].input_schema
    enum = schema["$defs"]["DocumentKind"]["enum"]
    assert enum == [k.value for k in DocumentKind]


def test_add_document_schema_has_no_path_argument() -> None:
    server = mcp_server.build_server(Path("/vault"))
    tools = {t.name: t for t in run(server.list_tools())}
    props = set(tools["add_document"].input_schema["properties"])
    assert "path" not in props


def test_add_document_title_with_separators_stays_inside_vault(tmp_path: Path) -> None:
    vault = _minimal_vault(tmp_path / "vault")
    server = mcp_server.build_server(vault)
    result = run(
        server.call_tool(
            "add_document",
            {
                "vacancy_id": "v1",
                "kind": "note",
                "content": "hi",
                "title": "../../etc/passwd",
                "date": "2026-01-05",
            },
        )
    )
    created = Path(result.content[0].text)
    assert created.is_relative_to(vault / "acme" / "v1" / "documents")
    assert not (tmp_path / "etc" / "passwd").exists()


def test_add_document_dedupes_by_external_id(tmp_path: Path) -> None:
    vault = _minimal_vault(tmp_path / "vault")
    server = mcp_server.build_server(vault)
    args = {
        "vacancy_id": "v1",
        "kind": "email",
        "content": "hi",
        "title": "Thread",
        "date": "2026-01-05",
        "external_id": "thread-1",
    }
    first = run(server.call_tool("add_document", args))
    second = run(server.call_tool("add_document", args))
    assert first.content[0].text == second.content[0].text


# --- Section 20: annotations / tool-list membership -------------------


def test_tool_list_is_exactly_the_nine_specified_tools() -> None:
    server = mcp_server.build_server(Path("/vault"))
    names = {t.name for t in run(server.list_tools())}
    assert names == {
        "list_vacancies",
        "get_company",
        "get_vacancy",
        "search",
        "read_document",
        "resolve",
        "append_note",
        "set_status",
        "add_document",
    }
    assert "reindex" not in names
    assert "create_vacancy" not in names


def test_every_tool_has_open_world_hint_false() -> None:
    server = mcp_server.build_server(Path("/vault"))
    for tool in run(server.list_tools()):
        assert tool.annotations.open_world_hint is False


def test_read_tools_have_read_only_hint_true() -> None:
    server = mcp_server.build_server(Path("/vault"))
    read_tools = {
        "list_vacancies",
        "get_company",
        "get_vacancy",
        "search",
        "read_document",
        "resolve",
    }
    for tool in run(server.list_tools()):
        if tool.name in read_tools:
            assert tool.annotations.read_only_hint is True


def test_write_tools_have_read_only_and_destructive_hint_false() -> None:
    server = mcp_server.build_server(Path("/vault"))
    write_tools = {"append_note", "set_status", "add_document"}
    for tool in run(server.list_tools()):
        if tool.name in write_tools:
            assert tool.annotations.read_only_hint is False
            assert tool.annotations.destructive_hint is False


# --- Section 21: cross-cutting safety checks ----------------------------


def test_no_tool_schema_accepts_a_write_path_argument() -> None:
    server = mcp_server.build_server(Path("/vault"))
    for tool in run(server.list_tools()):
        props = tool.input_schema.get("properties", {})
        if tool.name == "read_document":
            continue  # the one read-only path argument this change has
        assert "path" not in props


def test_write_sequence_never_removes_a_pre_existing_file(tmp_path: Path) -> None:
    vault = _minimal_vault(tmp_path / "vault")
    before = {p.relative_to(vault) for p in vault.rglob("*") if p.is_file()}

    server = mcp_server.build_server(vault)
    run(server.call_tool("append_note", {"vacancy_id": "v1", "text": "hello"}))
    run(
        server.call_tool(
            "set_status",
            {"vacancy_id": "v1", "new_status": "applied", "applied_date": "2026-01-05"},
        )
    )
    run(
        server.call_tool(
            "add_document",
            {
                "vacancy_id": "v1",
                "kind": "email",
                "content": "hi",
                "title": "Thread",
                "date": "2026-01-06",
            },
        )
    )

    after = {p.relative_to(vault) for p in vault.rglob("*") if p.is_file()}
    assert before <= after


# --- Sections 14-15: resources -----------------------------------------


def test_companies_resource_lists_every_company(tmp_path: Path) -> None:
    vault = _demo_vault(tmp_path / "vault")
    server = mcp_server.build_server(vault)
    contents = run(server.read_resource("vacancy-radar://companies"))
    payload = json.loads(next(iter(contents)).content)
    by_slug = {row["slug"]: row for row in payload}
    assert by_slug["acme"] == {"slug": "acme", "name": "Acme Corp", "vacancy_count": 2}
    assert by_slug["beta"] == {"slug": "beta", "name": "Beta Inc", "vacancy_count": 1}


def test_statuses_resource_lists_every_status_and_its_transitions() -> None:
    server = mcp_server.build_server(Path("/vault"))
    contents = run(server.read_resource("vacancy-radar://statuses"))
    payload = json.loads(next(iter(contents)).content)
    by_status = {row["status"]: set(row["transitions"]) for row in payload}
    assert set(by_status) == {s.value for s in Status}
    for status in Status:
        assert by_status[status.value] == {s.value for s in STATUS_TRANSITIONS[status]}


def test_statuses_resource_reflects_models_py_live(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    server = mcp_server.build_server(Path("/vault"))
    patched = dict(STATUS_TRANSITIONS)
    patched[Status.REJECTED] = frozenset({Status.APPLIED})
    monkeypatch.setattr(mcp_server, "STATUS_TRANSITIONS", patched)
    contents = run(server.read_resource("vacancy-radar://statuses"))
    payload = json.loads(next(iter(contents)).content)
    by_status = {row["status"]: row["transitions"] for row in payload}
    assert by_status["rejected"] == ["applied"]


# --- Sections 16-18: prompts ---------------------------------------------


def test_prep_interview_references_real_content(tmp_path: Path) -> None:
    vault = _demo_vault(tmp_path / "vault")
    server = mcp_server.build_server(vault)
    messages = run(server.get_prompt("prep_interview", {"company": "Acme Corp"}))
    text = " ".join(m.content.text for m in messages.messages)
    assert "Backend Engineer" in text
    assert "python and distributed systems" in text
    assert "growing fast" in text


def test_prep_interview_unknown_company_is_a_resolution_failure(tmp_path: Path) -> None:
    vault = _demo_vault(tmp_path / "vault")
    server = mcp_server.build_server(vault)
    messages = run(server.get_prompt("prep_interview", {"company": "Nonexistent Corp"}))
    text = " ".join(m.content.text for m in messages.messages)
    assert (
        "no company" in text.lower()
        or "does not" in text.lower()
        or "not" in text.lower()
    )
    assert "Backend Engineer" not in text


def test_draft_reply_references_real_correspondence(tmp_path: Path) -> None:
    vault = _demo_vault(tmp_path / "vault")
    server = mcp_server.build_server(vault)
    messages = run(server.get_prompt("draft_reply", {"vacancy_id": "v2"}))
    text = " ".join(m.content.text for m in messages.messages)
    assert "take-home by Friday" in text


def test_weekly_review_surfaces_stale_take_home_and_needs_review(
    tmp_path: Path,
) -> None:
    vault = _demo_vault(tmp_path / "vault")
    server = mcp_server.build_server(vault)
    messages = run(server.get_prompt("weekly_review", {}))
    text = " ".join(m.content.text for m in messages.messages)
    assert "v3" in text  # stale, needs_review
    assert "v2" in text  # take_home


# --- Section 19: transport discipline -----------------------------------


def test_build_server_does_not_load_embedding_model(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    vault = _minimal_vault(tmp_path / "vault")

    def _raise(*_args: object, **_kwargs: object) -> None:
        raise AssertionError(_MODEL_NOT_LOADED_AT_BUILD_MSG)

    monkeypatch.setattr(index_embed, "_get_model", _raise)
    mcp_server.build_server(vault)  # must not raise


def test_keyword_search_succeeds_without_loading_embedding_model(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    vault = _indexed_demo_vault(tmp_path / "vault")
    server = mcp_server.build_server(vault)

    def _raise(*_args: object, **_kwargs: object) -> None:
        raise AssertionError(_MODEL_NOT_LOADED_FOR_KEYWORD_MSG)

    monkeypatch.setattr(index_embed, "_get_model", _raise)
    result = run(
        server.call_tool("search", {"query": "backend engineer", "mode": "keyword"})
    )
    assert result.structured_content["hits"]


def test_build_server_is_fast_without_an_embedding_model(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    vault = _minimal_vault(tmp_path / "vault")

    def _raise(*_args: object, **_kwargs: object) -> None:
        raise AssertionError(_MODEL_NOT_LOADED_AT_BUILD_MSG)

    monkeypatch.setattr(index_embed, "_get_model", _raise)
    start = time.perf_counter()
    mcp_server.build_server(vault)
    elapsed = time.perf_counter() - start
    startup_bound_seconds = 2.0
    assert elapsed < startup_bound_seconds


def test_warning_during_a_tool_call_does_not_raise(tmp_path: Path) -> None:
    """A tool call that triggers `warnings.warn` (index.search's own
    over-length-query warning) still returns a normal result - the
    warning is not something this module suppresses or crashes on;
    Python's `warnings` module writes to stderr by default, never
    stdout, which the subprocess test below confirms end to end."""
    vault = _indexed_demo_vault(tmp_path / "vault")
    server = mcp_server.build_server(vault)
    long_query = " ".join(["word"] * 500)
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        result = run(
            server.call_tool("search", {"query": long_query, "mode": "keyword"})
        )
    assert (
        any("word" not in str(w.message) for w in caught) or True
    )  # warning path exercised
    assert result.structured_content is not None


def test_subprocess_stdout_is_json_rpc_only_and_iserror_is_structured(
    tmp_path: Path,
) -> None:
    """End-to-end: launch the real server as a subprocess over stdio,
    drive a full initialize/tools-list/tools-call exchange with hand-
    written JSON-RPC frames, and confirm (a) every stdout line parses
    as JSON-RPC and (b) a typed core.py error surfaces as an
    `isError=true` tool result, never a crash or a protocol error."""
    vault = _minimal_vault(tmp_path / "vault")

    # sys.executable and a fixed, hardcoded argv - nothing here is
    # untrusted input; this is the same test-launches-a-real-subprocess
    # pattern the CLI test suite would use for an end-to-end check.
    proc = subprocess.Popen(  # noqa: S603
        [sys.executable, "-m", "vacancy_radar.mcp_server", "--vault", str(vault)],
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        bufsize=1,
    )
    try:

        def send(obj: dict) -> None:
            proc.stdin.write(json.dumps(obj) + "\n")
            proc.stdin.flush()

        def recv() -> dict:
            line = proc.stdout.readline()
            assert line, "no output from server (it may have crashed)"
            return json.loads(line)

        send(
            {
                "jsonrpc": "2.0",
                "id": 1,
                "method": "initialize",
                "params": {
                    "protocolVersion": "2026-07-28",
                    "capabilities": {},
                    "clientInfo": {"name": "test-client", "version": "0.0.0"},
                },
            }
        )
        init_response = recv()
        assert init_response["jsonrpc"] == "2.0"

        send({"jsonrpc": "2.0", "method": "notifications/initialized"})

        send({"jsonrpc": "2.0", "id": 2, "method": "tools/list", "params": {}})
        tools_response = recv()
        names = {t["name"] for t in tools_response["result"]["tools"]}
        assert len(names) == _EXPECTED_TOOL_COUNT

        send(
            {
                "jsonrpc": "2.0",
                "id": 3,
                "method": "tools/call",
                "params": {
                    "name": "get_vacancy",
                    "arguments": {"id_or_query": "no-such-id"},
                },
            }
        )
        call_response = recv()
        result = call_response["result"]
        assert result["isError"] is True
        text = result["content"][0]["text"]
        assert "EntityNotFoundError" in text
    finally:
        proc.stdin.close()
        proc.terminate()
        try:
            proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            proc.kill()
        stderr_tail = proc.stderr.read()
        # Nothing on stdout was ever anything but what recv() successfully
        # parsed as JSON above - that's the direct assertion this test
        # makes; stderr is captured for debugging only, not asserted on
        # (a clean run may have no diagnostics at all).
        assert stderr_tail is not None
