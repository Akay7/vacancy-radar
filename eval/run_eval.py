"""Runs the four golden sets and writes the results as a markdown table for the README.

Ordered by ground-truth rigor, strongest first (see the eval section of the
maintainer's project plan for the full reasoning):
  1. grounding check       — automated, no golden file needed (cited text ∈ source)
  2. bullet retrieval      — eval/golden/bullets.jsonl (recall@5, MRR)
  3. similar-vacancy       — eval/golden/similar.jsonl (precision@3)
  4. filter-consistency    — eval/golden/filter-consistency.jsonl, reported with
                              sample size + confidence interval, not a bare percentage
"""


def main() -> None:
    raise NotImplementedError("M5")


if __name__ == "__main__":
    main()
