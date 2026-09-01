---
name: ci-watch
description: How to read this repo's CI from an agent session without losing the verdict. One script does it; hand-rolled gh polling loops are blocked at the pre-bash guard and at the Stop hook. Use whenever checking CI, waiting on a run, or diagnosing a red.
user-invocable: false
self-improving: true
---

# ci-watch: one script, because the recipe kept rotting

## Use this. There is no second way.

```bash
.ci/scripts/ci/ci-trace.py                       # one-shot: what is CI doing now
.ci/scripts/ci/ci-trace.py --wait                # block until THIS head is final
.ci/scripts/ci/ci-trace.py --wait --until-final  # babysitting: wait past the first red
```

`--wait` goes in a background task (`run_in_background: true`). It owns its polling
interval (`--timeout` overrides the 5400s default), so you never write a loop; the
process exit is the wake-up. Exits: **0** green, **1** red *or superseded*, **2** no
verdict (in flight, no open PR, unreadable), **3** head moved by a push (`--json` for
machine-readable output).

Ad-hoc `gh` watch commands are **refused**, and a hand-rolled watch left running
**blocks the Stop hook** ([incidents.md](incidents.md): five incidents in one week).
It keys on the **PR head commit**, so a watchdog rerun *replaces* the old attempt.

**Poll the head before arming**: `gh api .../pulls/<n> --jq .head.sha` lagged a push by
30-60s repeatedly on 2026-09-01, and a watch armed early traces the stale head.

**A dispatched run needs `--run <id>`.** A branch's `statusCheckRollup` does NOT contain
a `workflow_dispatch` run's checks: `--wait --ref main` reported GREEN while a Release
run was still tagging.

## Diagnosing a red

**`cancelled` is never a pass.** Cancelled *with* a failed job means the watchdog killed
the run for that failure; with *zero* failures it was superseded, so trace the new head.

**"It passed earlier" is NOT a classifier.** That shortcut lived here and was wrong: on
2026-09-01 a gate green on five earlier runs of the same branch went red five times and
was a real mid-branch regression. Four re-runs bought that lesson.

1. **Download the artifact first.** Where a gate uploads one, its `summary.json` names
   the failure mode in one command. Code-reading only guesses.
2. **Find the last green at STEP level**, not run level -- a cancelled run hides passing
   steps, so the run list places the boundary wrong.
3. **Read the window, including when it is empty:**

       git log --oneline <last-green>..HEAD       # what could have done it
       git log --oneline -- <the file that broke> # has it broken before, and why

   Only docs in the window is affirmative evidence for an environmental cause.
4. **Reproduce with `CI=true` set.** That alone changes subprocess output (TRAPS.md, "a
   gate that fails ONLY in CI may be matching bytes that CI coloured"), so "it passes
   locally" is not evidence against a real bug.

**Re-check on every wake.** A watch that never fires is indistinguishable from a run
that never finished; a `killed`/`failed` notification is a re-arm trigger, not a no-op.
Each push restarts the pipeline, so batch fixes into one push.
