---
name: ci-watch
description: How to read this repo's CI from an agent session without losing the verdict. One script does it; hand-rolled gh polling loops are blocked at the pre-bash guard and at the Stop hook. Use whenever checking CI, waiting on a run, or diagnosing a red.
user-invocable: false
self-improving: true
---

# ci-watch: one script, because the recipe kept rotting

## Use this. There is no second way.

```bash
.ci/scripts/ci/ci-trace.py            # one-shot: what is CI doing right now
.ci/scripts/ci/ci-trace.py --wait     # block until THIS head is final
.ci/scripts/ci/ci-trace.py --json     # machine-readable
```

`--wait` goes in a background task (`run_in_background: true`). It owns its
polling interval, so you never write a loop; the process exit is the wake-up.

| exit | meaning |
|---|---|
| 0 | green: head final, nothing failed |
| 1 | red: a job failed, **or** the run was superseded |
| 2 | no verdict: still in flight, no open PR, or unreadable |
| 3 | head moved: a push replaced the head being watched |

## Why you cannot hand-roll it

Ad-hoc `gh` watch commands are **refused** by `block-adhoc-sanctioned.sh`, and a
hand-rolled watch left running **blocks the Stop hook**. Four failures in one
afternoon bought that ([incidents.md](incidents.md)): a stale recipe in nine
places, a verdict from a superseded attempt, a verdict from an already-cancelled
run, and a swallowed network blip.

The script keys on the **PR head commit** and reads `statusCheckRollup`, which
exposes the latest check run per context. A watchdog rerun therefore *replaces*
the old attempt, and an old head is not in the rollup at all — so those failures
are not handled, they are inexpressible.

## Reading the answer

**`cancelled` is never a pass**, and two shapes mean opposites — the script says
which, so do not re-derive it:

| shape | meaning |
|---|---|
| cancelled **with** a failed job | the watchdog killed the run for that failure |
| cancelled, **zero** failures | a newer push superseded it; trace the new head |

**Classify before fixing.** A job that passed on an earlier run of this branch is
transient, already being retried, and "fixing" it edits working code. The script
marks retryable failures as not-yet-actionable while the head is live.

## Re-check on every wake

**A watch that never fires is indistinguishable from a run that never finished.**
Re-read on any re-invocation; a `killed`/`failed` notification is a re-arm
trigger, not a no-op. Each push restarts the pipeline, so batch fixes into one
push.
