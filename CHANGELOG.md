# Changelog

All notable changes to this project are documented here.
Format follows [Keep a Changelog](https://keepachangelog.com/); this project uses [SemVer](https://semver.org/).

Bumps marked **[reindex]** change the embedding model or the vector-store schema — after updating, run `vacancy-radar reindex` (see `src/vacancy_radar/compat.py`, which detects this automatically via a version stamp).

## [Unreleased]

### Added
- Repo scaffold: FastAPI skeleton, docker-compose (app + Ollama under `--profile local`), pyproject.toml, ruff + pytest wiring.
