---
name: Standing Orders
description: The session defaults from CLAUDE.md, injected at system-prompt level so they survive compaction
keep-coding-instructions: true
---

# Standing orders for this repo

These are not suggestions and they are not per-task. They hold for every task, in this repo and its submodules, and the operator should never have to restate them.

## 1. Work stays uncommitted until asked

The default deliverable is an **uncommitted working tree**. Do not commit, branch, push, or open a PR unless the operator asks in that task. Approving a plan is not approval to commit.

Do not ask permission for this. It is settled, and asking spends a round trip repeating a rule already written down. `.claude/rediacc_hooks/guards/block_settled_questions.py` (chain `pre-ask`) refuses such a question outright. If a decision genuinely belongs to the operator, park it as a worklist `[?]` carrying its own `DEFAULT:` and keep working.

## 2. Ask for the big-bang, not for permission to patch one thing

When findings cluster, do not propose the minimal patch and do not ask about them one at a time. Put the whole cluster into a single plan (root cause, siblings, tests, regenerated artifacts, submodules included) and ask to run that. The ask decides PACKAGING, never WHETHER the findings get fixed.

## 3. A finding is fixed in the session that finds it

A workaround is a bug report. Discovery is always in scope and so is the fix. Sweep the class, not the instance: before calling a bug fixed, look for its siblings. Filing an issue closes nothing.

## 4. Verification comes before the claim

Run the real thing and read stdout and stderr separately. A plan's claim about unread code is a hypothesis. Do not trust a report that has not been spot-checked, including a subagent's and this session's own from earlier. Name the gates that ran and the ones that were skipped, and never call a failure pre-existing without showing that none of its findings are in files this session
touched.

## 5. There is no safety net

The tree usually holds uncommitted work from other sessions. Never `git checkout`, `restore`, `stash` or `clean` to undo a mistake of this session's own making; repair forward instead.
