## Why

Stages 1-7 built a vault that can be read, searched, and written to, but
only from a human at a terminal. Stage 8 is what makes vacancy-radar
usable from an LLM client: an MCP server that exposes the same
`core.py` functions the CLI already calls, as tools, resources, and
prompts, over stdio. Per invariant 4, this is argument marshalling
only — the server's entire value is giving a model the same read/write
surface a human has, through a protocol a client like Claude Desktop
speaks natively, without any new business logic anywhere in this
change.

## What Changes

- Add `src/vacancy_radar/mcp_server.py`, entry point
  `vacancy-radar-mcp`, built on the official MCP Python SDK (the one
  new runtime dependency this change adds).
- Add six read tools (`readOnlyHint: true`): `list_vacancies`,
  `get_company`, `get_vacancy`, `search`, `read_document`, `resolve` —
  each a direct, unmodified call into the matching `core.py` function.
- Add three write tools (`readOnlyHint: false`, `destructiveHint:
  false`): `append_note`, `set_status`, `add_document` — same rule,
  calling `core.append_note`/`core.set_status`/`core.add_document`
  unchanged.
- Deliberately do not expose `reindex`, `create_vacancy`, or any stage
  9 import/migration capability — bulk and structural operations stay
  CLI-only, where a human reviews the outcome before it lands (see
  design.md).
- Add two resources: `vacancy-radar://companies` (slug, display name,
  vacancy count — loaded once so a model can resolve "the Acme thing"
  without a tool round-trip) and `vacancy-radar://statuses` (the
  `Status` vocabulary and `STATUS_TRANSITIONS` graph, read from
  `models.py` as data, never restated).
- Add three prompts: `prep_interview(company)`, `draft_reply
  (vacancy_id)`, `weekly_review()` — each composed from `core.py` read
  calls, returning a well-formed message referencing real vault
  content or a resolution failure, never a fabrication.
- Add vault-path resolution: explicit `--vault` argument, then
  `VAULT_PATH`, then a startup failure naming both mechanisms — reusing
  `config.resolve_vault_path`'s existing precedence and validation
  unchanged. **Deviates from the stage plan's roots-based precedence**:
  the installed MCP Python SDK's protocol revision (2026-07-28,
  SEP-2577) deprecates the entire roots capability (`roots/list`,
  `notifications/roots/list_changed`) and the high-level server class
  this change builds on exposes no supported hook for the
  `list_changed` notification at all — see design.md for the full
  reconciliation. The resolved vault path is fixed for the life of the
  process; every tool call passes it to its one `core.py` call via the
  stage 3 `index.store` seam's own per-path resolution, unchanged.
- Every tool description is treated as part of the interface: in
  particular, `search`'s description states when to prefer `keyword`
  mode over `hybrid`, referencing the stage 5 eval findings (hybrid's
  measured 0.5 default vector weight, keyword's edge on proper-noun/
  exact-name queries), so the model doesn't default to hybrid for
  everything the way it would with no guidance.
- Transport discipline: nothing is written to stdout except JSON-RPC
  frames; every diagnostic goes to stderr; the embedding model is not
  loaded at server start or for a keyword-mode search.

## Capabilities

### New Capabilities

- `mcp-read-tools`: the six read tools (`list_vacancies`,
  `get_company`, `get_vacancy`, `search`, `read_document`, `resolve`),
  each delegating to exactly one `core.py` function, with JSON schemas
  whose enum parameters are drawn from `models.py` and whose
  `readOnlyHint`/`openWorldHint` annotations are fixed.
- `mcp-write-tools`: the three write tools (`append_note`,
  `set_status`, `add_document`), same delegation and schema rules,
  `readOnlyHint: false`/`destructiveHint: false`/`openWorldHint:
  false`, and the safety properties that make them exposable to
  untrusted, model-relayed content (derived filenames, no path
  parameter, no delete/overwrite capability).
- `mcp-resources`: `vacancy-radar://companies` and `vacancy-radar://
  statuses`, read from the vault and from `models.py` respectively.
- `mcp-prompts`: `prep_interview`, `draft_reply`, `weekly_review`,
  each composing existing `core.py` read calls into one MCP prompt
  message.
- `mcp-vault-path`: the two-tier vault-path precedence
  (`--vault` > `VAULT_PATH` > startup failure naming both), resolved
  once at startup via `config.resolve_vault_path` unchanged. Named for
  what it resolves, not for MCP roots — this change does not use the
  roots capability (see design.md).
- `mcp-transport`: the stdio server itself — stdout/stderr discipline,
  lazy embedding-model loading, startup latency, the tool list's fixed
  exclusions (`reindex`, `create_vacancy`, any import/migration tool,
  any generic query/eval/exec tool), and how a `core.py` typed error
  surfaces to an MCP client.

### Modified Capabilities

(none — every tool in this change calls an existing, unmodified
`core.py` function; `config.resolve_vault_path`'s explicit-argument
seam, documented since stage 2 for exactly this purpose, is used as-is)

## Impact

- New file: `src/vacancy_radar/mcp_server.py`.
- New runtime dependency: the official MCP Python SDK (`mcp`). No
  others.
- Modified file: `pyproject.toml` — adds the dependency and the
  `vacancy-radar-mcp` entry point.
- New tests: `tests/test_mcp_server.py`, exercising every tool with
  `core.py` mocked (delegation), plus a real-vault integration pass for
  resources, prompts, vault-path precedence, and the stdout-purity/
  startup-latency checks. No test mutates `tests/fixtures/vault/`.
- No change to `core.py`, `cli.py`, `models.py`, `config.py`, or any
  `index/`/`vault/` module — this change is additive at the transport
  layer only.
- Downstream: stage 9 (xlsx migration) is unaffected; it lands as a
  CLI import path, not an MCP tool, per this change's exposure
  decision.
