## SESSION 9d92d9b6 2026-08-27T09:29:28Z

Branch `0826-3` @ `8ce700584`, rebased TWICE onto `origin/0826-2`. 21 commits,
all `PR-TASK: f2757830`. Submodule `private/account` on `0826-3` @ `5f55c91`.
Clean tree. NOTHING PUSHED. PR #577 is OPEN, not merged.

## Recovery refs (tags, not branches -- a backup is not a wave)

`preredo-0826` = `3ced1a4d8`, `prerebase-0826` = `9f3cb9f8c`, and
`private/account` `prerebase-0826` = `3e79b39`. Next wave takes **0826-4**.

## The live design work

`agent/PLAN-resumable-rebase-executor.md` -- the operator VETOED my narrowing
(`--execute` for force-push only, refusing rebase verbs): "We have AI. AI should
receive a prompt to continue and/or what happened. So, it should fix conflicts
and try again where he lefts."

THE INSIGHT: `git rebase` is ALREADY resumable. It persists step N of M, the
stopped sha, the todo and the conflict stages. So there is no state machine to
build -- anything this module wrote down would be a SECOND copy of a truth git
holds, and a second copy drifts. The missing piece was a verb that READS it.

MEASURED taxonomy from this branch's two real rebases, ten conflicts: ONE
gitlink (resolve_gitlink_target settled it unaided, naming a commit in NEITHER
stage), SIX mechanical registry unions, TWO genuine judgement calls (`run.sh`
setup(), and the suite one wave refactored from a monolith into 22 case files).

**Step 1 is SHIPPED** (`8ce700584`): `--git rebase-status` reads the halt and
classifies each path gitlink / registry / judgement. Verified against a REAL
halted rebase in a throwaway fixture. Conservative: anything unplaceable is
judgement, i.e. untouched.

Steps 2-5 remain: the invariants, `rebase-resolve` (gitlink class first, it is
already proven), registry classes one at a time, then the continue loop. **Step
2 needs a git fixture harness this repo does not have** -- that is the real cost.

THE MECHANICAL HALF IS THE DANGEROUS HALF. A blind union glued `touched`+`see`
into one token in `wl_agents.py` today and silently killed two stopwords; the
file parsed and the suite passed. Every union must land behind an invariant
proving meaning survived, and a class with no invariant stays judgement.

## Verified on the twice-rebased tree

`packages/cli` 2402 passed; review-status 60/0; worklist 805/0; hooks 1395/0
(wl_git now 35 controls); `--git verify-rebase` 18 carried / 0 missing; all four
gitlinks contain their base.

## Next action

Read `/tmp/.../scratchpad/v-acct.txt` (`private/account` npm test, started under
nohup -- check for a SUMMARY line, not the tail). Then run `npm run ci` end to
end, the last of the four checks the operator asked for. Then steps 2-5 of the
plan.

## Operator rulings, do NOT re-litigate

- PR base: wait for #577 to merge, then re-rebase onto `origin/main` and base
  the PR there. `check:ci-pr-task-trailers` stays RED until then on 0826-2's
  nine untagged commits (each attributed; none are mine). Do NOT weaken the gate
  and do NOT open a stacked PR.
- `/branch-rebase`'s `[base]` argument: implemented, not deleted (`f74a0c120`).
  Console rebases onto `origin/$BASE`; SUBMODULES always onto their own
  `origin/main`; step 4 verifies each against its own ref.
- Guard density: keep adding hooks, fix false positives as they fire.
- gitlab remote: credential stored, `git fetch --all` exits 0.

## Open, operator-gated

SES: `.env`'s AWS_SES_ACCESS_KEY_ID and SES_AK_ID are in no `ses-*` slug.
Ticked `door:operator-only`; do not reopen.
