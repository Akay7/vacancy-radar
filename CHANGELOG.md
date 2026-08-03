# Changelog

All notable changes to this project are documented here.
Format follows [Keep a Changelog](https://keepachangelog.com/); this project uses [SemVer](https://semver.org/).

Bumps marked **[reindex]** change the embedding model or the vector-store schema — after updating, run `vacancy-radar reindex` (see `src/vacancy_radar/compat.py`, which detects this automatically via a version stamp).

## [Unreleased]

### Changed
- `vacancy-radar ingest`/`sync`/`reindex` now exit non-zero with a clear message if `VACANCY_DIR` doesn't exist at all, instead of silently reporting zero items — a missing directory is far more likely to be a misconfiguration than a deliberately-empty one. A missing `CV_DIR` is still tolerated (FR-007, unchanged): the tool can log vacancy history without a CV, just not the reverse.

## [0.1.0] - 2026-08-03

### Added
- Repo scaffold: FastAPI skeleton, docker-compose (app + Ollama under `--profile local`), pyproject.toml, ruff + pytest wiring.
- Ingestion CLI (`vacancy-radar ingest` / `sync` / `reindex`): CV bullets + vacancy folders → Chroma, upsert-keyed by natural key, per-file staleness manifest for incremental `sync`. **[reindex]** (schema v1)
- `POST /similar`: ranked similar-vacancy retrieval with outcomes and a duplicate-application flag, backed by a cosine-space `vacancies` collection. **[reindex]** (schema v2)
- `POST /analyze`: full grounded match report — score, red/green flags, gaps, similar vacancies, and a draft opening paragraph, with every claim citation-checked against retrieved source text (`grounding.enforce()`) before it can appear in a response. Pluggable `LLMProvider` (Claude API or Ollama). **[reindex]** (schema v3, cosine-space `experience_bullets`)
- `eval/run_eval.py`: four fully local, deterministic checks (grounding enforcement, bullet-retrieval recall@5/MRR, similar-vacancy precision@3, filter-rule consistency) against checked-in golden fixtures, gating CI alongside `ruff`/`pytest`.
- Minimal browser UI (`GET /`, `POST /ui/analyze`): paste a job posting, see the report rendered in place via htmx — no build step, no new service. `Report.draft_sentences` pairs each draft-paragraph sentence with its citation so grounding is visible, not just enforced.
