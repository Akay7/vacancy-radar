# vacancy-radar

## What it is

A local-first job application tracker. A markdown vault is the source of
truth; a derived LanceDB index provides hybrid BM25 + vector search; an MCP
server exposes read/write tools to any LLM client.

## Stack

- Python 3.12+ (CI covers 3.12/3.13/3.14), uv
  - The 3.12 floor is load-bearing: `core.py` and `mcp_server.py` use PEP
    695 `type` statements, which do not parse on 3.11.

## License

- MIT licensed

## Architectural invariants

These constrain every change, not just the current one:

1. The vault is the source of truth. The index is derived and disposable —
   deleting it and reindexing must always reconstruct equivalent state.
2. No state exists only in the database. Status, notes, IDs, and dates live
   in markdown frontmatter.
3. Writes are append-only, validated status transitions, or validated field
   edits that record what they changed in the vault. Never delete; never
   overwrite a document, a note, or anything a write did not validate first.
4. The MCP server contains no logic beyond argument marshalling. Every tool
   delegates to a shared core module that the CLI also calls.
5. Nothing writes to stdout except JSON-RPC. Diagnostics go to stderr.

## Roadmap

Stages, in order: package skeleton → vault model → vault reader → index
build → retrieval → eval harness → core API → CLI → MCP server → xlsx
migration.

Each stage change should implement only its own stage — do not scaffold or
design ahead for later stages.
