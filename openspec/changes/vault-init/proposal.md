## Why

Every command in this codebase resolves its vault via
`config.resolve_vault_path`, which requires the target to already
exist, be a directory, and already contain a `.vacancy-radar/` marker
— `VaultNotFoundError` otherwise. Nothing anywhere in the CLI,
`core.py`, or the MCP server can create that marker: a first-time user
has to `mkdir -p /path/.vacancy-radar` by hand before `list`, `new`, or
any other command will run at all. This change adds the one command
that closes that gap: `vacancy-radar init`.

## What Changes

- Add `core.init_vault(path: str | Path | None = None) -> VaultInitResult`
  (`path: Path`, `created: bool`): creates the target directory (and
  its parents) if it doesn't exist, and the `.vacancy-radar/` marker
  inside it if that's missing — idempotent, never destructive. Uses
  the same explicit-argument-then-`VAULT_PATH`-then-typed-error
  precedence every other `core.py` function already uses, via a new,
  narrower resolution helper in `config.py` that doesn't require the
  marker to already exist (see design.md — `resolve_vault_path`
  itself is unchanged).
- Add `vacancy-radar init [PATH]`: `PATH` is an optional positional
  argument; omitted falls back to `VAULT_PATH`, matching every other
  CLI command's env-var-only convention (no existing command takes a
  `--vault` option). Renders through the existing
  `_render_write_outcome` helper, same `--json` shape as `new`/`add`.
- No vault scaffolding beyond the marker directory — no starter
  `_company.md`, no README, no `.gitignore`, no `git init`. An
  initialized vault is exactly the empty-marker vault every test's
  `_init_vault` helper already builds by hand.
- **Not exposed over MCP.** The MCP server resolves one fixed vault
  path once at startup and serves it for the process's whole lifetime
  (stage 8 design.md decisions 7-8) — there is no point in that
  lifecycle where creating a *different* vault at a caller-supplied
  path is meaningful, and the stage 8/9 constraint against any tool
  taking a caller-supplied filesystem path for writing already rules
  it out. This mirrors `reindex`'s existing shape: a `core.py`
  function the CLI exposes and the MCP server deliberately does not.
- README.md: a short "Getting started" note showing `vacancy-radar
  init` before the first `list`/`new` call — today the README jumps
  straight to commands that assume a vault already exists.

## Capabilities

### New Capabilities

- `vault-init`: `core.init_vault` and the `vacancy-radar init` CLI
  command — idempotent vault creation, the explicit-path/`VAULT_PATH`
  precedence it uses, and its `--json` outcome contract.

### Modified Capabilities

- `cli-write-commands`: the "every write command exits 0 on success,
  non-zero on a typed error" requirement's enumerated command list
  (`note`, `status set`, `add`, `new`, `reindex`) gains `init`.

## Impact

- Modified files: `src/vacancy_radar/config.py` (new resolution
  helper, factored out of `resolve_vault_path`'s existing precedence
  logic — no change to `resolve_vault_path`'s signature, behavior, or
  messages), `src/vacancy_radar/core.py` (new `init_vault` function
  and `VaultInitResult`), `src/vacancy_radar/cli.py` (new `init`
  command), `README.md` (Getting started note).
- New tests in `tests/test_config.py` (or wherever the resolution
  helper's own tests live today), `tests/test_core.py`
  (`init_vault`), `tests/test_cli.py` (`init` command).
- No new runtime dependency. No MCP tool. No change to any other
  command's behavior.
