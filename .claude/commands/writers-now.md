---
description: Drain the Promoted plans in agent/plans/QUEUE.md. One read-only survey sorts every open box into six groups first. Writers in leases take the code boxes only, grouped by the files a box touches, and land in one batch that is gated once. One sequential runner in the main checkout owns the live boxes, in the order fleet, bench, hostinger. Writers, gates and fleet runs never share the machine, and operator questions go in one batched ask. Free text after the command narrows it to matching plans.
argument-hint: "[filter: plan names or substrings, e.g. 'backup proxy'; omit for every unfinished Promoted plan]"
allowed-tools: Bash(.claude/hooks/stop/worklist.py --list --open:*), Bash(.claude/hooks/stop/worklist.py --plan-investigate:*), Bash(.claude/hooks/stop/worklist.py --plan-tick:*), Bash(.claude/hooks/stop/worklist.py --live-proof:*), Bash(.claude/hooks/stop/worklist.py --add:*), Bash(.claude/hooks/stop/worklist.py --add-many:*), Bash(.claude/hooks/stop/worklist.py --lease:*), Bash(.claude/hooks/stop/worklist.py --update:*), Bash(git add:*), Bash(git commit:*), Bash(npm run login\:bench:*), Bash(git branch:*), Bash(git log:*), Bash(sed:*), Bash(grep:*), Bash(date:*), Bash(uptime:*), Bash(nproc:*), Bash(python3 -c:*)
---

## The queue, gathered

- Branch: !`git branch --show-current`
- UTC now: !`date -u +%Y-%m-%dT%H:%MZ`
- Writer cap and turbo settings: !`sed -n '/^## Settings/,/^## /p' agent/plans/QUEUE.md | grep -E '^(writer_cap|turbo|turbo_push|batch_size|plan_concurrency|effort):' || echo '(no Settings section)'`
- Promoted progress (generated): !`sed -n '/queue:progress:begin/,/queue:progress:end/p' agent/plans/QUEUE.md`
- Live writer leases (every session's; the tag after the title names the owner): !`.claude/hooks/stop/worklist.py --list --open 2>/dev/null | grep -E '^\s*- \[>\]' | head -20 | grep . || echo '(none)'`
- Filter: `$ARGUMENTS`

## What to do

**Drain, do not report.** The operator types this instead of a long prompt, and one invocation is measured by boxes ticked and commits landed. An earlier round gave 25 writers to 30 plans and ticked nothing, because most open boxes were live runs that a lease cannot make. The rules of CLAUDE.md apply unchanged (rule 1 commits, rule 3 verification, rule 4 writer discipline).

### 1. Classify before spawning

The round is every Promoted plan whose row is not `done`, in table order, narrowed by the filter. One background `general-purpose` agent (model `sonnet`, read-only) sorts every open box of the round and writes `/tmp/writers-now/<branch>-<UTC stamp>.md`: signature, group and file:line evidence per box, plus the files each G5 box touches. It returns the path and the per-group counts. Writers start only once it has returned.

| Group | Meaning | Who takes it |
|---|---|---|
| G1 bench-rewordable | names edge or stable only as where it runs | a recorded correction to bench, then the live queue |
| G2 run now | a live run that can start today | the live queue (step 7) |
| G3 pipeline | proves CD, promote-stable, a nightly or a merge itself | nobody yet; named in the report |
| G4 time | needs a soak or a data window | nobody yet; named in the report |
| G5 code | real code or tests still to write | writers (step 2) |
| G6 operator | a decision or access only the operator has | the batched ask (step 7) |

`LP-<target> [live]` boxes are read mechanically, through `wl_liveproof.lp_boxes` and `parse_accept` (`.claude/hooks/stop/wl_liveproof.py`), which are exact. Every other tag is a hint. A writer's report overrides the survey: code it finds already present moves that box to G2, or closes it when the code was the whole box.

A plan whose `Depends-On:` prerequisite is unfinished stays in the round when the prerequisite is too, and boxes needing its output wait. A prerequisite outside the round skips the plan unless its boxes carry a `DEPS-WAIVED:` ruling.

### 2. The writer roster: G5 boxes only

Each box's signature and label are read together from the box parser, `wl_planrec.open_boxes` (`(line, raw, body, sig)` per box) or the `worklist.py` listing. `open_sigs` in `.ci/config/plan-boxes.json` is a sorted set, never a parallel list: zipped with a plan's `- [ ]` lines it pairs the wrong signature with each label, and that reached real briefs.

Writers are grouped by the files a box touches, never by thirds of a plan: boxes sharing a file go to one writer, and a plan with only live boxes gets no writer. A brief's `Owns` names those files even past the plan's own `Owns:` line, because a box outside that line otherwise goes undone. Boxes of different plans that share a file go to one writer under the plan holding the most of them.

Two hard limits bound the roster: the 20 concurrent subagents of the harness, and the 25 trees on disk at `writer_cap`. `.ci/rediacc_ci/dev/worktree_lease.py` counts finished trees too, so each is collected by `--id` as its report lands (step 6). Free slots are the smaller limit minus the running writers and the trees still on disk (`./run.sh worktree leases`).

The route is `isolation: "worktree"` on the Agent call, which reaches a lease through the harness's create hook: a detached tree under `.claude/worktrees/<id>` at the live branch's tip, submodules at their gitlinks, dependencies seeded. Uncommitted work in the main checkout is not in it. Which writer gets a lease is not asked (`block_settled_questions`). Separate leases cannot corrupt each other: `block_plan_concurrency` turns an `Owns` overlap into a note for an isolated spawn, and a clash surfaces as a cherry-pick conflict at landing, where the lead re-reads the file whole and matches its hunks to each report.

### 3. One thing at a time on the machine

Writers, or gates, or a fleet run, never two of them: writers beside gates made load 70-90 and false timeouts. Before a wave, `uptime` is read against `nproc`, and a wave waits while load is above it. The order of a round is writers, landing, one gate run, then the live queue.

### 4. Start the writers, all at once

Every writer that fits starts in ONE message with parallel Agent calls. Model: `sonnet` when its boxes implement against an existing oracle (ports, tests, sweeps, translations); `opus` when they create the oracle (a new gate, guard, schema or design). Never `haiku` for writes. A plan's `Concurrency: exclusive` is no reason to hold a writer back: it is started anyway, and `block_plan_concurrency` decides.

Each brief stands alone, because the writer sees nothing else. Its first two lines are load-bearing for the guards:

```
Plan: agent/plans/<PLAN-file>.md
Owns: <the plan's Owns: globs, verbatim, plus each file these boxes touch past them>

PR-TASK <the plan's epic id>, repo <repo root>. Boxes (this writer's share, with signatures):
  <sig> <label>
  ...
Prerequisite in this round: <PLAN-x.md, or "none">.
Survey: </tmp/writers-now/...md>, a hint; the tree decides.

Boundary: only the files named by Owns above. Any other file is not edited: the exact change goes
into the report for the lead.

Implement each box and run its acceptance command. A box the tree already holds changes nothing:
cite file:line or the commit, and run the command that proves it. A box whose remaining half is a
live run, a pipeline or a decision is not attempted: name the exact command or question.

Rules: no git checkout, restore, stash, clean, reset; no regenerate or sync script (name it for the
lead instead); never vitest from the repo root; no inline suppression. This tree is a lease:
  - commit on the detached HEAD with `git commit -F <msg> -- <paths>` and a `PR-TASK:` trailer;
    never push, never touch `agent/**` or a gitlink, never switch or create a branch;
  - run `npm run ci -- --narrow` or named tests; ci:quick, vm:check and live_proof record refuse a lease;
  - report the commit shas; the lead lands them. A result worth keeping goes in a commit or the
    report, because GC deletes the tree's ignored output with the tree.

Report, one block per box signature:
  <sig> <done|present|partial|untouched|blocked-on-dep>
  commits: <shas>
  commands: <each command run, with its exit code>
  remains: <the half still open and the exact command or decision that closes it, or "nothing">
```

**Track** the writers in one `--add-many <me>` call, one line per writer naming the plan and its box signatures, and lease each to the real agent id only after the Agent call returns it (`--lease <me> <id> +120 worker:<agent-id>`). `--plan-investigate` each box when its writer starts.

### 5. A refused writer is queued, never dropped

A spawn refused by `block_agent_cap` (cap full) gets its item leased to `worker:queue` with the refusal in the note. A spawn refused by `block_plan_concurrency` stays an open item, and `--update <me> <id> queued: refused by block_plan_concurrency behind <plan> (#<holding item>)` records the exact refusal. The brief is kept verbatim in the item's text or the round log, so the retry is a copy. When a writer reports, the queue is retried in roster order before anything new starts.

### 6. Land in a batch, then gate once

As each report lands, spot-check it against the artifact (rule 4), then collect its tree: `./run.sh worktree land <id>` prints the `git cherry-pick -x` lines and the lead runs them, submodules first, reading each pick's exit code; `./run.sh worktree gc --write --id <id>` frees the slot. A box ticks with the landed sha, never the lease's own. A `present` box closes with `--plan-investigate <me> <plan> <sig> present <kind>:<token> -- <evidence> --write` and then `--plan-tick`, after the cited evidence is checked.

Once the batch is landed, the gates run once. Only the reviews, worklist, reggate and effort ledgers count as record-only (`.ci/policy/record-paths.json`): any other commit voids the `ci:quick` receipt, so a plan or STATE commit comes before the gate run, not after. Anything freshness-red is bumped before the batch, and `pins bump` takes `--task`.

### 7. The live queue and the parked groups

G1 boxes first get their recorded correction: the box line stays byte-identical so its signature holds, with a `(corrected ASKED:<minute>Z) <bench form>` line under it. A clause bench cannot prove is named in its own box, never dropped. They then run as G2.

G2 boxes run sequentially in the main checkout, because leases refuse `vm:check` and `live_proof`, in the order fleet, bench, hostinger. Each box takes `--plan-investigate`, then `worklist.py --live-proof <me> <plan> <sig> --write --tick`, or the box's own command. The runner holds a real lease (`worker:<agent-id>`, or `worker:lead` beside a running background task), since `queue-slot` trips on `worker:queue` beside a free slot. A box ticks only after every clause is read, citing the landed commit and the run's exit code, and it states bench-only proof plainly.

Hostinger runs without asking, and provisioning restarts its services. Production data is never wiped; a restore test's temporary `-rt` copy is the only deletion, and `repo list` and `backup usage` are compared before and after each step. `backup schedule` and `strategy bind` go through `eu-remote`, never `eu-bench`.

G3 and G4 boxes stay open and are named once in the report. A G6 question goes in one batched `AskUserQuestion` with the recommended option first, only when no ruling settles it. There is no ask for what `feedback` memory already rules.

### 8. Report in one screen

Boxes ticked with their commits and commits landed lead the report. Then the writers running or queued with the refusal that holds each, the live box in progress, and the boxes still open by group. No narration of the survey.
