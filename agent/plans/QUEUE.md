# Plan queue

The ordered queue of approved plans the plan-per-PR loop pulls from (box L2 of agent/plans/PLAN-plan-per-pr-loop.md). One plan per PR by default.

How it is read: the first entry is the plan the live `MMDD-N` branch works. On the first push that finds the console PR's body without a `Plan:` line, `.claude/hooks/post-bash/refresh_pr_body.py` writes `Plan: <first entry>` into it, and that line is then the PR's own. Before a merge, `rediacc_hooks.plan_gate.plan_merge_refusal` (called by `block_admin_merge` and by the fast-forward fallback in `block_push_to_protected_branch`) refuses the PR while that plan has an open box, unless the body carries an `Operational-Reason:` line. A multi-plan PR records its reason the same way.

Format: one numbered entry per plan, `1. agent/plans/PLAN-<slug>.md`, optionally followed by ` -- <note>`; first = next. Only numbered entries are read, so prose here (this paragraph included) never becomes an entry. Each entry names an existing approved plan that still has open boxes. An entry leaves the queue when its PR merges, and the next one becomes the next branch's plan.

## Queue

1. agent/plans/PLAN-plan-per-pr-loop.md -- PR #591 also carries PLAN-ci-verdict and PLAN-per-commit-review, so it merges with an Operational-Reason
2. agent/plans/PLAN-per-commit-review.md
