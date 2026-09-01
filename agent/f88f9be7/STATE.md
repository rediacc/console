## SESSION f88f9be7 2026-09-01T13:45:18Z

`/pr-babysit` INLINE on `0831-1`, PR #583. Principal is the operator.

## The one thing that needs the operator

PR #583 @ `2f94fe197` is **fully green** -- re-verified this turn with a one-shot
`.ci/scripts/ci/ci-trace.py`, exit **0**, "every context succeeded or was skipped".

It still does not merge. Ruleset `12344707` requires TWO checks; the second,
**`Review Complete`**, never ran, because the operator settled that #583 merges with
no automated review. `/pr-merge` was made model-invocable by the operator this session
("make it AI callable. I authorize!", recorded in `.claude/commands/pr-merge.md`) and
that did NOT clear it. Dispatching `Review Status` by hand posts `failure`
(unreviewed head) -- more blocked, not less. Verified by reading the ruleset, the
workflow and its script.

Two honest exits, both the operator's: `gh pr merge 583 --squash --admin` (admins hold
`bypass_mode: always`; `--admin` is hook-banned for me by design), or
`gh workflow run "Claude Review" -f pr_number=583` then the normal path.

Tracked as `[?] f46112c0`. **Its DEFAULT fires ~2026-09-01T15:00Z and PUSHES the
sixteen held commits.**

## State of the tree

Tree CLEAN. **Sixteen commits local and unpushed**, `f5d9159c8`..`3d7f83b22`.
They live ONLY on `0831-1`, which a merge deletes -- **`git branch 0901-1` before any
merge.**

All gates green as of this turn: `ci:quick` **274 ok / 0 failed**, hook harness
**PASS=1885 FAIL=0**, 239 judge-schema controls, 16 counter controls, 15 controls on
the newest gate, ruff lint+format clean, shfmt clean.

Landed this session: the plan-section-10 replay (74 firings/month vs a once-a-month
floor, so `wl_shapedup` is WIRED and running on the allow path); an
accepted-divergence exit for the shape counter; a line-number fix (every `file:line`
it emitted was a normalised-array index); round five of the arrow/redirect guard
false positive; and `check:ci-git-history-depth`, three-point wired.

## Next action

1. Answer `[?] f46112c0`, or let its DEFAULT push at ~15:00Z.
2. **If that push happens, a CI run starts and needs a watch.** That is why crons
   `f892a1f9` and `b4bff02e` are still ARMED: this tick's step 8 said to CronDelete
   them on green, and I deliberately did not, because deleting a watchdog minutes
   before an automated push is the dropped-watch failure the cron exists to catch.
   Say so in any report rather than letting it look like an oversight.
3. Nothing else is blocked. If more work is wanted, the honest next piece is the
   208-span backlog -- but re-scope FIRST and read section 5 of
   `agent/PLAN-duplication-angle.md`: the span the plan called "the cleanest case in
   the repo" does NOT consolidate for 46 of its 62 instances.

## Volatile facts a fresh session would get wrong

- **The judged-rule calibration is NOT deterministic.** 14/14 was ONE draw. Across
  three live samples five fixtures missed at least once and none consistently,
  spanning all three rules; a 20-fixture run scored 17/20. `SHAPE_PROMPT` is
  deliberately ABSENT from `.ci/config/rubric-calibration.json` for that reason --
  do not "fix" that by adding it.
- There is NO round log for this wave; STATE.md is the artifact. Do not hunt for
  `reports/pr-babysit-0831-1.md`.
- ONE `wl_wait.py f88f9be7` waiter is alive. Two earlier ones overran their own
  `--timeout 3600` by 90+ minutes and were killed; elapsed-vs-timeout is what
  distinguishes hung from merely silent, never the byte count.
- `scripts/ci-runner/manifest.ts` carries peer `a276391d`'s hunks. Stage the HUNK.

## Open, not fixed

`[?] f46112c0` only. Peer `a276391d`'s `BACKUP_S3_BUCKET` finding needs credentials
neither session has.
