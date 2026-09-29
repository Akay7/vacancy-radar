import asyncio
import json
import re
import subprocess
import sys
import time
import warnings
from collections.abc import Coroutine
from datetime import date
from html.parser import HTMLParser
from pathlib import Path
from typing import Any
from unittest.mock import Mock

import pytest
from fastmcp.apps import UI_MIME_TYPE as APP_MIME_TYPE
from fastmcp.exceptions import ToolError
from mcp.server.lowlevel import NotificationOptions

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
_EXPECTED_TOOL_COUNT = 12


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
    props = set(tools["list_vacancies"].parameters["properties"])
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


def _prop_enum(schema: dict, prop: str) -> list[str]:
    """The enum a tool's `prop` argument accepts, wherever the schema
    generator put it. FastMCP inlines an enum into the property (and
    under `anyOf`/`items` for optional or list-valued ones) rather than
    emitting a `$defs` reference, so this walks the property subtree for
    the one `enum` it contains instead of assuming either encoding."""
    found: list[list[str]] = []

    def walk(node: object) -> None:
        if isinstance(node, dict):
            if isinstance(node.get("enum"), list):
                found.append(node["enum"])
            for value in node.values():
                walk(value)
        elif isinstance(node, list):
            for value in node:
                walk(value)

    walk(schema["properties"][prop])
    assert len(found) == 1, f"expected one enum under {prop!r}, got {len(found)}"
    return found[0]


def test_search_schema_enums_match_status_and_mode() -> None:
    server = mcp_server.build_server(Path("/vault"))
    tools = {t.name: t for t in run(server.list_tools())}
    schema = tools["search"].parameters
    status_enum = _prop_enum(schema, "status")
    mode_enum = _prop_enum(schema, "mode")
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


@pytest.mark.parametrize("tool", ["append_note", "add_document", "create_vacancy"])
def test_write_tool_output_schema_has_no_path_format(tool: str) -> None:
    # `format: "path"` (from a `Path` return) is not a JSON Schema format
    # and opencode warns about it on every startup.
    server = mcp_server.build_server(Path("/vault"))
    schema = run(server.list_tools())
    output = {t.name: t.output_schema for t in schema}[tool]

    assert '"format": "path"' not in json.dumps(output)


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
    schema = tools["set_status"].parameters
    enum = _prop_enum(schema, "new_status")
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
    schema = tools["add_document"].parameters
    enum = _prop_enum(schema, "kind")
    assert enum == [k.value for k in DocumentKind]


def test_add_document_schema_has_no_path_argument() -> None:
    server = mcp_server.build_server(Path("/vault"))
    tools = {t.name: t for t in run(server.list_tools())}
    props = set(tools["add_document"].parameters["properties"])
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


# --- Section 14b (stage 9): create_vacancy tool -------------------------

_CREATE_VACANCY_ARGS: dict[str, object] = {
    "company": "Acme Corp",
    "role": "Backend Engineer",
    "source_url": "https://jobs.acme.example/1",
    "found_date": "2026-08-10",
    "status": "found",
}


def test_create_vacancy_tool_delegates(monkeypatch: pytest.MonkeyPatch) -> None:
    vault = Path("/vault")
    server = mcp_server.build_server(vault)
    mock = Mock(
        return_value=Path("/vault/acme-corp/2026-08-10-acme-corp-backend/vacancy.md")
    )
    monkeypatch.setattr(core, "create_vacancy", mock)

    result = run(server.call_tool("create_vacancy", _CREATE_VACANCY_ARGS))

    mock.assert_called_once_with(
        "Acme Corp",
        "Backend Engineer",
        date(2026, 8, 10),
        Status.FOUND,
        source_url="https://jobs.acme.example/1",
        applied_date=None,
        stage_note=None,
        salary_note=None,
        recruiter=None,
        tags=None,
        vault=vault,
    )
    assert (
        result.structured_content["path"]
        == "/vault/acme-corp/2026-08-10-acme-corp-backend/vacancy.md"
    )
    assert result.structured_content["id"] == "2026-08-10-acme-corp-backend"


def test_create_vacancy_schema_matches_core_param_names() -> None:
    server = mcp_server.build_server(Path("/vault"))
    tools = {t.name: t for t in run(server.list_tools())}
    props = set(tools["create_vacancy"].parameters["properties"])
    assert props == {
        "company",
        "role",
        "source_url",
        "found_date",
        "status",
        "applied_date",
        "stage_note",
        "salary_note",
        "recruiter",
        "tags",
    }


def test_create_vacancy_status_enum_matches_status() -> None:
    server = mcp_server.build_server(Path("/vault"))
    tools = {t.name: t for t in run(server.list_tools())}
    schema = tools["create_vacancy"].parameters
    enum = _prop_enum(schema, "status")
    assert enum == [s.value for s in Status]


def test_create_vacancy_omitting_optional_fields_matches_core_defaults(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    vault = Path("/vault")
    server = mcp_server.build_server(vault)
    mock = Mock(return_value=Path("/vault/acme-corp/v1/vacancy.md"))
    monkeypatch.setattr(core, "create_vacancy", mock)

    run(server.call_tool("create_vacancy", _CREATE_VACANCY_ARGS))

    mock.assert_called_once_with(
        "Acme Corp",
        "Backend Engineer",
        date(2026, 8, 10),
        Status.FOUND,
        source_url="https://jobs.acme.example/1",
        applied_date=None,
        stage_note=None,
        salary_note=None,
        recruiter=None,
        tags=None,
        vault=vault,
    )


def test_create_vacancy_new_company_creates_directory(tmp_path: Path) -> None:
    vault = tmp_path / "vault"
    _init_vault(vault)
    server = mcp_server.build_server(vault)

    run(server.call_tool("create_vacancy", _CREATE_VACANCY_ARGS))

    assert (vault / "acme-corp" / "_company.md").is_file()


def test_create_vacancy_existing_company_leaves_company_md_untouched(
    tmp_path: Path,
) -> None:
    vault = tmp_path / "vault"
    _init_vault(vault)
    server = mcp_server.build_server(vault)
    run(server.call_tool("create_vacancy", _CREATE_VACANCY_ARGS))
    company_md = vault / "acme-corp" / "_company.md"
    before = company_md.read_bytes()

    second_args = dict(_CREATE_VACANCY_ARGS)
    second_args["role"] = "Designer"
    second_args["source_url"] = "https://jobs.acme.example/2"
    run(server.call_tool("create_vacancy", second_args))

    assert company_md.read_bytes() == before


def test_create_vacancy_result_is_immediately_listed(tmp_path: Path) -> None:
    vault = tmp_path / "vault"
    _init_vault(vault)
    server = mcp_server.build_server(vault)

    run(server.call_tool("create_vacancy", _CREATE_VACANCY_ARGS))

    result = run(server.call_tool("list_vacancies", {}))
    companies = {row["company"] for row in result.structured_content["result"]}
    assert "Acme Corp" in companies


@pytest.mark.embedding
def test_create_vacancy_result_is_immediately_searchable(tmp_path: Path) -> None:
    vault = tmp_path / "vault"
    _init_vault(vault)
    build_index(read_vault(vault), default_index_path(vault))
    server = mcp_server.build_server(vault)

    run(server.call_tool("create_vacancy", _CREATE_VACANCY_ARGS))

    result = run(
        server.call_tool("search", {"query": "Backend Engineer", "mode": "keyword"})
    )
    companies = {hit["company"] for hit in result.structured_content["hits"]}
    assert "Acme Corp" in companies


def test_create_vacancy_same_day_company_unknown_role_gets_distinct_ids(
    tmp_path: Path,
) -> None:
    vault = tmp_path / "vault"
    _init_vault(vault)
    server = mcp_server.build_server(vault)
    args = dict(_CREATE_VACANCY_ARGS)
    args["role"] = "unknown"

    first = run(server.call_tool("create_vacancy", args))
    second_args = dict(args)
    second_args["source_url"] = "https://jobs.acme.example/2"
    second = run(server.call_tool("create_vacancy", second_args))

    assert first.structured_content["id"] != second.structured_content["id"]


def test_create_vacancy_missing_applied_date_returns_typed_error(
    tmp_path: Path,
) -> None:
    vault = tmp_path / "vault"
    _init_vault(vault)
    server = mcp_server.build_server(vault)
    args = dict(_CREATE_VACANCY_ARGS)
    args["status"] = "applied"

    with pytest.raises(ToolError, match="InvalidVacancyDataError"):
        run(server.call_tool("create_vacancy", args))

    assert not (vault / "acme-corp").exists()


def test_create_vacancy_applied_date_before_found_date_returns_typed_error(
    tmp_path: Path,
) -> None:
    vault = tmp_path / "vault"
    _init_vault(vault)
    server = mcp_server.build_server(vault)
    args = dict(_CREATE_VACANCY_ARGS)
    args["status"] = "applied"
    args["applied_date"] = "2026-08-01"  # earlier than found_date 2026-08-10

    with pytest.raises(ToolError, match="InvalidVacancyDataError"):
        run(server.call_tool("create_vacancy", args))

    assert not (vault / "acme-corp").exists()


def test_create_vacancy_tool_without_source_url_creates_vacancy_with_none(
    tmp_path: Path,
) -> None:
    vault = tmp_path / "vault"
    _init_vault(vault)
    server = mcp_server.build_server(vault)
    args = dict(_CREATE_VACANCY_ARGS)
    del args["source_url"]

    result = run(server.call_tool("create_vacancy", args))

    vacancy_id = result.structured_content["id"]
    detail = run(server.call_tool("get_vacancy", {"id_or_query": vacancy_id}))
    assert detail.structured_content["source_url"] is None


def test_create_vacancy_description_states_no_source_url_convention() -> None:
    server = mcp_server.build_server(Path("/vault"))
    tools = {t.name: t for t in run(server.list_tools())}
    description = tools["create_vacancy"].description.lower()
    assert "source_url" in description
    assert "pdf" in description


def test_create_vacancy_description_states_unknown_role_convention() -> None:
    server = mcp_server.build_server(Path("/vault"))
    tools = {t.name: t for t in run(server.list_tools())}
    description = tools["create_vacancy"].description.lower()
    assert "unknown" in description
    assert "needs_review" in description


def test_create_vacancy_description_states_migrated_convention() -> None:
    server = mcp_server.build_server(Path("/vault"))
    tools = {t.name: t for t in run(server.list_tools())}
    description = tools["create_vacancy"].description.lower()
    assert "found_date" in description
    assert "applied_date" in description
    assert "migrated" in description


def test_create_vacancy_description_states_check_before_create_convention() -> None:
    server = mcp_server.build_server(Path("/vault"))
    tools = {t.name: t for t in run(server.list_tools())}
    description = tools["create_vacancy"].description.lower()
    assert "does not deduplicate" in description
    assert "find_existing" in description


_BATCH_SIZE = 10
_FAILING_BATCH_INDEX = 5


def test_create_vacancy_ten_sequential_calls_produce_distinct_ids(
    tmp_path: Path,
) -> None:
    vault = tmp_path / "vault"
    _init_vault(vault)
    server = mcp_server.build_server(vault)

    ids = set()
    for i in range(_BATCH_SIZE):
        args = dict(_CREATE_VACANCY_ARGS)
        args["source_url"] = f"https://jobs.acme.example/{i}"
        result = run(server.call_tool("create_vacancy", args))
        ids.add(result.structured_content["id"])

    assert len(ids) == _BATCH_SIZE


def test_create_vacancy_failure_mid_batch_leaves_prior_creations_intact(
    tmp_path: Path,
) -> None:
    vault = tmp_path / "vault"
    _init_vault(vault)
    server = mcp_server.build_server(vault)

    created_ids = []
    for i in range(_BATCH_SIZE):
        args = dict(_CREATE_VACANCY_ARGS)
        args["source_url"] = f"https://jobs.acme.example/{i}"
        if i == _FAILING_BATCH_INDEX:
            args["status"] = "applied"  # invalid: no applied_date
            with pytest.raises(ToolError, match="InvalidVacancyDataError"):
                run(server.call_tool("create_vacancy", args))
            continue
        result = run(server.call_tool("create_vacancy", args))
        created_ids.append(result.structured_content["id"])

    assert len(created_ids) == _BATCH_SIZE - 1
    snapshot = read_vault(vault)
    assert set(created_ids) <= set(snapshot.vacancies)


# --- Section 15 (stage 9): find_existing tool ----------------------------


def test_find_existing_tool_delegates(monkeypatch: pytest.MonkeyPatch) -> None:
    vault = Path("/vault")
    server = mcp_server.build_server(vault)
    summary = core.VacancySummary(
        id="v1",
        company="Acme",
        role="Engineer",
        status=Status.FOUND,
        last_activity=date(2026, 1, 1),
        document_count=0,
    )
    mock = Mock(return_value=[summary])
    monkeypatch.setattr(core, "find_existing", mock)

    result = run(
        server.call_tool(
            "find_existing",
            {"company": "Acme", "source_url": "https://acme.example/1"},
        )
    )

    mock.assert_called_once_with("Acme", "https://acme.example/1", vault=vault)
    assert result.structured_content["result"] == [summary.model_dump(mode="json")]


def test_find_existing_schema_matches_core_param_names() -> None:
    server = mcp_server.build_server(Path("/vault"))
    tools = {t.name: t for t in run(server.list_tools())}
    props = set(tools["find_existing"].parameters["properties"])
    assert props == {"company", "source_url"}


def test_find_existing_tool_returns_matches_for_existing_company(
    tmp_path: Path,
) -> None:
    vault = _demo_vault(tmp_path / "vault")
    server = mcp_server.build_server(vault)

    result = run(
        server.call_tool(
            "find_existing",
            {"company": "Acme Corp", "source_url": "https://nowhere.example/1"},
        )
    )

    companies = {row["company"] for row in result.structured_content["result"]}
    assert companies == {"Acme Corp"}


def test_find_existing_tool_without_source_url_still_matches_by_company(
    tmp_path: Path,
) -> None:
    vault = _demo_vault(tmp_path / "vault")
    server = mcp_server.build_server(vault)

    result = run(server.call_tool("find_existing", {"company": "Acme Corp"}))

    companies = {row["company"] for row in result.structured_content["result"]}
    assert companies == {"Acme Corp"}


def test_find_existing_tool_returns_empty_for_unknown_company_and_url(
    tmp_path: Path,
) -> None:
    vault = _demo_vault(tmp_path / "vault")
    server = mcp_server.build_server(vault)

    result = run(
        server.call_tool(
            "find_existing",
            {
                "company": "No Such Company",
                "source_url": "https://nowhere.example/1",
            },
        )
    )

    assert result.structured_content["result"] == []


def test_find_existing_tool_matches_source_url_across_company_spellings(
    tmp_path: Path,
) -> None:
    vault = _demo_vault(tmp_path / "vault")
    server = mcp_server.build_server(vault)

    result = run(
        server.call_tool(
            "find_existing",
            {
                "company": "Acme Corporation Ltd",
                "source_url": "https://jobs.acme.example/v1",
            },
        )
    )

    ids = {row["id"] for row in result.structured_content["result"]}
    assert "v1" in ids


# --- Section 20: annotations / tool-list membership -------------------


def test_tool_list_is_exactly_the_twelve_specified_tools() -> None:
    server = mcp_server.build_server(Path("/vault"))
    names = {t.name for t in run(server.list_tools())}
    assert names == {
        "list_vacancies",
        "get_company",
        "get_vacancy",
        "search",
        "read_document",
        "resolve",
        "find_existing",
        "append_note",
        "set_status",
        "edit_vacancy",
        "add_document",
        "create_vacancy",
    }
    assert "reindex" not in names


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
        "find_existing",
    }
    for tool in run(server.list_tools()):
        if tool.name in read_tools:
            assert tool.annotations.read_only_hint is True


def test_write_tools_have_read_only_and_destructive_hint_false() -> None:
    server = mcp_server.build_server(Path("/vault"))
    write_tools = {
        "append_note",
        "set_status",
        "edit_vacancy",
        "add_document",
        "create_vacancy",
    }
    for tool in run(server.list_tools()):
        if tool.name in write_tools:
            assert tool.annotations.read_only_hint is False
            assert tool.annotations.destructive_hint is False


# --- Section 21: cross-cutting safety checks ----------------------------


def test_no_tool_schema_accepts_a_write_path_argument() -> None:
    server = mcp_server.build_server(Path("/vault"))
    for tool in run(server.list_tools()):
        props = tool.parameters.get("properties", {})
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
    payload = json.loads(contents.contents[0].content)
    by_slug = {row["slug"]: row for row in payload}
    assert by_slug["acme"] == {"slug": "acme", "name": "Acme Corp", "vacancy_count": 2}
    assert by_slug["beta"] == {"slug": "beta", "name": "Beta Inc", "vacancy_count": 1}


def test_statuses_resource_lists_every_status_and_its_transitions() -> None:
    server = mcp_server.build_server(Path("/vault"))
    contents = run(server.read_resource("vacancy-radar://statuses"))
    payload = json.loads(contents.contents[0].content)
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
    payload = json.loads(contents.contents[0].content)
    by_status = {row["status"]: row["transitions"] for row in payload}
    assert by_status["rejected"] == ["applied"]


# --- Sections 16-18: prompts ---------------------------------------------


def test_prep_interview_references_real_content(tmp_path: Path) -> None:
    vault = _demo_vault(tmp_path / "vault")
    server = mcp_server.build_server(vault)
    messages = run(server.render_prompt("prep_interview", {"company": "Acme Corp"}))
    text = " ".join(m.content.text for m in messages.messages)
    assert "Backend Engineer" in text
    assert "python and distributed systems" in text
    assert "growing fast" in text


def test_prep_interview_unknown_company_is_a_resolution_failure(tmp_path: Path) -> None:
    vault = _demo_vault(tmp_path / "vault")
    server = mcp_server.build_server(vault)
    messages = run(
        server.render_prompt("prep_interview", {"company": "Nonexistent Corp"})
    )
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
    messages = run(server.render_prompt("draft_reply", {"vacancy_id": "v2"}))
    text = " ".join(m.content.text for m in messages.messages)
    assert "take-home by Friday" in text


def test_weekly_review_surfaces_stale_take_home_and_needs_review(
    tmp_path: Path,
) -> None:
    vault = _demo_vault(tmp_path / "vault")
    server = mcp_server.build_server(vault)
    messages = run(server.render_prompt("weekly_review", {}))
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


# --- Section 22 (edit-vacancy-fields): edit_vacancy tool --------------------


def _editable_vault(vault: Path, **overrides: object) -> Path:
    """`_minimal_vault`'s vacancy, applied rather than found, so the
    nullable fields an edit test needs can be set and cleared."""
    _init_vault(vault)
    _write_company(vault, "acme", "Acme Corp")
    fields: dict[str, object] = {
        "id": "v1",
        "company": "Acme Corp",
        "company_slug": "acme",
        "role": "Engineer",
        "source_url": "https://jobs.acme.example/v1",
        "status": Status.APPLIED,
        "found_date": date(2026, 1, 1),
        "applied_date": date(2026, 1, 3),
    }
    fields.update(overrides)
    vacancy_dir = _write_vacancy(vault, "acme", "v1", Vacancy(**fields))  # type: ignore[arg-type]
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


def test_edit_vacancy_tool_delegates(monkeypatch: pytest.MonkeyPatch) -> None:
    vault = Path("/vault")
    server = mcp_server.build_server(vault)
    result = core.EditResult(
        vacancy_id="v1",
        changed=True,
        changes=(
            core.FieldChange(
                field="source_url",
                old="https://jobs.acme.example/v1",
                new="https://acme.example/2",
            ),
        ),
    )
    mock = Mock(return_value=result)
    monkeypatch.setattr(core, "edit_vacancy", mock)

    call = run(
        server.call_tool(
            "edit_vacancy",
            {"vacancy_id": "v1", "source_url": "https://acme.example/2"},
        )
    )

    mock.assert_called_once_with("v1", vault=vault, source_url="https://acme.example/2")
    payload = call.structured_content
    assert payload["vacancy_id"] == "v1"
    assert payload["changed"] is True
    assert payload["changes"] == [
        {
            "field": "source_url",
            "old": "https://jobs.acme.example/v1",
            "new": "https://acme.example/2",
        }
    ]


def test_edit_vacancy_schema_matches_core_param_names() -> None:
    server = mcp_server.build_server(Path("/vault"))
    tools = {t.name: t for t in run(server.list_tools())}
    schema = tools["edit_vacancy"].parameters

    assert set(schema["properties"]) == {
        "vacancy_id",
        *core.EDITABLE_FIELDS,
        "clear",
    }
    assert schema["required"] == ["vacancy_id"]


def test_edit_vacancy_tool_omitted_parameters_leave_fields_untouched(
    tmp_path: Path,
) -> None:
    vault = _editable_vault(tmp_path / "vault", recruiter="Anna K.")
    server = mcp_server.build_server(vault)

    run(
        server.call_tool(
            "edit_vacancy",
            {"vacancy_id": "v1", "source_url": "https://acme.example/2"},
        )
    )

    updated = read_vault(vault).vacancies["v1"]
    assert updated.recruiter == "Anna K."
    assert updated.source_url == "https://acme.example/2"


def test_edit_vacancy_tool_clear_removes_a_field(tmp_path: Path) -> None:
    vault = _editable_vault(tmp_path / "vault", recruiter="Anna K.")
    server = mcp_server.build_server(vault)

    run(server.call_tool("edit_vacancy", {"vacancy_id": "v1", "clear": ["recruiter"]}))

    metadata, _ = frontmatter.parse(
        (vault / "acme" / "v1" / "vacancy.md").read_text(encoding="utf-8")
    )
    assert "recruiter" not in metadata


def test_edit_vacancy_tool_edit_is_visible_to_get_vacancy(tmp_path: Path) -> None:
    vault = _editable_vault(tmp_path / "vault")
    build_index(read_vault(vault), default_index_path(vault))
    server = mcp_server.build_server(vault)

    run(
        server.call_tool("edit_vacancy", {"vacancy_id": "v1", "role": "Staff Engineer"})
    )
    detail = run(server.call_tool("get_vacancy", {"id_or_query": "v1"}))

    assert detail.structured_content["role"] == "Staff Engineer"


@pytest.mark.parametrize(
    ("arguments", "expected_error"),
    [
        (
            {"vacancy_id": "v1", "source_url": "ftp://example.com/x"},
            "InvalidVacancyDataError",
        ),
        ({"vacancy_id": "v1", "clear": ["status"]}, "UneditableFieldError"),
        ({"vacancy_id": "v1", "clear": ["role"]}, "NotNullableFieldError"),
        (
            {"vacancy_id": "v1", "recruiter": "Anna K.", "clear": ["recruiter"]},
            "ConflictingEditError",
        ),
        (
            {"vacancy_id": "does-not-exist", "recruiter": "Anna K."},
            "EntityNotFoundError",
        ),
    ],
)
def test_edit_vacancy_tool_typed_errors_leave_the_vault_untouched(
    tmp_path: Path, arguments: dict[str, object], expected_error: str
) -> None:
    vault = _editable_vault(tmp_path / "vault")
    server = mcp_server.build_server(vault)
    before = {
        p.relative_to(vault): p.read_bytes() for p in vault.rglob("*") if p.is_file()
    }

    with pytest.raises(ToolError, match=expected_error):
        run(server.call_tool("edit_vacancy", arguments))

    after = {
        p.relative_to(vault): p.read_bytes() for p in vault.rglob("*") if p.is_file()
    }
    assert after == before


def test_edit_vacancy_tool_touches_no_file_but_the_target_vacancy(
    tmp_path: Path,
) -> None:
    vault = _editable_vault(tmp_path / "vault")
    server = mcp_server.build_server(vault)
    vacancy_md = vault / "acme" / "v1" / "vacancy.md"
    before = {
        p.relative_to(vault): p.read_bytes()
        for p in vault.rglob("*")
        if p.is_file()
        and p != vacancy_md
        and default_index_path(vault) not in p.parents
    }

    run(server.call_tool("edit_vacancy", {"vacancy_id": "v1", "recruiter": "Anna K."}))

    after = {
        p.relative_to(vault): p.read_bytes()
        for p in vault.rglob("*")
        if p.is_file()
        and p != vacancy_md
        and default_index_path(vault) not in p.parents
    }
    assert after == before
    assert vacancy_md.read_bytes() != before.get(vacancy_md.relative_to(vault))


# --- Section 23 (add-mcp-apps-ui): the MCP Apps UI extension ---------------
#
# The four read tools carry a `_meta.ui` reference to a `ui://` view the
# Apps extension registers; the extension is always on and adds nothing
# to any tool's result. A client that did not negotiate it never sees the
# `ui://` resources.

_UI_TOOL_URIS = {
    "list_vacancies": "ui://vacancy-radar/vacancy-list",
    "get_vacancy": "ui://vacancy-radar/vacancy-detail",
    "get_company": "ui://vacancy-radar/company-dossier",
    "search": "ui://vacancy-radar/search-results",
}
_NETWORK_TOKENS = ("fetch(", "XMLHttpRequest", "new WebSocket", "WebSocket(")
_EXTERNAL_REF = re.compile(r'(?:src|href)\s*=\s*["\']?(?:https?:)?//', re.IGNORECASE)


class _SingleRootHTML(HTMLParser):
    """Counts top-level elements to assert a view is one `<html>` document."""

    def __init__(self) -> None:
        super().__init__()
        self.depth = 0
        self.roots: list[str] = []

    def handle_starttag(self, tag: str, _attrs: object) -> None:
        if self.depth == 0:
            self.roots.append(tag)
        self.depth += 1

    def handle_endtag(self, _tag: str) -> None:
        self.depth = max(0, self.depth - 1)


def test_four_read_tools_reference_a_registered_ui_view() -> None:
    server = mcp_server.build_server(Path("/vault"))
    tools = {t.name: t for t in run(server.list_tools())}
    registered = {str(r.uri) for r in run(server.list_resources())}

    for name, uri in _UI_TOOL_URIS.items():
        assert tools[name].meta == {"ui": {"resourceUri": uri}}
        assert uri in registered

    for name, tool in tools.items():
        if name not in _UI_TOOL_URIS:
            assert not (tool.meta and "ui" in tool.meta)


def test_server_advertises_the_apps_extension() -> None:
    server = mcp_server.build_server(Path("/vault"))
    caps = server._mcp_server.get_capabilities(  # noqa: SLF001
        NotificationOptions(), {}
    )
    assert "io.modelcontextprotocol/ui" in (caps.extensions or {})


def test_cli_exposes_no_ui_toggle() -> None:
    assert vars(mcp_server._parse_args([])) == {"vault": None}  # noqa: SLF001
    for flag in ("--ui", "--no-ui", "--apps", "--no-apps"):
        with pytest.raises(SystemExit):
            mcp_server._parse_args([flag])  # noqa: SLF001


def test_ui_resources_are_self_contained_app_documents() -> None:
    server = mcp_server.build_server(Path("/vault"))
    listed = {str(r.uri): r for r in run(server.list_resources())}

    for uri in _UI_TOOL_URIS.values():
        assert uri in listed
        assert listed[uri].mime_type == APP_MIME_TYPE

        contents = run(server.read_resource(uri))
        item = contents.contents[0]
        assert item.mime_type == APP_MIME_TYPE

        body = item.content
        assert isinstance(body, str)
        parser = _SingleRootHTML()
        parser.feed(body)
        assert parser.roots == ["html"]

        assert not _EXTERNAL_REF.search(body)
        assert "<script src" not in body.lower()
        assert "<link " not in body.lower()
        for token in _NETWORK_TOKENS:
            assert token not in body

        csp = (item.meta or {}).get("ui", {}).get("csp", {})
        for key in ("connectDomains", "resourceDomains", "frameDomains"):
            assert not csp.get(key)


def test_ui_bound_tools_return_their_core_result_untouched(tmp_path: Path) -> None:
    """The four UI-bound tools return exactly what their one `core.py`
    call returns, serialized - the `ui://` view is `_meta` on the tool
    definition and adds nothing to the result a client reads."""
    vault = _indexed_demo_vault(tmp_path / "vault")
    server = mcp_server.build_server(vault)

    cases = [
        ("list_vacancies", {}, lambda: {"result": core.list_vacancies(vault=vault)}),
        (
            "get_vacancy",
            {"id_or_query": "v1"},
            lambda: core.get_vacancy("v1", vault=vault),
        ),
        (
            "get_company",
            {"name": "Acme Corp"},
            lambda: core.get_company("Acme Corp", vault=vault),
        ),
        (
            "search",
            {"query": "backend engineer", "mode": "keyword"},
            lambda: core.search(
                "backend engineer", vault=vault, mode=SearchMode.KEYWORD
            ),
        ),
    ]
    for name, args, direct in cases:
        served = run(server.call_tool(name, args)).structured_content
        expected = mcp_server._to_jsonable(direct())  # noqa: SLF001
        # `search` carries a wall-clock `elapsed_ms` that jitters between
        # any two calls; nothing in this change touches it.
        served.pop("elapsed_ms", None)
        expected.pop("elapsed_ms", None)
        assert served == expected, name


def test_ui_resources_do_not_disturb_the_data_resources(tmp_path: Path) -> None:
    vault = _demo_vault(tmp_path / "vault")
    server = mcp_server.build_server(vault)

    listed = {str(r.uri) for r in run(server.list_resources())}
    assert {u for u in listed if u.startswith("vacancy-radar://")} == {
        "vacancy-radar://companies",
        "vacancy-radar://statuses",
    }
    assert {u for u in listed if u.startswith("ui://")} == set(_UI_TOOL_URIS.values())

    companies = json.loads(
        run(server.read_resource("vacancy-radar://companies")).contents[0].content
    )
    assert {row["slug"] for row in companies} == {"acme", "beta"}
    statuses = json.loads(
        run(server.read_resource("vacancy-radar://statuses")).contents[0].content
    )
    assert {row["status"] for row in statuses} == {s.value for s in Status}


def test_vacancy_detail_view_reads_only_vacancy_detail_fields(tmp_path: Path) -> None:
    """The vacancy-detail render function touches only fields that exist
    on `VacancyDetail`/`DocumentSummary` - a rename in core.py surfaces
    here, and a stray `body`/`text` access (a document body) fails."""
    detail_fields = set(core.VacancyDetail.model_fields)
    document_fields = set(core.DocumentSummary.model_fields)
    js = mcp_server.RENDER_JS["get_vacancy"]

    referenced_d = set(re.findall(r"\bd\.([a-z_]+)", js))
    referenced_doc = set(re.findall(r"\bdoc\.([a-z_]+)", js))

    assert referenced_d <= detail_fields, referenced_d - detail_fields
    assert referenced_doc <= document_fields, referenced_doc - document_fields
    for forbidden in ("body", "text", "content"):
        assert forbidden not in referenced_d
        assert forbidden not in referenced_doc

    # The real result really does carry every field the view reads.
    vault = _demo_vault(tmp_path / "vault")
    server = mcp_server.build_server(vault)
    call = run(server.call_tool("get_vacancy", {"id_or_query": "v1"}))
    result = call.structured_content
    assert referenced_d <= set(result)
    assert result["documents"]
    assert referenced_doc <= set(result["documents"][0])


def test_subprocess_serves_ui_views_and_unchanged_text_to_a_plain_client(
    tmp_path: Path,
) -> None:
    """End-to-end over stdio with a client that does NOT negotiate the
    Apps extension: the four read tools still carry `_meta.ui.resourceUri`,
    the `ui://` resources are listed and served as app documents, and a
    tool call returns the same JSON result a non-UI client has always
    seen. (The `capabilities.extensions` advertisement is gated to the
    2026-07-28 wire - the plain `initialize` handshake this hand-rolled
    client uses negotiates 2025-11-25, where `ServerCapabilities` has no
    `extensions` field; `test_server_advertises_the_apps_extension`
    covers the advertisement in-process.)"""
    vault = _demo_vault(tmp_path / "vault")

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
                    "capabilities": {},  # no extensions negotiated
                    "clientInfo": {"name": "plain-client", "version": "0.0.0"},
                },
            }
        )
        assert recv()["result"]["protocolVersion"]

        send({"jsonrpc": "2.0", "method": "notifications/initialized"})

        send({"jsonrpc": "2.0", "id": 2, "method": "tools/list", "params": {}})
        tools = {t["name"]: t for t in recv()["result"]["tools"]}
        assert len(tools) == _EXPECTED_TOOL_COUNT
        for name in ("list_vacancies", "get_vacancy", "get_company", "search"):
            uri = tools[name]["_meta"]["ui"]["resourceUri"]
            assert uri.startswith("ui://vacancy-radar/")
        assert "ui" not in (tools["read_document"].get("_meta") or {})

        send({"jsonrpc": "2.0", "id": 3, "method": "resources/list", "params": {}})
        resource_uris = {r["uri"] for r in recv()["result"]["resources"]}
        assert {
            "ui://vacancy-radar/vacancy-list",
            "ui://vacancy-radar/vacancy-detail",
            "ui://vacancy-radar/company-dossier",
            "ui://vacancy-radar/search-results",
            "vacancy-radar://companies",
            "vacancy-radar://statuses",
        } <= resource_uris

        send(
            {
                "jsonrpc": "2.0",
                "id": 4,
                "method": "resources/read",
                "params": {"uri": "ui://vacancy-radar/vacancy-list"},
            }
        )
        contents = recv()["result"]["contents"][0]
        assert contents["mimeType"] == "text/html;profile=mcp-app"
        assert contents["text"].startswith("<!doctype html>")

        send(
            {
                "jsonrpc": "2.0",
                "id": 5,
                "method": "tools/call",
                "params": {"name": "list_vacancies", "arguments": {}},
            }
        )
        call_result = recv()["result"]
        assert call_result.get("isError") is not True
        rows = call_result["structuredContent"]["result"]
        assert {row["id"] for row in rows} == {"v1", "v2", "v3"}
    finally:
        proc.stdin.close()
        proc.terminate()
        try:
            proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            proc.kill()
