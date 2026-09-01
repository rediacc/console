## SESSION f88f9be7 2026-09-01T13:25:42Z

`/pr-babysit` INLINE on `0831-1`, PR #583. Principal is the operator.

## The one thing that needs you

PR #583 @ `2f94fe197` is **fully green** -- 0 failing, 0 pending, `CI Complete`
success. It does not merge, and `/pr-merge` being AI-callable did not change that.
Ruleset `12344707` requires TWO checks; the second, **`Review Complete`**, never ran
because you settled that #583 merges with no automated review. Dispatching
`Review Status` would post `failure` (unreviewed head) -- more blocked, not less.

Two honest exits, both yours: `gh pr merge 583 --squash --admin` (repo admins hold
`bypass_mode: always`; `--admin` is hook-banned for me by design), or run the review
after all. Tracked as `[?] f46112c0`, DEFAULT in ~105m = push the held commits so the
wave is not stranded on a branch the merge deletes.

**Before any merge: `git branch 0901-1`.** Twelve commits live only on `0831-1`.

## Where the work stands

Tree CLEAN. Twelve commits local and unpushed. This stretch landed nine of them and
all gates are green: `ci:quick` **274 ok / 0 failed**, hook harness **PASS=1885
FAIL=0**, 239 judge-schema controls, 16 counter controls, python lint+format clean,
shfmt clean.

- **The replay is DONE** (`4cbdddd88`). Seeded at 2026-07 the counter would have
  fired **74x in 2026-08**. The plan feared twice a year; the depth question does
  not re-open.
- `wl_shapedup` is WIRED and running on the allow path.
- Four plan claims died on contact with the code; all four are in
  `agent/PLAN-duplication-angle.md`.

## Next action

1. Answer `[?] f46112c0` above, or let its DEFAULT push.
2. Nothing else is blocked. If more work is wanted, the honest next piece is the
   208-span backlog -- but re-scope it first, and read section 5 of the plan doc
   before starting: the span the plan called "the cleanest case in the repo" does
   NOT consolidate for 46 of its 62 instances.

## Traps worth carrying

- **The judged-rule calibration is NOT deterministic.** 14/14 was ONE draw. Across
  three samples, five fixtures missed at least once and none consistently, spanning
  all three rules; a 20-fixture run scored 17/20. Never claim "calibrated at N/N"
  without saying how many samples. `SHAPE_PROMPT` is deliberately NOT in
  `.ci/config/rubric-calibration.json` for exactly this reason.
- **Never build a fixture from a transcribed file:line.** Two of three were wrong;
  the model was right both times it disagreed. Build them from the counter's output
  -- doing so is what found the line-numbering bug.
- A negative fixture pointing at REAL duplication tests nothing.
- `gate-test:claude-hooks` does NOT exist; it is `check:ci-hook-worklist-suite`.
- `git ls-tree` does NOT glob (0 hits where `git ls-files` gives 103).
- `$?` after a pipeline is grep's status, not the gate's.
- A control whose subject must be running ELSEWHERE goes vacuous when that thing
  exits. Start your own victim process.
- `sleep` over 120s is hook-blocked even backgrounded; `npx ruff` is blocked (use
  `ruff` directly); a whole Bash call is rejected at PreToolUse, so a blocked
  command runs NONE of its parts.
- Do NOT put `"files": []` on the root tsconfig (`4dbcff0c7`).
- `scripts/ci-runner/manifest.ts` carries peer `a276391d`'s hunks. Stage the HUNK.

## Open, not fixed

`[?] f46112c0` only. Peer `a276391d`'s `BACKUP_S3_BUCKET` finding needs credentials
neither session has.
