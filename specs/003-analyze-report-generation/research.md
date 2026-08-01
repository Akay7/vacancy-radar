# Phase 0 Research: `/analyze` Full Report Generation

No open `NEEDS CLARIFICATION` markers remain in the Technical Context. The decisions below turn
the spec's resolved clarifications (categorical rubric-based band, filter-rules file, silent
omission of ungroundable claims) into concrete technical choices — several of which revise the
grounding *mechanism* originally sketched in the M1 scaffold's stub docstrings, with rationale.

## Decision: One shared, provider-agnostic grounding validator (not native Claude citations)

**Decision**: Neither provider uses Anthropic's native `citations: {enabled: true}` document
content-block feature. Instead, both providers are prompted to produce structured JSON where
every flag and every draft-paragraph sentence carries an explicit `quote` + `source_id` pair
(the same shape as the existing `Citation` model), and a single shared function —
`grounding.enforce()` — validates every such pair against the actual retrieved bullets/filter-
rule text *after* either provider returns, stripping anything that doesn't verbatim-match
(whitespace/case-normalized substring check) before the response is built.

**Rationale**: The claude-api skill confirms native citations (`citations: {enabled: true}` on
`document` blocks) are **incompatible with `output_config.format`** (returns a 400) — and this
feature needs structured output (score/flags/gaps/draft_paragraph together) more than it needs
native citation metadata. Native citations also only attach to Claude's own free-text response,
with no equivalent on Ollama at all (`llm/ollama.py`'s own docstring already says grounding
there is "prompt-enforced citations, validated post-hoc" — there is no native alternative to
choose between). Building the native-citation-block-parsing path for Claude AND a separate
prompt-validated path for Ollama would mean two different code paths enforcing the same
Constitution II requirement, with two different bug surfaces — a direct YAGNI/Constitution IV
violation when one shared path enforces the identical guarantee for both. Centralizing the
check *outside* both providers is also strictly safer: it catches a provider's own prompt-
following slipping, rather than trusting each provider to self-enforce (defense in depth for a
NON-NEGOTIABLE constitutional principle).

**Alternatives considered**: Native citations for Claude + prompt-validation for Ollama —
rejected for the reasons above. Trusting each provider to self-validate its own output —
rejected because it means Constitution II's guarantee depends on every future provider
implementation getting it right individually, rather than one always-applied checkpoint.

## Decision: Structured output per provider

**Decision**: `ClaudeProvider` requests JSON via `output_config.format` with a `json_schema`
covering `match_band`, `flags[]` (each with `label`, `severity`, `reason`, `quote`,
`source_id`), `gaps[]` (plain strings, no citation required per spec Assumptions), and
`draft_sentences[]` (each with `text`, `quote`, `source_id`) — deliberately *not* the final
public `Report` shape (see data-model.md's `CandidateReport`). `OllamaProvider` prompts for the
identical JSON shape in plain text (no structured-output enforcement available on a local
Ollama server) and parses the response with `json.loads()`, retrying the request once with a
"your last response wasn't valid JSON, return only JSON" follow-up if parsing fails.

**Rationale**: `output_config.format` is confirmed available on Claude (`anthropic` 0.120.2 is
installed, well past when this shipped) and guarantees valid JSON matching the schema — the
right tool for Claude. Ollama has no equivalent guarantee, so a one-retry-then-fail approach is
the simplest robust handling (Constitution IV) — for a single local model call, more elaborate
retry/backoff machinery isn't justified at this project's scale.

**Alternatives considered**: Using Claude's tool-use (`tool_choice: {type: "tool"}`) instead of
`output_config.format` for the candidate report — rejected as an unnecessary alternative
mechanism when `output_config.format` already does exactly this job and is documented as the
recommended approach for structured JSON extraction.

## Decision: Match band derivation

**Decision**: The match band (`strong` / `good` / `weak` / `poor`) is produced by the LLM itself
as part of the same structured JSON response, guided by an explicit rubric embedded in the
prompt: compare the JD's stated requirements against the retrieved bullets and similar-vacancy
history across four fixed dimensions — required skills present, experience-level match,
domain/industry match, and evidenced impact — then classify holistically. The rubric text is a
fixed constant in the prompt-building code, not user-configurable.

**Rationale**: The clarified answer ("categorical band... derived from a rubric") calls for
structure in the *judgment process*, not for a separate hand-built scoring engine — building a
deterministic rule-based scorer comparing arbitrary JD text against arbitrary bullet text would
be a much larger, more fragile undertaking than prompting an already-capable LLM with explicit
criteria (Constitution IV). The four dimensions are the natural breakdown of "does this person's
real experience match this posting," and are stable enough to hardcode; per spec Assumptions,
the exact rubric criteria are an implementation detail, not a fixed business rule.

**Alternatives considered**: A separate pre-LLM keyword-overlap scorer feeding a numeric input
to the LLM — rejected as needless complexity when the LLM can read both texts directly and
apply the rubric itself.

## Decision: Filter-rules file

**Decision**: A new `filter_rules.py` module with one function, `load_filter_rules(path:
Path) -> str`, defaulting to `data/user/filter-rules.md` (mirroring `CV_DIR`'s convention of
living under the user's own data directory). Returns the file's raw text if present, or an
empty string if absent — an absent file is a valid, non-error state (FR-007).

**Rationale**: Matches the resolved clarification exactly (a plain-text file of personal
dealbreakers/preferences) and reuses the existing `data/user/` convention already established
for CV bullets and vacancy folders, rather than inventing a new location or format.

**Alternatives considered**: An environment variable holding the rules inline — rejected as
awkward for anything longer than a one-liner, and inconsistent with how CV bullets are already
supplied (a file, not an env var).

## Decision: Bullet retrieval (`query_bullets`) — no similarity threshold

**Decision**: Implement `Retriever.query_bullets(query_text, top_k=5)` analogously to
`query_similar_vacancies()` (embed the JD, cosine-query `experience_bullets`, return the top
`top_k`), but **without** a `MIN_SIMILARITY`-style cutoff — always return up to `top_k` bullets
regardless of score, letting the grounding validator (not retrieval) be the only gate on what
ends up in the final report.

**Rationale**: For `/similar`, filtering weak matches directly serves the user-facing "don't
show irrelevant vacancies" requirement (SC-002 there). For `/analyze`, the retrieved bullets are
internal LLM context, not shown directly to the user — supplying the LLM with its best 5
candidates (even if only loosely relevant) gives it more material to reason over, and any bullet
it doesn't actually use simply isn't cited. Thresholding here would only risk starving the model
of context with no corresponding user-facing benefit.

**Alternatives considered**: Applying the same `MIN_SIMILARITY = 0.6` cutoff from
[[002-similar-retrieval]] — rejected per the above; that threshold was calibrated for a
user-facing relevance judgment, not an internal retrieval-augmentation step.

## Decision: Extend the cosine-space collection metadata to `experience_bullets`

**Decision**: Add `BULLETS_COLLECTION_METADATA = {"hnsw:space": "cosine"}` alongside the
existing `VACANCIES_COLLECTION_METADATA` in `ingest.py`, wired into the same `upsert`/
`reset_collection` call sites used for bullets. Bump `compat.CURRENT_STAMP.schema_version`
again (e.g. `"2"` → `"3"`) so the existing auto-reindex mechanism ([[001-ingestion-cli]]) picks
up the change on the next `ingest`/`sync`.

**Rationale**: `experience_bullets` was created under Chroma's default (L2) space in
[[001-ingestion-cli]], before any feature needed similarity search over it. `query_bullets()`
needs the same bounded, thresholdable cosine similarity that [[002-similar-retrieval]] already
established for `vacancies` — reusing the identical mechanism (rather than inventing a
bullets-specific one) is the direct continuation of that decision, and the compat-stamp
auto-reindex already exists precisely to handle "the embedding space changed underneath you."

**Alternatives considered**: Leaving bullets on L2 space and working with raw distance in
`query_bullets()` — rejected for the same reason [[002-similar-retrieval]] rejected it: no
stable, explainable bound to reason about, and no threshold is even needed here (previous
decision), but cosine is still the more natural space for sentence embeddings generally and
costs nothing extra to standardize on.

## Decision: `Report.score` becomes a match-band literal

**Decision**: Change `Report.score: float` to `Report.score: Literal["strong", "good", "weak",
"poor"]` in `models.py`. The field name `score` is kept (not renamed to `match_band`) to
minimize disruption to the one field `Report` already had for this purpose — its meaning
changes, per FR-005, but nothing else consumes this field yet ([[002-similar-retrieval]]'s
`SimilarVacancy` is a separate model; `/analyze` has never been implemented).

**Rationale**: A `float` score implies a precision the underlying LLM judgment can't honestly
deliver (SC guidance in the spec's own quality bar, and the explicit clarification answer
rejecting a bare percentage). Since nothing outside this feature depends on `score`'s current
type, changing it now is free.

**Alternatives considered**: Adding a new `match_band` field alongside the old `score: float` —
rejected as carrying a field with no defined meaning or producer, which is worse than a clean
type change with no real consumers yet.

## Decision: `httpx` moves from dev-only to a main dependency

**Decision**: Move `httpx>=0.27` from `[project.optional-dependencies].dev` to `[project]`'s
main `dependencies` list in `pyproject.toml`.

**Rationale**: `OllamaProvider.analyze()` needs to make a real HTTP call to a local Ollama
server (`OLLAMA_HOST`) at runtime, in production — not just under test. `httpx` is already
installed transitively (via `anthropic`'s and `fastapi`'s own dependencies) and already used in
this project's dev/test tooling, so it's the natural choice over adding a new HTTP library like
`requests` (Constitution IV).

**Alternatives considered**: Python's stdlib `urllib.request` — avoids the dependency-list
change entirely, but `httpx` is already present in the dependency tree regardless, and using the
stdlib here would mean two different HTTP-calling idioms in the codebase for no real benefit.
