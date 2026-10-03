"""Review-support tooling that is not a quality gate.

`claude_review_gate` decides whether the advisory PR-level Claude review runs and posts its report, inline findings and marker (agent/plans/PLAN-github-pr-review-restore.md); its prompts live in `prompts/` beside it. `pr_labels` derives a PR's labels from the per-commit review records under `agent/reviews/<branch>/`, and `standing_orders_brief` prints the `/standing-orders` live-state brief.
"""

__all__: list[str] = []
