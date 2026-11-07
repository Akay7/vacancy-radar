## Context

See proposal.md - Why. Observed in opencode 1.18.33: the warning repeats
once per `Path`-returning tool. Confirmed by listing the built server's
tools: only `append_note` and `add_document` have `format: "path"` in their
output schema.

## Goals / Non-Goals

**Goals:**
- Output schemas contain only standard JSON Schema formats.

**Non-Goals:**
- Changing which value the tools report, or adding structured output types.

## Decisions

- **Return `str(path)` from the tool handlers**, keeping `core.*`
  returning `Path`. Matches `create_vacancy`, which already stringifies
  in the handler. Alternative: strip `format` from the schema post-hoc —
  rejected, more machinery than a return-type change.

## Risks / Trade-offs

- [Clients relying on the schema's `format: path`] → none known; the wire
  value is identical.
