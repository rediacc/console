## SESSION d778be9d 2026-10-04T21:51:06Z

# STATE d778be9d

## Where things are (2026-10-04 ~21:45Z)

- PR #595 (branch 1004-2, draft) is open. Its remote head is 5965e4598, CI run 37233225451 RED: Quality / Pytest (3/3), 7 test_ci_profiler_sampler_linux host-tier cases. The golden for the retired bash sampler was recorded on a 24-core host, so CI's 4 cores give 4000 vs 24000.
- Fixed locally, not pushed:
  - 522bd7ad1: host readings are compared against this host (75 passed at 24 cores and under taskset -c 0-3).
  - 9548df90d: lane-durations refresh for two drifted units.
- The 4-core sweep of 205 golden modules found no other host value.
- Pre-push for the current head is running as bpwq1r2g5 (scratchpad/prepush.sh: ci:quick, then `npx tsx scripts/ci-runner/run.ts --only <dropped>` into .ci/cache/prepush-receipt.json). Carried: P-A1:e2588e9ce034 (admitted by the PR body's Operational-Reason) and check:ci-pytest "*" (4 WSL/live-container skips).
- PR body: Plan: PLAN-stop-hook-turbo, an Operational-Reason naming 5 part-done plans, the epic block synced (agent/pr/1004-2.md committed). The PR has to be created with --body inline, not --body-file.
- Turbo is off. PLAN-deletion-budget is written and postponed (P3 operator), and DB29 is filled in.
- After the merge, the session dispatches the release runs (#ab92320e): cd-v2 patch, promote-stable after the soak, backfill-release-sentinel dry_run.
- Rebase lessons: after any rebase, run scratchpad/remap.py for plan citations, and remap agent/ledgers/plan-investigation.jsonl `["commit",sha]` and `["commit",true,full]` pointers by subject. CI's fresh checkout lacks rewritten objects (finding #ad75ce33).

## Next action

1. bpwq1r2g5 green (only check:ci-pytest red) and origin/main unmoved: `git push origin 1004-2`, then ci-trace --wait --until-final on #595. If main moved: snapshot, rebase, verify-rebase, remap citations and the ledger, commit, rerun prepush.
2. CI green: `gh pr ready 595`, wl_prreview --wait and answer the review, then gh pr merge 595 --rebase --auto. Then dispatch #ab92320e.
