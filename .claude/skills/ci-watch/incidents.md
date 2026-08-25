# ci-watch: the incidents behind the rules

Kept out of `SKILL.md` because that file is capped at 60 lines so it sharpens
instead of growing. This one is the evidence; append, never prune.

## The compound watch that swallowed a red run (2026-08-24)

On a landing already nine rounds deep, the watch was:

```bash
# BROKEN: do not copy
R=<run-id>
until [ "$(gh run view $R --json status --jq .status)" = "completed" ]; do sleep 20; done
gh run view $R --json conclusion,jobs --jq '...'           # verdict printed HERE
SHA=$(git rev-parse HEAD)
until <review marker for $SHA appears>; do sleep 20; done  # ...then it kept waiting
echo REVIEWED
```

CI failed at **23:55:13**. The verdict, `failed: ["Quality / Static"]`, was
written into the output file and **nothing woke the session**, because the
process had not exited: it had moved straight into the second `until`, waiting
for a review marker that a red run never posts.

The failure sat unread for about **ninety minutes**. It surfaced only when the
operator pasted the failing job's URL into the chat, asking "don't you watch?".
The session was, on its own reading, healthily waiting: the pure-background-wait
check-in kept reporting a live worker, because the worker *was* live.

The stuck process was still running hours later, with its answer on disk, until
it was killed by hand (exit 144, SIGTERM).

## `gh run watch` is a convenience, not a contract

`--exit-status` exists and returns non-zero when the run fails
(<https://cli.github.com/manual/gh_run_watch>). It is still rejected here: it
dropped **four times out of four** in one campaign. The run went terminal,
nothing fired, and the loop stopped for over an hour each time. It has also been
seen exiting 1 while the run was still `in_progress`. The `until` poll exits on a
state you read yourself, which is the property that matters.

## A killed watch answered as a no-op (2026-08-24)

A round-4 watch was killed rather than completing. The notification was treated
as "no response requested" and the session stopped. The run had gone **green**
and sat unwatched, PR still in draft, until the operator asked. This is the same
failure the delegated-mode note warns about, reproduced in-session.

## Why the mechanism is what it is

Confirmed against the docs rather than assumed: background output is written to a
file and read on demand, and the wake-up is the process exiting
(<https://code.claude.com/docs/en/interactive-mode>,
<https://code.claude.com/docs/en/tools-reference>).

## A watch fired on attempt 1 of a run that was not over (2026-08-25)

Landing console#574 — this skill's own PR. The watch was the form this file
recommended at the time:

```bash
# INCOMPLETE: exits on the first `completed`
until [ "$(gh run view $R --json status --jq .status)" = "completed" ]; do sleep 20; done
```

It fired and reported `conclusion: cancelled, failed: ["CI Complete"]`. A
re-query moments later returned an EMPTY job list and a null run conclusion,
which reads like a `gh` glitch and is not one: `run_attempt` had gone to **2**.
The watchdog had classified the failure as transient and re-dispatched the run,
so a run that had genuinely reached `completed` was `in_progress` again, and the
verdict the watch delivered belonged to a superseded attempt.

The underlying failure was `OPS Tests / OPS Provision (macos-intel)` hanging 55
minutes on `Verify: SSH connectivity` until its `timeout-minutes: 45` cancelled
it; `CI Complete` then failed the run with `OPS_TESTS: cancelled (soft-required,
must be 'success' or 'skipped')`. The QEMU/HVF VM never came up for SSH.

Two rules came out of it. **`completed` is not terminal** — require the same
`run_attempt` to still be complete on a second look. And **classify before
fixing**: the same job had passed on run `32805254228` on the same branch, which
makes it transient by the pr-merge skill's own test, so the correct action was to
let the watchdog's retry run rather than to "fix" working workflow code.
