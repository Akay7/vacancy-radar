## Why

`index/extract.py`'s PDF-text extraction (`extract_to_sidecar`) is
fully implemented and unit-tested, but unreachable from anything a
user can actually run: `core.reindex` calls `build_index` without
`extract_sidecars=True`, and no CLI command ever passes that flag
either — verified by actually running `vacancy-radar reindex` against
a vault with a PDF under `documents/` and confirming no sidecar gets
written. Stage 3's (`index-build`) own design.md Non-Goals section
named this gap and deferred it: "A CLI or MCP surface for triggering a
build or extraction (stages 8-9)... `build_index`/`extract_to_sidecar`
are library functions only." Neither stage 8 (`mcp-server`) nor stage
9 (`llm-import`) delivered it. A PDF attached to a vacancy today is
searchable by filename only, with no visible warning why — `reindex`'s
plain-text output never prints `IndexReport.warnings` at all, for any
warning kind.

Separately, and found while verifying the above: `vacancy-radar add
--file some.pdf` crashes with a raw `UnicodeDecodeError` traceback
instead of a typed, readable error.

## What Changes

- `core.reindex` gains `extract_sidecars: bool = False`, forwarded to
  `build_index` unchanged. Default stays `False` — this change makes
  the capability reachable, it does not flip stage 3's "must not
  silently create sidecar files on every run" default.
- `vacancy-radar reindex --extract-sidecars` (default off) passes that
  flag through. `reindex`'s plain-text output now prints every warning
  `IndexReport` carries — extraction warnings and every other kind
  (`vanished_source`, `stale_sidecar`, ...), all currently dropped
  silently in plain-text output regardless of this change's PDF focus.
  `--json` already includes `warnings`; unaffected.
- `add --file`/`--stdin` reject non-UTF-8 content with a clean CLI
  error naming the file and pointing at the actual PDF-attachment
  workflow (copy into `documents/`, `reindex --extract-sidecars`) —
  not an unhandled traceback. No change to `add_document`'s signature
  or to what content types `add` accepts; this is a failure-mode fix,
  not new binary-file support.
- README.md: replace the "Attaching a PDF" caveat (added ad hoc while
  diagnosing this) with the now-accurate, now-working workflow.

## Capabilities

### New Capabilities

- `sidecar-extraction-cli`: the `reindex --extract-sidecars` flag and
  `reindex`'s plain-text warning output — the CLI/core surface stage
  3's design.md deferred and neither stage 8 nor stage 9 delivered.

### Modified Capabilities

- `reindexing`: `core.reindex`'s signature gains `extract_sidecars`,
  forwarded to `build_index` unchanged; its returned `IndexReport`'s
  `warnings` field is populated when extraction runs.
- `cli-write-commands`: `add --file`/`--stdin` reject non-UTF-8
  content with a typed CLI error instead of an unhandled exception.

## Impact

- Modified files: `src/vacancy_radar/core.py` (`reindex` signature),
  `src/vacancy_radar/cli.py` (`reindex --extract-sidecars`, warning
  printing, `add`'s content-reading error handling), `README.md`.
- New tests: `tests/test_core.py` (`reindex(extract_sidecars=...)`),
  `tests/test_cli.py` (`reindex --extract-sidecars`, warning output,
  `add`'s non-UTF-8 error).
- No new runtime dependency. No new extractor. No change to
  `add_document`'s signature or `index/extract.py` itself.
