# RULES: branch 0809-1

**SHARPEN THIS FILE. Do not append to it.** Settled facts and standing
constraints for this branch; edit in place when one proves wrong.

Sharpened 2026-08-09 by session 2fd369e0 at wave start.

## What this branch is

The big-bang PR: full CI-side AI autonomy (autopilot S1 → all flags,
INCLUDING submodule pushes — operator decision) + profiler persistence via
annotation harvest + blocking runner-advice gate. Approved plan:
`~/.claude/plans/not-yet-let-s-switch-tender-harp.md`. Two Opus writers with
disjoint ownership: writer-autopilot owns autopilot.yml +
.ci/scripts/autopilot/** + invariants checker/tests + 03-v2-autonomy.md;
writer-profiler owns .ci/scripts/ci/profiler/** + check_runner_advice.py +
baseline/allowlist/gate-test + the four registration points.

## Operator decisions (do not re-litigate)

- **Submodule autonomy is IN** (full S6 surface, per-repo push walls).
- **NO budget flag**: bounds are max-turns 80/60 + the 30-min job timeout.
  Do not wire --max-budget-usd.
- **Escalate latches autopilot-blocked** (posts reason + halts that PR).
- Advisor enforces BOTH directions (move-down + slim-reliability); baseline
  refresh is MANUAL (my call, veto-able, logged in the plan).
- The initial runner-sizing baseline is EMPTY and the gate's VACUOUS exit 1
  is CORRECT until seeded from this PR's own CI annotations (B6). Do not
  soften the gate to make CI green early.

## Standing constraints

- Security walls (invariants gate enforces): gate job tokenless, model job
  never holds a write token, all writes post-model, trusted-checkout-first,
  persist-credentials false, track_progress false, cancel-in-progress false.
  Model text is data: never shell-interpolated, passed via files/-f params.
- Flag flips happen AFTER merge only (workflow runs from main). Order:
  ALLOW_STATE first, always.
- Babysit mechanics per .claude/agents/pr-babysitter.md when the PR opens.
- Never git add -A after the snapshot; never restore/reset/stash; never push
  main; private/growth + private/generative never staged.
