## SESSION 9d92d9b6 2026-08-27T09:02:17Z

Branch `0826-3` @ `b015da5e2`, REBASED A SECOND TIME onto `origin/0826-2`, which
had gained 11 commits. 18 commits, all `PR-TASK: f2757830`. Submodule
`private/account` on `0826-3` @ `5f55c91`. NOTHING PUSHED. PR #577 is still
OPEN (its CI is green; it has NOT merged).

Uncommitted: trapguard's `rebase-unverified` rule, the
`block-self-matching-pgrep` false-positive fix, and
`block-git-force-push`'s new message.

## The second rebase, verified by the tool built for it

`--git verify-rebase` against a `--git snapshot` taken first:
console **18 carried, 0 absorbed**, `private/account` 1 carried, the other three
0/0, **0 MISSING anywhere**. All four gitlinks contain their base.
`private/account` needed no rebase this round (its `origin/main` had not moved
and its tip already contained it). `private/renet`'s WORKTREE lagged the
recorded pointer again -- `git submodule update` fixed it; that is a
worktree-vs-index gap, not a bad gitlink.

## Verified on the rebased tree

- `packages/cli` unit tests: **2402 passed**
- `.ci/scripts/test/gates/test-review-status.sh`: **60 pass / 0 fail**
- Still running: `test-worklist-v5.sh`, `test-hooks.sh` (both under nohup, so
  the Stop hook cannot see them; watch their SUMMARY lines, not the tail).
- Still to run: `npm run ci` end to end (held only because it runs the two hook
  suites itself), and `private/account`'s own `npm test`.

## Operator's discoverability point, and what it exposed

"You knew how and when to use verify-rebase because you built it -- is there any
hint?" There was none. Measured: `worklist.py --git` was referenced by ZERO
commands, agents and docs. Worse, `block-git-force-push.sh` REFUSED a force-push
and said "the operator runs it with the ! prefix", sending a session away
empty-handed for an operation the repo authorises through `--git force-push`.
That message now names the verb, both forms, and why the guard must stay strict
rather than gain an allow-list.

The hint itself is `trapguard[rebase-unverified]`: fires right after a rebase
reports success and names both checks. trapguard is the right surface because it
never blocks and already exists to say "you just did X, here is what bites".

## A false positive in my own guard, fixed

`block-self-matching-pgrep` refused an ordinary command: it tested the loop
keyword and the `pgrep` INDEPENDENTLY, so a one-shot `pgrep -cf` plus the
English word "while" in a worklist message read as a wedged waiter. It now
requires the pgrep to sit inside the loop's CONDITION (keyword to `; do`). Also
learned: the bracket trick hides a pattern from ITSELF, not from a plain copy of
the literal elsewhere in the same command.

## Next action

Read the two suite summary lines (item `#6f67f133` is leased to waiter
`bnvbx8yai`, which watches the OUTPUT FILES, not processes -- no pgrep, the
shape the guard recommends). When both are green, WIRE THE CONTROLS for
`trapguard[rebase-unverified]` and for the pgrep false-positive fix into
`.claude/hooks/test-hooks.sh` -- that edit is blocked until the suites exit, by
`block-edit-of-running-script`. Then commit with a `PR-TASK: f2757830` trailer,
then run `npm run ci` and `private/account`'s suite.

## Expected failure, do NOT "fix" it

`check:ci-pr-task-trailers` fails on `0826-2`'s untagged commits. Each was
attributed individually; none are mine. It self-resolves when #577 merges and
this branch re-rebases onto `origin/main`. Do not weaken the gate and do not
back-fill trailers onto another wave's commits.

## Open, operator-gated

SES: `.env`'s AWS_SES_ACCESS_KEY_ID and SES_AK_ID are in no `ses-*` slug.
Ticked `door:operator-only`; do not reopen.

## Settled, do not re-ask

Guard density: keep adding, fix FPs as they fire. gitlab remote: credential
stored. Commit redo: done. Rebase target: 0826-2 by operator choice.
