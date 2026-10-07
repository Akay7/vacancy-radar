## Why

opencode prints `unknown format "path" ignored in schema at path
"#/properties/result"` repeatedly on every start. `append_note` and
`add_document` return a `Path`; FastMCP derives their output schema from
that annotation as `{"result": {"type": "string", "format": "path"}}`.
`path` is not a standard JSON Schema format, so opencode's validator
warns once per occurrence.

## What Changes

- `append_note` and `add_document` return `str` (the path as a string)
  instead of `Path`, so their output schema is a plain string.
- Test that no write tool's output schema contains `format: "path"`.
- CHANGELOG entry.
- No change to the value returned on the wire (it was already the
  path's string form); `create_vacancy` already returns a string.

## Capabilities

### New Capabilities

### Modified Capabilities

(none — the reported path is unchanged; `.openspec.yaml` sets `skip_specs`)

## Impact

- `src/vacancy_radar/mcp_server.py`: two tool return types.
- `tests/test_mcp_server.py`, `CHANGELOG.md`.
