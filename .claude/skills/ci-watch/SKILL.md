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

`--wait` goes in a background task (`run_in_background: true`). It owns its polling interval, so no loop is ever hand-written; the process exit is the wake-up. Exits: **0** green, **1** red (a job failed, or a gate was cancelled and the cause is named), **2** no verdict (in flight, still registering, a truncated read, no open PR, unreadable), **3** head moved by a push, **4** no CI for the head (a `[skip ci]` or path-filtered commit, after a registration grace; for a branch head the nearest ancestor with checks is named and judged) (`--json` for machine-readable output).

**GREEN means `CI Complete` reported success on this head.** Contexts that registered early (`CI - OBS Mirror` within a minute of a push) are not a verdict: on 2026-10-02 a tracer without this rule printed GREEN for run 36953549081 one minute in, and the run was later cancelled. While `CI Complete` is absent the read is `running` and names what has registered. `CI Verdict` and `Publish CI Verdict` never block GREEN.

`--wait --worklist-item <id> --session <sid8>` also writes the final verdict (head, run, attempt, cause, next command) onto that worklist item, and every final `--wait` verdict lands in the branch's verdict cache, so a later turn or another session reads it without a network call. The git-push PostToolUse hook (`arm_ci_watch.py`) arms exactly that `--wait --until-final` in the background after each push of the live branch. `--worklist-script <path>` is a hidden test seam that replaces the worklist CLI in the tracer's tests; it is never passed by hand.

**`--timeout` requires a unit suffix**: `90m`, `5400s` or `1h`, default `5400s`. A bare number is refused, because its unit would have to be guessed.

Ad-hoc `gh` watch commands are **refused**, and a hand-rolled watch left running **blocks the Stop hook** ([incidents.md](incidents.md): five incidents in one week). It keys on the **PR head commit**, so a watchdog rerun *replaces* the old attempt.

Raw CI **reads** are refused too, by the pre-bash guard `block_raw_ci_read`: `gh pr checks`, `gh run list` and `gh run view`, `gh api` GETs on actions runs, jobs, logs, check-runs and annotations, and GraphQL rollup queries. Each refusal prints the tracer verb that answers it, from the `CI_READ_VERBS` table in `.claude/hooks/lib/sanctioned.py`. Writes are not refused (`gh run rerun`, `cancel`, `download`, `gh api -X POST`), nor are PR edits, `pulls/<n>`, issues, releases, artifacts or a run list of another workflow. <!-- raw-ci-read-ok: names what is refused -->

**Poll the head before arming**: `gh api .../pulls/<n> --jq .head.sha` lagged a push by 30-60s repeatedly on 2026-09-01, and a watch armed early traces the stale head.

**A submodule PR needs `--repo OWNER/NAME`**, run from inside its checkout: `.ci/scripts/ci/ci-trace.py --repo rediacc/account` traces that repo's open PR for the checkout's branch. Without the flag every read targets the console. A PR head with no check contexts at all (account has no workflows) reads `NO-CI` and exits 4 once the 180 s grace has passed.

**A dispatched run needs `--run <id>`.** A branch's `statusCheckRollup` does NOT contain a `workflow_dispatch` run's checks: `--wait --ref main` reported GREEN while a Release run was still tagging.

## Diagnosing

Start with `--why`. Every verb is one read that exits, compact by default, `--json` for structure:

```bash
.ci/scripts/ci/ci-trace.py --why                         # the PR head's Console CI run: cause, failing step, category, silences
.ci/scripts/ci/ci-trace.py --run <id> --why              # the same for one run
.ci/scripts/ci/ci-trace.py --runs                        # the newest Console CI runs on the branch (--ref main after a merge)
.ci/scripts/ci/ci-trace.py --scheduled                   # newest scheduled run of every cron workflow on main, failed jobs named (--workflow X: its last 5)
.ci/scripts/ci/ci-trace.py --run <id> --jobs             # counts + every job that did not pass, durations against p90
.ci/scripts/ci/ci-trace.py --run <id> --jobs --attempt 2 # one attempt of a watchdog-rerun run
.ci/scripts/ci/ci-trace.py --job <id> --errors           # the failing step's excerpt, infra/code category, top silences
.ci/scripts/ci/ci-trace.py --job <id> --steps            # every step with its duration, silences flagged
.ci/scripts/ci/ci-trace.py --job <id> --log              # the whole log, ANSI-stripped, cached once complete
.ci/scripts/ci/ci-trace.py --history "<job name>"        # that job's last 5 completed runs
.ci/scripts/ci/ci-trace.py --watchdog                    # the Watchdog Monitor runs for the head's run (or --watchdog <run>)
```

A red or cancelled `--wait` exit already appends the `--why` render, so the first diagnosis is in the wake-up itself. Every verdict also prints a **PR SIGNALS** block: the PR's bot comments for this head (a Claude review attempt with its class and the exact re-run command, the review summary, the per-commit table, the labels ledger), and `--wait` prints a new one as soon as it appears. The Claude review starts only after Console CI completes, so its outcome is `python3 .claude/hooks/stop/wl_prreview.py --wait`, which names the attempt class on a failed run.

**Scheduled runs are a Stop-hook blocker, not a human-only issue.** A red scheduled run on main (`--scheduled`) holds the session's stop under `scheduled-red` until an item tracks it (`sched:<stem> run:<id>` in its text), and a tick needs a newer green scheduled run as evidence (a fix commit on main is not enough; operator ruling 2026-10-04). A red nightly holds the stable promotion, which counts only green scheduled runs. An Actions job's check-run id is its job id, so the id in a check-run URL works with `--job`.

**`cancelled` is never a pass, and it is never assumed superseded.** `--why` attributes a cancel with zero failed jobs from evidence, in this order: `watchdog-budget` (a Watchdog Monitor run recorded `CI BUDGET VIOLATION` for a job; run 36953549081 was this, a 20.1 m job against a 20 m budget), `watchdog-failure`, `superseded` (the PR head moved past the run, or a newer run exists on the same head), `timeout-kill`, `manual`, else `unknown`. Only `superseded` means trace the new head; every other cause is a red to diagnose.

When `--why` is not enough (a gate red that its own artifact explains, a boundary between green and red to place, a CI-only failure): [diagnosing.md](diagnosing.md).

**Re-check on every wake.** A watch that never fires is indistinguishable from a run that never finished; a `killed`/`failed` notification is a re-arm trigger, not a no-op. Each push restarts the pipeline, so batch fixes into one push.
