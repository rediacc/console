---
name: ci-watch
description: How to watch a GitHub Actions run from an agent session without losing the verdict. The wake-up contract, why cancelled is not passed, and the compound-watch bug that swallowed a real failure for 90 minutes. Use whenever arming a background watch on CI, a review marker, or any other terminal state.
user-invocable: false
self-improving: true
---

# ci-watch — arming a watch that actually wakes you

The loop is only as alive as its wake-up. Everything here was paid for by a wave
that stopped without noticing.

## The contract, in one line

**A background watch notifies on process EXIT, not on output.** So a watch must
EXIT the moment the thing you are waiting for reaches a terminal state — and
must wait for exactly ONE thing.

## The bug this file exists for: the compound watch

Observed 2026-08-24, on a landing that had already run nine rounds. The watch was:

```bash
# BROKEN — do not copy
R=<run-id>
until [ "$(gh run view $R --json status --jq .status)" = "completed" ]; do sleep 20; done
gh run view $R --json conclusion,jobs --jq '...'          # verdict printed here
SHA=$(git rev-parse HEAD)
until <review marker for $SHA appears>; do sleep 20; done  # ...then it kept waiting
echo REVIEWED
```

CI failed at 23:55:13. The verdict — `failed: ["Quality / Static"]` — was written
into the output file **and nothing woke the session**, because the process had not
exited: it had moved straight into the second `until`, waiting for a review marker
that would never appear, because a red run posts no review.

The failure sat unread for about ninety minutes. It was found only when the
operator pasted the failing job's URL into the chat. The session was, from its own
point of view, healthily waiting.

**Rule: one wait per background command.** Want a second condition? Arm a SECOND
watch after the first one fires. Two cheap watches beat one clever one.

The tell, if you are auditing a live wait: a watch whose output file is
NON-EMPTY while the task is still running has already answered and is now waiting
for something else. That is the signature of this bug.

## The canonical form

```bash
R=<run-id>
until [ "$(gh run view $R --repo <owner>/<repo> --json status --jq .status)" = "completed" ]; do sleep 20; done
gh run view $R --repo <owner>/<repo> --json conclusion,jobs \
  --jq '{conclusion, failed:[.jobs[]|select(.conclusion=="failure")|.name], cancelled:[.jobs[]|select(.conclusion=="cancelled")|.name]|length}'
```

with `run_in_background: true`. `sleep 20` is deliberate — a pre-bash hook blocks
anything longer.

## Read the JOBS, never just the run

`conclusion: cancelled` is NOT a pass and NOT always a failure. Two shapes look
identical in a run list and mean opposite things:

| shape | meaning | what to do |
|---|---|---|
| cancelled siblings **with** a failed job | the watchdog killed the run for that failure | fix the failure |
| cancelled with **zero** failures and a newer head | superseded by a later push | ignore; watch the newer run |

So the jq above counts cancelled jobs as well as failures. A filter for
`conclusion=="failure"` that comes back empty has NOT proved the run was clean.

## `gh run watch` is a convenience, not a contract

`gh run watch --exit-status` exists and returns non-zero when the run fails
(<https://cli.github.com/manual/gh_run_watch>). Do not use it here: it dropped
**four times out of four** in one campaign — the run went terminal, nothing fired,
and the loop simply stopped for over an hour each time. It has also been seen
exiting 1 while the run was still `in_progress`. The `until` poll above exits on a
state you read yourself, which is the property that matters.

## Every re-invocation re-checks the run

A watch can be killed, dropped, or superseded, and **a watch that never fires is
indistinguishable from a run that never finished**. So whenever you are woken for
any reason:

1. Re-read the run (`gh run view <id> --json status,conclusion`) rather than
   assuming the watch still holds it.
2. Re-arm freely. An extra watch costs nothing; a dropped one costs the night.

A task notification whose `status` is `killed` or `failed` is a **re-arm trigger,
not a no-op**. Answering one with "no response requested" is how a green run sat
unnoticed in draft on 2026-08-24 until the operator asked "don't you watch?".

## A push supersedes the run you are watching

Each push restarts the pipeline, so the watch you armed is now pointed at a run
that will be cancelled. Re-arm on the new run id after every push — and batch
fixes into one push, because three pushes is three full pipelines.
