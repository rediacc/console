---
name: Standing Orders
description: The session defaults from CLAUDE.md, injected at system-prompt level so they survive compaction
keep-coding-instructions: true
---

# Standing orders for this repo

These are not suggestions and they are not per-task. They hold for every task, in this repo and its submodules, and the operator should never have to restate them.

## 1. Verified work is committed as it lands, on the one branch

Uncommitted work is not allowed to pile up into a mountain nobody can review. A verified unit (one purpose inside one epic, its acceptance check run with the exit code read, only paths this session owns) is committed right away with `git commit -F <msg> -- <paths>` and a `PR-TASK:` trailer, before the next unit starts; a worklist item is ticked with `commit:<sha>`. Writers never commit: the lead commits their spot-checked output. Pushes are separate: at an epic milestone, at least every 2 hours of committed work, and before a stop that leaves unpushed commits.

One branch and one PR per repository, with no agent path to a second: `block_second_branch` and `block_second_open_pr` refuse it, and a second one is the operator's own `!` command. `main` takes only a commit whose subject ends in `[hotfix]` with a `Hotfix-Evidence:` trailer, and only the operator pushes it.

Do not ask permission for this. It is settled, and asking spends a round trip repeating a rule already written down. `.claude/rediacc_hooks/guards/block_settled_questions.py` (chain `pre-ask`) refuses such a question outright. If a decision genuinely belongs to the operator, park it as a worklist `[?]` carrying its own `DEFAULT:` and keep working.

## 2. Ask for the big-bang, not for permission to patch one thing

When findings cluster, do not propose the minimal patch and do not ask about them one at a time. Put the whole cluster into a single plan (root cause, siblings, tests, regenerated artifacts, submodules included) and ask to run that. The ask decides PACKAGING, never WHETHER the findings get fixed.

## 3. A finding is fixed in the session that finds it

A workaround is a bug report. Discovery is always in scope and so is the fix. Sweep the class, not the instance: before calling a bug fixed, look for its siblings. Filing an issue closes nothing.

## 4. Verification comes before the claim

Run the real thing and read stdout and stderr separately. A plan's claim about unread code is a hypothesis. Do not trust a report that has not been spot-checked, including a subagent's and this session's own from earlier. Name the gates that ran and the ones that were skipped, and never call a failure pre-existing without showing that none of its findings are in files this session
touched.

## 5. The commit is the safety net

Committed work survives; uncommitted work does not, and the tree usually holds uncommitted work from other sessions. Never `git checkout`, `restore`, `stash` or `clean` to undo a mistake of this session's own making; repair forward instead, with a new commit when the mistake is already committed (no amending).
