# Importing an existing tracker by conversation

There is no importer in this codebase — no CSV/xlsx parser, no
interchange format, no batch script. If you already track your job
search in a spreadsheet, a notes app, or a half-abandoned Notion page,
you import it by pasting rows to Claude (or another MCP client) and
letting it call `create_vacancy` and `find_existing` directly, a batch
at a time, with you reviewing what it proposes before it writes
anything. This document is that conversation's playbook — mostly aimed
at the model doing the importing, but written for the human reading
over its shoulder too.

Every tracker has different columns, in a different language, with
different ideas about what counts as "found" versus "applied." Nothing
here tries to encode that mapping once for every tracker — the point
of doing this conversationally is that the mapping happens per tracker,
per batch, with a human confirming each one.

## 1. Triage first

Most rows in a long tracker are dead ends — an application that never
got a reply, a posting bookmarked and never pursued. Giving all of
them equal fidelity is weeks of work for no return. Before creating
anything:

- **Rows that got a reply, an interview, an offer, or a rejection**
  (i.e. anything past "applied" in spirit) get a full `create_vacancy`
  call, with whatever detail the tracker actually has.
- **Everything else** — no reply, no memory of following up — goes to
  `_archive/index.md` by hand as a one-line entry (company, role,
  date, source URL if known), not through `create_vacancy` at all.
  This is a plain markdown file a human edits directly; there's no
  tool for it, because there's no reason to give it the same ceremony
  as a live vacancy.

Ask the user, per row or per obvious group of rows ("everything before
2024 that says 'no response'"), which bucket it falls in before doing
either.

## 2. Work in batches of ten to twenty rows

A whole spreadsheet in one message exhausts context, and past a
certain point the model starts inventing field values it can no longer
see clearly. Batches of ten to twenty rows per turn keep the mapping
visible, keep any one turn's blast radius small enough to actually
read, and match the size a human can sanity-check in one sitting.

For each batch:

1. Propose the mapping for every row in the batch (company, role,
   status, dates, `stage_note`) as a table or list — not as tool
   calls yet.
2. The user confirms or corrects the mapping.
3. Only then call `find_existing`, then `create_vacancy`, for each row
   in the confirmed batch.
4. Verify with `vacancy-radar list` (see step 5) before starting the
   next batch.

## 3. Map stage vocabulary in the same pass

Trackers use their own words for pipeline stages — "phone screen,"
"waiting to hear back," "ghosted lol," "2. Runde." None of that is
`vacancy-radar`'s `Status` vocabulary
(`found`/`applied`/`screening`/`take_home`/`interview`/`offer`/
`rejected`/`ghosted`). When proposing a mapping:

- Pick the closest `Status` value for the tracker's stage column.
- Put the tracker's **original text verbatim** in `stage_note` — never
  discard it, even after mapping it to a `Status`. `stage_note` is
  free text; the original phrase is often more informative than the
  status enum it maps to ("recruiter went quiet after round 2" says
  more than `ghosted`).
- If a row's stage doesn't map cleanly to anything, propose your best
  guess and flag it in the batch summary — the user confirms or
  corrects it along with everything else in the batch, per step 2.

## 4. Derive role from the source URL when possible

Many job-board URLs carry the title in the path
(`.../jobs/senior-backend-engineer-1234`). When a tracker row has a
source URL but no separate title column, derive `role` from the URL's
slug rather than leaving it blank. When there's truly no way to tell
what the role was — no URL, no title column, nothing in free-text
notes — use `role="unknown"` and add `needs_review` to `tags`, per
`create_vacancy`'s own tool description. Don't guess a plausible-
sounding title from company name alone; a wrong role is worse than an
honest `unknown`.

The same applies to `found_date`: if the tracker has no date the
posting was found, only an applied date, pass that as `applied_date`
and synthesize `found_date` from it (same day is a reasonable default
absent better information), tagging the record `migrated` so it's
identifiable later as a date that was inferred, not observed.

## 5. Check before creating, then verify after

`create_vacancy` does not deduplicate — two calls with the same
company and role mint two distinct vacancies, not one. Before each
`create_vacancy` call, call `find_existing(company, source_url)` first.
If it returns a match, skip creating and tell the user instead of
silently overwriting or duplicating anything (there's no overwrite
path either way — `find_existing` is what keeps you from needing one).

After each batch, run:

```bash
uv run vacancy-radar list --company "<company from this batch>"
```

or, for a broader check:

```bash
uv run vacancy-radar list
```

and read it against what you meant to create. This is the point where
a wrong status, a garbled role, or a batch that silently only half-ran
(see "Failure mode," below) is easiest to catch — while the mapping is
still in your head, not three batches later.

## 6. Work through needs_review afterwards

Once every batch is imported, go back over the rows tagged during
import:

```bash
uv run vacancy-radar list --needs-review
```

For each one, see if there's now enough context (a company name, a
half-remembered title) to fill in the real `role` — `edit_vacancy`
sets it in place, whether it was merely `unknown` at import time or
recorded wrong, and records the correction in the vacancy's edit
history. Drop the `needs_review` tag in the same call, since
`edit_vacancy`'s `tags` replaces the whole list: pass the tags you
want to keep. Use it for the other fields a hurried import got wrong
too — a `source_url` you only found later, a recruiter's name.

## Worked example: non-English headers

A tracker exported from a spreadsheet with German column headers:

| Firma | Rolle | Status | Datum | Link |
| --- | --- | --- | --- | --- |
| Beispiel GmbH | Backend Entwickler | Interview am 14.03. | 2026-02-01 | https://jobs.beispiel.example/backend-entwickler-88 |
| Muster AG | (leer) | Abgelehnt | 2026-01-20 | https://jobs.muster.example/12345 |
| Kleinfirma KG | Werkstudent Data | Beworben, keine Antwort | 2026-02-10 | — |

Proposed mapping for this batch:

| row | company | role | status | found_date | applied_date | stage_note | tags |
| --- | --- | --- | --- | --- | --- | --- | --- |
| 1 | Beispiel GmbH | Backend Entwickler | `interview` | 2026-02-01 | 2026-02-01 | "Interview am 14.03." (original) | — |
| 2 | Muster AG | unknown | `rejected` | 2026-01-20 | 2026-01-20 | "Abgelehnt" | `needs_review` (URL slug `12345` carries no title) |
| 3 | Kleinfirma KG | Werkstudent Data | `applied` | 2026-02-10 | 2026-02-10 | "Beworben, keine Antwort" | `migrated` (no source URL; row 3 is triage-only per step 1 unless the user says otherwise) |

After the user confirms, the calls (row 1 shown; the others follow the
same shape):

```
find_existing(company="Beispiel GmbH", source_url="https://jobs.beispiel.example/backend-entwickler-88")
# -> [] (no match)

create_vacancy(
    company="Beispiel GmbH",
    role="Backend Entwickler",
    source_url="https://jobs.beispiel.example/backend-entwickler-88",
    found_date="2026-02-01",
    status="interview",
    applied_date="2026-02-01",
    stage_note="Interview am 14.03.",
)
```

Row 2's URL (`.../12345`) carries no title, so `role="unknown"` and
`tags=["needs_review"]`, per step 4. Row 3 has no source URL at all —
per step 1, a row without a URL and without a reply is usually a
triage candidate for `_archive/index.md`, not a `create_vacancy` call;
it's included here only to show the `migrated` convention on a
same-day `found_date`/`applied_date` guess, and would normally be
confirmed with the user before creating anything for it.

## Failure mode: this is not transactional

There is no batch commit, no rollback, no dry run. If a batch of ten
`create_vacancy` calls is interrupted after the sixth — a dropped
connection, a client crash, the user closing the conversation — six
real vacancies exist in the vault and four rows are still unimported,
with nothing in the vault marking that the batch was cut short.

This is why batches stay small (step 2) and are verified before moving
on (step 5): recovering from an interrupted batch means running
`vacancy-radar list` to see exactly what landed, then re-running the
remaining rows — not reconciling a half-committed transaction, because
there isn't one to reconcile. A batch of ten to twenty rows makes "what
landed" something you can read off one `list` call rather than
something you have to reconstruct.
