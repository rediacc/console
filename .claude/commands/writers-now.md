---
description: Drain the Promoted plans in agent/plans/QUEUE.md. One read-only survey sorts every open box into nine groups and writes the code clusters by file and the live run order per target. The lead ticks the PRESENT boxes first, in one batch. One wave then starts the code writers in leases, a standing review-findings writer, and one live runner per target (bench, hostinger, VM fleet, production) in the main checkout. Runners record evidence without committing; the lead commits the ticks in one batch right before the single gate run. GITHUB and TIME boxes are named once and carried through the PR, operator questions go in one batched ask, and the round ends with a numeric report. Free text after the command narrows it to matching plans.
argument-hint: "[ask] [filter: plan names or substrings, e.g. 'backup proxy'; omit for every unfinished Promoted plan; 'ask' asks for risk/permit rulings that unblock stuck boxes]"
allowed-tools: Bash(.claude/hooks/stop/worklist.py --list --open:*), Bash(.claude/hooks/stop/worklist.py --plan-investigate:*), Bash(.claude/hooks/stop/worklist.py --plan-tick:*), Bash(.claude/hooks/stop/worklist.py --live-proof:*), Bash(.claude/hooks/stop/worklist.py --box-audit:*), Bash(.claude/hooks/stop/worklist.py --add:*), Bash(.claude/hooks/stop/worklist.py --add-many:*), Bash(.claude/hooks/stop/worklist.py --lease:*), Bash(.claude/hooks/stop/worklist.py --update:*), Bash(.claude/hooks/stop/worklist.py --review-mark:*), Bash(git add:*), Bash(git commit:*), Bash(npm run login\:bench:*), Bash(git branch:*), Bash(git log:*), Bash(ls:*), Bash(sed:*), Bash(grep:*), Bash(date:*), Bash(uptime:*), Bash(nproc:*), Bash(python3 -c:*)
---

## The queue, gathered

- Branch: !`git branch --show-current`
- UTC now: !`date -u +%Y-%m-%dT%H:%MZ`
- Effort: !`sed -n '/^## Settings/,/^## /p' agent/plans/QUEUE.md | grep -E '^effort:' || echo '(no Settings section)'`
- Promoted progress (generated): !`sed -n '/queue:progress:begin/,/queue:progress:end/p' agent/plans/QUEUE.md`
- Live writer leases (every session's; the tag after the title names the owner): !`.claude/hooks/stop/worklist.py --list --open 2>/dev/null | grep -E '^\s*- \[>\]' | head -20 | grep . || echo '(none)'`
- Last survey (the baseline of the round's report): !`ls -t /tmp/writers-now/*.md 2>/dev/null | grep -v -- '-evidence-' | head -1 | grep . || echo '(none)'`
- Filter: `$ARGUMENTS`

## What to do

**This is the development tree's default order.** The development tree (the main checkout) always builds: the Stop hook names this command when Promoted plans have open boxes, and the round below is how they drain. It never waits on the landing tree, which babysits the one open PR, and pushes only as a backup.

**Drain, do not report.** The operator types this instead of a long prompt, and one invocation is measured by boxes ticked and commits landed. The rules of CLAUDE.md apply unchanged (rule 1 commits, rule 3 verification, rule 4 writer discipline).

Why the round is shaped this way, measured on 2026-11-16 after many rounds: 25 of 75 Promoted plans done, 1162 of 1397 boxes. Of the 235 open boxes, 25 were code, 9 were already present in the tree, 29 were GITHUB, TIME or OPERATOR boxes, and 172 (73%) were live runs: 63 bench, 25 VM fleet, 53 hostinger, 31 production. Earlier rounds staffed writers and left the live queue as a paragraph nobody ran, so the round now staffs a runner per live target in the same wave as the writers, and the work a lease cannot do is no longer the work nobody does.

### 1. Survey first, in the required format

The round is every Promoted plan whose row is not `done`, in table order, narrowed by the filter. One background `general-purpose` agent (model `sonnet`, read-only) sorts every open box of the round and writes `/tmp/writers-now/<branch>-<UTC stamp>.md`. It returns the path and the per-group counts. Nothing else starts until it has returned, except the PRESENT batch of a previous survey (section 2); a survey that fails or stalls is restarted once, and then the lead reads the boxes itself.

| Group | Meaning | Who takes it |
|---|---|---|
| CODE | real code or tests still to write | writers in leases (section 3) |
| PRESENT | the tree already holds the work; only the record is stale | the lead, first, in one batch (section 2) |
| LIVE-BENCH | a run against bench (`--config eu-bench`, bench Workers, D1 clones), including a box that names edge or stable only as where it runs | the bench runner (section 5) |
| LIVE-VM | a run on the local KVM fleet or an ops VM: `vm:check`, e2e-local, drills, lab boxes | the fleet runner |
| LIVE-HOSTINGER | a run on the hostinger machine | the hostinger runner |
| LIVE-PROD | a run against edge, stable or production: `release:local`, account Workers, D1, DNS | the production runner, when authorized |
| GITHUB | tagged `GitHub-only: CD`, `CI parity`, `native-runner` or `preview`, or a CI run on the PR head | named once, carried by the PR (section 9) |
| TIME | tagged `GitHub-only: soak`, or needs a data window | named once, carried by the PR (section 9) |
| OPERATOR | a decision or access only the operator has | the batched ask (section 9) |

**A GitHub wait is LIVE until a tag says otherwise** (operator ruling R2 of 2026-11-11: "The planner should really find no way to test/deploy locally to go with github.", which Design L of the plan reads as: no box goes to GitHub while a local route exists). A box names a GitHub wait when its text matches a phrase of `tiers.live.github_waits` in `.ci/config/proof-tiers.json` ("released", "after the merge", "CD", "nightly", a CI or ct-tests run), read through `wl_plandeps.box_github_wait`. With no valid `GitHub-only:` tag on its line or in a `(corrected ...)` line, it is LIVE and runs on a local route of its surface (`surfaces.<name>.local`: vm:check, hostinger, deploy_bench, the D1 clones, the e2e-local fleet); a box that names edge or stable becomes LIVE-BENCH through a recorded correction (section 2). A valid `Local-route:` correction makes it LIVE on the runners it names. A valid `GitHub-only: <kind> -- <why>` tag decides the group by its kind alone: TIME for `soak`, GITHUB for `CD`, `CI parity`, `native-runner` and `preview`. "Waits for the merge" or "a CI run" is therefore never a reason the survey gives for GITHUB on an untagged box. The tag grammar and LP8 are in docs/agent-reference/plan-records.md.

**`Needs:` says when a box can start** (agent/plans/PLAN-push-decoupling.md Design 3). An indented `Needs: none|bench-deploy|verified-vmcheck|pushed-head` sub-line under a box, read through `wl_plandeps.box_needs`, names what it waits for. `none` is provable from a lease or the main checkout as it stands; `bench-deploy` waits for the branch's code on bench; `verified-vmcheck` for a VERIFIED vm:check receipt on the tree; `pushed-head` for the branch tip on origin. With no line the value is derived: a valid `GitHub-only:` tag gives `pushed-head`, and a `Local-route:` correction the class of its runners (`deploy-bench`, `bench-cli`, `d1-migrations`, `deploy-proxy-bench` and `enterprise-bench` give `bench-deploy`; `vm-check`, `hostinger` and `e2e-local` give `verified-vmcheck`; `www-local` gives `none`). A box with neither a line nor a tag is `none`.

The survey records the value in each box's row, and the wave routes by it. A `none` box starts at once, a CODE box with its writer and a LIVE box with its runner, without waiting for a landing, a receipt or a push. A `bench-deploy` box runs after the bench runner's deploy_bench step, and a `verified-vmcheck` box after the round's `vm:check -- --changed` reads VERIFIED. A `pushed-head` box waits for the batch's push and is named once with the GITHUB boxes. `wl_boxready.ready_boxes` (the IDLE CAPACITY block) holds `[writer]` boxes the same way.

`LP-<target> [live]` boxes are read mechanically, through `wl_liveproof.lp_boxes` and `parse_accept` (`.claude/hooks/stop/wl_liveproof.py`), which are exact. Every other tag is a hint. A writer's or runner's report overrides the survey: code found already present moves that box to its LIVE group, or closes it when the code was the whole box. The survey folds in `worklist.py --box-audit <me> --live-owed`, the boxes whose code landed and whose live or operator half is owed.

A plan whose `Depends-On:` prerequisite is unfinished stays in the round when the prerequisite is too, and boxes needing its output wait. A prerequisite outside the round skips the plan unless its boxes carry a `DEPS-WAIVED:` ruling.

**The survey file has these sections, in this order**, because the 2026-11-16 survey in this shape was the first one the round could staff directly from:

1. One table per plan: `sig8 | box (first 60 characters) | group | needs | evidence or command (file:line)`.
2. `## Totals`: one count per group and the total.
3. `## Audit fold-in`: the `--box-audit --live-owed` rows and any group they change.
4. `## CODE boxes clustered by shared files`: one cluster per file-disjoint writer (`CL-A`, `CL-B`, ...), each naming its boxes with signatures and the exact files it touches; split into "startable now" and "blocked behind live boxes", the blocker named by signature. Plan-close and ledger-only edits form a lead cluster with no lease.
5. `## LIVE run order per target`: one numbered list per target (LIVE-VM, LIVE-BENCH, LIVE-HOSTINGER, LIVE-PROD), each step naming its box signatures and the command that runs it, shared setup first (one deploy_bench, one branch-renet provision, one `vm:check -- --changed`), read-only before mutating, destructive last, `LP-<target>` receipts last per plan.
6. `## GITHUB` and `## TIME`: the signatures, each with what settles it (the run, the merge, the window and its date).
7. `## OPERATOR items (verbatim)`: the box text quoted, plus the probed items that turned out not to be operator-only.
8. `## Findings`: stale box text, measured gate results, and the PRESENT signatures in one line.

### 2. PRESENT boxes and corrections first: the lead, one batch

PRESENT boxes are free progress that earlier rounds skipped while staffing writers. Before the wave starts, the lead takes every PRESENT box of the survey: checks the cited evidence against the tree (rule 3), then `--plan-investigate <me> <plan> <sig> present <kind>:<token> -- <evidence> --write` (pointer kinds: `blob`, `tree`, `commit`, `ancestor`, `fileline`, `gate`, `plan`, `trap`), then `--plan-tick <me> <plan> <sig> '<evidence>' --write`. A box whose evidence does not hold returns to its real group.

The same batch writes each bench correction: the box line stays byte-identical so its signature holds, with a `(corrected ASKED:<minute>Z) <bench form>` line under it. A clause bench cannot prove is named in its own box, never dropped. These plan edits stay uncommitted with the rest of the tick batch (section 7).

### 3. The writer roster: CODE clusters

Each box's signature and label are read together from the box parser, `wl_planrec.open_boxes` (`(line, raw, body, sig)` per box) or the `worklist.py` listing. `open_sigs` in `.ci/config/plan-boxes.json` is a sorted set, never a parallel list: zipped with a plan's `- [ ]` lines it pairs the wrong signature with each label, and that reached real briefs.

One writer per startable cluster of the survey, never thirds of a plan: boxes sharing a file go to one writer, and a plan with only live boxes gets no writer. A brief's `Owns` names those files even past the plan's own `Owns:` line, because a box outside that line otherwise goes undone. Boxes of different plans that share a file go to one writer under the plan holding the most of them. A blocked cluster is queued (section 6) behind the box that blocks it.

**The roster**, read before the wave: there is no writer limit and no tree limit (agent/plans/PLAN-unlimited-writers.md), so the harness's own concurrent-subagent ceiling (20 when last measured) is the only bound. Live runners hold no tree but count against that ceiling. The wave takes, in this order: up to four live runners (section 5), one review-findings writer per file cluster of open findings (section 4, at most two), then one CODE writer per remaining cluster. Each finished tree is collected by `--id` as its report lands (`./run.sh worktree leases`).

The route is `isolation: "worktree"` on the Agent call, which reaches a lease through the harness's create hook: a detached tree under `.claude/worktrees/<id>` at the development branch's tip (the branch of the tree the session runs in, stacked on the landing branch when a landing tree exists), submodules at their gitlinks, dependencies seeded. Uncommitted work in the main checkout is not in it. Which writer gets a lease is not asked (`block_settled_questions`). Separate leases cannot corrupt each other: `block_plan_concurrency` turns an `Owns` overlap into a note for an isolated spawn (an exclusive plan's mutex still refuses an isolated spawn whose Owns overlap it), and a clash surfaces as a cherry-pick conflict at landing, where the lead re-reads the file whole and matches its hunks to each report.

Model: `sonnet` when the boxes implement against an existing oracle (ports, tests, sweeps, translations); `opus` when they create the oracle (a new gate, guard, schema or design). Never `haiku` for writes. A plan's `Concurrency: exclusive` is no reason to hold a writer back: it is started anyway, and `block_plan_concurrency` decides.

Each brief stands alone, because the writer sees nothing else. Its first two lines are load-bearing for the guards. `Owns:` is comma-separated globs; a prose line is not read, and the refusal says so. A planless brief opens `Plan: none -- <reason>`, which serves no plan whatever items the brief names:

```
Plan: agent/plans/<PLAN-file>.md
Owns: <the plan's Owns: globs, verbatim, plus each file these boxes touch past them>

PR-TASK <the plan's epic id>, repo <repo root>. Boxes (this writer's share, with signatures):
  <sig> <label>
  ...
Prerequisite in this round: <PLAN-x.md, or "none">.
Survey: </tmp/writers-now/...md>, a hint; the tree decides.

Boundary: only the files named by Owns above, plus the outputs of the one generator the Rules below admit. Any other file is not edited: the exact change goes into the report for the lead.

Implement each box and run its acceptance command. A box the tree already holds changes nothing:
cite file:line or the commit, and run the command that proves it. A box whose remaining half is a
live run, a pipeline or a decision is not attempted: name the exact command or question.

Rules: no git checkout, restore, stash, clean, reset; no regenerate or sync script (name it for the lead instead), except the one generator the lease's own commit-policy hook names for the commit in hand (`npx tsx scripts/gen/gen-docs.ts --write` for a stale doc region, `npm run generate:cli-contract -w @rediacc/cli` for a stale CLI contract): run it in the lease and commit its outputs, because the hook refuses the commit without them (2026-11-10: three writers stopped short or packed new modules into one file to avoid it); never vitest from the repo root; no inline suppression. This tree is a lease:
  - commit on the detached HEAD with `git commit -F <msg> -- <paths>`, the message written to a
    `mktemp` path in a separate call, a `PR-TASK:` trailer and one Plan-Box trailer per box the
    commit serves (the lease commit-msg hook and `land` refuse without):
      Plan-Box: <PLAN-file>.md#<sig8> clauses=<C1,C2,...|all>
      Plan-Box: none -- <reason, at least 12 characters>
    never push, never touch `agent/**` or a gitlink, never switch or create a branch;
  - each git command is its own simple Bash call, with no `;`, `&&`, pipe or redirect in the same command, `git -C <lease>` in place of `cd ... &&`, and the exit code read from the tool result rather than `; echo rc=$?`, because the harness refuses a compound command naming git inside an isolated worktree;
  - `npm run ci -- --narrow` or named tests only; ci:quick, vm:check and live_proof record refuse a lease;
  - Python tests run with `PYTHONPATH=.ci .ci/cache/toolchain/uv-tools/bin/pytest <files> -q` (neither
    the system python3 nor .venv has pytest, and `-p no:cacheprovider` fails on the repo's cache_dir); a lease is seeded with that binary, and one without it runs the main checkout's copy by absolute path with the lease as the working directory;
  - the commit shas go in the report; the lead lands them. A result worth keeping goes in a commit or
    the report, because GC deletes the tree's ignored output with the tree.

Report: per box the commands run with their exit codes, then one TICK line per box signature,
the line the lead's tools read (`wl_planbox.parse_tick`):
  TICK <PLAN-file>.md#<sig8> <done|present|partial|untouched|blocked> commits=<lease shas|-> landed=<C1,C2|all|-> owed=<C3:live,C4:operator|->
    close: <the exact command or question that closes what is owed, or "nothing">
For example:
  TICK PLAN-rediaccfile-unprivileged.md#afa91934 partial commits=ec099603d landed=C1 owed=C2:live
    close: worklist.py --live-proof <me> agent/plans/PLAN-rediaccfile-unprivileged.md afa91934 --write --tick
```

**Track** every agent of the wave (writers, the review writer, runners) in one `--add-many <me>` call, one line per agent naming its plan or target and its box signatures, and lease each to the real agent id only after the Agent call returns it (`--lease <me> <id> +120 worker:<agent-id>`). `--plan-investigate` each CODE box when its writer starts.

### 4. The standing review-findings writer

Every landed commit is reviewed, and its findings are fixed before merge. One session spent many rounds closing one to three findings at a time between waves; the round now keeps one standing follow-up writer per file cluster of open findings, budgeted in the roster (section 3). At the wave's start the lead groups the open per-commit findings of this branch (the review hook's notes, `agent/reviews/<branch>/`) by the files they name; each cluster gets one lease writer with the brief above, `Plan: none -- review findings of landed commits`, an `Owns:` of the cluster's files, and the finding ids with their text. Findings of a commit landed during the round join the running writer of their cluster by `SendMessage`, or start the cluster's writer when none runs, never held for the next round. After its commits land, each finding closes with `worklist.py --review-mark <me> <id> fixed <landed sha>`; a finding that is no defect closes `not-a-bug` with the evidence.

### 5. Live runners, in the same wave

One background agent per live target with open boxes, started in the same message as the writers: bench, hostinger, VM fleet and production. Each runs in the MAIN checkout (no `isolation`), because leases refuse `vm:check` and `live_proof record`. A runner's `vm:check` evidence covers the development branch only: the landing PR's push needs its own receipt, recorded in the landing tree. A runner edits no tracked file, so its brief opens `Owns: none -- live runner <target>` and holds no plan. Agent type: `account-dev` for bench, `ops-vms` (or `e2e-local` when the list is mostly suites) for the fleet, `general-purpose` for hostinger and production; model `sonnet`.

**One machine, one runner.** Two runners never touch the same remote machine at the same time, and no lock enforces it, so each brief names the machines it owns and forbids the others: the bench runner owns the bench Workers, the bench D1 and R2 resources and the bench machines; the hostinger runner owns the hostinger machine, reached through `eu-bench` (and `eu-remote` for `backup schedule` and `strategy bind`); the fleet runner owns the local VMs; the production runner owns edge, stable and the production Workers. A box needing two runners' machines goes to the later one in the run order, after the earlier one reports.

**Bench, hostinger and production start at once** (standing operator order, 2026-11-05: bench and hostinger are open to every agent at any time), beside writers, gates or a fleet run, and never wait for a landing, a push, a merge or an operator answer, nor for a gate, with one exception: a `release:local` step builds on this machine, counts as a gate in section 6, and so waits for any gate that is running and runs alone. Hostinger runs without asking, and provisioning restarts its services. Production data is never wiped; a restore test's temporary `-rt` copy is the only deletion, and `repo list` and `backup usage` are compared before and after each step. The production runner starts only under a standing authorization for the round (an operator answer with `ASKED:<minute>Z`, or a `feedback` memory that rules it, such as eu deploys and local releases); it records the rollback version and each D1 bookmark before every Worker deploy, a stable deploy carries `RELEASE_ASKED`, and destructive steps run last. Without the authorization its list goes into the report's OPERATOR lines instead.

**The fleet runner shares the local machine** with writers and gates (section 6), so it starts with the wave but works its list in two halves: lab boxes on ops VMs that are already up first, and each `vm:check` or e2e-local run only once `uptime` reads below `nproc` and no gate runs. A step the load holds back goes in its report as untouched, and the lead resumes the runner with `SendMessage` after the gate run.

Each runner's brief stands alone:

```
Plan: none -- live runner <target>
Owns: none -- live runner <target>: main checkout, runs and records, edits no tracked file

PR-TASK <epic id>, repo <main checkout root>, branch <branch>, lead session <me>.
Target: <bench|hostinger|VM fleet|production>. Machines owned: <names>. Machines forbidden: <the
other runners' machines>. Profile: <`--config eu-bench` | hostinger through eu-bench | ops VMs | the
deploy skill's bws profiles>; bench login is headless (`npm run login:bench`).
Survey: </tmp/writers-now/...md>, section "LIVE run order", the <target> list.
Authorization (production only): <the ASKED line or memory that rules it>.

Boxes, in this order (shared setup first, read-only before mutating, destructive last):
  1. <sig8> <plan> <label>: <command>
  2. ...

Commands this target uses (each one as its own background call, read to completion; no polling loop):
  - bench deploy:       PYTHONPATH=.ci python3 -m rediacc_ci.ops.deploy_bench --region <eu|us|asia>
  - enterprise proofs:  ./run.sh enterprise proof <add|routing|signer|release|replay|proxy|cost|region-loss|remove|keys> --bench
                        (ENTERPRISE_PROOF_BWS_PROJECT set to the enterprise bws project id)
  - LP-<target> boxes:  .claude/hooks/stop/worklist.py --live-proof <me> <plan> <sig> --write
  - VM proof:           npm run vm:check -- --changed
  - drills:             PYTHONPATH=.ci python3 -m rediacc_ci.drills.<name>
  - e2e on the fleet:   rediacc_ci.env.create_e2e_env, then rediacc_ci.testrun.e2e (the e2e-local recipe)
  - edge release:       npm run release:local -- --channel edge [--workers-only --regions <list>] (production only)
  - box-specific:       <the command the box names>

Recording, and nothing else written:
  - before a box's run: .claude/hooks/stop/worklist.py --plan-investigate <me> <plan> <sig> <absent|partial>
    commit:<landed sha> fileline:<path>:<n> -- <what the run will prove> --write
  - an LP box: --live-proof ... --write WITHOUT --tick; it appends the receipt row and prints the
    ready --plan-tick line, which goes into the evidence file
  - every box: one TICK line appended to /tmp/writers-now/<branch>-<stamp>-evidence-<target>.md
  - progress: .claude/hooks/stop/worklist.py --update <me> <item> <box sig, rc, log path>
  - never --plan-tick, never git add or commit, never an edit to a plan or any tracked file, never a
    machine on the forbidden list. A machine found busy with another run is waited for, not shared.

Each box is read clause by clause before it is called done; a bench-only proof says so. A failed run
is not retried blind: its log path, the exact command and its exit code go in the TICK line.

Report: the TICK lines (same grammar as the writers', commits=-), then the evidence file path, then
each box not run with the reason (load, a missing permit, a predecessor that failed).
  TICK <PLAN-file>.md#<sig8> <done|partial|blocked|untouched> commits=- landed=<C1|all|-> owed=<...|->
    close: worklist.py --plan-tick <me> <plan> <sig> '<live-proof line, or command rc=0 log=<path>>' --write
```

A runner holds a real lease (`worker:<agent-id>`), never `worker:queue`, since `queue-slot` trips on a `worker:queue` lease no live plan holds. When a runner reports, its next boxes are the runner's own to continue: the lead resumes it with `SendMessage` while its list has startable boxes, rather than ending the target's queue with the first report.

### 6. One thing at a time on the local machine; a refused spawn is queued

Writers, or gates, or a fleet `vm:check` or e2e run, never two of them: writers beside gates made load 70-90 and false timeouts. Before a wave, `uptime` is read against `nproc`, and a wave waits while load is above it. The order on this host is writers, landing, one gate run, then the fleet runner's heavy half. Bench, hostinger and production runs work on remote machines and are exempt, except `release:local`, which builds here and counts as a gate.

A spawn refused by `block_plan_concurrency` gets its item leased to `worker:queue`, which the lease verb admits only while a live plan holds the item and stamps `HELD_BY:<plan>`, and `--update <me> <id> queued: refused by block_plan_concurrency behind <plan> (#<holding item>)` records the exact refusal. No count of writers refuses a spawn. The brief is kept verbatim in the item's text or the round log, so the retry is a copy. When an agent reports, the queue is retried in roster order before anything new starts.

### 7. Evidence, ticks and the push receipt

Only `.ci/policy/record-paths.json` paths are record-only (`agent/reviews/**`, `agent/worklist/*.jsonl`, `agent/reggate/*.jsonl`, `agent/ledgers/effort-*.jsonl`, `.ci/config/carried-reds.json`); any other commit voids the `ci:quick` receipt. A tick commit touches plan files, so ticks committed one by one void the receipt over and over. The receipt keys on `HEAD^{tree}`, not on the working tree, so uncommitted ledger rows and ticks do not disturb it until they are committed. Hence runners record and do not commit, and the lead commits every tick of the round in one batch right before the gate run. What each verb writes (read from `worklist.py` and `wl_liveproof.py`; none of them commits):

| Verb | Files written | Record-only |
|---|---|---|
| `--add`, `--add-many`, `--update`, `--lease`, `--tick`, `--defer` | the worklist event log under `agent/worklist/` | yes |
| `--plan-investigate ... --write` | `agent/ledgers/plan-investigation.jsonl` (locked append) | no |
| `--live-proof <plan> <sig> --write` | `agent/ledgers/live-proof.jsonl` (locked append, VERIFIED rows only); the full log at `.ci/cache/live-proof/<id>.log` (ignored); prints the ready `--plan-tick` line | no |
| `--live-proof ... --write --tick`, `--plan-tick ... --write` | the plan file, `.ci/config/plan-boxes.json` and `agent/INDEX.md`, each rewritten whole | no |
| `--box-progress ... --write`, `worktree land <id> --ticks --run` | `agent/ledgers/plan-box-progress.jsonl` (and the ticks, as above) | no |

The two appends take a lock, so several runners may write them at once. `--plan-tick` rewrites three whole files with no lock, so only the lead runs it, one call at a time; that is why a runner leaves `--tick` off. The tick batch reads every runner's evidence file and every writer's report, checks each TICK line against its log or landed commit, runs the `close:` lines in order, and commits in one call: `git commit -F <msg> -- agent/plans/ .ci/config/plan-boxes.json agent/INDEX.md agent/ledgers/live-proof.jsonl agent/ledgers/plan-investigation.jsonl agent/ledgers/plan-box-progress.jsonl` (only the paths this session wrote, rule 1). A runner still running at batch time keeps writing its uncommitted rows; they ride the next batch.

### 8. Land in a batch, then gate once

As each writer reports, spot-check it against the artifact (rule 4), then collect its tree: `./run.sh worktree land <id>` prints the `git cherry-pick -x` lines and the lead runs them, submodules first, reading each pick's exit code; then `./run.sh worktree land <id> --ticks` maps each lease commit to its landed sha and prints, per box its Plan-Box trailers name, the progress rows, a post-landing `--plan-investigate` line where the box has no row, and a ready `--plan-tick` where every clause is covered. Those lines join the tick batch of section 7 instead of running one by one. `./run.sh worktree gc --write --id <id>` frees the slot, and the slot is refilled at once with the next queued cluster or a review-findings writer. A box ticks with the landed sha, never the lease's own.

The order of the batch's end is fixed: last landing, the tick batch commit (with the plan, STATE and review commits), then `ci:quick` once, with `vm:check -- --changed` beside it when the push range touches the VM trigger paths in `.ci/config/proof-tiers.json` (CLAUDE.md rule 1), then the push. Anything freshness-red is bumped before the batch, and `pins bump` takes `--task`.

### 9. GITHUB, TIME and OPERATOR: named once, carried by the PR

A GITHUB or TIME box is not re-surveyed every round. The first round that finds it records it once: one worklist item per box naming what settles it (the CI run on the PR head, the merge, the CD run, the window and its date). Later rounds only count it. When the PR nears merge (every CODE and LIVE box ticked or owed only to these), the boxes are carried either in the PR body's `Operational-Reason:` line, which names each signature and what settles it and admits the merge with them open, or into a post-merge plan in `agent/plans/QUEUE.md` that the next branch starts with. A CI run on the PR head settles its boxes at the next push with no extra work, and with two trees the draft PR's run on the development branch carries them; their ticks join the next tick batch.

An OPERATOR question goes in one batched `AskUserQuestion` with the recommended option first, only when no ruling settles it. There is no ask for what `feedback` memory already rules, and probing comes before calling a box operator-only (rule 3).

### 9a. The permit ask: trading risk for time (opt-in)

A round often stalls on boxes no writer or runner can move without a wider permit: a gate the recorder will not pass (no VERIFIED `vm:check`), a soak window, a production or destructive step, an external send, or a decision parked as OPERATOR. Steps 1 and 2 below run on every round, right after the survey returns, since the report (section 10) names their top reasons. Steps 3 and 4 run only when the arguments carry the word `ask` (any position; it is removed from the filter), and they run before any writer or runner of sections 3 and 5 starts, so the answers shape the round; the runs a permit unlocks then join the runners' lists.

1. **Group the stuck boxes by the reason they cannot move**, from the survey's GITHUB, TIME and OPERATOR lines and the live boxes blocked on a gate, window or permit. Skip the reasons a merge or a CI run settles, which only a box tagged `GitHub-only:` may give. Count boxes per reason and keep the top ten.
2. **Turn each reason into the permit that would move it**, phrased as the action the session would then take, with its consequence: for example a recorder waiver marked `--vm-waived ASKED:<minute>` that a later VERIFIED run confirms, a 2-hour window in place of a day, a production run on a named region, a destructive cleanup after its archive step, a real mail to a named address, or a parked decision taken now. A reason that a ruling or `feedback` memory already settles is acted on, not asked.
3. **Ask in batches of up to four** with `AskUserQuestion`, the riskier permit first and labelled with its consequence, the conservative option beside it, and a free-text answer always possible. More than four reasons go in the next batch after the first is answered.
4. **Record each answer before acting on it**: one round-log DECISIONS line with the operator's words and `ASKED:<minute>Z`, and one worklist item per permit granted naming the boxes it moves. Then the runs the permits unlock join the runners' lists.

Without the word `ask`, steps 3 and 4 do not run, and the report names the top stuck reasons in one line each, ending with "run `/writers-now ask` to be asked for the permits". With `ask` in away mode (`/awk`) the questions are refused, so step 3 parks each permit as a `[?]` whose DEFAULT is the conservative option instead of asking.

### 10. Report: numbers first

The operator reads progress, not prose. The report opens with one table, its baseline the survey of this round:

```
group           survey  ticked  landed-owed  still open
PRESENT              9       9            -           0
CODE                25      14            6           5
LIVE-BENCH          63      21            -          42
...
TOTAL              235      58            6         171
Promoted plans done: <n> of <m> (was <n0>); boxes done: <n> of <m> (was <n0>)
```

`ticked` counts boxes ticked this round (committed in a tick batch); `landed-owed` counts CODE boxes whose code landed and whose live half is owed. Then the commits landed, one line each with its sha. Then the OPERATOR items, quoted verbatim from the survey with their signatures, and the top stuck reasons of section 9a, one line each with the permit that would move it (and the answers taken, when `ask` ran). Then the agents still running or queued with what holds each. No narration of the survey.
