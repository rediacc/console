---
description: Drain the Promoted plans in agent/plans/QUEUE.md with parallel writers. One invocation gives every unfinished Promoted plan at least one writer, started while writer_cap has a free slot and queued once it has none, and three for a plan with more than five open boxes (split by thirds of its open boxes), filling writer_cap. Each writer gets a self-contained brief with the plan's Owns as its boundary and handles every box class itself (local, already done, bench, hostinger, post-merge, operator). A writer the concurrency guard refuses is queued, never dropped. The read-only survey is optional and lands in a file. Free text after the command narrows it to matching plans.
argument-hint: "[filter: plan names or substrings, e.g. 'backup proxy'; omit for every unfinished Promoted plan]"
allowed-tools: Bash(.claude/hooks/stop/worklist.py --list --open:*), Bash(.claude/hooks/stop/worklist.py --plan-investigate:*), Bash(.claude/hooks/stop/worklist.py --plan-tick:*), Bash(.claude/hooks/stop/worklist.py --add:*), Bash(.claude/hooks/stop/worklist.py --lease:*), Bash(.claude/hooks/stop/worklist.py --update:*), Bash(git add:*), Bash(git commit:*), Bash(npm run login\:bench:*), Bash(git branch:*), Bash(git log:*), Bash(sed:*), Bash(grep:*), Bash(date:*), Bash(python3 -c:*)
---

## The queue, gathered

- Branch: !`git branch --show-current`
- UTC now: !`date -u +%Y-%m-%dT%H:%MZ`
- Writer cap and turbo settings: !`sed -n '/^## Settings/,/^## /p' agent/plans/QUEUE.md | grep -E '^(writer_cap|turbo|turbo_push|batch_size|plan_concurrency|effort):' || echo '(no Settings section)'`
- Promoted progress (generated): !`sed -n '/queue:progress:begin/,/queue:progress:end/p' agent/plans/QUEUE.md`
- Live writer leases (every session's; the tag after the title names the owner): !`.claude/hooks/stop/worklist.py --list --open 2>/dev/null | grep -E '^\s*- \[>\]' | head -20 | grep . || echo '(none)'`
- Filter: `$ARGUMENTS`

## What to do

**Drain, do not report, and do not survey first.** The operator types this instead of a long prompt; it means "every unfinished Promoted plan gets a writer now". Earlier versions surveyed first and then started a few hand-built batches, and run after run left most Promoted plans untouched. The output of one invocation is a writer on EVERY unfinished Promoted plan (or a queued item naming why it is not running yet), not a status essay. Rules of CLAUDE.md apply unchanged (rule 1 commits, rule 3 verification, rule 4 writer discipline).

### 1. Pick the plans

Every Promoted plan whose row is not `done`, in table order (the order already puts prerequisites first). With a filter, keep only plans whose file name matches it. A plan whose `Depends-On:` prerequisite is unfinished still gets its writer when the prerequisite is also in this round; the writer's brief names the prerequisite, and the writer leaves boxes that need its output as `blocked-on-dep`. A plan whose prerequisite is outside the round and unfinished is skipped unless its boxes carry a `DEPS-WAIVED:` ruling.

### 2. Build the roster, mechanically

The roster comes from the progress table and the plan files, not from a survey. For each picked plan, list its open boxes in file order with their 8-hex signatures (`open_sigs` in `.ci/config/plan-boxes.json`, or the `- [ ]` lines of the plan).

- **Five or fewer open boxes**: one writer takes them all.
- **More than five open boxes**: three writers, each a contiguous third of the open boxes in file order (sizes differ by at most one).
- **Free slots** are `writer_cap` minus the live writers counted by the gathered leases and this session's running agents.
- **Order of starting**: first one writer per plan in table order (the first third for a split plan), then the second and third thirds in table order. Whatever does not fit in the free slots is queued (step 5), in that same order.
- **Filling the cap**: when every planned writer fits and slots remain, the largest remaining share above five boxes splits into thirds again, repeated until the slots run out or no share is above five.

Writers of the same plan share the plan's `Owns:` boundary (the concurrency guard judges plans, so siblings are not refused against each other), so the guard cannot keep two siblings out of one file. Sibling writers therefore run with `isolation: "worktree"`, each in its own checkout, and never write one tree: the lead copies each accepted report's files and merges by hand any file two siblings both report. Each sibling's brief still names the other siblings' box ranges, so such a file is rare: a file one sibling's boxes plainly need belongs to that sibling, and a writer that finds it must edit a sibling's file stops and puts the exact change in its report for the lead.

### 3. The survey, optional and on disk

A survey helps only when it does not hold the writers back. When one is wanted, start a single background `general-purpose` agent (model `sonnet`, read-only) in the same message as the writers, never before them. It classifies every open box of the round into the classes of the brief below, with file:line evidence, and WRITES the result to `/tmp/writers-now/<branch>-<UTC stamp>.md`, returning only the path and per-class counts. The lead reads the counts, not the file. Writers are told the path and treat it as a hint, never as a reason to skip their own check of a box.

### 4. Start the writers, all at once

Every writer that fits is started in ONE message with parallel Agent calls, each with `isolation: "worktree"` (step 2). Model: `sonnet` when the plan's open boxes implement against an existing oracle (ports, tests, sweeps, translations); `opus` when they create the oracle (a new gate, guard, schema or design). Never `haiku` for writes. A plan's `Concurrency: exclusive` is no reason to hold its writer back: it is started anyway, and `block_plan_concurrency` decides.

Each brief stands alone, because the writer sees nothing else. Its first two lines are load-bearing for the guards and are copied from the plan header:

```
Plan: agent/plans/<PLAN-file>.md
Owns: <the plan's Owns: globs, verbatim>

PR-TASK <the plan's epic id>, repo <repo root>. Boxes (this writer's share, with signatures):
  <sig> <label>
  ...
Siblings on this plan: <writer A: sigs ...; writer B: sigs ...>, or "none".
Prerequisite in this round: <PLAN-x.md, or "none">.
Survey hint, if present: </tmp/writers-now/...md>.

Boundary: only files matching the Owns globs above. Any other file, or a file a sibling's boxes
plainly need, is not edited: the exact change goes into the report for the lead.

Handle each box by its class, which this writer determines itself from the tree:
- LOCAL: code, tests, docs or config doable in this checkout. Implement it and run its acceptance
  command.
- ALREADY-DONE: the tree already holds it. Change nothing; cite file:line or the commit, and run
  the command that proves it.
- BENCH: needs bench or edge. Land the code half, then run the box's own named accept command on
  bench (`npm run login:bench` logs in headlessly; bench deploys are free). A run that rebuilds the
  CLI (vm:check, a drill) or deploys edge is not run here: name the exact command for the lead.
- HOSTINGER: needs the production hostinger machine. Land the code half and name the exact
  acceptance command; the production machine is not touched by this writer.
- POST-MERGE: needs main, a released CLI or renet, CD, a nightly or the stable promote. Land any
  local half and name what closes the box after the merge.
- OPERATOR: needs an operator decision or operator-only access. Change nothing; write the decision
  as one question with the recommended option first.
A box whose code landed but whose live accept is open is classified by its open half.

Rules: never commit; no git checkout, restore, stash, clean, reset or add; no regenerate or sync
script (name it for the lead instead); never vitest from the repo root; no edits outside the
boundary.

Report, one block per box signature:
  <sig> <class> <done|partial|untouched|blocked-on-dep>
  files: <changed paths>
  commands: <each command run, with its exit code>
  remains: <the half still open and the exact command or decision that closes it, or "nothing">
```

**Track** each writer as one worklist item (`--add`, text naming the plan and its box signatures), and lease it to the real agent id only after the Agent call returns it (`--lease <me> <id> +120 worker:<agent-id>`). `--plan-investigate` each box when its writer starts.

### 5. A refused writer is queued, never dropped

A spawn refused by `block_agent_cap` (cap full) gets its item leased to `worker:queue` with the refusal in the note. A spawn refused by `block_plan_concurrency` (an exclusive plan, or an Owns overlap with a live writer) stays an open item, and `--update <me> <id> queued: refused by block_plan_concurrency behind <plan> (#<holding item>)` records the guard's exact refusal. Either way the brief is kept verbatim in the item's text or the round log, so the retry is a copy, not a rewrite. When a writer reports, the queue is retried in the order of step 2 before anything new starts.

### 6. As each writer reports

Spot-check against the artifact (rule 4), rerun its acceptance commands, run any regenerate it named, commit by path (submodules first, then the pointer), and `--plan-tick` each box it finished with the commit and the proof. An ALREADY-DONE box is closed with `--plan-investigate <me> <plan> <sig> present <kind>:<token> -- <evidence> --write` and then `--plan-tick`, after the cited evidence is checked (an agent's "already done" is a hypothesis). Settle the per-commit review findings, then start the next queued writer.

### 7. Live and parked boxes

- A BENCH command a writer named runs as soon as nothing it needs is mid-edit (a vm:check or a drill rebuilds the CLI; no CLI writer runs beside one).
- A HOSTINGER command runs by the lead, exactly as named; a step the plan does not name goes to the operator.
- POST-MERGE boxes stay open and are named once in the report; they close after the merge.
- OPERATOR questions from every writer become one batched `AskUserQuestion` (recommended option first), never one question per box.

### 8. Report in one screen

Writers running (plan, share, agent), writers queued with the refusal that holds each, boxes ticked this round with commits, and the boxes still open by class. No narration of the survey.
