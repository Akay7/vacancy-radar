<!--
Sync Impact Report
- Version change: 1.0.0 → 2.0.0
- Modified principles:
  - III. Pluggable, Provider-Agnostic LLM → III. Standard Integration Layers via LangChain
    (backward-incompatible redefinition: the custom `LLMProvider` ABC and hand-rolled
    `Retriever`/`ChromaStore` wrapper are no longer the compliant mechanism — LangChain's
    `BaseChatModel` and `VectorStore`/`Retriever` interfaces are)
- Added sections: none (existing principle broadened in place; renamed for accuracy since its
  scope now explicitly covers retrieval, not only generation)
- Removed sections: none
- Clarified: IV. Simplicity & Right-Sized Infra (YAGNI) — added an explicit note reconciling
  the LangChain adoption in Principle III with this principle's "new dependencies must justify
  their addition" rule, and its Technology Constraints entries updated to name the LangChain
  packages this project now standardizes on.
- Templates requiring updates: none checked in this run — command scope is constitution-only;
  dependent templates/commands read this file at runtime (see Scope Guard). The actual
  migration of `src/vacancy_radar/llm/` and `src/vacancy_radar/retriever.py`/`chroma_store.py`
  to LangChain is a deferred, non-governance intent — see Next Actions in the command output.
- Follow-up TODOs: none within this file.
-->

# Vacancy Radar Constitution

## Core Principles

### I. Local-First & Private by Default
Vacancy Radar MUST run entirely on the user's own machine against the user's own data.
CV bullets, vacancy history, correspondence, and any other personal career data MUST NOT be
committed to this repository or baked into a built image. `data/example/` (sanitized, fake)
is the only personal-looking data allowed in the repo, used for README examples and CI.
Docker images and default configs MUST work unmodified against a user-supplied `CV_DIR` /
`VACANCY_DIR` bind mount.

**Rationale**: the tool's entire value proposition is querying a person's private job-search
history; leaking that data (into git history, into a shared image, into a third-party service
by default) would be a worse outcome than the tool not existing.

### II. Grounded Generation (NON-NEGOTIABLE)
Every generated claim in a match report or draft opening paragraph MUST cite its source: an
experience bullet or a filter rule. Output containing an achievement, skill, or claim that
cannot be traced to retrieved source material MUST be treated as a bug, not a style issue.
`/analyze` and any future generation endpoint MUST carry this citation requirement through to
the eval harness (grounding check is a required eval, not optional).

**Rationale**: a cover-letter draft that invents an achievement is worse than no draft — the
README states this explicitly as the reason citations are required on every generated claim.

### III. Standard Integration Layers via LangChain
LLM generation and retrieval MUST go through LangChain's abstractions rather than hand-rolled
per-vendor/per-store clients:
- **Generation**: `langchain_core.language_models.BaseChatModel` — `ChatAnthropic` (from
  `langchain-anthropic`) for the hosted Claude backend, `ChatOllama` (from `langchain-ollama`)
  for the fully local/offline backend. Calling code (API routes, the eval harness) MUST NOT
  special-case a specific provider and MUST depend only on the shared interface
  (`.invoke()` / `.with_structured_output()`), never a vendor SDK call directly.
- **Retrieval**: LangChain's `VectorStore` / retriever interfaces — `langchain-chroma`'s
  `Chroma` wrapping the same embedded/persistent store — instead of a hand-rolled wrapper
  around the Chroma client.

At minimum, a hosted LLM provider (Claude API) and a fully local/offline provider (Ollama, via
the `local` docker-compose profile) MUST both remain functional through the same
`BaseChatModel` interface.

**Rationale**: keeps a fully offline mode available (no API key, no data leaving the machine)
as a first-class option, not an afterthought bolted onto a Claude-only implementation — and
avoids this repo re-implementing and re-verifying request/response handling, structured
output, retries, and vector-store integration that LangChain's maintained integrations already
solve. A hand-rolled client per vendor is duplicated maintenance for a well-solved problem, not
a meaningful abstraction this project needs to own.

### IV. Simplicity & Right-Sized Infra (YAGNI)
Prefer embedded/serverless components over standalone services until actual data volume or
concurrency requires otherwise (e.g., Chroma runs embedded/persistent-mode — including through
LangChain's `Chroma` wrapper — not as a separate server process). Do not add infrastructure,
abstractions, or configuration for hypothetical future scale or features not on the current
[Roadmap](../../README.md#roadmap). New dependencies must justify their addition against this
principle: "LangChain already solves this integration problem correctly" is the justification
for the specific LLM/retrieval packages named in Principle III — it is not a blanket license to
adopt other LangChain components (its agent/orchestration framework, additional document
loaders, etc.) for problems this project doesn't actually have.

**Rationale**: this is a single-user, few-thousand-vector tool; matching infra weight to real
load keeps `docker compose up` fast and keeps the project approachable for its one maintainer.
Depending on LangChain's chat-model and vector-store integrations is judged to reduce real
maintenance weight — less hand-written, per-vendor request/response code to keep correct — not
add it, which is why it's compatible with this principle rather than an exception carved out
against it.

### V. Test & Lint Gates
`ruff` (lint) and `pytest` (tests) MUST pass before a change is considered done. New API
endpoints, retrieval logic, and ingestion/upsert logic MUST ship with test coverage in
`tests/`. This applies equally to the eval harness (`eval/run_eval.py`) where it exercises
retrieval or generation code paths.

**Rationale**: codifies the gates already wired into this repo (`ruff`, `pytest`, configured in
`pyproject.toml`) as a project-wide expectation rather than an implicit convention.

### VI. Regenerable Derived State
The Chroma vector store is a disposable cache derived from git-tracked source (CV bullets,
vacancy `vacancy.yaml` folders) — it is NEVER the source of truth and MUST NEVER be committed.
Ingestion MUST be upsert-keyed by natural key so the store can be deleted and rebuilt from
source data at any time without data loss.

**Rationale**: source-of-truth stays human-readable and git-tracked (per the architecture
diagram in the README); the embedding/index layer must stay swappable (models, chunking,
embedding dimension) without risking the user's actual career data.

## Technology Constraints

- API layer: FastAPI (async), Python >= 3.11.
- Vector store: Chroma, embedded/persistent mode only, accessed via LangChain's `Chroma`
  vector store (`langchain-chroma`) — no standalone Chroma server dependency.
- Embeddings: local `sentence-transformers` models (default `BAAI/bge-small-en-v1.5`) — no
  embedding calls to a paid API.
- Generation: LangChain `BaseChatModel`; supported backends are Claude API (`langchain-anthropic`'s
  `ChatAnthropic`) and Ollama (`langchain-ollama`'s `ChatOllama`, local).
- Data model: one folder per vacancy (`data/user/vacancies/YYYY-MM-DD_company-slug_position-slug/`),
  with `vacancy.yaml` as the source-of-truth record plus posting snapshots, correspondence, and
  generated analysis alongside it.
- Packaging: `pyproject.toml` / hatchling; lint via `ruff` (`select = ["E","F","I","UP","B"]`,
  line-length 100); tests via `pytest` under `tests/`.

## Development Workflow

- Single maintainer project, developed feature-by-feature against the
  [Roadmap](../../README.md#roadmap): ingestion CLI → `/similar` → `/analyze` → eval harness →
  minimal UI → `v0.1.0`.
- Spec-driven changes (this Spec Kit workflow) are the expected path for any new feature or
  behavior change: `/speckit-specify` → `/speckit-plan` → `/speckit-tasks` → `/speckit-implement`.
- CI and README examples run only against `data/example/` (sanitized/fake data) — never against
  real personal data.
- Every feature that adds or changes a generation path MUST update or extend the eval harness
  (grounding check, retrieval recall/MRR, similar-vacancy precision, filter-consistency) rather
  than relying on manual spot-checks alone.

## Governance

This constitution supersedes ad hoc practice for this repository. All specs, plans, and task
lists produced by the Spec Kit workflow MUST be checked against these principles before being
marked ready for implementation; a plan that knowingly violates a principle MUST document the
violation and justification (e.g., in the plan's Complexity Tracking section) rather than
silently deviating.

Amendments are made via `/speckit-constitution`: propose the change, update this file, record
the version bump and rationale in the Sync Impact Report at the top of this file. Versioning
follows semantic rules — MAJOR for backward-incompatible principle removal/redefinition, MINOR
for a new principle or materially expanded guidance, PATCH for clarification/wording only.

**Version**: 2.0.0 | **Ratified**: 2026-07-31 | **Last Amended**: 2026-08-04
