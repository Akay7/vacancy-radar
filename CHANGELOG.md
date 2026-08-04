# Changelog

All notable changes to this project are documented here.
Format follows [Keep a Changelog](https://keepachangelog.com/); this project uses [SemVer](https://semver.org/).

Bumps marked **[reindex]** change the embedding model or the vector-store schema — after updating, run `vacancy-radar reindex` (see `src/vacancy_radar/compat.py`, which detects this automatically via a version stamp).

## [0.1.0] - 2026-08-04

### Added
- Repo scaffold: FastAPI skeleton, docker-compose (app + Ollama under `--profile local`), pyproject.toml, ruff + pytest wiring.
- Ingestion CLI (`vacancy-radar ingest` / `sync` / `reindex`): CV bullets + vacancy folders → Chroma, upsert-keyed by natural key, per-file staleness manifest for incremental `sync`. **[reindex]** (schema v1)
- `POST /similar`: ranked similar-vacancy retrieval with outcomes and a duplicate-application flag, backed by a cosine-space `vacancies` collection. **[reindex]** (schema v2)
- `POST /analyze`: full grounded match report — score, red/green flags, gaps, similar vacancies, and a draft opening paragraph, with every claim citation-checked against retrieved source text (`grounding.enforce()`) before it can appear in a response. Pluggable `LLMProvider` (Claude API or Ollama). **[reindex]** (schema v3, cosine-space `experience_bullets`)
- `eval/run_eval.py`: four fully local, deterministic checks (grounding enforcement, bullet-retrieval recall@5/MRR, similar-vacancy precision@3, filter-rule consistency) against checked-in golden fixtures, gating CI alongside `ruff`/`pytest`.
- Minimal browser UI (`GET /`, `POST /ui/analyze`): paste a job posting, see the report rendered in place via htmx — no build step, no new service. `Report.draft_sentences` pairs each draft-paragraph sentence with its citation so grounding is visible, not just enforced.
- Vacancy upload UI (`GET /ingest`, `POST /ui/ingest/draft`, `POST /ui/ingest/confirm`): upload a job posting/offer as an image, PDF, DOCX, or plain text file; company/position/date are drafted from it via the configured `LLMProvider` for review, outcome is always typed by hand, and confirming writes a real vacancy folder into `VACANCY_DIR` and embeds it immediately. Existing folder-based ingestion (`sources/`/`correspondence/`) now accepts the same image/PDF/DOCX formats.
- Vision-based drafting for image uploads (specs/007-vision-drafting): company/position/date for a photographed or screenshotted posting are now drafted from the configured `LLMProvider` reading the image directly (Claude's vision API, or Ollama's `images` field for a vision-capable local model), rather than local OCR. If the configured backend can't interpret the image, or the attempt fails, the maintainer sees a specific message explaining that image-based drafting isn't available with the current setup, and can still fill in every field manually.
- `vacancy-radar serve` — runs the web server (`--host`/`--port`/`--reload`) without needing to know the `uvicorn vacancy_radar.api:app` invocation; this is also what the Docker image now runs.

### Changed
- `docker-compose.yml`'s `data/user` mount is now read-write (was read-only) — the upload feature above is the first thing that ever needs to write to the maintainer's real vacancy history; `data/example` stays read-only.
- `vacancy-radar ingest`/`sync`/`reindex` now exit non-zero with a clear message if `VACANCY_DIR` doesn't exist at all, instead of silently reporting zero items — a missing directory is far more likely to be a misconfiguration than a deliberately-empty one. A missing `CV_DIR` is still tolerated (FR-007, unchanged): the tool can log vacancy history without a CV, just not the reverse.
- `Dockerfile`'s `CMD` now runs `vacancy-radar serve` instead of a raw `uvicorn` invocation.

### Removed
- The M1-scaffold `POST /ingest/vacancy` stub (always returned `501`, never implemented) — superseded by the upload UI above.
- Local OCR (`pytesseract`, `Pillow`, and the Dockerfile's `tesseract-ocr` system package) — superseded by vision-based drafting above. Image uploads no longer have any local text-extraction step; PDF/DOCX (`pypdf`/`python-docx`) are unaffected.
