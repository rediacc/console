# PLAN: Parallel-writer roster, where the Stop hook and the main session share supervision of the writers

Status: ready
Owner: d778be9d
Updated: 2026-09-24
First-Seen: 2026-09-24

## Why

The operator, 2026-09-24:

> *"usually there is single writer. but ... the stop hook pushes a lot. I'd suggest a mechanism that the main session and stop hook work collaboratively on parallel writers maintenance. So, stop hook may skip pushing the main session when it detects that the main session is honest about the current parallel sub-agent writers. The important point is we must have a limit. I'd suggest having up to 4 writers in parallel. The stop hook system should also ping when it detects [that] the latest status report didn't come for [the] last 20 mins. So, there should be no escape hatches."*

## Finding: the live incident, measured on this session's tree

Every fact below was read from the working tree or from this session's live harness artifacts on 2026-09-24. None is inferred.

**F1. What the harness actually reports about a background agent.** The last Stop event (`/tmp/claude-worklist/home_developer_console.lastevent-d778be9d.json`) lists 17 running tasks. 15 are `{"type": "subagent", "agent_type": "<type>", "id": "a<hex>", ...}` and 2 are `shell`. So the event already says which kind of agent each one is: `general-purpose`, `gate-author`, `pr-babysitter` or `Plan`.

- The task id matches the transcript file name exactly: `~/.claude/projects/-home-developer-console/<sid>/subagents/agent-<id>.{jsonl,meta.json}`. `wl_report.running_agent_ids` (`.claude/hooks/stop/wl_report.py:591`) already relies on this.
- Each task's `tasks/<id>.output` is a symlink to that transcript, so `bg_output_facts` (`.claude/hooks/stop/wl_liveness.py:168`) already reads transcript freshness for subagents.

**F2. The liveness code for agents only recognises the old task kind.** `live_teammate_transcripts` counts only metas with `taskKind == "in_process_teammate"` (`wl_liveness.py:293`). `prune_background` only looks at `type == "teammate"` (`wl_liveness.py:534`).

- None of this session's 305 subagent metas carries `taskKind`. They carry `agentType`, `spawnDepth`, `parentAgentId`, `requestShape` and `model`.
- So for the harness as it runs today, the "teammate count" is always 0 and the reaping step does nothing for subagents.
- This matters for section 1.3 (see Coordination). Its box widens the predicate "using the teammate count from `wl_liveness.py:318`", and that count is 0 for every `type: "subagent"` task.

**F3. The session was honest, and the hook could not tell.** The store `agent/worklist/d778be9d.jsonl` folds to 38 `[>]` items, 11 `[?]` items and no plain `[ ]` items.

- 36 of the 38 leases name an id that is in the live event.
- 30 or more of those carry `worker_verified: false` even though the id is live. `--lease` checks the id against the previous stop's snapshot (`worklist.py:1030-1047`), and the lease is taken seconds after the spawn, before any snapshot has seen it. **Checking at lease time is structurally blind for a worker that was just spawned.** Any honesty check has to verify at stop time, against the current event.

**F4. The "dead worker" push was wrong, and the cause is missing parent/child tracking.**

- Agent `ac4d98abd37e1deb3` (general-purpose, depth 2, "Port devbox.sh remainder") is a child of `a7bd52e4028757e77`. The link exists only in the child's meta `parentAgentId`. The Stop event lists the child with no parent marker.
- When a parent that holds leases (items `6f60b65e`, `cfbcfa7a`, `e44fe9c0` are on `a7bd52e4028757e77`) finishes while its child keeps working, the ladder computes `gone = wid not in now_bg and worker_verified` (`wl_liveness.py:663`). That fires `ladder-gone` (`wl_checks.py:4006`) with no knowledge of the child.

**F5. One lease really was dead, and nothing named it cleanly.** Item `8ea2de80` is leased to `ad404a11224579535`. That is a finished haiku "Survey plans citing retired .sh files" whose transcript last moved at 06:31Z and which is absent from the event. It is a `general-purpose` agent doing read-only work. So the harness agent type alone does not settle whether an agent writes.

**F6. What an agent type does and does not prove.**

- **Plan and Explore never write.** Across this session, none of 66 Plan and 65 Explore transcripts contains an `Edit`, `Write` or `MultiEdit` tool call.
- **Custom agent types are mostly writers.** Of the custom types, only `test-advisor` omits Edit and Write in its frontmatter `tools:` line (`.claude/agents/test-advisor.md`).
- **Many agents do write.** 169 of 305 transcripts contain an edit tool call.

**F7. Workers already send status that the lead cannot fake.** SendMessage calls with `"to":"main"` appear in worker transcripts (`agent-a149262d8b6a1601f.jsonl`, 16 of them). `harvest_transcript` (`wl_report.py:679`) already parses them, with timestamps.

**F8. The sequence that pushed on every stop.**

1. `open-items` (`wl_checks.py:2873`, rotating, highest tier) fires whenever any item is unleased, or a lease expires on a worker the harness no longer lists.
2. `ladder-gone` fires, per F4.
3. `agent-state` goes stale (`wl_checks.py:3573`), because the structural world signature moves each time a worker ticks an item.
4. `bg-report` fires every `BG_REPORT_MIN` (15 minutes) in a pure wait (`wl_checks.py:2650`).
5. `stuck` fires when the lead itself moves nothing, even though its workers are moving things.

None of these can ask "is every open item leased to a verified live writer?", because nothing computes that.

**F9. Every current liveness threshold can be overridden from the environment.** Examples: `LADDER_*_MIN` (`wl_liveness.py:45-47`), `BG_STALE_MIN`/`BG_REPORT_MIN` (`:200-201`), `TEAMMATE_FRESH_MIN` (`:258`), `WORKER_IDLE_BLOCK_MIN` (`:313`) and `ROSTER_MAX` (`:578`). All of them are registered in `.ci/policy/worklist-env-registry.json`, which only requires that a variable be registered, not that it be absent.

**F10. The spawn cannot be intercepted today.** `.claude/settings.json` has PreToolUse matchers only for `Bash`, the Edit family and `AskUserQuestion`. There is none for `Agent` or `Task`. The settings file is generated from `lifecycle.PATTERNS` (`.claude/rediacc_hooks/lifecycle.py:84`), and `test_settings_collapse.py:184` checks that the two agree.

**F11. The cap is written down in six places, and one of them is a gate.**

- `CLAUDE.md:37` ("max 2, rule 4") and `CLAUDE.md:131`
- `.ci/scripts/quality/check_hint_corpus.py:209`, which pins the exact CLAUDE.md sentence, so it has to change in the same commit
- `.claude/hooks/stop/worklist_messages.py:1739` and `:1781`
- `.claude/commands/handoff.md:69`

`docs/agent-reference/model-routing.md` does **not** restate the cap (checked by grep), so it needs no edit.

**F12. Who is editing what right now.**

- The current uncommitted diff to `wl_checks.py` belongs to the **defer-settle** writer (`a2b593dbefc625beb`: the `wl_defersettle` import, `CITE_RE`, and the judge batch near :2946 and :4426-4630).
- The **section-1.3** writer (`a305ee07a5e707b64`, items `cb7cc1db` and `507de6b3`) is live but has not changed `wl_checks.py` or `wl_liveness.py` yet. `git diff -- wl_liveness.py` is empty.
- So "design on top of 1.3" means designing on top of the 1.3 box's stated change, not on a diff that exists.
- Line numbers below are from the current working tree (the defer-settle edits included). They drifted by 4 during this investigation.

## Design

### Recommendation: one new module, `wl_roster.py`, that produces one verdict from three sources the lead cannot edit

The three sources are the Stop event, the subagent metas and transcripts, and the append-only store. The main session has no way to *declare* the roster, only to make it true.

**Terms**

| Term | Definition (all computed at stop time) |
|---|---|
| **Subagent** | An event task with `type == "subagent"`, joined by id to `subagents/agent-<id>.meta.json`. |
| **LIVE(id)** | The id is in the event's running list (the harness is authoritative for existence, as the honesty rule at `wl_liveness.py:20` already requires), **and** its transcript is not proven finished (`_record_is_idle` on the last record, `wl_liveness.py:383`, with quiet ≥ `IDLE_EDGE_EPSILON_S`). The `--reap` list is **ignored** for any subagent whose transcript is not proven finished. Otherwise reaping a live writer would hide it from the cap. |
| **Lineage** | The transitive `parentAgentId` chain from the metas. `descendants(id)` and `ancestors(id)` are computed once per stop from the session's `subagents/` directory. |
| **Covered lease** | A `[>]` item of this session with `worker:<id>`, where LIVE holds for `id` or any of its descendants. This fixes F4. |
| **Leased-dead** | A `[>]` item of this session whose worker is a known subagent (a meta exists) and is not covered. This catches F5. |
| **Writer** | A LIVE subagent at any spawn depth whose agent type is not in `READ_ONLY_AGENT_TYPES`, **or** whose transcript contains a tool call in `EDIT_TOOLS` (proven writer, even if its type claims read-only). `READ_ONLY_AGENT_TYPES` = `{"Plan", "Explore"}` plus the `.claude/agents/*.md` definitions whose `tools:` list includes none of `EDIT_TOOLS` (today that is `test-advisor`). `EDIT_TOOLS = {"Edit", "Write", "MultiEdit", "NotebookEdit"}`. Shell tasks are not writers; they are watchers and stay on the existing ladder. |
| **Unleased writer** | A writer where neither it nor any ancestor holds one of this session's leases. A child writer inherits its parent's lease. |
| **Status time** | `status_at(id)` is the newest of: (a) the `at` of the lease event on any item leased to `id` or an ancestor (a spawn counts as a fresh status); (b) a `status` event written by the new verb `worklist.py --status` (below); (c) the timestamp of a `SendMessage` call in the transcript of `id` or a descendant (the worker speaking for itself, via `harvest_transcript`); (d) a SubagentStop capture for `id`. **`--update` is deliberately excluded**: it is prose from the lead, unverified, and it is what resets the old ladder. |
| **Status due** | A LIVE leased worker (or a descendant covering its lease) with `now - status_at >= STATUS_PING_MIN`. |

**Constants.** These are module-level literals, and the module never reads the environment: `WRITER_CAP = 4`, `STATUS_PING_MIN = 20`, `READ_ONLY_AGENT_TYPES`, `EDIT_TOOLS`, and `ROSTER_SUPPRESSES` (below).

**The verdict.** `wl_roster.roster(event, fold, session_id, state_doc, cwd)` returns rows for display plus:

- `writers` and `readers`
- the defect lists: `unleased`, `leased_dead`, `over_cap`, `status_due` and `silent`
- `state`, one of three values:
  - **HONEST**: no plain open items of this session, no defects, and every `[>]` of this session is a covered subagent lease or a shell lease that is live and not `suspect`.
  - **DISHONEST**: at least one defect.
  - **UNKNOWN**: a lease on a worker the roster cannot judge, such as a teammate leased by name with no resolvable meta, or a `suspect` shell. UNKNOWN changes nothing, and the existing battery runs exactly as today.

**The cap and the ping are checked in every state.** Honesty only decides whether the stop is suppressed. It never turns enforcement off.

**What each outcome does inside `run_stop`**

1. **Defects add violations in the always tier.** Each defect is added with `vadd(key, True, text)`, which means it is never rotated away (`wl_checks.py:4327`) and defeats the cadence pause (guard A, `wl_checks.py:4207`). The keys:
   - `roster-cap`, in the "someone else is waiting" tier (the operator's order). The text is the exact writer roster: id, agent type, description, depth/parent, age, and leased items. The remedy is `TaskStop <newest excess ids>`, then release or re-lease their items.
   - `roster-status`, same tier. Each due worker is named with its status age and the source of its last status, plus the command `worklist.py --status <me> all`.
   - `roster-silent`, same tier. The transcript has not grown for ≥ `STATUS_PING_MIN` and the last record is not an in-flight tool call. The remedy is `SendMessage` to `<id>`, or `TaskStop`, then release or re-lease.
   - `roster-unleased`, in the integrity tier. Remedy: `--lease <me> <item> +N worker:<id>`.
   - `roster-dead`, integrity tier. Remedy: tick with evidence, `--lease <id> release`, or re-lease.

   Every remedy is something the session can do on its own, so the "every rung's exit is a solo action" rule (`wl_liveness.py:24-27`) still holds and no deadlock is possible.

2. **HONEST suppresses the push, in one place.** Just before the cadence gate (the `always_now` computation above `wl_checks.py:4207`), drop from `violations` every key in `ROSTER_SUPPRESSES`:
   - `bg-report`, `ladder-investigate`, `ladder-resolve`, `ladder-gone` and `ladder-idle`, but only for subjects the roster owns
   - `stuck`, `idle-stall` and `solo-grind`
   - `agent-state`, only when its verdict is `stale` (`missing`, `thin`, `bloated`, `aimless` and `waitled` still fire)

   Nothing else is dropped. Requests, CI red, pr-finish, the judge tier and integrity checks all still block. If nothing is left after the drop, the stop is **allowed** with a `systemMessage` roster summary: "ROSTER HONEST: N writer(s)/4, M reader(s), next status due HH:MMZ", one line per worker, capped by the existing `ROSTER_MAX` display budget. That replaces today's `What the OS could verify about your background workers` block (`worklist_messages.py:1366/1379/1391`) for subagent rows.

3. **The 45/90/120 ladder is replaced for subagent leases and kept for everything else.** `wl_liveness.ladder` (`:632`) skips any `item:` subject whose worker is a known subagent id. For those subjects the roster's 20-minute ping and lineage-aware dead check take over. The ladder keeps shell-worker leases, teammates leased by name, and `task:*` harness tasks, whose clocks the roster cannot read.
   - Nesting was rejected. Nested, the same item would get a report at 45 minutes, a block at 90 and another at 120 on top of the 20-minute ping. The ladder's `gone` branch would also keep producing the false death from F4.
   - `poll_fast_path` (`wl_checks.py:1164`, rung forfeit at `:1247`) skips the same subjects and gains a roster forfeit: any cap, status, silent or dead defect returns `False`. **Without this, the silent poll path would be an escape hatch.**

4. **`bg-report` fits on top of section 1.3.** After 1.3 lands, the suppression test at `wl_checks.py:2650` becomes `if not (_only_waiters or <1.3's automatic-liveness predicate> or roster_covers_all(live_bg)) or _bg_actionable`. `roster_covers_all` is true when every live background task is a roster-verified subagent or a confirmed waiter. Shell tasks keep the 15-minute check-in, and subagents move to the 20-minute status clock. The clock is restamped on both branches, as 1.3's box requires.

**The new verb: `worklist.py --status <me> [<id>|all]`.** It is the only way the lead answers a ping, and it is hook code reading the worker's transcript, not the lead typing a claim.

- **Output:** agent type, description, depth/parent, live children, minutes since the transcript last grew, the last assistant text (at most 600 characters), the last tool call and its target, and the edit-tool count.
- **Record:** it appends `{"ev":"status","worker":id,"at":now,"size":…,"mtime":…,"inflight":<tool or "">,"by":me}`.
- **When it resets the clock:** only if the transcript grew since the previous status event, **or** the last record is an in-flight tool call. The in-flight case covers a worker legitimately sitting in a 25-minute gate run, which is F7's lesson from `wl_report.py:59`.
- **Otherwise:** it records `silent: true`, does not reset the clock, and the next stop raises `roster-silent`.
- `all` answers every due worker in one command, so the operator's ping costs one tool call per 20 minutes.

### Enforcing the cap: both layers, with the PreToolUse guard as the primary and the Stop block as the backstop

- **Primary: a new `pre-agent` pattern in `lifecycle.PATTERNS`**, matcher `^(Agent|Task)$`, running a new guard `.claude/rediacc_hooks/guards/agent_cap.py` through `dispatch.py --chain pre-agent`.
  - It reads `tool_input.subagent_type` (default `general-purpose`). A writer-class spawn is refused with exit 2 and the roster when the live writer count is already `>= WRITER_CAP`.
  - The count comes from `wl_roster.live_writers_estimate(cwd, session_id)`: the freshest `.lastevent` running list, joined with metas whose transcripts are not proven finished. Spawning a Plan or Explore agent is never refused.
  - It shares `WRITER_CAP` and `READ_ONLY_AGENT_TYPES` by importing `wl_roster`, so the two layers cannot disagree.
  - It fails **open** when it cannot count. That is not an escape hatch, because the Stop block recomputes from the authoritative event on the next stop.
  - Whether the payload carries `agent_id` for spawns made *inside* a subagent is unverified, so the plan does not depend on it. Depth-2 writers are counted by the Stop layer either way.
- **Backstop: `roster-cap` at Stop**, which is authoritative.

**Rejected alternatives**

- **Stop-only enforcement.** By the time the Stop hook sees a fifth writer, it has run and edited files for a whole turn. The only remedy then is to TaskStop it and waste that work.
- **Guard-only enforcement.** A PreToolUse payload carries no `background_tasks`, so the guard can only estimate. A guard that is the only enforcement and fails open is exactly the "check that cannot fail" trap.
- **A `--writer` flag on `--lease` to mark writers.** That is a self-report, and leaving the flag off would be the escape hatch.
- **A `--role read` declaration to take an agent out of the cap.** A declaration that removes an agent from the cap is an override by definition. Read-only work is instead dispatched as Plan or Explore, and the rule 4 text changes to say so (F5 is why).
- **Counting lineages instead of tasks.** A writer that spawns three writer children would then occupy one slot while four agents edit the tree. The cap is on concurrent editors. Writers are told in their briefs not to spawn writers.
- **Nesting the ping inside the ladder.** See point 3 above.
- **Using transcript growth alone as the status.** It measures liveness, not a status the lead has seen. The operator asked for a *report*, so the ping has to cost the lead one read, and `--status` is that read.

### No escape hatches

- `wl_roster.py` and `guards/agent_cap.py` contain no `os.environ` or `os.getenv` calls, and their thresholds are literal `ast.Constant` values.
- **Gate:** a `"sealed_modules"` map is added to `.ci/policy/worklist-env-registry.json`, keyed by path with a `why` for each. `rediacc_ci/quality/worklist_env_registry.py` treats *any* environment read inside a sealed module as a finding that registering the variable cannot clear, with a selftest that plants one. This turns "don't add a knob" from a comment into CI red.
- **Belt:** an AST test in the new pytest module checks that the constants are `== 4` and `== 20`.
- The roster keys are always-tier, so `WORKLIST_CADENCE`, `WORKLIST_FOCUS=off` (which renders every violation) and rotation cannot hide them.
- The quiet-wake path (`wl_checks.py:4163`) only stands down when `bg-report` is the *only* violation, so roster keys defeat it.
- The poll fast path forfeits on them.
- `--reap` cannot remove a writer whose transcript is not proven finished.

## Boxes

- [x] Add `.claude/hooks/stop/wl_roster.py` with the literal constants `WRITER_CAP = 4`, `STATUS_PING_MIN = 20`, `READ_ONLY_AGENT_TYPES`, `EDIT_TOOLS` and `ROSTER_SUPPRESSES`, and no environment reads.
    (ticked) 2026-09-24T08:58:58Z by d778be9d: .claude/hooks/stop/wl_roster.py:35 WRITER_CAP = 4 and :37 STATUS_PING_MIN = 20, no env read; check_worklist_env_registry.py exit 0, and exit 1 with an os.environ read planted in wl_roster.py
- [x] In `wl_roster.py`, add a meta and lineage loader: scan the session's `subagents/*.meta.json` once and build `{id: (agentType, parentAgentId, spawnDepth, jsonl)}`, reusing `wl_report._projects_dir` and `_munged`.
    (ticked) 2026-09-24T08:58:58Z by d778be9d: .claude/hooks/stop/wl_roster.py:87 load_metas, :129 ancestors, :141 descendants; .claude/rediacc_hooks/tests/test_wl_roster.py:280 test_r3b passes (pytest exit 0) and fails when the descendant walk is removed
- [x] In `wl_roster.py`, add `live()`: harness running list, minus transcripts proven finished via `wl_liveness._record_is_idle` and `idle_edge`, with the `--reap` list honoured only for proven-finished transcripts.
    (ticked) 2026-09-24T08:58:59Z by d778be9d: .claude/hooks/stop/wl_roster.py:227 proven_finished and the LIVE loop in roster() at .claude/hooks/stop/wl_roster.py:338; .claude/rediacc_hooks/tests/test_wl_roster.py:291 test_r3c passes (pytest exit 0) and fails when proven_finished always returns False
- [x] In `wl_roster.py`, add writer classification: agent type outside `READ_ONLY_AGENT_TYPES`, or a proven edit tool call found by an incremental per-agent byte-offset scan cached in `state_doc["roster"]["scan"]`. Derive the custom read-only types from `.claude/agents/*.md` `tools:` frontmatter.
    (ticked) 2026-09-24T08:58:59Z by d778be9d: .claude/hooks/stop/wl_roster.py:152 read_only_types, .claude/hooks/stop/wl_roster.py:247 scan_transcript cached in state_doc roster.scan; .claude/rediacc_hooks/tests/test_wl_roster.py:330 test_r4d passes (pytest exit 0) and fails when the edit-evidence term is removed
- [x] In `wl_roster.py`, add `status_at(id)` from lease events, `status` events, worker SendMessage timestamps (`wl_report.harvest_transcript`, tail-bounded) and SubagentStop captures, following lineage in both directions.
    (ticked) 2026-09-24T08:58:59Z by d778be9d: .claude/hooks/stop/wl_roster.py:449 status_at; .claude/rediacc_hooks/tests/test_wl_roster.py:338 test_r5, :350 test_r5b, :366 test_r5c pass (pytest exit 0); test_r5 fails when the threshold is moved to 30
- [x] In `wl_roster.py`, add `roster()`, returning rows, writers, readers, the five defect lists and `state` in {HONEST, DISHONEST, UNKNOWN}.
    (ticked) 2026-09-24T08:58:59Z by d778be9d: .claude/hooks/stop/wl_roster.py:338 roster(); .claude/rediacc_hooks/tests/test_wl_roster.py:242 test_r1 and :428 test_r7 pass (pytest exit 0); explain_lastevent replays the live session read-only
- [x] In `wl_roster.py`, add `live_writers_estimate(cwd, session_id)` for the PreToolUse guard.
    (ticked) 2026-09-24T08:58:59Z by d778be9d: .claude/hooks/stop/wl_roster.py:633 live_writers_estimate over live_estimate; guards/test-block_agent_cap.py 13 cases exit 0, 4 refused, and exit 1 with the cap comparison planted as >
- [x] In `wl_store.py`, fold a new `status` event kind beside the `lease` fold at `.claude/hooks/stop/wl_store.py:962`, and add an `S.status_event()` writer next to `lease_item` at `:1189`.
    (ticked) 2026-09-24T08:59:00Z by d778be9d: .claude/hooks/stop/wl_store.py:917 status fold arm, :1232 status_event writer; .claude/rediacc_hooks/tests/test_wl_roster.py:542 test_s3 and :559 test_s3b pass (pytest exit 0)
- [x] Add the `--status <me> [<id>|all]` verb to `.claude/hooks/stop/worklist.py` beside `--lease` (`:979`). It records a reset only when the transcript grew or a tool call is in flight, and records `silent` otherwise. Add the usage text to `worklist_messages.CLI_ITEM_USAGE`.
    (ticked) 2026-09-24T08:59:00Z by d778be9d: .claude/hooks/stop/worklist.py:902 --status branch; .claude/rediacc_hooks/tests/test_wl_roster.py:559 test_s3b passes (pytest exit 0); test_wl_identity.py:492 row passes 184/185; live run on agent a15d3a8f exit 0
- [x] Add the templates `V_ROSTER_CAP`, `V_ROSTER_STATUS`, `V_ROSTER_SILENT`, `V_ROSTER_UNLEASED`, `V_ROSTER_DEAD` and `N_ROSTER_HONEST` to `.claude/hooks/stop/worklist_messages.py`. Each must name the exact ids and commands.
    (ticked) 2026-09-24T08:59:00Z by d778be9d: .claude/hooks/stop/worklist_messages.py:2682 V_ROSTER_CAP onward; test_wl_poll_and_waiting.py:624 test_117 arity passes (pytest exit 0)
- [x] Wire `wl_roster.roster()` into `run_stop` right after `worker_facts` and `ladder` (`.claude/hooks/stop/wl_checks.py:2708-2710`), with the defect `vadd`s in the always tier. Register the five keys in `PRIORITY_LADDER` (`:2028`) and in `ALWAYS_KEYS` in `.claude/hooks/stop/test-always-tier.py:23`.
    (ticked) 2026-09-24T08:59:00Z by d778be9d: .claude/hooks/stop/wl_checks.py:2386 roster call, .claude/hooks/stop/wl_checks.py:2843 roster vadds, ladder at .claude/hooks/stop/wl_checks.py:2093; test-always-tier.py:54 ALWAYS_KEYS, test-always-tier.py exit 0; .claude/rediacc_hooks/tests/test_wl_roster.py:497 test_s2 fails when the cap vadd is removed
- [x] Add the HONEST suppression and summary allow in `run_stop`: filter `ROSTER_SUPPRESSES` out of `violations` immediately before the cadence gate (`wl_checks.py:4207`), dropping `agent-state` only for the `stale` verdict, and emit `N_ROSTER_HONEST` when nothing remains.
    (ticked) 2026-09-24T08:59:01Z by d778be9d: .claude/hooks/stop/wl_checks.py:4290 HONEST block; .claude/rediacc_hooks/tests/test_wl_roster.py:481 test_s1 passes (pytest exit 0) and fails when the HONEST branch is disabled
- [x] Make `wl_liveness.ladder` (`.claude/hooks/stop/wl_liveness.py:632`) skip `item:` subjects whose worker is a known subagent id, and make `poll_fast_path`'s rung forfeit (`wl_checks.py:1247`) skip the same subjects.
    (ticked) 2026-09-24T08:59:01Z by d778be9d: .claude/hooks/stop/wl_liveness.py:699 skip, .claude/hooks/stop/wl_checks.py:1265 poll skip; .claude/rediacc_hooks/tests/test_wl_roster.py:601 test_s5 passes (pytest exit 0) and fails when the ladder skip is removed
- [x] Add a roster forfeit to `poll_fast_path` (`wl_checks.py:1164`) that returns False on any cap, status, silent or dead defect.
    (ticked) 2026-09-24T08:59:01Z by d778be9d: .claude/hooks/stop/wl_checks.py:1224 roster forfeit; .claude/rediacc_hooks/tests/test_wl_roster.py:579 test_s4 passes (pytest exit 0) and fails when the forfeit is disabled
- [x] After 1.3 lands, extend the `bg-report` suppression at `wl_checks.py:2650` with `roster_covers_all(live_bg)`, keeping 1.3's restamp on both branches.
    (ticked) 2026-09-24T08:59:01Z by d778be9d: .claude/hooks/stop/wl_checks.py:2695 roster_covers_all term; test_wl_background_waits.py:1189 test_13h passes (pytest exit 0), it failed while roster_covers_all used rows instead of verified
- [x] Add a `pre-agent` pattern (matcher `^(Agent|Task)$`) to `.claude/rediacc_hooks/lifecycle.py:84` and a guard at `.claude/rediacc_hooks/guards/agent_cap.py` that refuses a writer-class spawn at `WRITER_CAP`. Regenerate `.claude/settings.json` from `lifecycle.hooks_block()` and keep `test_settings_collapse.py:184` green.
    (ticked) 2026-09-24T08:59:01Z by d778be9d: .claude/rediacc_hooks/lifecycle.py:120 pre-agent; .claude/rediacc_hooks/guards/block_agent_cap.py:77 run; test_settings_collapse.py passes (pytest exit 0); live chain-head pre-agent exit 2 on a writer at cap, exit 0 on Explore
- [x] Add `sealed_modules` to `.ci/policy/worklist-env-registry.json` and enforce it in `.ci/rediacc_ci/quality/worklist_env_registry.py`: any environment read in a sealed module is a finding, with a selftest plant.
    (ticked) 2026-09-24T08:59:02Z by d778be9d: .ci/rediacc_ci/quality/worklist_env_registry.py:208 check_sealed, .ci/policy/worklist-env-registry.json:9 sealed_modules; --selftest exit 0 with 7 new PLANT controls; real-tree plant in wl_roster.py exit 1
- [x] CONTROL, in the new `.claude/rediacc_hooks/tests/test_wl_roster.py`, with a `mk_sub(wl, aid, agent_type, age_min, parent=None, last="tool_use", edits=False)` helper modelled on `mk_mate` (`test_wl_background_waits.py:655`, using `CLAUDE_CONFIG_DIR`) and `type: "subagent"` rows in `wl.bg`. Each case is listed below.
    (ticked) 2026-09-24T08:59:02Z by d778be9d: .claude/rediacc_hooks/tests/test_wl_roster.py:58 mk_sub; 25 cases pass (pytest exit 0); 13 planted defects across wl_roster, wl_checks and wl_liveness each turned at least one case red
- [x] Control, honest roster: 3 writers and 1 Plan agent, every item leased, statuses 5 minutes old → decision allow, "ROSTER HONEST" present, no `bg-report` or `ladder` text. Positive control in the same test: unleasing one item makes it block.
    (ticked) 2026-09-24T08:59:02Z by d778be9d: .claude/rediacc_hooks/tests/test_wl_roster.py:242 test_r1 and .claude/rediacc_hooks/tests/test_wl_roster.py:481 test_s1 pass (pytest exit 0), positive control inside each
- [x] Control, unleased live writer: a live `general-purpose` agent with no lease on itself or any ancestor → block `roster-unleased` naming its id. The same agent as a child of a leased parent → no `roster-unleased`.
    (ticked) 2026-09-24T08:59:02Z by d778be9d: .claude/rediacc_hooks/tests/test_wl_roster.py:257 test_r2 passes (pytest exit 0) with both directions
- [x] Control, leased dead writer: a lease on an id that is absent from the event with no live descendant → block `roster-dead`. Lineage control from the incident: the parent is absent and its `parentAgentId` child is live → no `roster-dead` and no `ladder-gone`.
    (ticked) 2026-09-24T08:59:03Z by d778be9d: .claude/rediacc_hooks/tests/test_wl_roster.py:271 test_r3, :280 test_r3b, :601 test_s5 pass (pytest exit 0)
- [x] Control, cap: 5 leased writers → block `roster-cap` listing all 5. 4 writers plus 2 Plan agents → no `roster-cap`. A depth-2 writer child counts toward the cap.
    (ticked) 2026-09-24T08:59:03Z by d778be9d: .claude/rediacc_hooks/tests/test_wl_roster.py:300 test_r4, :310 test_r4b, :321 test_r4c, :497 test_s2 pass (pytest exit 0)
- [x] Control, status ping: status 21 minutes old → block `roster-status` naming the worker and `--status`. At 19 minutes → no ping. After `--status` with a grown transcript → the next stop allows. `--status` on a silent transcript → `roster-silent`.
    (ticked) 2026-09-24T08:59:03Z by d778be9d: .claude/rediacc_hooks/tests/test_wl_roster.py:338 test_r5, :350 test_r5b, :542 test_s3, :559 test_s3b pass (pytest exit 0)
- [x] Control, override env: `WORKLIST_WRITER_CAP=99`, `WORKLIST_STATUS_PING_MIN=999`, `WORKLIST_ROSTER=off`, `WORKLIST_FOCUS=off`, `WORKLIST_CADENCE=off`, every `WORKLIST_LADDER_*=9999`, `WORKLIST_BG_REPORT_MIN=9999` and `WORKLIST_TEAMMATE_FRESH_MIN=9999` → the 5-writer case still blocks and the 21-minute case still pings. Also an AST assertion that `wl_roster.py` and `agent_cap.py` contain no `environ` or `getenv` and that the constants are the literals 4 and 20.
    (ticked) 2026-09-24T08:59:03Z by d778be9d: .claude/rediacc_hooks/tests/test_wl_roster.py:386 test_r6, :409 test_r6b, :497 test_s2 with the hatch env pass (pytest exit 0)
- [x] Control, poll fast path: a due ping forfeits the silent poll path.
    (ticked) 2026-09-24T08:59:03Z by d778be9d: .claude/rediacc_hooks/tests/test_wl_roster.py:579 test_s4 passes (pytest exit 0) and fails when the poll forfeit is disabled
- [x] Control, the `pre-agent` guard: refuses a fifth `general-purpose` spawn, allows an `Explore` spawn at cap, and allows when it cannot count.
    (ticked) 2026-09-24T08:59:04Z by d778be9d: .claude/rediacc_hooks/guards/test-block_agent_cap.py:105 CASES, exit 0 with 13 cases and 4 refusals; exit 1 with the comparison planted as >
- [x] Docs: rewrite the writer bullet at `CLAUDE.md:131` to "at most 4 at a time, enforced by the Stop hook roster (`wl_roster.WRITER_CAP`) and the pre-agent guard; lease every writer; read-only work goes to Plan/Explore, which do not count". Change "max 2" to "max 4" at `CLAUDE.md:37`, and update the pinned sentence at `.ci/scripts/quality/check_hint_corpus.py:209` in the same commit.
    (ticked) 2026-09-24T08:59:04Z by d778be9d: CLAUDE.md:37 max 4, CLAUDE.md:131 at most 4 enforced by wl_roster.WRITER_CAP and the pre-agent guard; .ci/scripts/quality/check_hint_corpus.py:210; check_hint_corpus.py exit 0; stale-cap grep 0 matches
- [x] Docs: update `worklist_messages.py:1739` and `:1781` and `.claude/commands/handoff.md:69` to "at most 4". Confirm `docs/agent-reference/model-routing.md` has no copy of the cap (re-run the grep). Add the incident to `docs/agent-reference/TRAPS.md` beside the ListAgents trap at `:260`.
    (ticked) 2026-09-24T08:59:04Z by d778be9d: .claude/hooks/stop/worklist_messages.py:1740, .claude/commands/handoff.md:69, docs/agent-reference/TRAPS.md:273; check_trap_registry.py exit 0 at floor 97

## Critical files, with anchors verified on the working tree 2026-09-24

- `/home/developer/console/.claude/hooks/stop/wl_checks.py`: `poll_fast_path` :1164 (rung forfeit :1247); `PRIORITY_LADDER` :2028; `live_bg` and `prune_background` :2343-2352; `classify_items` call :2353; `_only_waiters` :2613, consumed at :2650 and :3875; `worker_facts`/`ladder` :2708-2710; `vadd` :2774; `bg-report` :2831 and :2846; `open-items` :2873; `agent-state` :3573; `ladder-investigate`/`ladder-gone` :4000 and :4006; cadence `pause` :4207
- `/home/developer/console/.claude/hooks/stop/wl_liveness.py`: ladder constants :45-47; `TEAMMATE_FRESH_MIN` :258; `taskKind` filter :293; `_record_is_idle` :383; `prune_background` :521 (teammate-only :534); `ROSTER_MAX` :578; `ladder` :632 (`gone` :663, teammate branch :723)
- `/home/developer/console/.claude/hooks/stop/worklist.py`: `--lease` :979; `lease_item` call :1063
- `/home/developer/console/.claude/hooks/stop/wl_store.py`: lease fold :962; `lease_item` :1189; `classify_items` :1231
- `/home/developer/console/.claude/hooks/stop/wl_report.py`: `running_agent_ids` :591; `harvest_transcript` :679
- `/home/developer/console/.claude/rediacc_hooks/lifecycle.py`: `PATTERNS` :84; `pre-edit` :99
- `/home/developer/console/.claude/rediacc_hooks/tests/wlfix.py` (fixture) and `/home/developer/console/.claude/rediacc_hooks/tests/test_wl_background_waits.py:655` (`mk_mate`)
- `/home/developer/console/.claude/hooks/stop/test-always-tier.py:23` (`ALWAYS_KEYS`)
- `/home/developer/console/.ci/policy/worklist-env-registry.json` and `/home/developer/console/.ci/rediacc_ci/quality/worklist_env_registry.py` (`scan_python` :111)
- `/home/developer/console/CLAUDE.md:37` and `:131`; `/home/developer/console/.ci/scripts/quality/check_hint_corpus.py:209`; `/home/developer/console/.claude/hooks/stop/worklist_messages.py:1366/1379/1391` (the roster block), `:1739` and `:1781` (the cap); `/home/developer/console/.claude/commands/handoff.md:69`

## Verification

```bash
# the new controls, then the whole Stop suite (fixtures are rebuilt per test)
.ci/cache/toolchain/uv-tools/bin/pytest -q .claude/rediacc_hooks/tests/test_wl_roster.py
.ci/cache/toolchain/uv-tools/bin/pytest -q .claude/rediacc_hooks/tests/ -k "wl_ or settings or wiring"
python3 .claude/hooks/stop/test-always-tier.py
# the no-override gate, including its sealed-module selftest
python3 .ci/scripts/quality/check_worklist_env_registry.py --selftest
python3 .ci/scripts/quality/check_worklist_env_registry.py
python3 .ci/scripts/quality/check_hint_corpus.py
# the settings file is still what lifecycle.PATTERNS generates
.ci/cache/toolchain/uv-tools/bin/pytest -q .claude/rediacc_hooks/tests/test_settings_collapse.py
# no stale cap text anywhere
grep -rnE "at most 2 (writers|at a time)|max 2, rule 4|At most 2 concurrent writers" CLAUDE.md .claude docs .ci/scripts | grep -v _done/
# live replay against today's incident: must print ROSTER HONEST or name the real dead lease 8ea2de80
python3 -c "import sys,json; sys.path.insert(0,'.claude/hooks/stop'); import wl_roster; print(wl_roster.explain_lastevent('d778be9d'))"
```

The last command needs a read-only `explain_lastevent(prefix)` helper in `wl_roster` that reads the sidecar and the store and prints the verdict. It is the in-tree way to rerun the incident.

## Coordination with the section-1.3 writer (`a305ee07a5e707b64`, items `cb7cc1db` and `507de6b3`) and the defer-settle writer (`a2b593dbefc625beb`)

**Must wait for 1.3 to land.** These touch the same lines or the same fixture file:
- The `bg-report` suppression box at `wl_checks.py:2650`. 1.3 widens that exact predicate, and this plan adds a third term to it.
- Any edit to `wl_liveness.live_teammate_transcripts` or `prune_background` (none is planned, but see the message below).
- New test functions in `test_wl_background_waits.py`. 1.3's control goes there, which is why this plan's controls live in a new module, `test_wl_roster.py`.

**Must wait for the defer-settle writer to commit.** These edit `wl_checks.py` hunks near its uncommitted diff:
- the cadence-gate suppression (around :4207)
- the always-tier `vadd` wiring (around :2710)

Both writers edit `wl_checks.py` without committing, and a third writer in the same file breaks the disjoint-ownership rule in CLAUDE.md rule 4.

**Can start now.** These touch files neither writer owns:
- `wl_roster.py`
- the `wl_store.py` `status` event
- the `worklist.py --status` verb
- the `worklist_messages.py` templates (append-only, new names)
- `guards/agent_cap.py` and the `lifecycle.py` pattern
- the env-registry `sealed_modules` gate
- `test_wl_roster.py`, including the cases that only need `wl_roster` directly, not `run_stop`
- the docs boxes

The `wl_liveness.ladder` skip box touches only `wl_liveness.py`, which 1.3's box does not edit (its box edits `wl_checks.py`), so it can also start now. Recheck with `git diff -- .claude/hooks/stop/wl_liveness.py` before editing.

**Tell the 1.3 writer now (F2).** Its box says to widen the predicate "using the teammate count from `wl_liveness.py:318`". That count filters `taskKind == "in_process_teammate"`, which none of this harness's `type: "subagent"` metas carry (0 of 305). So the widened predicate would stay false for every subagent in today's event. Its control should plant `type: "subagent"` rows and metas with no `taskKind`, or it proves only the old teammate shape.

### Critical Files for Implementation
- /home/developer/console/.claude/hooks/stop/wl_checks.py
- /home/developer/console/.claude/hooks/stop/wl_liveness.py
- /home/developer/console/.claude/hooks/stop/worklist.py
- /home/developer/console/.claude/rediacc_hooks/lifecycle.py
- /home/developer/console/.claude/rediacc_hooks/tests/wlfix.py
