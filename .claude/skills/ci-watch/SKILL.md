---
name: ci-watch
description: How to watch a GitHub Actions run from an agent session without losing the verdict. The wake-up contract, why cancelled is not passed, and the compound-watch bug that swallowed a real failure for 90 minutes. Use whenever arming a background watch on CI, a review marker, or any other terminal state.
user-invocable: false
self-improving: true
---

# ci-watch: arming a watch that actually wakes you

The loop is only as alive as its wake-up. Every rule here was paid for by a wave
that stopped without noticing. Incidents: [incidents.md](incidents.md).

## The contract

**A watch notifies on process EXIT, not on output.** So it must EXIT at the
terminal state, and wait for exactly ONE thing.

**One wait per background command.** Need a second condition? Arm a second watch
after the first fires. Two cheap watches beat one clever one.

*Audit tell:* a NON-EMPTY output file on a still-running watch means it already
answered and is waiting on something else. That is the compound-watch bug.

## The canonical form

```bash
R=<run-id>
until [ "$(gh run view $R --repo <owner>/<repo> --json status --jq .status)" = "completed" ]; do sleep 20; done
gh run view $R --repo <owner>/<repo> --json conclusion,jobs \
  --jq '{conclusion, failed:[.jobs[]|select(.conclusion=="failure")|.name], cancelled:[.jobs[]|select(.conclusion=="cancelled")|.name]|length}'
```

`run_in_background: true`. `sleep 20`, because a pre-bash hook blocks anything longer.

## Read the JOBS, not the run

`cancelled` is not a pass. Two shapes look identical and mean opposites:

| shape | meaning |
|---|---|
| cancelled siblings **with** a failed job | watchdog killed the run for that failure; fix it |
| cancelled, **zero** failures, newer head | superseded by a later push; watch the newer run |

A `conclusion=="failure"` filter returning empty has NOT proved a run clean.

## Re-check on every wake

A watch can be killed, dropped or superseded, and **a watch that never fires is
indistinguishable from a run that never finished**. So on any re-invocation,
re-read the run rather than trusting the watch, and re-arm freely. An extra
watch costs nothing; a dropped one costs the night.

A `killed`/`failed` notification is a **re-arm trigger, not a no-op**.

## A push supersedes the run you are watching

Each push restarts the pipeline. Re-arm on the new run id, and batch fixes into
one push: three pushes is three full pipelines. **`gh run watch` stays rejected
here**; see [incidents.md](incidents.md).
