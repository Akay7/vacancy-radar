# Retrieval evaluation: real-vault procedure

README.md's [Retrieval evaluation](../README.md#retrieval-evaluation)
table is measured against `tests/fixtures/vault/` — a synthetic,
generator-produced vault (`tests/fixtures/generate.py`). Its proper
nouns, phrasing patterns, and document lengths are artifacts of the
generator, not a sample of real vacancies, emails, or notes. **Those
numbers characterize the retrieval design on adversarial fixtures.**
They justify a *default* (`vector_weight=0.5`,
`fusion_strategy=linear_combination`); they are not a claim that
generalizes to a real corpus. Trust them for "which default should
`SearchConfig` ship," not for "how well will this actually work on my
job search."

The numbers to trust for retuning that default, once you have a real
vault with real search history in it, are the ones this document's
procedure produces — run once you have enough real content and real
queries to make them meaningful, not shipped here, because this
change's own fixture-generated vault has none.

## Why `vacancy-radar eval` doesn't do this directly

`vacancy-radar eval` (`cli.py`'s `eval_command`) is hard-coded to
`tests/fixtures/vault/` and `eval/queries.yaml` — it builds a
throwaway index from the fixture vault every time and takes no `--vault`
argument. That's deliberate: `eval/queries.yaml`'s `expected_doc_ids`
are hand-labeled against the fixture vault's specific companies,
roles, and documents (see `eval/queries.yaml`'s own header comment) —
reusing it against a different vault would score every query against
the wrong answer key, not a smaller version of the right one. A real
vault needs its own labelled query set, in the same shape, hand-written
against its own content — there's no way around that per-corpus labeling
step, real or fixture.

## Procedure

1. **Have a real vault with real content.** Import your tracker first
   (see [import-guide.md](import-guide.md)) — there's nothing to
   evaluate retrieval against before that.

2. **Write your own labelled query set**, in `eval/queries.yaml`'s
   shape (`id`, `query`, `expected_doc_ids`, `category`, `note`,
   optional `filter`) but pointed at your real vault's content. Find
   real `doc_id`s with:

   ```bash
   uv run vacancy-radar search "<something you know is in your vault>" --scores
   uv run vacancy-radar show <vacancy-id>
   ```

   A vacancy-row hit's `doc_id` is `vacancy:<vacancy_id>`; a document
   hit's is the document's own `id` (same convention `eval/queries.yaml`
   documents). Aim for the same category spread the fixture set uses —
   `exact_name`, `technical`, `paraphrase`, `temporal`, `multi_result`,
   `filtered`, `negative` — so the real-vault table lines up column
   for column against README's fixture table. Ten to twenty queries is
   enough to see a signal; you don't need thirty just because the
   fixture set has thirty.

   Save this file outside the repo (it will reference your real
   company/vacancy names) — nothing under `eval/` in this repo should
   ever contain real data, per this project's own constraint.

3. **Build (or refresh) your real vault's index:**

   ```bash
   uv run vacancy-radar reindex --vault /path/to/your/vault
   ```

   (Not usually necessary — every write already reindexes eagerly —
   but harmless, and worth doing explicitly before a measurement run.)

4. **Run the sweep against your vault and your queries.** There's no
   CLI flag for this (see above), so invoke `eval.run` directly from a
   repo checkout, the same way `eval_command` does internally, but
   pointed at your vault and your queries file instead of the fixture
   ones:

   ```bash
   uv run python -c '
   from pathlib import Path
   from vacancy_radar.index.store import get_index_handle
   from eval.run import FULL_SWEEP, load_queries, run_eval

   queries = load_queries(Path("/path/to/your/real-queries.yaml"))
   index = get_index_handle(Path("/path/to/your/vault"))
   report = run_eval(queries, index, FULL_SWEEP)
   print(report.to_markdown())
   '
   ```

5. **Compare the resulting per-category recall@5/MRR table against
   README's fixture table.** You're looking for two things:
   - Does `vector_weight=0.5`/`linear_combination` still win or tie
     overall, the way it does on the fixture set? If a different
     `vector_weight` in `[0.3, 0.7]` wins clearly on your real
     queries, that's a `SEARCH_DEFAULT_VECTOR_WEIGHT` override worth
     making (`config.py`'s `SearchConfig` reads it from the
     environment already — no code change needed).
   - Does keyword still lead specifically on `exact_name`-shaped
     queries, the way `search`'s own tool description
     (`mcp_server.py`) tells a calling model to expect? If your real
     `exact_name` queries don't show the same gap, the tool
     description's guidance is citing a fixture-specific number, worth
     revisiting.

6. **Don't commit the numbers or the queries file.** Real-vault recall/
   MRR numbers are specific to one person's job search and one
   person's vault; there is nothing generalizable to ship here. This
   document describes the procedure once; running it and acting on the
   result is a per-deployment exercise, not something with a canonical
   answer to check in.
