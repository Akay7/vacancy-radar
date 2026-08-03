# Phase 0 Research: Minimal UI

## 1. Framework choice

**Decision**: Server-rendered Jinja2 templates from the existing FastAPI app, with HTMX
(vendored as a single local `.js` file) handling form submission without a full page reload.

**Rationale**: Per explicit direction, no new dependencies beyond the minimum required. The
feature's actual interaction shape — paste text, submit, view a structured result, no multi-step
flow, no client-side state to manage — doesn't need a client-side framework, a build step, or a
separate frontend service. FastAPI already renders Jinja2 templates natively
(`fastapi.templating.Jinja2Templates`); HTMX adds partial-page updates with one `<script>` tag
and zero new tooling. This keeps `docker compose up` unchanged (one service, as today) and
avoids introducing Node/npm into an otherwise pure-Python repository.

**Alternatives considered and explicitly rejected this round**:
- **CopilotKit** (raised and discussed with the user directly): requires a React app plus a
  separate Node "Copilot Runtime" service, and its own conversational LLM call sitting outside
  `grounding.enforce()` — architecturally mismatched with this feature's single-shot,
  already-grounded interaction, and rejected per the user's "no extra dependencies for now"
  direction.
- **Plain React + Vite SPA**: reasonable if the UI were expected to grow substantially, but adds
  a build toolchain for a one-page feature — rejected for the same reason, not because it's a
  bad tool in general.

## 2. What new dependencies does this actually require?

**Decision**: Add two direct dependencies: `jinja2` and `python-multipart`.

**Rationale**: `python -c "import jinja2"` already succeeds in the project's virtualenv — some
existing dependency (e.g. a Chroma/sentence-transformers sub-dependency) pulls it in
transitively. Relying on an undeclared transitive dependency is fragile: if the package that
currently pulls it in ever drops it, the UI breaks with no signal in `pyproject.toml` explaining
why. Declaring it explicitly costs nothing (it's already installed) and is the honest reflection
of a now-direct import.

`python-multipart`, however, is a genuinely new dependency, corrected from an earlier assumption
in this document: FastAPI's `Form(...)` parameter support requires it unconditionally to parse
*any* form body, `application/x-www-form-urlencoded` included — not only
`multipart/form-data` file uploads as its name might suggest. Verified directly: a minimal
FastAPI route using `Form(...)` raises `RuntimeError: Form data requires "python-multipart" to
be installed` at route-registration time without it, regardless of how the client encodes the
POST body. There's no way to accept an HTML `<form>` submission through FastAPI's `Form()`
mechanism without it. This is still a small, single-purpose, dependency-light library (not a
framework, no build step) — consistent with "no extra dependencies" meaning no new
toolchain/service, not literally zero new packages for a feature that, by definition, needs to
parse form submissions for the first time in this codebase.

**Alternative considered**: Parse `request.body()` manually with `urllib.parse.parse_qs` to
avoid the dependency entirely — rejected as reinventing a small, standard piece of a web
framework's job for no real benefit over the one-line addition of a widely-used, minimal
library already documented as FastAPI's own recommended path for form handling.

## 3. How does the UI reuse `/analyze`'s logic without duplicating it?

**Decision**: Extract the existing `POST /analyze` route's orchestration (retrieve bullets +
similar vacancies, load filter rules, build the prompt, call the resolved `LLMProvider`, run
`grounding.enforce()`, assemble the `Report`) into a plain function, e.g. `run_analysis(jd_text:
str, provider: LLMProvider) -> Report`, in `api.py`. The existing JSON route becomes a thin
wrapper: validate input, call `run_analysis()`, return it via `response_model=Report`. The new
`POST /ui/analyze` route becomes an equally thin wrapper: validate input (same rule), call the
same `run_analysis()`, render `_report.html` (or `_error.html`) with the result.

**Rationale**: The two routes differ only in input encoding (JSON body vs. HTML form) and output
encoding (JSON vs. rendered HTML) — the actual analysis logic, and the grounding guarantee it
carries, must be identical and must not be duplicated (a second copy is a second place for a
grounding-relevant bug to diverge). This is a refactor of existing code, not new business logic.

**Alternatives considered**: Have the HTML route make an internal HTTP call to `POST /analyze` —
rejected as needless overhead and a layering violation (a route calling another route over HTTP
within the same process) for no benefit over a direct function call.

## 4. Making the draft paragraph's grounding visible (FR-003)

**Decision**: Add a new field to `Report`: `draft_sentences: list[DraftSentence]`, where
`DraftSentence = {text: str, citation: Citation}`. `grounding.enforce()` already iterates
`candidate.draft_sentences` one at a time, appending the kept sentence's text to one list and
its citation to another, in lockstep — it already has the pairing, it just currently discards it
by flattening both into separately-shaped outputs (`draft_paragraph: str` joined with spaces, and
a `citations: list[Citation]` that also mixes in flags' citations first). This change makes
`enforce()` also emit the pairing structurally, so a template can render each sentence next to
its citation without guessing which of the flat `citations` entries (order-dependent, and mixed
with unrelated flag citations) corresponds to which part of the paragraph string.

**Backward compatibility**: `draft_paragraph` and `citations` are unchanged in both shape and
content — `draft_sentences` is purely additive. Existing consumers of `POST /analyze` (including
the existing automated test suite from [[003-analyze-report-generation]]) are unaffected;
`response_model=Report` gains one more field in its JSON output, which is a backward-compatible
change for any reasonable client.

**Rationale**: FR-003 explicitly requires "a visible association between each part of [the draft
paragraph] and the citation that grounds it," and Constitution Principle II is framed around
grounding actually mattering, not just being enforced invisibly. The current flat shape cannot
support this without the UI re-deriving a fragile guess at sentence boundaries and citation
ownership; a small, additive backend field removes the guesswork entirely.

**Alternatives considered**: Render the whole paragraph as one block with all citations listed
underneath it, unordered — rejected as not actually satisfying FR-003's "each part" requirement,
and the fix on the backend side is small enough that working around it in the UI isn't worth the
imprecision.

## 5. Handling errors and loading state without JSON status-code plumbing in HTMX

**Decision**: `POST /ui/analyze` always returns `200 OK` with one of three rendered partials:
the report (`_report.html`), a validation message (`_error.html`, empty/whitespace input — no
request to the backend's analysis logic is made), or a backend-failure message (`_error.html`,
a different message body, triggered when `run_analysis()` raises the same provider error the
JSON route already turns into a `502`). A `hx-indicator`-driven spinner shows while the request
is in flight; the submit control is disabled for the duration via HTMX's built-in
`hx-disabled-elt`, preventing an accidental duplicate submission.

**Rationale**: HTMX can swap content from non-2xx responses too, but doing so cleanly requires
extra client-side event wiring (`htmx:responseError`) for a distinction (validation vs. backend
failure) that's simpler to express as "always 200, vary the rendered partial" for a page whose
only consumer is a human reading rendered HTML — the JSON `POST /analyze` route keeps its
correct `422`/`502` status codes unchanged, since machine clients of that endpoint still need
them.

**Alternatives considered**: Propagate real HTTP status codes to the HTML route too and handle
them via `htmx:responseError` — rejected as unnecessary complexity for a page with no
programmatic consumer other than the browser itself.

## 6. Where `templates/` and `static/` live, and whether they survive packaging

**Decision**: Both directories live *inside* `src/vacancy_radar/`, next to `api.py`, not at the
repo root — and `api.py` resolves them via `Path(__file__).resolve().parent / "templates"` /
`"static"`, never a literal relative-path string.

**Rationale**: These are assets the FastAPI app itself serves, not repo-level configuration —
`data/` and `eval/` are legitimately repo-root concerns (user data, a maintainer tool
independent of the package), but a template the app renders belongs with the code that renders
it. A literal string like `"src/vacancy_radar/templates"` would only work by coincidence of the
process's current working directory: the Dockerfile runs `pip install .` (installing the
package into site-packages) and then starts `uvicorn` from `/app`, where `./src/...` happens to
still physically exist on disk post-build — but `__file__`-relative resolution is what actually
works correctly regardless of CWD or install method, since it points at wherever the *imported*
module actually lives.

Verified rather than assumed: built a minimal throwaway package with the same
`packages = ["src/<name>"]` wheel config as this project's `pyproject.toml`, with no `.git`
directory present (matching the Dockerfile's build context exactly — `COPY src/ ./src/` copies
no VCS metadata), and confirmed `pip install .` correctly bundles non-Python files
(`templates/index.html`, `static/x.js`) into the installed package under site-packages by
default. Hatchling's default wheel file-selection includes every file under a declared package
directory, not only `.py` files, with no extra `pyproject.toml` configuration required for this
project's existing `[tool.hatch.build.targets.wheel] packages = ["src/vacancy_radar"]` setting.

**Alternatives considered**: A top-level `static/`/`templates/` at the repo root — rejected per
the correction above; it would work today only because of the Dockerfile's incidental
CWD/source-tree overlap, not because it's actually served from the installed package.
