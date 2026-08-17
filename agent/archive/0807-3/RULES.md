# RULES: branch 0807-3 (the deadlock-breaker, PR #554)

**SHARPEN THIS FILE. Do not append to it.** Settled facts and standing
constraints for this branch. Wrong rule -> edit it here, not below it.
Sharpened from `.agent/0807-2/RULES.md` on 2026-08-07 by session d136ac61.

**Most of 0807-2's content deliberately did NOT carry forward.** That branch is
the version-hole wave with two writer agents and a 71-assertion baseline; this
branch is a THREE-FILE cherry-pick with one purpose. Carrying its writer-ownership
table or its gate-test baseline here would describe work that does not exist on
this branch, which is how these files become the committed lie the README warns
about.

## What this branch is

ONE commit (`0af433de8`, cherry-picked from `36c763a72` on 0807-2) cut off `main`
at `e4cd1fd2d`, existing for exactly one reason:

> **#553 cannot unblock itself.** It is BLOCKED by required
> `Review Complete=FAILURE`, caused by the split-numerator bug. The fix lives on
> 0807-2 — but `review-status.yml` checks out `.ci/scripts` from the **DEFAULT
> BRANCH**, so the fix is inert until it is on `main`. That is the circularity;
> this branch is the only legitimate way out of it.

Merging this makes #553's deadlock guard fire on its own. It is NOT a bypass —
the guard is existing, deliberate machinery that could not reach its own
condition.

## Do not re-litigate

- **The numerator, not the cap, was the bug.** `claude-review-gate.sh` counted
  `posted + spent` (3/3, refuses to review) while `review-status.sh` counted
  posted reports only (0/3, guard mute). Same PR, same instant, two answers.
- **Sharing a file is not sharing the computation.** `lib/common.sh` already
  shared `review_cap_for()` (the DENOMINATOR) when this bug shipped. Fixing it
  meant moving the NUMERATOR there too.
- Do NOT "simplify" `review-status.sh`'s `ATTEMPT_PREFIX` parse away. A missing
  prefix silently reads the cap LOW and reproduces the bug exactly, which is why
  it refuses to run rather than defaulting.
- Verified live before pushing: `posted=0 spent=3 TOTAL=3 cap=3` -> guard fires.
  Under the old numerator the same PR read `0/3`.
- Scope is FROZEN at three files. Anything else belongs on 0807-2 or its own
  branch; a bigger diff here risks the very turn-starvation that created the
  deadlock (#553 starved three times at 50 turns on 3024 lines).

## Standing constraints

- **AUTOPILOT is active** (operator asleep, invoked `/pr-merge`). Landing PRs is
  authorised. `--admin` is NOT, and is hook-blocked: if something cannot merge
  legitimately, STOP AND REPORT rather than force it.
- Never push `main` directly, never force-push, never suppress a gate.
- Never `git checkout/restore/stash/clean` to undo a mistake. Repair forward.
  Shared tree — other sessions' work may be in it.
- Never `git add -A`. Stage by explicit path. NEVER stage
  `.claude/settings.local.json`, `private/generative`, `private/growth`, or a
  submodule pointer that merely drifted.
- A blocked PreToolUse hook aborts the ENTIRE compound command — nothing in it
  ran. Do not assume an earlier `git push` in the same call happened.
- PRs on `rediacc/console` MUST be created `--draft` (hook-enforced), then
  flipped with `gh pr ready` once `CI Complete` is green. That flip is what
  triggers the automated review.
- After EVERY branch switch: `git submodule update private/account`. 0807-1 and
  0807-2 record DIFFERENT account commits; committing the wrong one rolls work
  back. Decide by which commit is NEWER, never by whose work it looks like.
- shfmt is `-i 4 -ci`. `mapfile` is BANNED. ruff reads the GIT mode, so a
  shebanged `.py` needs `git update-index --chmod=+x`.
- No attribution trailers in commits; no backticks in `git commit -m`; amending
  is hook-blocked — make a NEW commit.
