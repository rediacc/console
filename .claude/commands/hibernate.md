---
description: Hibernate the Windows host this WSL session runs on, after every running sub-agent and background job has finished. Records STATE.md first so the session resumes cleanly on wake.
argument-hint: "[now] (the word now, in any case, skips waiting for sub-agents; default waits for them)"
# User-only by operator ruling 2026-10-18 ("Be sure that it's invokable only from user, so AI agents should not be able to invoke it."): an entry in the model-invocation exception list.
disable-model-invocation: true
allowed-tools: Bash(date:*), Bash(git status:*), Bash(git log:*), Bash(git branch --show-current), Bash(grep:*), Bash(head:*)
---

## Current state

- UTC now: !`date -u +%FT%H:%MZ`
- Branch: !`git branch --show-current`
- Uncommitted paths (outside agent/): !`git status --short | grep -v ' agent/' | head -20`

## Task: hibernate the host

The operator invoked `/hibernate $ARGUMENTS`. The Windows host suspends to disk; WSL, this session and every process in it freeze and resume where they stopped when the machine wakes.

1. **Start nothing new.** Spawn no sub-agent and no new background job from here on.
2. **Wait for what is running**, unless the arguments contain the word `now` (in any case): every live sub-agent and background task finishes and its result is read (a writer's patch stays where it was delivered; applying it is work for after the wake). A wake-up timer started with `wl_wake.py` may be stopped, since it only exists to wake this session.
3. **Record the resume point**: commit any verified unit the session holds, then rewrite `STATE.md` through `worklist.py --state <me>` with the patches waiting to be applied, the items in flight and the next actions in order, and commit it by path. Commit the per-commit review records (`worklist.py --review-commit <me>`). If any part of this step fails, stop and report the failure; step 4 does not run.
4. **Hibernate**: run `/mnt/c/Windows/System32/shutdown.exe /h`. On success the host suspends during the call and nothing runs until the operator wakes the machine; if the call returns, report its exit code (non-zero means the host did not hibernate).
5. **On wake**, the operator says so; continue from `STATE.md`'s next actions.
