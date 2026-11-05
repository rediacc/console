# PLAN: tick tracking: every landed writer commit names the plan box it serves, landing prints the tick, code and live halves are tracked per clause without touching a box line, and an open box with landed work and no record stops the session

Status: approved -- operator order 2026-11-05, "let's plan for tick. make it promoted after planning." <!-- style-ok -->
Owner: d778be9d
Priority: P1 -- writer work lands and its box stays open: five landed writer commits of branch 1104-1 (1d600b20e, d4125a0b1, ec099603d, e2bdb427c, 4b3e830f0) serve five open boxes, and three of those boxes have no investigation row at all
Depends-On: no-dep -- the land verb and the lease records of PLAN-worktree-lease.md are landed; its one open box, W15, is a live lead run that changes none of the lines T2 and T4 touch
Concurrency: parallel -- four file groups (see "Groups"): T2 and T4 share worktree_lease.py and land one at a time; T5, T6 and T7 share wl_report.py; T7, T10 and T12 share wl_checks.py and worklist_messages.py, and land in that order; T6 and T14 share writers-now.md. wl_checks.py, worklist.py, wl_store.py and worklist_messages.py overlap PLAN-stop-hook-retro-20261101.md at different lines, and block_plan_concurrency serializes those writers.
Owns: agent/plans/PLAN-tick-tracking.md, .claude/hooks/stop/wl_planbox.py (new), .claude/hooks/stop/wl_boxaudit.py (new), .claude/hooks/stop/wl_report.py, .claude/hooks/stop/wl_roster.py, .claude/hooks/stop/wl_worktrees.py, .claude/hooks/stop/wl_liveproof.py, .claude/hooks/stop/wl_planrec.py, .claude/hooks/stop/wl_store.py, .claude/hooks/stop/wl_checks.py, .claude/hooks/stop/worklist.py, .claude/hooks/stop/worklist_messages.py, .claude/hooks/stop/test-wl_worktrees.py, .claude/rediacc_hooks/git/githooks.py, .ci/rediacc_ci/dev/worktree_lease.py, .ci/rediacc_ci/tests/test_dev_worktree_lease.py, .claude/rediacc_hooks/tests/test_wl_planbox.py (new), .claude/rediacc_hooks/tests/test_wl_boxaudit.py (new), .claude/rediacc_hooks/tests/test_wl_report_tick.py (new), .claude/rediacc_hooks/tests/test_githook_plan_box.py (new), .claude/rediacc_hooks/tests/test_wl_report_inbox.py, .claude/rediacc_hooks/tests/test_wl_roster.py, .claude/rediacc_hooks/tests/test_wl_state_document.py, .claude/rediacc_hooks/tests/tick_tracking_fixtures/** (new), agent/ledgers/plan-box-progress.jsonl (new), .claude/config/effort.json, .claude/commands/writers-now.md, .claude/skills/pr-epics/trailers.md, docs/agent-reference/plan-records.md, CLAUDE.md
Live-Proof: none -- CI and agent tooling only: every Owns path is under .claude, .ci/rediacc_ci/dev, agent or docs, so `surfaces.owns_surfaces` returns no surface and no live receipt is owed
Updated: 2026-11-05
First-Seen: 2026-11-05

## Order

Operator, 2026-11-05: "let's plan for tick. make it promoted after planning." <!-- style-ok --> The plan closes one gap. Sub-agent work lands, but the plan box it serves is never ticked, or the writer's report is lost on the way to the lead.

## Measured facts

Read on 2026-11-05 on branch 1104-1. Nothing was created to measure them.

- **The TICK block is prose.** A writer report carries a "TICK block": the plan, the box signature, the clause list, which clauses each commit satisfies, and the open clauses with the command that closes them. Nothing reads it by machine. `wl_report.open_boxes` (.claude/hooks/stop/wl_report.py:458) counts only `- [ ]` lines, and reads 0 on all five reports below.
- **Five landed writer commits, five open boxes.** Each commit carries `PR-TASK: 09b8bdfa` and a `-x` line. None names a box. The captured reports do name the box, in prose:

  | Landed | Lease sha | Report | Box |
  |---|---|---|---|
  | 1d600b20e | e72acf0a | f82f8c024294 | PLAN-ssh-key-source-ranges.md#7692f2db |
  | d4125a0b1 | 2a3bb490 | f04ac7cf729c | PLAN-detached-jobs.md#1d17b634 |
  | ec099603d | e841f2f78 | 87b716637410-2 | PLAN-rediaccfile-unprivileged.md#afa91934 (H2) |
  | e2bdb427c | d93cb2901 | b756fa793919-2 | PLAN-backup-local-image.md#339bf791 |
  | 4b3e830f0 | ae15f7cba | 85c8b92ea520, 85c8b92ea520-2 | PLAN-detached-jobs.md#3d256594 (L5) |

  All five boxes are open in `.ci/config/plan-boxes.json`. In `agent/ledgers/plan-investigation.jsonl`, afa91934, 339bf791 and 3d256594 have no row. 7692f2db has 36 rows, the latest `partial` at head 9524cedb8 (2026-11-04). 1d17b634 has one `present` row at head 3169397f6 (2026-10-30).
- **Landing goes quiet.** After `./run.sh worktree land <id>` and the picks, `worktree-unlanded` (.claude/hooks/stop/wl_worktrees.py:250-376) has nothing to say. Nothing compares landed commits with boxes still open. `land_plan` (.ci/rediacc_ci/dev/worktree_lease.py:493) refuses only a missing `PR-TASK:`, a gitlink and `agent/**`. A PR-TASK names an epic, not a box. `check:ci-plan-implementation` judges only ticks that were made.
- **Mixed boxes stall.** A box with a code half and a live half gets its code landed, and the item goes back to open with a note. Nothing schedules the live run. Most writer reports of this round read "partial: code landed, live half owed". The survey /tmp/writers-now/1104-1-20261105T2005Z.md counts 135 open boxes over 26 Promoted plans: G2 90, G3 12, G4 6, G5 26, G6 1.
- **Phantom reports.** A coordinator sub-agent (a465aa7e2ca09a227) sent 21 instructions by SendMessage to 11 writer ids. `harvest_transcript` (.claude/hooks/stop/wl_report.py:850-880) keeps every SendMessage, whatever its `to`. Each of the coordinator's 15 stops became an unread report, a7e2ca09a227 through a7e2ca09a227-15, titled from its last outgoing order ("Coordinator ruling: ..."). `scan` (:950-975) uses the same harvest.
- **Who sends to the lead.** Across every stored body, the recipients are `main` 12,497 times, a raw agent id 432 times, and `coordinator` 25 times. A writer's meta records `parentAgentId` (for example, agent-a455a87b716637410.meta.json names a465aa7e2ca09a227). So a coordinator's children can be read without guessing.
- **The finished-worker block cites no report.** The lead learned of six finished writers only from "LEASED TO A FINISHED WORKER" (worklist_messages.py:2910, raised at wl_checks.py:3977 from `wl_roster` `leased_dead`). Each row names an agent and an item, not the captured report.
- **The plan advisory is capped.** `PLAN FILE vs WORKLIST` (wl_planfile.py:685, queued at wl_checks.py:4375) is advisory by design, at 3 per stop.
- **Writers cannot investigate.** A lease writer cannot write `agent/**` (block_lease_boundary), so it cannot run `--plan-investigate` or `--plan-tick`. The lead runs both in the main checkout.
- **Clause 1 forbids a late row.** `investigation_for` takes the LATEST row of a box (wl_planrec.py:2357). `clause1_ordering` (:2659) refuses a tick whose cited commit does not descend from that row's `head`, except under a `present` verdict. A "code landed, live owed" row written into the investigation ledger after landing would therefore refuse the later honest tick that cites the code commit.

## Design

### 1. The `Plan-Box:` trailer

Grammar, one trailer per box a commit serves:

    Plan-Box: <PLAN-file>.md#<sig8> clauses=<C1,C2,...|all>
    Plan-Box: none -- <reason, at least 12 characters>

- The plan is a basename, resolved under `agent/plans/`. A `Moved-To:` stub is followed.
- `sig8` is `wl_planrec.box_sig` of an open box at land time.
- `clauses=all` is legal for a box with no clause map (section 3). Clause ids must exist in the map when one does.
- `git cherry-pick -x` copies the message and adds its line after the trailers, so the trailer survives landing. It lives in git history, so it also survives compaction.
- `.claude/hooks/stop/wl_planbox.py` holds the one parser. It also holds the TICK grammar (section 5) and the lease-to-landed map (section 2). `worktree_lease.py` loads it through `_hook_module`, as it already loads `wl_worktrees`.

Refusals:

- `land_plan` refuses a lease commit with no `Plan-Box:` trailer, beside its PR-TASK refusal.
- It also refuses a malformed trailer, a box that is not open, and an unknown clause id.
- The lease `commit-msg` hook refuses the same cases at commit time. The writer can then fix the message in its own lease, before the lead ever reads it.

### 2. `worktree land` finishes the job

`land` stays read-only before the picks. It also prints, per commit, the boxes the commit names.

A new mode runs after the picks:

    ./run.sh worktree land <id> --ticks [--run]

It works in four steps:

1. **Map each lease sha to its landed sha.** The map reads `(cherry picked from commit <sha>)` on the live branch, which is the `PICKED_LINE` reader `wl_worktrees` already uses.
2. **Read the Plan-Box trailers of each landed commit.**
3. **Print, per box:**
   - the clause-progress row that records the landed clauses (section 3);
   - when no investigation row exists, the `--plan-investigate` line, with pointers `commit:<landed sha>` and a fileline, and the note opening `post-landing:`;
   - when every clause is covered and a row recorded before the work exists, a ready `--plan-tick <me> <plan> <sig> 'commit:<landed sha> ...'`.
4. **With `--run`:** write the progress rows, and run `--plan-tick` only where step 3 printed one. `--run` never writes an investigation row, because the latest-row rule and Clause 1 make an automatic late row harmful.

A lease's own sha never reaches a tick line.

### 3. Code and live halves, split without touching a box line

**Decision: a sibling ledger, `agent/ledgers/plan-box-progress.jsonl`.** Not the investigation ledger, and not child boxes.

- **Investigation ledger: rejected.** A clause-progress row would become the latest row. Its `head` would then sit past the code commit, and Clause 1 would refuse the live tick that cites that commit. Loosening Clause 1 reopens the cheat its docstring describes.
- **Child boxes: rejected.** They pass G-A1 (adding a box is legal). But they add an open box per half. The queue progress block and `plan_gate.open_boxes` then report extra work, and the parent box still owes its own tick. Two ticks for one unit is a record that disagrees with itself.
- **The sibling ledger changes no plan byte.** G-A0, G-A1 and check:ci-plan-record hold by construction.

The ledger has two row kinds:

- `define`: `{at, by, plan, sig, clauses:[{id:"C1", half:"code"|"live"|"operator", text}]}`. It is written by `worklist.py --box-clauses <me> <plan> <sig> "C1 [code] <text>" "C2 [live] <text>" ... --write`. The sig must be open, and is resolved through `wl_planrec.open_boxes` and `select_box`.
- `progress`: `{at, by, plan, sig, clause, state:"landed"|"proved"|"live-owed", ref}`. `ref` is a landed sha, a live-proof row id, or a release note. It is written by `land --ticks`, by `--live-proof --write`, and by the release path (section 7).

A clause map is a reading of the box, never a rewrite. When the box text itself is wrong, the existing `(corrected ASKED:<minute>Z)` sub-line pattern (agent/plans/PLAN-free-license.md:65) stays the only door, and the box line stays byte-identical.

**Migration (T13).** Every open Promoted box with a landed commit and no clause map gets a `define` row. That covers about 135 boxes, the five above included. Only ledger rows are written; no plan file changes.

### 4. `worklist.py --box-audit <me> [plan] [--sha <list>] [--live-owed] [--mixed-unsplit]`

`.claude/hooks/stop/wl_boxaudit.py` reads five sources per open box:

1. landed commits on the live branch since the merge-base whose `Plan-Box:` names the box;
2. captured reports whose TICK lines name the box, with each named lease sha mapped to its landed sha by the `-x` line;
3. VERIFIED rows for the box in `agent/ledgers/live-proof.jsonl`, through the `wl_liveproof` reader;
4. investigation rows (`wl_planrec.investigation_for`);
5. progress and define rows.

One verdict per box, first match wins:

- **tickable-now**: every clause, or `all`, is landed or proved, and an investigation row exists. The ready `--plan-tick` line is printed.
- **stale-investigation**: work is linked, but the latest row's `head` is unreachable from HEAD with no rebase successor, or `wl_planpreflight.survey` marks the row not current.
- **live-owed**: a code clause is landed and a live or operator clause is not proved.
- **untouched**: nothing linked. A box whose item is leased to a live writer is shown with that lease.

The audit has three outputs:

- It renders an "Owed ticks" section: the tickable-now and live-owed boxes of plans this session owns.
- `--mixed-unsplit` lists open boxes that have linked landed work and no clause map.
- The exit code is 0, or 1 when `--mixed-unsplit` lists anything, so the migration has a gate.

### 5. Capture, the TICK format, and report citation

**Capture.** `harvest_transcript` keeps a SendMessage only when `to` is a lead recipient (`main`, `team-lead`, `lead`). The final text is always kept.

- The index still records the number of outgoing sends, as `out`, so the report still shows that the agent ran.
- `unread` re-judges legacy rows from the `## SendMessage N -> <to>` headers in the body. A send to anyone else adds no substance, and the title comes from the final message.
- The 15 coordinator rows stop reading as reports.

**TICK format.** Defined in `.claude/commands/writers-now.md`, one line per box, after the prose:

    TICK <PLAN-file>.md#<sig8> <done|present|partial|untouched|blocked> commits=<lease shas|-> landed=<C1,C2|all|-> owed=<C3:live,C4:operator|->
      close: <the exact command or question that closes what is owed>

- `wl_planbox.parse_tick` reads these lines. `capture` stores them on the index row as `boxes: [{plan, sig, state, commits, landed, owed}]`, bounded by `_fit`.
- A legacy reader covers the prose blocks of this round. The pattern is a plan path, then ``box `<sig8>` ``, then 7-to-12-hex shas. It exists so the five commits above can be linked; new reports use the TICK line.

**Report citation.**

- A worklist item whose text names a box shows `report <rid> names box <sig> (<state>, owed <halves>)` beside it.
- Each `LEASED TO A FINISHED WORKER` row cites the report id of the agent it names.
- When the leased agent is a coordinator, the row also lists each child: the metas whose `parentAgentId` is that agent, each with its report id and box sigs.

### 6. The blocking check `plan-box-owed`

Once the audit lands, the Stop hook blocks in one case. A commit landed on the live branch names a still-open box (by trailer or by report TICK), the box has no investigation row, and that has held for 3 stops in a row. Three stops is the work window the effort tuner already uses.

- The block message is the audit line plus the `--plan-investigate` command.
- It is a `vadd` key, `plan-box-owed`, entered in `.claude/config/effort.json` as `{"block": "smart", "advise": "low"}`.
  - That places it in the `smart` bundle ("owed work and record integrity").
  - The key carries no `tuned` stamp. Per agent/plans/_done/PLAN-stop-hook-effort-tuning.md, moving a key later is the tuner's job, from outcome rows: promotion applies on its own, demotion only after one batched /ask.
  - The effort-table rule of check:ci-plan-record requires the key in the same commit as the `vadd`.

### 7. The live-owed state

On `worklist.py --lease <me> <id> release`, the hook looks for three conditions together:

- the item names a box;
- the audit links landed code to that box;
- a live or operator clause of the box is not proved.

When all three hold, the release appends a `progress` row with `state: live-owed` for each such clause, and prints it. A box with no clause map counts as owing its live half when its report TICK carries `owed=...:live`, or when the box is an `LP-` box.

Two places read the state:

- The audit shows the box as live-owed.
- writers-now step 7 starts its live queue from `worklist.py --box-audit <me> --live-owed`, so a released half is scheduled, not forgotten.

## Groups

Boxes that share a file go to one writer, or land in the stated order.

- **Lease (T2, T4):** `.ci/rediacc_ci/dev/worktree_lease.py`, `.ci/rediacc_ci/tests/test_dev_worktree_lease.py`. One writer. T2 lands before T4.
- **Report (T5, T6, T7):** `.claude/hooks/stop/wl_report.py`. T5 and T6 go to one writer. T7 follows, and also needs the checks group.
- **Checks (T7, T10, T12):** `wl_checks.py`, `worklist_messages.py`. Landed in the order T7, T10, T12.
- **Verbs (T8, T9, T11):** `worklist.py` and `wl_boxaudit.py`. One writer in order T8, T9, T11. T9 needs T1 and T6.
- **writers-now.md (T6, T14):** T6 adds the TICK section, and T14 edits the rest after it.
- T1 and T3 stand alone. T13 and T15 are lead boxes in the main checkout, because they write `agent/**`.

The test prefix below is `PYTHONPATH=.ci .ci/cache/toolchain/uv-tools/bin/pytest`, written as `PYTEST`.

## Tasks

- [ ] T1 [writer, opus] The grammar module `wl_planbox.py`: `parse_plan_box(message)`, `parse_tick(body)` with the legacy prose reader, and `landed_map(root, lease_shas)` from the `-x` line.
  Owns: .claude/hooks/stop/wl_planbox.py, .claude/rediacc_hooks/tests/test_wl_planbox.py, .claude/rediacc_hooks/tests/tick_tracking_fixtures/**. Accept: `PYTEST .claude/rediacc_hooks/tests/test_wl_planbox.py -q` rc 0. The cases: `Plan-Box: PLAN-detached-jobs.md#3d256594 clauses=C1,C2` parses; `Plan-Box: none -- <12+ chars>` parses; a short reason, a 7-hex sig and two `#` are refused; the trailer survives a fixture `git cherry-pick -x` and still parses beside the `-x` line. The legacy reader, over copies of the five report bodies in the fixture directory, returns exactly the five (plan, sig, lease sha) rows of the Measured-facts table. CONTROL: the message of 4b3e830f0 (`git show -s --format=%B 4b3e830f0`) yields "no Plan-Box", and `wl_report.open_boxes` over the same five bodies returns 0, which is the old reading.

- [ ] T2 [writer, opus] `land` refuses a lease commit without a valid Plan-Box, and prints the boxes each admitted commit names. Changes: `_problems` (.ci/rediacc_ci/dev/worktree_lease.py:440) calls `wl_planbox`; LAND_HELP names the rule.
  Owns: .ci/rediacc_ci/dev/worktree_lease.py, .ci/rediacc_ci/tests/test_dev_worktree_lease.py. Accept: `PYTEST .ci/rediacc_ci/tests/test_dev_worktree_lease.py -q -k plan_box` rc 0. Over a fixture lease: a commit with only `PR-TASK:` makes `land` exit 1, naming the sha and "no Plan-Box trailer", with nothing on stdout. `Plan-Box: none -- <reason>` is admitted. A trailer naming a ticked box, or an undefined clause, is refused. CONTROL: the same PR-TASK-only fixture passes `land_plan` with T2's call removed, and the test asserts that pairing.

- [ ] T3 [writer, sonnet] The lease `commit-msg` hook refuses a missing or malformed Plan-Box. Only in a lease tree (`commit_policy.lease_root`); the main checkout is unchanged.
  Owns: .claude/rediacc_hooks/git/githooks.py, .claude/rediacc_hooks/tests/test_githook_plan_box.py. Accept: `PYTEST .claude/rediacc_hooks/tests/test_githook_plan_box.py -q` rc 0. The cases: a lease commit without the trailer exits 1 with the grammar line; with a valid trailer it exits 0; the same message in a non-lease repository exits 0. CONTROL: the old `commit_msg` admits the trailerless lease message, asserted by running the test against `commit_msg` with the new branch stubbed out.

- [ ] T4 [writer, opus] `./run.sh worktree land <id> --ticks [--run]` (Design 2).
  Owns: .ci/rediacc_ci/dev/worktree_lease.py, .ci/rediacc_ci/tests/test_dev_worktree_lease.py, .claude/hooks/stop/wl_worktrees.py, .claude/hooks/stop/test-wl_worktrees.py. Accept: `PYTEST .ci/rediacc_ci/tests/test_dev_worktree_lease.py -q -k ticks` rc 0. Over a fixture lease landed with `-x`: the output names each box with the landed sha. A fully covered box with a row recorded before the work gets a `--plan-tick` line. A box with an uncovered clause gets only the progress line. A box with no row gets the `post-landing:` `--plan-investigate` line, and `--run` writes no investigation row. Also `python3 .claude/hooks/stop/test-wl_worktrees.py` rc 0. CONTROL: an assertion that no printed tick line holds a lease sha fails when the map is bypassed (the test plants that bypass).

- [ ] T5 [writer, opus] Capture keeps only lead-bound sends and the final text, on both the hook path and `scan`. Legacy rows are re-judged from their body headers.
  Owns: .claude/hooks/stop/wl_report.py, .claude/rediacc_hooks/tests/test_wl_report_inbox.py, .claude/rediacc_hooks/tests/tick_tracking_fixtures/**. Accept: `PYTEST .claude/rediacc_hooks/tests/test_wl_report_inbox.py -q -k recipient` rc 0. The fixture transcript is shaped after a465aa7e2ca09a227: 21 sends to 11 agent ids, then a final text. Both `handle_subagent_stop` and `scan` store a body with no `## SendMessage` section, `sends` 0 and `out` 21. A send `to: main` is kept. The copies of bodies a7e2ca09a227 and a7e2ca09a227-15 read as not unread-substantive, and are not titled "Coordinator ruling". CONTROL: the old `harvest_transcript` returns 21 sends for the same fixture, and the test asserts that count against the pre-change function, kept as `_harvest_all` for the test only. One-off, recorded in the tick: `worklist.py --reports --list --unread --as d778be9d` lists no `a7e2ca09a227` row.

- [ ] T6 [writer, opus] The TICK line format in writers-now.md, parsed onto the report row. Changes: the Report block of the brief in `.claude/commands/writers-now.md` gains the TICK line (Design 5); `capture` stores `boxes`.
  Owns: .claude/hooks/stop/wl_report.py, .claude/commands/writers-now.md, .claude/rediacc_hooks/tests/test_wl_report_tick.py. Accept: `PYTEST .claude/rediacc_hooks/tests/test_wl_report_tick.py -q` rc 0. The test reads the TICK example straight out of writers-now.md and parses it to one box, so the documented form is the tested form. A capture of a body with two TICK lines indexes two `boxes` entries. The five legacy bodies index their box through the T1 reader. CONTROL: the old Report template text ("one block per box signature") parses to zero boxes.

- [ ] T7 [writer, opus] "report names open box X" beside the item, and report ids in LEASED TO A FINISHED WORKER, coordinator children included. Changes: `wl_roster` resolves children through `parentAgentId`; V_ROSTER_DEAD rows (worklist_messages.py:2910) gain `report <rid>` and the box sigs.
  Owns: .claude/hooks/stop/wl_roster.py, .claude/hooks/stop/wl_checks.py, .claude/hooks/stop/worklist_messages.py, .claude/rediacc_hooks/tests/test_wl_roster.py. Accept: `PYTEST .claude/rediacc_hooks/tests/test_wl_roster.py -q -k report` rc 0. The fixture is an item leased to `worker:a465aa7e2ca09a227` with five finished child metas and their captured reports. The dead row lists f82f8c024294, f04ac7cf729c, 87b716637410-2, b756fa793919-2 and 85c8b92ea520-2 with sigs 7692f2db, 1d17b634, afa91934, 339bf791 and 3d256594. An item whose text names afa91934 renders "report 87b716637410-2 names box afa91934 (partial, owed live)". CONTROL: the old V_ROSTER_DEAD row for the same fixture holds no report id, asserted against the pre-change format string.

- [ ] T8 [writer, opus] The progress ledger and the clause verbs. Changes: `wl_planbox` reads and appends `agent/ledgers/plan-box-progress.jsonl` under a TMPDIR flock, as the investigation ledger does; `worklist.py --box-clauses` and `--box-progress` (Design 3).
  Owns: .claude/hooks/stop/wl_planbox.py, .claude/hooks/stop/worklist.py, .claude/hooks/stop/wl_planrec.py, .claude/rediacc_hooks/tests/test_wl_planbox.py. Accept: `PYTEST .claude/rediacc_hooks/tests/test_wl_planbox.py -q -k progress` rc 0. A `define` row for an open sig is written once; the same row again is deduped; a done or unknown sig is refused. Then, in the main checkout, `worklist.py --box-clauses d778be9d agent/plans/PLAN-rediaccfile-unprivileged.md afa91934 "C1 [live] baseline read-only" ... --write` rc 0, `git diff --exit-code -- agent/plans/` rc 0, and `npm run check:ci-plan-boxes` and `npm run check:ci-plan-record` rc 0. CONTROL: `--box-clauses` on sig 1d17b634 with a typo (1d17b635) exits 2 and writes nothing.

- [ ] T9 [writer, opus] `worklist.py --box-audit` (Design 4) in `wl_boxaudit.py`.
  Owns: .claude/hooks/stop/wl_boxaudit.py, .claude/hooks/stop/worklist.py, .claude/hooks/stop/wl_liveproof.py, .claude/rediacc_hooks/tests/test_wl_boxaudit.py. Accept: `PYTEST .claude/rediacc_hooks/tests/test_wl_boxaudit.py -q` rc 0, with one fixture per verdict. Then, on this tree, `worklist.py --box-audit d778be9d --sha 1d600b20e,d4125a0b1,ec099603d,e2bdb427c,4b3e830f0` rc 0. It names each sha against its box from the Measured-facts table, with no box `untouched`, afa91934 `live-owed`, and 1d17b634 and 7692f2db `stale-investigation` or `live-owed` as the tree decides. CONTROL: with the report store pointed at an empty directory (`WORKLIST_REPORTS_DIR`), the same five read `untouched`, which proves that report linkage is what finds work that carries no trailer.

- [ ] T10 [writer, opus] The blocking check `plan-box-owed` (Design 6) and its effort-table row.
  Owns: .claude/hooks/stop/wl_checks.py, .claude/hooks/stop/worklist_messages.py, .claude/hooks/stop/wl_boxaudit.py, .claude/config/effort.json, .claude/rediacc_hooks/tests/test_wl_boxaudit.py. Accept: `PYTEST .claude/rediacc_hooks/tests/test_wl_boxaudit.py -q -k stopcheck` rc 0. A box with landed work and no investigation row stays quiet for stops 1 and 2 and blocks on stop 3 with the audit line. Writing the row silences it. Also `npm run check:ci-plan-record` rc 0 with the new key. On this tree, three fixture stops over the real ledger name afa91934, 339bf791 and 3d256594. CONTROL: deleting `plan-box-owed` from effort.json makes `npm run check:ci-plan-record` exit non-zero (the effort-table rule), and the test asserts that the check fires nothing at effort `quiet`.

- [ ] T11 [writer, sonnet] Live-owed on release (Design 7).
  Owns: .claude/hooks/stop/worklist.py, .claude/hooks/stop/wl_boxaudit.py, .claude/rediacc_hooks/tests/test_wl_boxaudit.py. Accept: `PYTEST .claude/rediacc_hooks/tests/test_wl_boxaudit.py -q -k release` rc 0. Releasing an item that names a box with landed code and a live clause appends one `live-owed` row per clause and prints it. `--box-audit --live-owed` then lists the box. CONTROL: releasing an item whose box has no landed work appends nothing, and the release message stays byte-identical to today's.

- [ ] T12 [writer, sonnet] STATE.md "Owed ticks". Changes: when the audit finds a tickable-now or live-owed box in a plan this session owns, the `wl_store` shape verdict for a body with no `## Owed ticks` section is `owing`, refused at write time like `unfocused`. The audit result is cached per HEAD.
  Owns: .claude/hooks/stop/wl_store.py, .claude/hooks/stop/worklist.py, .claude/hooks/stop/worklist_messages.py, .claude/rediacc_hooks/tests/test_wl_state_document.py. Accept: `PYTEST .claude/rediacc_hooks/tests/test_wl_state_document.py -q -k owed` rc 0. A body with no section and one tickable box is `owing`; the same body with the section is `ok`; with no owed box, the section is not demanded. CONTROL: the first case reads `ok` with the audit stubbed out, which is the old verdict.

- [ ] T13 [lead] Migration: a clause map for every open Promoted box with landed work, and the five commits linked. Changes: a read-only sonnet survey proposes the clauses per box from the survey file and the box text; the lead writes `--box-clauses` rows; no plan file changes.
  Owns: agent/ledgers/plan-box-progress.jsonl. Accept: `worklist.py --box-audit d778be9d --mixed-unsplit` rc 0, printing nothing. `git diff --exit-code <base> -- agent/plans/` shows no box line changed. `npm run check:ci-plan-boxes`, `npm run check:ci-plan-record` and `npm run check:ci-plan-implementation` rc 0. CONTROL: the same `--mixed-unsplit` command, run before the rows are written, exits 1 and lists afa91934 (H2: offline recipe landed in ec099603d, live run owed) among its rows.

- [ ] T14 [lead] Docs. Changes: the writers-now brief gains the Plan-Box line; step 6 runs `land <id> --ticks`; step 7 starts from `--box-audit --live-owed`; the CLAUDE.md lease paragraph names the trailer; `docs/agent-reference/plan-records.md` gains the progress ledger and the audit; `.claude/skills/pr-epics/trailers.md` puts Plan-Box beside PR-TASK.
  Owns: .claude/commands/writers-now.md, CLAUDE.md, docs/agent-reference/plan-records.md, .claude/skills/pr-epics/trailers.md. Accept: `npm run check:ci-prose-style` and `npm run check:ci-plan-citations` rc 0. `PYTEST .claude/rediacc_hooks/tests/test_wl_report_tick.py -q` still rc 0, since it reads the doc. CONTROL: `grep -c "Plan-Box:" .claude/commands/writers-now.md CLAUDE.md .claude/skills/pr-epics/trailers.md` prints a non-zero count for each file, and 0 for each on the base commit.

- [ ] T15 [lead] End to end on one real box. Changes: none beyond what a real box needs: one open G5 box of a Promoted plan goes through /writers-now with a Plan-Box trailer, is landed, and is ticked from what `land --ticks` printed.
  Owns: agent/plans/PLAN-tick-tracking.md. Accept, in order:
  - `--plan-investigate` before the spawn;
  - the writer's commit carries `Plan-Box:`;
  - `./run.sh worktree land <id>` names the box;
  - the picks run;
  - `./run.sh worktree land <id> --ticks --run` rc 0, ticking the box with the landed sha;
  - `worklist.py --box-audit d778be9d <plan>` no longer lists the box;
  - `npm run check:ci-plan-implementation` rc 0;
  - `./run.sh worktree gc --write --id <id>` rc 0.

  The command transcript goes in Verification notes.

## Alternatives rejected

- **Clause progress in the investigation ledger.** The latest-row rule and Clause 1 turn a late progress row into a refusal of the real tick (Measured facts).
- **Child boxes per half.** They inflate open counts and leave the parent box owing a second tick (Design 3).
- **Rewording a mixed box into two boxes.** G-A1 reads the vanished signature as a deletion.
- **`land` running the picks itself.** `review_commit.py` fires only on a `git cherry-pick` in the Bash text (PLAN-worktree-lease, "What the code refuted"). So `land` keeps printing, and `--ticks` runs after the lead's picks.
- **Writers running `--plan-investigate`.** block_lease_boundary keeps `agent/**` out of a lease, and the investigation must come before the work, so the lead writes it at spawn.
- **Making `PLAN FILE vs WORKLIST` blocking.** Its design note documents the deadlock: a plan with many open boxes would refuse every turn. `plan-box-owed` blocks only on landed work with no record.

## Verification notes

(empty until the first box)
