## 1. Fix

- [x] 1.1 Change `append_note` and `add_document` to return `str(path)`; verify the server's tool listing has no `format: "path"` in any output schema
- [x] 1.2 Add a parametrised test in tests/test_mcp_server.py over `append_note`, `add_document`, `create_vacancy` asserting no `format: "path"`; verify it fails without 1.1 and passes with it
- [x] 1.3 Add a CHANGELOG `### Fixed` entry under `[Unreleased]` (tag v0.2.0 exists)

## 2. Verify

- [x] 2.1 Run `uv run pytest` and `ruff check`; then restart opencode and confirm the warnings are gone
