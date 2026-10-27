---
description: Drain the Promoted plans in agent/plans/QUEUE.md with parallel writers. Reads the generated progress table, classifies every open box of every unfinished Promoted plan (local now, live on bench/edge, live on hostinger, post-merge, operator, already done), then fans out writers on the local-now and bench/edge work with disjoint file ownership up to writer_cap, leases each, and keeps going until every open box is either ticked or genuinely waiting on something named. Free text after the command narrows it to matching plans.
argument-hint: "[filter: plan names or substrings, e.g. 'backup proxy'; omit for every unfinished Promoted plan]"
allowed-tools: Bash(.claude/hooks/stop/worklist.py --list --open:*), Bash(git branch:*), Bash(git log:*), Bash(sed:*), Bash(grep:*), Bash(date:*), Bash(python3 -c:*)
---

## The queue, gathered

- Branch: !`git branch --show-current`
- UTC now: !`date -u +%Y-%m-%dT%H:%MZ`
- Writer cap and turbo settings: !`sed -n '/^## Settings/,/^## /p' agent/plans/QUEUE.md | grep -E '^(writer_cap|turbo|turbo_push|batch_size|plan_concurrency|effort):' || echo '(no Settings section)'`
- Promoted progress (generated): !`sed -n '/queue:progress:begin/,/queue:progress:end/p' agent/plans/QUEUE.md`
- Live writer leases of this session: !`.claude/hooks/stop/worklist.py --list --open 2>/dev/null | grep -E '^\s*- \[>\]' | head -20 || echo '(none)'`
- Filter: `$ARGUMENTS`

## What to do

**Drain, do not report.** The operator types this instead of a long prompt; it means "the Promoted plans have open boxes, get parallel writers on everything that can move now". The output is writers running and boxes ticking, not a status essay. Rules of CLAUDE.md apply unchanged (rule 1 commits, rule 3 verification, rule 4 writer discipline).

### 1. Pick the plans

Every Promoted plan whose row is not `done`, in table order (the order already puts prerequisites first). With a filter, keep only plans whose file name matches it. Skip a plan whose `Depends-On:` prerequisite is unfinished unless its boxes carry a `DEPS-WAIVED:` ruling.

### 2. Classify every open box, once, with read-only agents

Fan out `Explore`/`general-purpose` agents (read-only; they do not count against the cap), one per plan or per group of small plans, model `sonnet`. Each returns, per open box: the 8-hex signature (from `.ci/config/plan-boxes.json` `open_sigs`), a one-line summary, and exactly one class:

- **LOCAL-NOW**: code, tests, docs or config doable in this checkout now;
- **LIVE-BENCH**: needs bench or edge (agents deploy both freely; `npm run login:bench` logs in headlessly; ops VMs via `./rdc.sh ops up`);
- **LIVE-HOSTINGER**: needs the production hostinger machine (always available; through `eu-bench` or `eu-remote`);
- **POST-MERGE**: needs `main`, a released CLI or renet, CD, a nightly, or the stable promote;
- **OPERATOR**: needs an operator decision or operator-only access;
- **ALREADY-DONE**: the tree already holds it (cite file:line or commit) and only the tick is missing.

Plus, for LOCAL-NOW and LIVE-BENCH boxes, the files each would touch. A box whose code landed but whose live accept is open is classified by the open half.

### 3. Tick what is already done

For each ALREADY-DONE box: `worklist.py --plan-investigate <me> <plan> <sig> present <kind>:<token> -- <evidence> --write`, then `--plan-tick` with the commit and the command that proves it. Spot-check the evidence first (rule 3); an agent's "already done" is a hypothesis.

### 4. Fan out writers

- **Batches**: group LOCAL-NOW boxes (and LIVE-BENCH boxes whose run is cheap and safe) into batches with DISJOINT file ownership. One plan may need several batches; one batch never spans two writers' files. Respect each plan's `Owns:` and `Concurrency:` header (`block_plan_concurrency` refuses overlap).
- **Cap**: fill up to `writer_cap` live writers, counting writers already running. Overflow batches are leased to `worker:queue` and started as slots free.
- **Model**: `sonnet` for implementation against an existing oracle (ports, tests, sweeps, translations); `opus` when the writer creates the oracle (new gate, guard, schema, design). Never `haiku` for writes.
- **Brief** (each one stands alone): the plan path and box labels with signatures; what the survey found (file:line); the exact files owned and a ban on every other file; the acceptance command per box; the rules: writers never commit, no `git checkout/restore/stash/clean/add/reset`, no regenerate or sync script (name it for the lead), never vitest from the repo root, report changed files and every command with its exit code, and say which half of each box remains live.
- **Track**: one worklist item per batch (`--add`), leased to the real agent id once it returns (`--lease <me> <id> +120 worker:<agent-id>`). Run `--plan-investigate` for each box before its writer starts.

### 5. As each writer reports

Spot-check against the artifact (rule 4), rerun its acceptance commands, regenerate what it named, commit by path (submodules first, then the pointer), `--plan-tick` each finished box with the commit and the proof, settle its per-commit review findings, then start the next queued batch.

### 6. Live and parked boxes

- LIVE-BENCH and LIVE-HOSTINGER boxes get a writer or the lead as soon as nothing in the tree they need is mid-edit (a vm:check or a drill rebuilds the CLI; no CLI writer runs beside one).
- POST-MERGE boxes stay open and are named once in the report; they close after the merge.
- OPERATOR boxes become one batched `AskUserQuestion` (recommended option first), never one question per box.

### 7. Report in one screen

Writers running (batch, plan, boxes, agent), boxes ticked this round with commits, and the boxes still open by class. No narration of the survey.
