# Example data

Sanitized demo data — public CV bullets + a handful of public postings — used for README screenshots and CI. Structurally identical to a real user's `data/user/` (see the vacancy record format in the maintainer's project plan), just fictional/public content.

- `experience.md` — a handful of CV bullets.
- `vacancies/` — five fixture folders exercising the ingestion CLI's edge cases: two valid
  vacancy folders with different outcomes, one with a `vacancy.yaml` missing a required field,
  one whose folder name doesn't follow the natural-key convention, and two whose `vacancy.yaml`
  content collides on the same natural key despite different folder names.

Real personal data (yours or the maintainer's) never lives here — it's bind-mounted from your own separate git repo into the gitignored `data/user/`.
