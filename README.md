# vacancy-radar

A local-first job application tracker. A markdown vault is the source of
truth; a derived LanceDB index provides hybrid BM25 + vector search; an MCP
server exposes read/write tools to any LLM client.

## Status

Early scaffolding. No vault, index, or MCP server yet.

## Install

```bash
uv sync --all-groups
```

## Usage

```bash
uv run vacancy-radar --version
```

## Development

```bash
uv run pytest
uv run ruff check .
uv run ruff format --check .
```

### Pre-commit hooks

Install the git hooks once per clone so lint/format issues are caught
before you commit (the same checks CI runs):

```bash
uv run pre-commit install
```

Run them on demand against all files:

```bash
uv run pre-commit run --all-files
```

## Retrieval evaluation

Filled in at the eval-harness stage.

| mode | weighting | recall@5 |
| ---- | --------- | -------- |
|      |           |          |

## License

MIT — see [LICENSE](LICENSE).
