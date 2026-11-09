# PLAN: vm:check reruns only what failed and diffs against the last VERIFIED tree
Status: approved -- operator /ask ASKED:2026-11-08T19:20Z "Green first, then batch (Recommended)": the vm:check half is one plan after the ci:quick half
Depends-On: PLAN-ciquick-green-then-batch.md
Owner: d778be9d
Updated: 2026-11-08
Priority: P2 -- on 1104-1, 29 vm:check runs took 22.65 h and 18.4 h of it ended FAILED or NOT_VERIFIED, each retry a full rerun
Concurrency: parallel -- the boxes own the vm:check runner, the vm tier admission and their tests
Live-Proof: none -- tooling only, no deployable surface; V3's fleet cycle on local VMs is the proof (operator ruling closed as #a09952dc)
Owns: agent/plans/PLAN-vmcheck-incremental.md, .ci/rediacc_ci/proof/**, .ci/rediacc_ci/tests/**, .claude/rediacc_hooks/guards/block_vm_unverified_push.py, docs/agent-reference/ci-gates.md

## Context (measured 2026-11-08 on 1104-1)
- Receipts live in `.ci/cache/vm-check/<tree>.json`; a rerun at the same tree overwrites, so counts are a floor: 6 VERIFIED, 14 FAILED, 9 NOT_VERIFIED.
- FAILED is step-failed in 14 runs over about 12 different steps; NOT_VERIFIED is area-not-verified 5, phase-not-run 2, receipt-first 1, and one of the 9 carries no classified reason.
- An `--only` run never reaches VERIFIED (`.ci/rediacc_ci/drills/vm_check.py:1447`), and `--changed` diffs against the push base (`.ci/rediacc_ci/proof/surfaces.py:584`), so a larger batch pulls in more areas.
- Both sides (renet and account) were required in 29 of 29 runs, so a per-side digest split pays almost nothing and is not part of this plan.

## Boxes
- [x] V1 a same-tree `--only` pass of exactly the steps a FAILED receipt names merges into that receipt, the way `droppedVerified` works for ci:quick, and the receipt becomes VERIFIED when no failed step remains. Accept: proof tests for a FAILED receipt plus a passing `--only` of its failed steps (VERIFIED), a partial `--only` (still FAILED), and a different tree (refused).
    (ticked) 2026-11-09T01:21:02Z by d778be9d: commit:3dd946ffdf commit:da923f2ce9 a passing --only of the FAILED receipt's failed steps merges and re-judges to VERIFIED, a partial rerun stays FAILED, another tree is refused; pytest proof + vm_check 746 passed; guard harness test-block_vm_unverified_push.py 0 failures. DEPS-WAIVED: PLAN-ciquick-green-then-batch has only G7 (operator-held live run) open
- [x] V2 `--changed` diffs against the newest VERIFIED tree on the branch when one exists, falling back to the push base, so a batch after a VERIFIED run selects only what changed since it. Accept: surfaces tests for both bases, and `block_vm_unverified_push` still refuses a tree whose digest no VERIFIED chain covers.
    (ticked) 2026-11-09T01:21:03Z by d778be9d: commit:3dd946ffdf commit:da923f2ce9 --changed diffs from the newest commit whose VERIFIED receipt the guard admits (else the push base), the guard follows verifiedBase with the base head's real tree checked, and a tree no VERIFIED chain covers is refused; pytest 746 passed. DEPS-WAIVED: PLAN-ciquick-green-then-batch has only G7 (operator-held live run) open
- [ ] V3 live: one fleet cycle of FAILED, a fix, `--only` of the failed step, VERIFIED, then a push admitted by the guard. Accept: the receipt sequence and the guard's admit line.
