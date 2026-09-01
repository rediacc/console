---
name: ci-watch
description: How to read this repo's CI from an agent session without losing the verdict. One script does it; hand-rolled gh polling loops are blocked at the pre-bash guard and at the Stop hook. Use whenever checking CI, waiting on a run, or diagnosing a red.
user-invocable: false
self-improving: true
---

# ci-watch: one script, because the recipe kept rotting

## Use this. There is no second way.

```bash
.ci/scripts/ci/ci-trace.py                    # one-shot: what is CI doing right now
.ci/scripts/ci/ci-trace.py --wait             # block until THIS head is final
.ci/scripts/ci/ci-trace.py --wait --until-final  # babysitting: keep waiting past the first red
.ci/scripts/ci/ci-trace.py --json             # machine-readable
```

`--wait` goes in a background task (`run_in_background: true`). It owns its
polling interval (`--timeout` overrides the 5400s default), so you never write
a loop; the process exit is the wake-up.

| exit | meaning |
|---|---|
| 0 | green: head final, nothing failed |
| 1 | red: a job failed, **or** the run was superseded |
| 2 | no verdict: still in flight, no open PR, or unreadable |
| 3 | head moved: a push replaced the head being watched |

## Watching a DISPATCHED run (Release), not a PR's CI

A branch's `statusCheckRollup` does NOT contain a `workflow_dispatch` run's
checks. `--wait --ref main` reported GREEN while a Release run was still
tagging/deploying. Use `--run <id>` instead (in-flight -> exit 2, success -> 0).

## Why you cannot hand-roll it

Ad-hoc `gh` watch commands are **refused**, and a hand-rolled watch left running
**blocks the Stop hook** -- five incidents in one week bought that
([incidents.md](incidents.md)). The script keys on the **PR head commit**, so a
watchdog rerun *replaces* the old attempt rather than becoming inexpressible.

## Reading the answer

**`cancelled` is never a pass**, and two shapes mean opposites — the script says
which, so do not re-derive it:

| shape | meaning |
|---|---|
| cancelled **with** a failed job | the watchdog killed the run for that failure |
| cancelled, **zero** failures | a newer push superseded it; trace the new head |

**Classify before fixing, and "it passed earlier" is NOT the classifier.** That
shortcut used to live here and it was wrong: on 2026-09-01 a gate that had passed
on five earlier runs of the same branch went red five times running, and it was a
real regression introduced mid-branch, not a flake. Four re-runs were spent on it.

An earlier pass is evidence only once you have asked what changed since it:

    git log --oneline <last-green-sha>..HEAD     # find the last STEP-level green first
    git log --oneline -- <the file that broke>   # has this broken before, and why

Read the answer including when it is empty. A window containing only docs is
affirmative evidence for an environmental cause; a window containing the failing
file is your suspect. **And find the last green at STEP level, not run level** — a
cancelled run hides passing steps, so the run list will place the boundary wrong.

**A red that reproduces locally is not environmental, and a red that does NOT
reproduce locally is not automatically environmental either.** `CI=true` alone
changes subprocess output (see TRAPS.md, "a gate that fails ONLY in CI may be
matching bytes that CI coloured"); re-run the failing command with `CI=true` set
before concluding the runner was at fault.

**Download the artifact before diagnosing from code.** Where a gate uploads one,
its `summary.json` names the failure mode directly and costs one command.

## Re-check on every wake

**A watch that never fires is indistinguishable from a run that never finished.**
A `killed`/`failed` notification is a re-arm trigger, not a no-op. Each push
restarts the pipeline, so batch fixes into one push.
