# vacancy-radar

A local-first job application tracker. A markdown vault is the source of
truth; a derived LanceDB index provides hybrid BM25 + vector search; an MCP
server exposes read/write tools to any LLM client.

## Status

Early scaffolding. No vault, index, or MCP server yet.

## Install

```bash
uv sync --all-groups
```

## Usage

```bash
uv run vacancy-radar --version
```

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
mode's top 5 results. Reproduce it with `uv run vacancy-radar _eval`
(private; the public `eval` command lands at stage 6).

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
the generator, not a sample of real vacancies, emails, or notes. A
second eval run against a real vault after import belongs in stage 9's
documentation; until then, treat this table as justification for a
*default*, not a claim that generalizes — `SearchConfig`'s existing
environment-variable overrides (`SEARCH_DEFAULT_VECTOR_WEIGHT`,
`SEARCH_FUSION_STRATEGY`) remain the way to retune per-deployment if a
real vault's numbers disagree.

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
