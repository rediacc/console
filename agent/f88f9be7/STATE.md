## SESSION f88f9be7 2026-09-01T13:09:10Z

`/pr-babysit` INLINE on `0831-1`, PR #583. Principal is the operator.

## The headline: CI is GREEN, and the merge is OPERATOR-ONLY

PR #583 @ `2f94fe197`: **0 failing, 0 pending**, "CI Complete" success. It does NOT
merge, and the reason is mechanical: the ruleset (`12344707`) requires TWO checks,
`CI Complete` and **`Review Complete`**. The second never ran, because the operator
settled that #583 merges with no automated review. `mergeStateStatus` is BLOCKED
solely on that.

The operator has since made `/pr-merge` model-invocable ("make it AI callable. I
authorize!"), recorded in `.claude/commands/pr-merge.md` frontmatter. So the merge is
now runnable HERE, but `Review Complete` is still missing and no honest path posts
that status. **Do not fake a check and do not `--admin` around it. Ask.**

## Local commits, NOT pushed (a push restarts the run the merge waits on)

`f5d9159c8` wl_shapedup, `8dd3d1546` meta-control, `1cf2a3733` rubric-calibration,
plus this stretch: `1a8f9bc60` the arrow fix, `e42f9352e` the counter's accepted
exit, `85549005f` the wl_shapedup wiring.

**Before merging, `git branch 0901-1` first.** These commits live only on `0831-1`,
which the merge deletes.

## Done this stretch

- **The replay (plan section 10) is DONE** and written up in
  `agent/PLAN-duplication-angle.md`. Seeded at 2026-07 the counter would have fired
  **74x in 2026-08**, far above the plan's once-a-month floor. The depth question
  does NOT re-open. Graft artifact gone: `609314a41` adds 4 files, not 4,531.
- The counter gained an `accepted` + BLOCKER exit; `--seed` now refuses over an
  existing seed.
- `wl_shapedup` wired on the ALLOW path; its latch had two real bugs (never
  incremented, wrong guard) plus one bad control. 239 controls green.
- `block-bash-write-to-running-script.sh`: round FIVE of "a mention is not a target"
  -- an ASCII `->` read as a redirect. Fixed, 3 cases added.

## Next action

1. **Ask the operator how to clear `Review Complete`** -- it is the only thing
   between green and merged, and no answer to it is mine to invent.
2. `git branch 0901-1`, then `/pr-merge 0831-1` once (1) is answered.
3. Finish the SHAPE_PROMPT calibration (worker below) and add it to
   `.ci/config/rubric-calibration.json` only if it earns the entry.
4. `[?] 5fd1f91d`: step 5, RE-SCOPE FIRST -- 219 spans, not ~9.

## Volatile traps right now

- **The calibration is NOT deterministic.** 14/14 was ONE sample. Re-runs of the
  same fixtures on the same rubric produced a sweep MISS and later a brave MISS,
  each passing on other samples. Never claim "calibrated at N/N" without saying how
  many samples.
- A negative fixture that points at REAL duplication tests nothing. Mine cited three
  `check` closures as "the findings report"; the model was right and I was wrong.
- `gate-test:claude-hooks` does NOT exist. It is `check:ci-hook-worklist-suite`.
- `git ls-tree` does NOT glob: 0 hits where `git ls-files` gives 103.
- Reading `$?` after a pipeline gives grep's status, not the gate's.
- `sleep` over 120s is hook-blocked, even backgrounded.
- Do NOT put `"files": []` on the root tsconfig (`4dbcff0c7`).
- `scripts/ci-runner/manifest.ts` carries peer `a276391d`'s hunks. Stage the HUNK.

## Open, not fixed

`[>] b4fee388` (SHAPE_CASES live run in flight), `[?] 5fd1f91d`, `[>] 3b520036`
(replay done; ticking). Peer `a276391d`'s `BACKUP_S3_BUCKET` finding needs
credentials neither session has.
