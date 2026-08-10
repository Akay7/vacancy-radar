# vacancy-radar

A local-first job application tracker. A markdown vault is the source of
truth; a derived LanceDB index provides hybrid BM25 + vector search; an MCP
server exposes read/write tools to any LLM client.

## Status

Vault, index, retrieval, CLI (read and write), and MCP server are all
implemented. Stage 9 (import) is too — conversationally, via
`create_vacancy`/`find_existing` over MCP (see
[docs/import-guide.md](docs/import-guide.md)), not an xlsx/CSV
importer; this project ships no spreadsheet parser or interchange
format.

## Install

```bash
uv sync --all-groups
```

## Getting started

Every command below expects a vault to already exist at `VAULT_PATH`
(or an explicit path, where the command takes one). Create one first:

```bash
uv run vacancy-radar init /path/to/vault
export VAULT_PATH=/path/to/vault
```

`init` is idempotent - running it again against the same path is a
no-op, not an error - and it never touches anything already in a
directory it adopts (see [design.md](openspec/changes/vault-init/
design.md) for the full rationale).

## Usage

```bash
uv run vacancy-radar --version
```

`list`, `show`, `search`, and `doctor` are read-only: they never write to
the vault or the index. Every command prints a Rich table for humans by
default; add `--json` for a machine-readable, stable, documented shape
suitable for piping (see `openspec/changes/archive/2026-08-06-cli-read/
design.md`'s `--json` contract).

```bash
# List vacancies, optionally filtered (--status, --company, --since,
# --needs-review, --stale-days), sorted by last activity.
uv run vacancy-radar list --status applied --status interview

# Show one vacancy or company - which kind it is is auto-detected.
uv run vacancy-radar show acme-corp

# Search the vault's index (see "Retrieval evaluation" below);
# --scores prints each hit's keyword/semantic rank and fused score.
uv run vacancy-radar search "backend engineer" --scores

# Report vault and index health: marker, index freshness, embedding
# model availability, and every warning collected while reading.
uv run vacancy-radar doctor
```

### Writing

`note`, `status set`, `add`, `new`, and `reindex` write to the vault.
Every write is append-only or a validated status transition (see
`openspec/changes/archive/2026-08-06-cli-write/design.md`) - nothing
here deletes or overwrites existing content, and there is no delete
command anywhere in the CLI. `note`, `status set`, and `add` accept a
vacancy by id, company name, or unambiguous fuzzy match, resolved the
same way `show` resolves its argument; an ambiguous match prints the
candidates and exits non-zero without writing anything. `--json`
follows the same stable, documented-shape convention as the read
commands above.

```bash
# A vacancy argument is an id, a company name/slug (if it resolves to
# exactly one vacancy), or an unambiguous fuzzy match - the same rule
# `show` uses. A company with several vacancies needs the vacancy id.

# Append a dated note. The filename is always derived from the date -
# never something you (or an LLM, at a later stage) supply.
uv run vacancy-radar note 2022-03-22-acme-corp-backend-engineer \
    "Called the recruiter, no news yet."

# Move a vacancy's status. Backward transitions need --force; the first
# move off 'found' needs --applied-date.
uv run vacancy-radar status set 2022-03-22-acme-corp-backend-engineer \
    applied --applied-date 2026-01-15
uv run vacancy-radar status set 2022-03-22-acme-corp-backend-engineer \
    found --force

# File a document (posting, email, note, or takehome) from a file or
# stdin. --external-id makes re-filing the same source (e.g. the same
# email thread) a no-op instead of a duplicate.
uv run vacancy-radar add 2022-03-22-acme-corp-backend-engineer \
    --kind email --title "Recruiter reply" --date 2026-01-16 \
    --external-id gmail-thread-42 --stdin < email.txt

# Create a new vacancy (and its company directory, if new).
uv run vacancy-radar new --company "Acme Corp" --role "Backend Engineer" \
    --url https://jobs.acme.example/1 --found-date 2026-01-10

# Rebuild the index from the vault's current state. Not required for
# ordinary use - every write above already reindexes its own effect
# eagerly, before returning, so it's searchable immediately.
uv run vacancy-radar reindex
```

## MCP server

`vacancy-radar-mcp` exposes the same `core.py` functions the CLI above
calls, as MCP tools/resources/prompts over stdio, for any MCP client
(Claude Desktop, etc.) - see `openspec/changes/mcp-server/design.md`
for the full rationale.

```bash
uv run vacancy-radar-mcp --vault /path/to/vault
```

**Vault path**: `--vault` if given, else the `VAULT_PATH` environment
variable; neither present fails startup naming both. MCP's client-
supplied-roots capability is deliberately not used here - it is
deprecated as of the protocol revision the MCP Python SDK speaks by
default (2026-07-28, SEP-2577), so `--vault`/`VAULT_PATH` are the only
two ways to point the server at a vault, exactly like configuring any
other stdio MCP server.

**Eleven tools**, matching `core.py`'s functions one for one - argument
marshalling only, no filtering/sorting/business logic of its own:

| tool | delegates to |
| ---- | ------------- |
| `list_vacancies` | `core.list_vacancies` |
| `get_company` | `core.get_company` |
| `get_vacancy` | `core.get_vacancy` |
| `search` | `core.search` |
| `read_document` | `core.read_document` |
| `resolve` | `core.resolve` |
| `find_existing` | `core.find_existing` |
| `append_note` | `core.append_note` |
| `set_status` | `core.set_status` |
| `add_document` | `core.add_document` |
| `create_vacancy` | `core.create_vacancy` |

`reindex` is deliberately **not** exposed - every write tool already
refreshes the index itself, and there's no legitimate reason for a
client-connected model to trigger a full rebuild (design.md's exposure
decision). `create_vacancy` *is* exposed, for conversational import
(see [docs/import-guide.md](docs/import-guide.md)): it does not
deduplicate, so its own tool description tells a calling model to call
`find_existing` first and only create when that returns no match.
`search`'s description tells the model to prefer `mode="keyword"` for
exact-name/proper-noun queries and leave `mode` unset (hybrid)
otherwise, citing the measured numbers in "Retrieval evaluation" below
- without that guidance a model defaults to hybrid for everything and
the per-category tuning goes unused. A typed `core.py` error (an
ambiguous match, an invalid status transition, a nonexistent vacancy)
surfaces as a structured tool result the calling model can read and
act on, never a raw crash.

**Two resources**: `vacancy-radar://companies` (every company's slug,
display name, and vacancy count) and `vacancy-radar://statuses` (every
status and the transitions permitted from it, read live from
`models.py`).

**Three prompts**: `prep_interview(company)` (dossier, postings, prior
notes, take-homes), `draft_reply(vacancy_id)` (prior correspondence, to
match tone), and `weekly_review()` (stale applications, pending
take-homes, vacancies tagged `needs_review`). An unresolved or
ambiguous `company`/`vacancy_id` returns a message saying so - never a
fabricated dossier.

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

Measured with `eval/`'s harness: 30 labelled queries (`eval/queries.yaml`,
across seven categories) run against the committed fixture vault
(`tests/fixtures/vault/`), scored with `recall_at_k`/`mrr` over each
mode's top 5 results. Reproduce it with `uv run vacancy-radar eval`.

**Overall, by mode:**

| mode | vector_weight | fusion | recall@5 | MRR |
| ---- | -------------- | ------------------- | -------- | ----- |
| keyword | — | — | 0.761 | 0.675 |
| semantic | — | — | 0.678 | 0.583 |
| hybrid | 0.5 | rrf | 0.672 | 0.541 |
| hybrid (**shipped default**) | 0.5 | linear_combination | 0.794 | 0.687 |

**Per category, keyword vs. semantic vs. the shipped hybrid default (recall@5):**

| category | keyword | semantic | hybrid (0.5, linear_combination) |
| ------------ | ----- | ----- | ----- |
| exact_name | 1.000 | 0.800 | 1.000 |
| technical | 0.800 | 0.800 | 1.000 |
| paraphrase | 0.250 | 0.750 | 0.250 |
| temporal | 1.000 | 0.250 | 1.000 |
| multi_result | 0.417 | 0.250 | 0.417 |
| filtered | 0.792 | 0.833 | 0.792 |
| negative | 1.000 | 1.000 | 1.000 |
| **overall** | **0.761** | **0.678** | **0.794** |

Keyword dominates `exact_name` (company/recruiter proper nouns) exactly
as hypothesized at stage 4, and semantic strictly dominates `paraphrase`
(queries sharing no content word with their target) — the one category
keyword structurally cannot serve at all. Both single modes are weak on
`multi_result` and one of them is weak on `temporal`, which top-5
recall@5 punishes when several correct documents compete for five
slots. **The fusion strategy default did not survive contact with
measurement**: RRF (stage 4's original default) *underperforms plain
keyword search* on this corpus — 0.672 vs. 0.761 overall recall@5,
identical across every `vector_weight` since RRF is rank-based and
weight-agnostic — while Linear Combination fusion at `vector_weight`
0.3–0.6 ties for the best result on every metric checked (0.3–0.6 score
identically; 0.7 ties on recall@5 but drops on MRR). `default_vector_weight`
is set to `0.5`, the middle of that tied band, and `fusion_strategy` to
`LINEAR_COMBINATION` — both a reversal of stage 4's guess, not a
confirmation of it. See `config.py`'s `SearchConfig` docstring and this
change's `tasks.md` (section 5) for the full per-category sweep.

**Limitations.** These numbers characterize the retrieval *design*
against a synthetic, generator-produced fixture vault — not a real
corpus of job-search correspondence. `tests/fixtures/generate.py`'s
proper nouns, phrasing patterns, and document lengths are artifacts of
the generator, not a sample of real vacancies, emails, or notes. Treat
this table as justification for a *default*, not a claim that
generalizes. See [docs/evaluation.md](docs/evaluation.md) for the
procedure to run a second eval against your own real vault after
import, and for which numbers to trust when retuning
`SEARCH_DEFAULT_VECTOR_WEIGHT`/`SEARCH_FUSION_STRATEGY` for your own
deployment.

**Future work, not built here.** `multi_result` and `temporal` recall
suggest a reranker could help beyond what fusion-weight tuning alone
achieves — not implemented in this change per its constraints. Whether
`negative`-category queries should return a score-floor-suppressed
empty result instead of five low-relevance ones is a real product
question, deliberately left open (see design.md): it would change
`search()`'s return contract and belongs in its own change if a real
vault's negative-query scores ever turn out close enough to real hits
to mislead.

## License

MIT — see [LICENSE](LICENSE).
