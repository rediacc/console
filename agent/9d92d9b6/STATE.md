## SESSION 9d92d9b6 2026-08-26T19:46:42Z

Branch `0826-3`, REBASED ONTO `origin/0826-2` (PR #577, draft, the operator's
other machine). 16 commits, all `PR-TASK: f2757830`. Submodule
`private/account` on its own `0826-3` @ `5f55c91`. NOTHING PUSHED.

Uncommitted: the rebase's `run.sh` repairs (see Next action).

## Recovery refs, if anything looks wrong

- tag `preredo-0826` = `3ced1a4d8` -- console tip BEFORE this rebase
- tag `prerebase-0826` = `9f3cb9f8c` -- console tip before the commit redo
- `private/account` tag `prerebase-0826` = `3e79b39`

A backup is not a wave, so these are TAGS, not `MMDD-N` branches. Next wave
takes **0826-4**.

## The rebase, and how it was verified

`private/account` rebased onto its OWN `origin/main` first (submodules always
do), producing `5f55c91`. The console gitlink then conflicted with stage 2 =
`218776b` (their main tip) and stage 3 = `3e79b39` (my pre-rebase tip) -- and
the correct answer was NEITHER: `5f55c91`, the rebased tip. `--git
resolve-gitlinks` named it and verified containment; I ran the two commands it
printed.

Verified after: all four gitlinks contain their base; **16 commits carried, 0
absorbed** by `git cherry` (a COUNT cannot tell a legitimate rebase-merge drop
from a `--skip`, which is why branch-rebase.md no longer compares counts); tree
clean; `git submodule update` was needed for renet/homebrew-tap, whose
worktrees lagged the correctly-recorded pointers.

## Merges that were decisions, not conflicts

- **`setup()`**: both waves rewrote it the same day. Result keeps 0826-2's
  devcontainer skeleton and flags, swaps its check-only step 1 for 0826-3's
  INSTALLERS, and KEEPS `ensure_host_tools` after them (it also checks zstd,
  curl, git, which no installer covers). `exit 1` became `return 1`.
- **`npm install` vs `install:natives`**: sequential, not alternatives. Both
  kept; `.npmrc` sets ignore-scripts, so dropping either breaks the tree.
- **The suite**: 0826-2 split the 11,978-line monolith into 22 files under
  `.claude/hooks/stop/worklist-cases/`. THEIR architecture won; my cases were
  relocated into it (ARITY -> 08, L1_TABLE/NO_ME/183 -> 18, email removal ->
  13, case 176 -> 17, ci_run json.dumps -> 09).

## Defects the rebase introduced, all fixed

1. Merging both waves' stopword lines GLUED `touched`+`see` into `touchedsee`
   (adjacent Python literals concatenate). Two stopwords silently died. Fixed,
   swept, and gated in `check_agent_hint_liveness.py`.
2. `setup()` ran `setup_go_toolchain` (reads `private/renet/go.mod`) BEFORE the
   submodule init. On a fresh clone: "Cannot determine the required Go version".
   Caught by `check:ci-setup-idempotency`; init lifted ahead of its reader.
3. `setup_check` did not report the phases the merge added, so `--check`
   under-counted. Now reports gh, compiler, git identity.

## Next action

COMMIT the uncommitted `run.sh` work (submodule-init ordering + the
`setup_check` phases) with a `PR-TASK: f2757830` trailer. Then read waiter
`b01tlqoge` (worklist suite; an earlier run DIED at case 65 with no summary --
a partial run is not a pass, check for the `passed=` line). Then build
`--git snapshot` + `verify-rebase` (item `#e80415f5`), the last piece of the
approved plan.

Gates already green on the rebased tree: check:ci-setup-idempotency,
check:ci-bootstrap-idempotency, check:ci-shell-size, check:ci-watch-recipe,
check:ci-parity, check:ci-merge-method-prose. `./run.sh setup --check` runs
clean and mutates nothing.

## Open, operator-gated

- `[?] #f6e059ec` CI confirmation of the trapguard heredoc controls on a real
  PR. DEFAULT: do not push.
- SES: `.env`'s AWS_SES_ACCESS_KEY_ID and SES_AK_ID are in no `ses-*` slug.
  Ticked `door:operator-only`; do not reopen.

## Settled, do not re-ask

Guard density: keep adding, fix false positives as they fire. gitlab remote:
credential stored, `git fetch --all` exits 0. Commit redo: done. Rebase target:
0826-2, chosen by the operator over waiting for the merge.
