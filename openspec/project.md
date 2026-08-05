# vacancy-radar

## What it is

A local-first job application tracker. A markdown vault is the source of
truth; a derived LanceDB index provides hybrid BM25 + vector search; an MCP
server exposes read/write tools to any LLM client.

## Stack

- Python 3.12, uv

## License

- MIT licensed

## Architectural invariants

These constrain every change, not just the current one:

1. The vault is the source of truth. The index is derived and disposable —
   deleting it and reindexing must always reconstruct equivalent state.
2. No state exists only in the database. Status, notes, IDs, and dates live
   in markdown frontmatter.
3. Writes are append-only or validated status transitions. Never delete,
   never overwrite.
4. The MCP server contains no logic beyond argument marshalling. Every tool
   delegates to a shared core module that the CLI also calls.
5. Nothing writes to stdout except JSON-RPC. Diagnostics go to stderr.

## Roadmap

Stages, in order: package skeleton → vault model → vault reader → index
build → retrieval → eval harness → core API → CLI → MCP server → xlsx
migration.

Each stage change should implement only its own stage — do not scaffold or
design ahead for later stages.
