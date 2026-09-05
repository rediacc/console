## SESSION d1589e0b 2026-09-04T23:33:29Z

# d1589e0b — babysit 0903-1, then merge, then main, then the prod release

## Next action
Read worker b1r0q48tl (worklist suite, greps FAIL). It names the two assertions
that regressed from the 922/0 baseline, and it doubles as an experiment: a PEER
suite has been running concurrently, so a clean result means those two were
contention, not regressions. Then `ci:quick`, commit my uncommitted work, push.
Separately, CI cannot go green until peer 74de73ca lands four floors (below);
waiter bl6kfap9j is armed on request #1eb71e3b.

## Where the branch is
HEAD == origin/0903-1 == **780b96cdb**. Console CI run **33928012450** is RED on
it. Read the JOB conclusions, never the run's: 1 failure, 5 cancelled alongside
= watchdog kill. The ddc4fa17d run also reads `cancelled` but is the SUPERSEDED
shape (0 failures, newer commit exists).

## THE BLOCKER: four floors committed-test-without-implementation
Job 101201197468: `FAIL: retire-shadowed-secrets: an impossible MIN_WORKFLOWS
was accepted`. The peer's test is RIGHT and the tree is wrong — the whole floor
is UNCOMMITTED while the test requiring it is tracked. The test exits on first
failure, so THREE MORE REDS are queued. All four are uncommitted:

  .ci/scripts/housekeeping/retire-shadowed-secrets.py  MIN_WORKFLOWS    failing
  .ci/scripts/security/shfmt.sh                        MIN_SHELL_FILES  masked by the 77 SKIP
  scripts/dev/secret-rename.py                         MIN_FILES        next
  scripts/lib/action-refs.ts                           MIN_ACTION_FILES after

They are the peer's. Do NOT commit them; #1eb71e3b asks them to land all four in
ONE commit and offers to land them on their word. If they go silent for a long
stretch, that offer is the escalation, not a unilateral commit.

## The rule this branch has now paid for three times
**Every local gate reads the WORKING TREE; CI checks out only TRACKED files.** A
committed test may not depend on uncommitted behaviour, and no local gate can
see it. Round 9's sweep reported 0 siblings but only checked tests against
MANIFEST entries, never against the CODE they exercise — same class, missed.
TRAPS `working-tree-green-tracked-tree-red`. Read `git diff --cached --stat`
before every commit. Also: do not edit a file a running suite reads (cost two
restarts tonight).

## Uncommitted, mine alone
1. **wl_judge.py + test-judge-schema.py** — the judge exited 1 on
   `error_max_structured_output_retries` and skipped the retry the identical
   exit-0 failure already gets, so a flake was reported as a broken gate offering
   WORKLIST_JUDGE=off. Real call verified 3/3 valid at 4-5x the failing cost. One
   shared helper at all four call sites; 9 paired controls; judge left ARMED.
2. **26-migrate.sh case 204** — fold(store) == fold(compact(store)) across every
   record key, all four states, with anti-vacuity and an inverted control. Passes.

## The three orders
1. **#e9ad31ad** green + reviewed + threads resolved, then `/pr-merge`.
2. **#dfe46a93** then follow main, fixing DIRECTLY ON MAIN (operator override).
   Pre-diagnosed: qs/fast-uri advisories already fixed here.
3. **#624e1863** then `Release to Production -f force=true`. Failure expected.
   Verified the 6x failure is already fixed here (promote-stable.yml:74-76,
   assert-edge-tag-exists.sh:83/:90-91), so the NEXT failure is the real work.

## Constraints
Peer 74de73ca is live in this worktree and branch. Stage HUNKS not files. No
Co-Authored-By/Generated-with trailers; every commit needs `PR-TASK: 24c98380`.
Cron 49fa57a0 drives this loop; tear it down only when prod release is green.
