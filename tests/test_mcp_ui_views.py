"""Browser render tests for the MCP Apps `ui://` views (change: add-mcp-apps-ui).

Each view is the real HTML `mcp_server.PAGES` ships (assembled from the
`.html`/`.css`/`.js` files under `assets/mcp_ui/`). These tests load it in
headless Chromium, drive it with the ext-apps `ui/notifications/tool-result`
message the host would send, and assert on what it actually renders - the
automated stand-in for "open it in a real MCP host and look" (tasks 5.2/5.3).

The tool results here are built from `core` models directly (serialized the way
the server serializes them), so these tests stay fast and self-contained;
`test_mcp_server.py` already covers the real tool -> result path.

Skips cleanly when Playwright or its Chromium build is missing, so a plain
`uv run pytest` still works without `uv run playwright install chromium`.
"""

from __future__ import annotations

import re
from collections.abc import Callable, Iterator
from datetime import date
from typing import TYPE_CHECKING, Any

import pytest

from vacancy_radar import core, mcp_server
from vacancy_radar.index.search import SearchHit, SearchMode
from vacancy_radar.models import DocumentKind, Status

sync_api = pytest.importorskip("playwright.sync_api")

if TYPE_CHECKING:
    from playwright.sync_api import Browser

# A `message` recorder, injected as the first <script> in <head> so it runs
# before the view's bridge script. The view posts to `window.parent`, which is
# `window` for a top-level page, so stubbing `postMessage` captures the bridge's
# `ui/initialize` and `ui/notifications/size-changed` without a cross-frame hop.
# (Playwright's `add_init_script` only fires on real navigations, not
# `set_content`, so the recorder has to travel in the markup.)
_CAPTURE_SCRIPT = (
    "<script>window.__captured = [];"
    "window.parent.postMessage = (m) => { window.__captured.push(m); };</script>\n"
)

_DELIVER_RESULT = """
(params) => window.dispatchEvent(new MessageEvent('message', {
  data: { jsonrpc: '2.0', method: 'ui/notifications/tool-result', params }
}))
"""

RenderFn = Callable[[str, dict[str, Any]], dict[str, Any]]


# --- Result fixtures (serialized exactly as the server serializes them) ----


def _list_result() -> dict[str, Any]:
    rows = [
        core.VacancySummary(
            id="v1",
            company="Acme Corp",
            role="Backend Engineer",
            status=Status.APPLIED,
            applied_date=date(2026, 1, 3),
            last_activity=date(2026, 1, 4),
            document_count=2,
        ),
        core.VacancySummary(
            id="v2",
            company="Beta Inc",
            role="Data Scientist",
            status=Status.TAKE_HOME,
            applied_date=date(2026, 1, 2),
            last_activity=date(2026, 1, 5),
            document_count=1,
        ),
    ]
    return {"result": [r.model_dump(mode="json") for r in rows]}


def _vacancy_detail_result() -> dict[str, Any]:
    return core.VacancyDetail(
        id="v1",
        company="Acme Corp",
        company_slug="acme",
        role="Backend Engineer",
        status=Status.APPLIED,
        source_url="https://jobs.acme.example/v1",
        found_date=date(2026, 1, 1),
        applied_date=date(2026, 1, 3),
        stage_note="phone screen booked",
        recruiter="Dana R.",
        tags=["referral"],
        documents=[
            core.DocumentSummary(
                id="v1-posting",
                title="Backend Engineer posting",
                kind=DocumentKind.POSTING,
                date=date(2026, 1, 1),
                path="acme/v1/documents/v1-posting.md",
            ),
        ],
    ).model_dump(mode="json")


def _company_result() -> dict[str, Any]:
    return core.CompanyDossier(
        slug="acme",
        name="Acme Corp",
        domains=["acme.example"],
        recruiters=["Dana R."],
        notes="Series C, hiring across platform.",
        vacancies=[
            core.VacancySummary(
                id="v1",
                company="Acme Corp",
                role="Backend Engineer",
                status=Status.APPLIED,
                applied_date=date(2026, 1, 3),
                last_activity=date(2026, 1, 4),
                document_count=2,
            ),
        ],
    ).model_dump(mode="json")


def _search_result() -> dict[str, Any]:
    hits = [
        SearchHit(
            doc_id="v1-posting",
            vacancy_id="v1",
            company="Acme Corp",
            company_slug="acme",
            role="Backend Engineer",
            status="applied",
            kind="posting",
            path="acme/v1/documents/v1-posting.md",
            date=date(2026, 1, 1),
            score=1.867,
            snippet="We need a backend engineer fluent in distributed systems.",
            keyword_rank=1,
            semantic_rank=None,
        ),
    ]
    return mcp_server._to_jsonable(  # noqa: SLF001 - the server's own serializer
        core.SearchResults(
            hits=hits,
            mode=SearchMode.KEYWORD,
            effective_vector_weight=None,
            elapsed_ms=3.1,
            total_candidates=1,
        )
    )


# --- Browser fixtures -----------------------------------------------------


@pytest.fixture
def chromium_browser() -> Iterator[Browser]:
    # Function-scoped on purpose: the sync Playwright API drives an asyncio
    # loop on this thread for as long as it is open, and `test_mcp_server.py`
    # calls `asyncio.run(...)`, which refuses to run while a loop is live.
    # Opening and fully closing Playwright per test keeps the two apart
    # regardless of collection order.
    try:
        with sync_api.sync_playwright() as playwright:
            browser = playwright.chromium.launch()
            try:
                yield browser
            finally:
                browser.close()
    except Exception as exc:  # noqa: BLE001 - any launch failure means "unusable here"
        pytest.skip(f"playwright chromium unavailable: {exc}")


@pytest.fixture
def render_view(chromium_browser: Browser) -> Iterator[RenderFn]:
    context = chromium_browser.new_context()

    def _render(tool: str, structured_content: dict[str, Any]) -> dict[str, Any]:
        _title, html = mcp_server.PAGES[mcp_server.VIEW_URIS[tool]]
        page = context.new_page()
        page.set_content(html.replace("<head>\n", "<head>\n" + _CAPTURE_SCRIPT, 1))
        page.evaluate(_DELIVER_RESULT, {"structuredContent": structured_content})
        result = {
            "text": page.text_content("#vr-root"),
            "html": page.inner_html("#vr-root"),
            "messages": page.evaluate("window.__captured"),
        }
        page.close()
        return result

    yield _render
    context.close()


def _methods(messages: list[dict[str, Any]]) -> list[str | None]:
    return [m.get("method") for m in messages]


# --- Tests --------------------------------------------------------------


def test_vacancy_list_view_renders_every_row(render_view: RenderFn) -> None:
    sc = _list_result()
    view = render_view("list_vacancies", sc)

    text = view["text"]
    for row in sc["result"]:
        assert row["company"] in text
        assert row["role"] in text
        assert row["id"] in text
        assert row["status"] in text

    methods = _methods(view["messages"])
    assert "ui/initialize" in methods
    assert methods[-1] == "ui/notifications/size-changed"


def test_vacancy_detail_view_shows_fields_and_document_index_not_bodies(
    render_view: RenderFn,
) -> None:
    sc = _vacancy_detail_result()
    text = render_view("get_vacancy", sc)["text"]

    assert sc["role"] in text
    assert sc["source_url"] in text
    assert sc["stage_note"] in text
    assert sc["recruiter"] in text
    for doc in sc["documents"]:
        assert doc["title"] in text
        assert doc["path"] in text
    # A VacancyDetail result carries no document body; the word "systems"
    # only appears in a body, so it must not show up here.
    assert "systems" not in text


def test_company_dossier_view_renders_metadata_and_vacancies(
    render_view: RenderFn,
) -> None:
    sc = _company_result()
    text = render_view("get_company", sc)["text"]

    assert sc["name"] in text
    assert sc["notes"] in text
    assert "acme.example" in text
    for vacancy in sc["vacancies"]:
        assert vacancy["role"] in text
        assert vacancy["id"] in text


def test_search_view_renders_each_hit_from_its_own_fields(
    render_view: RenderFn,
) -> None:
    sc = _search_result()
    text = render_view("search", sc)["text"]

    assert sc["hits"]
    for hit in sc["hits"]:
        assert hit["path"] in text
        assert hit["role"] in text
        assert hit["snippet"] in text  # part of the result, shown verbatim


def test_view_handles_an_empty_result(render_view: RenderFn) -> None:
    assert "No vacancies." in render_view("list_vacancies", {"result": []})["text"]


def test_view_survives_a_malformed_result_without_a_blank_frame(
    render_view: RenderFn,
) -> None:
    view = render_view("search", {})  # `hits` missing entirely
    assert "No matches." in view["text"]
    assert "ui/notifications/size-changed" in _methods(view["messages"])


def test_theme_from_host_context_is_applied(chromium_browser: Browser) -> None:
    _title, html = mcp_server.PAGES[mcp_server.VIEW_URIS["list_vacancies"]]
    page = chromium_browser.new_context().new_page()
    page.set_content(html, wait_until="load")
    page.evaluate(
        """() => window.dispatchEvent(new MessageEvent('message', { data: {
             jsonrpc: '2.0', method: 'ui/notifications/host-context-changed',
             params: { theme: 'dark' } } }))"""
    )
    assert page.get_attribute("html", "data-theme") == "dark"


def test_all_four_views_reference_only_their_result_fields() -> None:
    """A structural mirror of the render checks that runs without a
    browser: every `<var>.<field>` a view's render function reads is a
    field the matching model actually has, so a `core.py` rename fails
    here even when Chromium is absent."""
    summary = set(core.VacancySummary.model_fields)
    search_hit = {
        "doc_id",
        "vacancy_id",
        "company",
        "company_slug",
        "role",
        "status",
        "kind",
        "path",
        "date",
        "score",
        "snippet",
        "keyword_rank",
        "semantic_rank",
    }
    search_results = {
        "hits",
        "mode",
        "effective_vector_weight",
        "elapsed_ms",
        "total_candidates",
        "freshness_warning",
    }
    bindings = {
        "list_vacancies": {"row": summary},
        "get_vacancy": {
            "d": set(core.VacancyDetail.model_fields),
            "doc": set(core.DocumentSummary.model_fields),
        },
        "get_company": {
            "d": set(core.CompanyDossier.model_fields),
            "row": summary,
        },
        "search": {"d": search_results, "hit": search_hit},
    }
    assert set(bindings) == set(mcp_server.RENDER_JS)
    for tool, vars_ in bindings.items():
        js = mcp_server.RENDER_JS[tool]
        for var, allowed in vars_.items():
            referenced = set(re.findall(rf"\b{var}\.([a-z_]+)", js))
            assert referenced <= allowed, f"{tool}: {var}.{referenced - allowed}"
