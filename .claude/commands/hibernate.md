---
description: Suspend this native Linux host (hibernate to disk when it can resume from it, suspend to RAM otherwise), after every running sub-agent and background job has finished. Records STATE.md first so the session resumes cleanly on wake.
argument-hint: "[now] (the word now, in any case, skips waiting for sub-agents; default waits for them)"
# User-only by operator ruling 2026-10-18 ("Be sure that it's invokable only from user, so AI agents should not be able to invoke it."): an entry in the model-invocation exception list.
disable-model-invocation: true
allowed-tools: Bash(date:*), Bash(git status:*), Bash(git log:*), Bash(git branch --show-current), Bash(grep:*), Bash(head:*), Bash(./run.sh worktree landing --status)
---

## Current state

- UTC now: !`date -u +%FT%H:%MZ`
- Branch (this tree): !`git branch --show-current`
- Branch (landing tree, from the `rediacc-landing.json` record under the git common dir): !`./run.sh worktree landing --status`
- Uncommitted paths (outside agent/): !`git status --short | grep -v ' agent/' | head -20`

## Task: hibernate the host

The operator invoked `/hibernate $ARGUMENTS`. The host suspends; this session and every process in it freeze and resume where they stopped when the machine wakes. `/tmp` is a tmpfs on this host: suspend keeps it, but a failed resume or a power loss during a suspend to RAM loses it and every process, so the resume point in step 3 is what survives.

1. **Start nothing new.** Spawn no sub-agent and no new background job from here on.
2. **Wait for what is running**, unless the arguments contain the word `now` (in any case): every live sub-agent and background task finishes and its result is read (a writer's patch stays where it was delivered; applying it is work for after the wake). A wake-up timer started with `wl_wake.py` may be stopped, since it only exists to wake this session.
3. **Record the resume point**: commit any verified unit the session holds, then rewrite `STATE.md` through `worklist.py --state <me>` with the patches waiting to be applied, the items in flight and the next actions in order, and commit it by path. Commit the per-commit review records (`worklist.py --review-commit <me>`). If any part of this step fails, stop and report the failure; step 4 does not run.
4. **Suspend**: hibernate to disk only when the host can resume from it: `/sys/power/state` lists `disk`, `swapon --show` totals at least the RAM in `free -b`, and `/proc/cmdline` carries `resume=`. Then run `sudo systemctl hibernate`; otherwise run `sudo systemctl suspend` (suspend to RAM) and say which one ran and why (measured 2026-11-25 on the native Ubuntu host: 8 GB swap against 62 GB RAM and no `resume=`, so suspend to RAM). On success the host suspends during the call and nothing runs until the operator wakes the machine; if the call returns, report its exit code (non-zero means the host did not suspend).
5. **On wake**, the operator says so; continue from `STATE.md`'s next actions.
