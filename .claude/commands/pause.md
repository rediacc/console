---
description: Pause the session for an operator break (a restart, an update, a trip): switch the Stop hook to quiet, start nothing new, let running sub-agents finish and record what they left, cancel the session's crons, and write a resume point. Resuming restores the effort level and continues from STATE.md.
argument-hint: "[resume-effort] [note]  (resume-effort is quiet|low|smart|high|ultra, the level to restore on resume; default: the level in force now)"
allowed-tools: Bash(date:*), Bash(git branch --show-current), Bash(grep:*), Bash(head:*), Bash(git status:*)
---

## Current state

- UTC now: !`date -u +%FT%H:%MZ`
- Branch: !`git branch --show-current`
- Effort in force: !`grep -m1 '^effort:' agent/plans/QUEUE.md`
- Uncommitted paths (outside agent/): !`git status --short | grep -v ' agent/' | head -20`

## Task: pause for the operator

The operator invoked `/pause $ARGUMENTS`. The machine may restart, Docker or WSL may be updated, or the operator is simply away: anything not on disk or in git may be gone afterwards, `/tmp` included.

1. **Quiet the hook.** Note the effort level in force above, then `worklist.py --queue-set <me> effort=quiet`. The resume level is the first argument when it names a level, otherwise the noted one.
2. **Cancel the session's crons** (`CronList`, then `CronDelete` each): a continue-loop or heartbeat would restart work the operator asked to stop. Keep each cancelled cron's schedule and prompt for the resume point.
3. **Start nothing new.** No sub-agent, workflow, writer wave, live run or background job from here on, and no fix of a finding the hook raises beyond recording it.
4. **Let running sub-agents finish.** Keep the wake timer armed (`wl_wake.py <me>` as its own background call, timeout 2400000) only while one is still running. As each finishes, record what it left without landing it: its worktree path, its commit shas per repo, its verdicts or report file, and any diff it handed back. Copy any result file it wrote under `/tmp` to `.ci/cache/pause/<me>/` (a restart empties `/tmp`). Put the record on its worklist item with `--update`, then `--lease <me> <id> release` so the hook does not chase a finished worker. Background shells keep running unless they only exist to wake the session.
5. **Commit and write the resume point.** Commit any verified unit already in hand (the CLAUDE.md rule 1 form) and the review records (`worklist.py --review-commit <me>`). Then rewrite STATE.md through `worklist.py --state <me>` with a pause line (why, when, the resume effort level), the cancelled crons with their prompts, every lease waiting to land with its result path, and the next actions in order, the first being to land those leases. Commit `agent/plans/QUEUE.md` and STATE.md by path.
6. **Report in one screen**: what finished, what waits to land and where, the resume level, and that nothing will start until the operator returns. A cron firing or a timer exit that arrives while paused gets one line saying the session is paused, nothing more.

## On resume

When the operator says they are back, restore the effort level (`--queue-set <me> effort=<resume level>`), recreate any cancelled cron still wanted, check what the break may have changed (`./rdc.sh ops status` for the VM fleet, `docker version` after a Docker update), and continue from STATE.md's next actions.
