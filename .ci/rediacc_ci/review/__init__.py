"""Review-support tooling that is not a quality gate.

`pr_labels` derives a PR's labels from the per-commit review records under `agent/reviews/<branch>/`, and `standing_orders_brief` prints the `/standing-orders` live-state brief. The PR-level Claude review tooling that used to live here was retired on 2026-10-02 (agent/plans/PLAN-per-commit-review.md section 11.6).
"""

__all__: list[str] = []
