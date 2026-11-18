# PLAN: the Stop hook judges the worklist store, not the message prose
Status: approved -- operator request 2026-11-18: the store is the one status channel, the hook renders status from it, and the judge stops checking the message for ids
Owner: d778be9d
First-Seen: 2026-11-18
Depends-On: no-dep -- no box waits on another plan; box X1 supersedes R20261117.1 of PLAN-stop-hook-retro-20261117.md, and that plan's R20261117.2 to .4 edit the same three judge-fact sites, so its writers start after J1
Priority: P1 -- 49 of 103 judge blocks in the 2026-11-10 to 11-17 window rested at least partly on omitted ids; 22 were answered with a full table of 15 or more ids, 17 replies made no work call, and the replies came to 144,613 characters
Concurrency: parallel -- S2 and S3 start together once S1 lands, on disjoint files; wl_checks.py, worklist_messages.py and effort.json then pass to J1 and then to R1, one writer at a time; D1 and X1 run beside R1
Owns: agent/plans/PLAN-stop-hook-store-status.md, agent/plans/PLAN-stop-hook-retro-20261117.md, .claude/hooks/stop/wl_storestatus.py, .claude/hooks/stop/wl_checks.py, .claude/hooks/stop/wl_judge.py, .claude/hooks/stop/worklist_messages.py, .claude/hooks/stop/worklist.py, .claude/hooks/stop/wl_effort.py, .claude/hooks/stop/wl_effort_tune.py, .claude/config/effort.json, .claude/rediacc_hooks/tests/test_wl_store_status.py, .claude/rediacc_hooks/tests/test_wl_roster.py, .claude/rediacc_hooks/tests/test_wl_judge_facts.py, .claude/rediacc_hooks/tests/test_wl_judge_effort.py, .claude/rediacc_hooks/tests/test_wl_judge_local_batch.py, .claude/rediacc_hooks/tests/test_wl_judge_receipt_inflight.py, .claude/rediacc_hooks/tests/test_wl_core_blocking.py, .claude/rediacc_hooks/tests/test_wl_remaining_bank.py, scripts/data/doc-registry.md, .ci/config/shards/quality-pytest.json, CLAUDE.md, docs/agent-reference/loop-prompt.md

## Context (measured 2026-11-17 and 2026-11-18)

- PLAN-stop-hook-retro-20261117.md measured the window: 49 of 103 judge blocks rested on omitted ids (agent/plans/PLAN-stop-hook-retro-20261117.md:58). 22 were answered with a full table, 17 replies made no work call, and the replies came to 144,613 characters (agent/plans/PLAN-stop-hook-retro-20261117.md:27).
- On 2026-11-18 the same check forced a status table of 20 to 30 rows to be re-typed on nearly every stop. The table was copied from data the hook already holds. A copy can drift from the store and proves nothing the store does not.

The roster check has three doors, and all three read the message:

1. **The judge's checklist.** It asks "Does the message list EVERY open task by id?" (.claude/hooks/stop/worklist_messages.py:2231-2234) and is fed `MISSING IDS` (.claude/hooks/stop/worklist_messages.py:3376-3383). `_judge_facts` computes that list as the tracked ids, store items and harness tasks, that the message does not name (.claude/hooks/stop/wl_checks.py:3297-3357). `render_facts` renders it (.claude/hooks/stop/wl_judge.py:1215-1241).
2. **The judge's `out-of-sync` basis.** It sits in the schema enum (.claude/hooks/stop/wl_judge.py:75) and in `REPORT_BASES` and `JUDGE_BASIS` (.claude/hooks/stop/wl_judge.py:1360-1369).
3. **The deterministic `out-of-sync` check.** It blocks when a message with a `## Remaining` heading omits a harness task id (.claude/hooks/stop/wl_checks.py:5937-5938 and :6144-6149, text at .claude/hooks/stop/worklist_messages.py:1153-1157). Its effort row is at .claude/config/effort.json:312-315, and the tuner promoted it on 2026-11-06 (.claude/config/effort.json:609-618).

The hook already holds every fact the message was asked to repeat:

- the fold, with each item's state, `upd`, `worker`, `worker_verified`, `lease_at` and `lastnote` (`_fold_events`, .claude/hooks/stop/wl_store.py:1095);
- live workers (`live_worker_ids`, .claude/hooks/stop/wl_liveness.py:295; the roster, .claude/hooks/stop/wl_roster.py:608);
- process verdicts (`worker_facts`, called at .claude/hooks/stop/wl_checks.py:4263);
- blockers (`waiting_on`, .claude/hooks/stop/wl_leasehelp.py:74);
- the 45/90/120 ladder (.claude/hooks/stop/wl_liveness.py:46-48, `ladder` at :685).

The ladder fires each blocking rung once per item stamp. After the 120-minute rung has fired, an item that stays quiet is not named again. That gap is real, and the freshness check in this plan closes it.

## Out of scope

- **`open-items` stays as it is.** It blocks on in-scope open work in hand (.claude/hooks/stop/wl_checks.py:4575-4593) and sits in the mission tier. An unstarted in-scope item is work, not a status question.
- **The FLOOR stays as it is** (.claude/hooks/stop/wl_floor.py:9-23): `ci-red`, `roster-dead`, `unread-reports`, `wake-timer` and the rest. No box edits wl_floor.py.
- **The ladder and process verification are kept.** `wl_liveness.ladder` and `wl_roster` are read by this plan and never edited.
- **`unstated`, `mislabelled` and `unconfirmed` keep their predicates.** They judge only lines that already name a harness task inside a `## Remaining` section (.claude/hooks/stop/wl_checks.py:5946-5973), so none of them demands that an id be named.

## Design

**D1. One pure module, `.claude/hooks/stop/wl_storestatus.py`.** It holds no I/O beyond what it is handed. It reads no environment variable, takes its thresholds from `wl_liveness`, and keeps its message text as module constants, the way `wl_judge.V_PHANTOM_GATE` does. That keeps the parallel boxes off worklist_messages.py. It has five functions:

- `snapshot(fold, session_id, now)` returns `{"at": [stamp, ns], "stop_at": epoch, "items": {id: [state, upd, worker, lease_at, note8]}}`. It covers every item this session owns in states ` `, `>` and `?`. `note8` is the first 8 hex of the sha1 of `lastnote`. `at` is the newest event's `event_order` key (.claude/hooks/stop/wl_store.py:957).
- `changes(prev, fold, session_id)` returns change rows. The kinds are: new item, ticked (now `x`), deferred (now `?`), reopened, leased (worker set or changed), unleased (worker cleared), note (`note8` moved) and retired (gone from the fold).
- `freshness(fold, session_id, prev, live, verdicts, roster_live, queued_ids, covered, now)` gives one class per owned open item. `covered` is the set of item ids that another check names this stop.
- `render_table(rows, cap)` renders the table.
- `render_changes(rows, cap)` renders the change summary.

**Why the snapshot is not a byte offset.** The request asked for the store's event offset. The store is one file per writer under agent/worklist/, folded in `(at, ns)` order, and `compact_store` rewrites files (.claude/hooks/stop/wl_store.py:1867). A byte offset into one file would therefore point at the wrong event after any compaction. The snapshot keeps the `(at, ns)` high-water mark, which survives compaction, plus a per-item digest. Compaction carries `upd` forward in its `add` events (.claude/hooks/stop/wl_store.py:1203), so a compacted store shows no phantom changes.

**D2. Freshness classes, first match wins.** A quiet item is one whose digest equals the snapshot.

| Class | Rule | Blocks |
|---|---|---|
| `moved` | not quiet: new or changed since the last stop | no |
| `live` | `[>]` whose worker is in `live_worker_ids` and verified: shell `confirmed` by `verify_background`, subagent LIVE in the roster, teammate transcript fresh | no |
| `waiting` | `waiting_on` is non-empty (BLOCKED_BY or plan wait), or a queue or `HOLD_FOR` lease (.claude/hooks/stop/wl_roster.py:57, :119), or an agent waiting on a shell it armed | no |
| `queued` | a plain `[ ]` outside the live PR scope (`classify_items` puts it in `queued`); the hook's own plan order holds it | no |
| `deferred` | `[?]`; its DEFAULT window and audit stay with the deferral checks | no |
| `quiet` | quiet, age since `upd` under `LADDER_RESOLVE_MIN` | no |
| `stale` | quiet, age at or past `LADDER_RESOLVE_MIN`, no live verified worker, no blocker | yes, as `wl-stale` |
| `orphaned` | `[>]` whose worker no oracle finds (not live, not lead-covered, not queue), quiet at or past `LADDER_INVESTIGATE_MIN` | yes, as `wl-stale` |

**No double block.** A `stale` or `orphaned` item that another check names this stop is listed in the table with that key and is left out of `wl-stale`. The covering keys are `open-items`, `roster-dead`, `roster-silent`, `ladder-investigate`, `ladder-resolve` and the ladder's gone and idle lists. In practice `wl-stale` names what the one-shot ladder has stopped naming. It fires on every stop while the item stays stale. No latch is needed, because each exit is an action the session can complete alone: advance the item and `--update` it, lease it to a live worker, add `BLOCKED_BY:#<id>` through `--update`, defer it with a DEFAULT, or `--tick` it with evidence.

**Harness tasks.** These are TaskCreate tasks, outside the store. They leave the freshness verdict, and the ladder keeps its `in_progress` task subjects (.claude/hooks/stop/wl_liveness.py:755-771).

**D3. The hook renders, the message does not.** `run_stop` works in this order:

1. It computes the snapshot, the changes and the freshness verdict once. This happens after the ladder (.claude/hooks/stop/wl_checks.py:4264), the classification (:3792) and the roster (:3841).
2. It writes the snapshot to `state_doc["store_snap"]` at the bookkeeping save (.claude/hooks/stop/wl_checks.py:4286), so a blocked stop and an allowed stop both advance it.
3. It shows the table in the `systemMessage`, which is the operator's channel, on three exits: the main block exit (.claude/hooks/stop/wl_checks.py:6590-6604), the judge-continue exit (:7144) and the allow exit (:7355).

The table has one row per owned open, in-flight or deferred item:

    #<id>  [>]  <worker> (live, verified)  12m  live     <latest note, 60 chars>

The columns are id, state, worker with its live and verified state (`live`, `suspect`, `gone`, `queue`, `lead` or `-`), minutes since the last update, freshness class, and the latest note.

- The table is capped at 40 rows. A cut table ends with a `+N more: worklist.py --status <me>` tail, so the cut is never silent.
- An allow with no owned open, in-flight or deferred item stays silent, as v18 ruled (.claude/hooks/stop/wl_checks.py:7351-7354).

The block `reason` does not get the table, so the model's context does not pay for it. It gets two things:

- one count line: `STORE STATUS: n open (a moved, b live, c waiting, d queued, e quiet, f stale)`, plus the `--status` pointer;
- the change summary, capped at 15 rows with the same `+N more` tail.

**D4. `worklist.py --status <me> [--since-last-stop]`.** It prints the same table and the same changes inside a turn.

- `--status <me>` alone dies today at the arity guard (.claude/hooks/stop/worklist.py:1774), so the bare form and the `--since-last-stop` form are free shapes. The new branch sits before that guard.
- `--status <me> all|<agent-id>` keeps the roster read (`status_verb`, .claude/hooks/stop/wl_roster.py:1889).
- The new form is read-only. It never advances the snapshot, so repeated calls within one turn share one baseline.
- There is no Stop event inside a turn, so worker liveness comes from `wl_roster.live_estimate` (.claude/hooks/stop/wl_roster.py:1733). A shell worker reads `unverified (no stop event)`, never `live`.
- With no snapshot (first stop, or a fresh session id after compaction), the output says so and lists every item as current.

**D5. The judge reads the verdict, not the message.**

1. `_judge_facts` drops `missing_ids` and gains two facts:
   - `freshness`: the class counts, plus `(id, age, why)` for each stale and orphaned item;
   - `changes`: the capped change rows.

   `tracked` stays, because `settle_batch_no_local` reads it (.claude/hooks/stop/wl_judge.py:1244).
2. `JUDGE_FACTS` replaces the `MISSING IDS` line with `STORE FRESHNESS` and `CHANGES SINCE LAST STOP`.
3. The first checklist bullet (.claude/hooks/stop/worklist_messages.py:2231-2234) is replaced by this text: "STORE FRESHNESS is the hook's verdict on every open item. Never ask the message to list, restate or table items. A turn that only waited, says so in one line and cites CHANGES SINCE LAST STOP, is a complete report. Judge only whether real work remains undone."
4. `out-of-sync` leaves the schema enum, `REPORT_BASES` and `JUDGE_BASIS`.
5. A new `settle_status_demand` joins the settle chain beside `settle_wait_only_continue` (.claude/hooks/stop/wl_judge.py:1415). It reads a `continue` as `stop` when its reason or order matches the tuner's status-table shape (`_STATUS`, .claude/hooks/stop/wl_effort_tune.py:400; the shape is at :416-421) and its order names no file, verb or open item. The judge's text then goes to the advisory queue. This is the backstop against prompt drift: the judge still sees the remaining list in its prompt.

**D6. The message contract.** The final message covers what changed this turn, decisions, operator questions and blockers. A turn that only waited says so in one line and cites the hook's change summary. `no-remaining` keeps its key and predicate (.claude/hooks/stop/wl_checks.py:6164-6176, banked by `report_items_sig`, .claude/hooks/stop/wl_store.py:2978). The text after its opening clause changes, so it no longer prints the remaining items or asks for a list. It asks for the D6 content and says the hook renders the table. The opening clause "your last message has no '## Remaining' section" is kept byte-identical, because five test files match on it. The deterministic `out-of-sync` producer is retired.

**D7. Effort table.**

- **`wl-stale` gets a new row**, `{"block": "smart", "advise": "low"}`, the level `open-items` holds (.claude/config/effort.json:96-99). The row is added in the same commit as its producer, because the effort-table rule refuses a produced key with no row (`table_problems`, .claude/hooks/stop/wl_effort.py:211; run by `check_plan_record.py --effort-table`, .ci/scripts/quality/check_plan_record.py:1575). The `plan-box-owed` row was added the same way in commit 82fd346db2. `wl-stale` goes in the mission tier of `PRIORITY_LADDER` (.claude/hooks/stop/wl_checks.py:2359) and is not always-tier.
- **The roster check's key, `out-of-sync`, is retired by a decision recorded first.** `worklist.py --effort-propose <me> out-of-sync off@<level> <evidence>` writes the decision row to agent/ledgers/effort-proposals.jsonl. The verb refuses evidence that cites none of that key's outcome rows by id or gives no count (`propose`, .claude/hooks/stop/wl_effort_tune.py:1014). The verb has no removal form (`_SPEC`, .claude/hooks/stop/wl_effort_tune.py:50). Once the producer is gone, the effort-table rule refuses the row and its `tuned` stamp (`tuned_problems`, .claude/hooks/stop/wl_effort_tune.py:498), so both leave in the producer's commit, and that commit cites the proposal row's id. No other row changes.

## Operator decision

- **DEFAULT (R1 as written):** retire `out-of-sync`, recording the proposal row first. **Alternative:** keep the producer and demote it to off through the tuner path (`--effort-propose`, a tuner run, then `--effort-answer accept`). The alternative leaves a check that still demands harness task ids whenever a message writes a `## Remaining` heading. The lead puts this choice to the operator in its next batched ask, before R1 starts.

## Boxes

Order: the module, then the verb and the hook wiring in parallel, then the judge, then the retirement with the docs beside it.

- [ ] S1 [writer] `wl_storestatus.py`: snapshot, change rows, freshness classes and the two renderers as pure functions (D1, D2)
    Owns: .claude/hooks/stop/wl_storestatus.py, .claude/rediacc_hooks/tests/test_wl_store_status.py, scripts/data/doc-registry.md, .ci/config/shards/quality-pytest.json
    Depends on: none.
    Needs: none
    Accept: `PYTHONPATH=.ci .ci/cache/toolchain/uv-tools/bin/pytest -q .claude/rediacc_hooks/tests/test_wl_store_status.py` exits 0. It has one case per change kind (new, ticked, deferred, reopened, leased, unleased, note, retired), each with a control where the same fold gives no row. It has one case per freshness class, with the boundary minute on each side of `LADDER_INVESTIGATE_MIN` and `LADDER_RESOLVE_MIN`. Two more cases: a fold rewritten by `compact_store` gives no change rows against the old snapshot, and an item in `covered` is listed and left out of the blocking set. A table and a change list over their caps end with the `+N more` tail. `npx tsx scripts/gen/gen-docs.ts` and `npm run check:ci-shard-manifest-coverage` exit 0 after `npx tsx scripts/gen/gen-docs.ts --write` and `npm run shard:place` place the two new files.
- [ ] S2 [writer] `worklist.py --status <me> [--since-last-stop]` prints the table and the changes since the last stop, read-only, with the roster read kept for `all` and an agent id (D4)
    Owns: .claude/hooks/stop/worklist.py, .claude/hooks/stop/worklist_messages.py, .claude/rediacc_hooks/tests/test_wl_roster.py
    Depends on: S1.
    Needs: none
    Accept: `PYTHONPATH=.ci .ci/cache/toolchain/uv-tools/bin/pytest -q .claude/rediacc_hooks/tests/test_wl_roster.py` exits 0 with these new cases:
    - the bare form prints one row per owned open item;
    - `--since-last-stop` prints only the rows changed against a planted snapshot, and prints the same output twice with the state file byte-identical after both calls;
    - with no snapshot the output says so and lists every item;
    - a shell worker reads `unverified (no stop event)`;
    - `--status <me> all` still answers the 20-minute ping exactly as before;
    - a wrong prefix is refused by the identity check.

    The usage line at .claude/hooks/stop/worklist_messages.py:1743 names both forms.
- [ ] S3 [writer] The Stop hook snapshots the store on every stop, shows the table in its systemMessage, puts the count line and the change summary in the block reason, and blocks `wl-stale` on stale or orphaned items no other check names (D2, D3, D7 first half)
    Owns: .claude/hooks/stop/wl_checks.py, .claude/hooks/stop/wl_storestatus.py, .claude/config/effort.json, .claude/rediacc_hooks/tests/test_wl_store_status.py
    Depends on: S1.
    Needs: none
    Accept: `PYTHONPATH=.ci .ci/cache/toolchain/uv-tools/bin/pytest -q .claude/rediacc_hooks/tests/test_wl_store_status.py` exits 0 with full-hook cases driven through `wlfix`:
    - **Pass:** a stop whose message names no id, with every owned item moved, live-leased, waiting or queued, is not blocked by `wl-stale`, and its systemMessage holds the table header and the change summary.
    - **Block:** one `[>]` item quiet past `LADDER_RESOLVE_MIN`, with no live worker, on a stop where the ladder's rung for it already fired at that stamp, blocks with `wl-stale` naming that item. Control: the same item with a live verified worker passes. Control: the same item with `BLOCKED_BY` on an open blocker passes.
    - **No double block:** an item that `roster-dead` names this stop is not named again by `wl-stale`.
    - **Snapshot:** a blocked stop advances `store_snap`, and the next stop lists only what moved in between.
    - **Silence:** an allow with no owned item stays silent.

    `python3 .ci/scripts/quality/check_plan_record.py --effort-table` and `python3 .claude/hooks/stop/test-always-tier.py` exit 0.
- [ ] J1 [writer] The judge reads STORE FRESHNESS and CHANGES SINCE LAST STOP: the MISSING IDS fact, its checklist rule and the `out-of-sync` basis are removed, and a continue that demands a status table is read as stop (D5)
    Owns: .claude/hooks/stop/wl_judge.py, .claude/hooks/stop/worklist_messages.py, .claude/hooks/stop/wl_checks.py, .claude/hooks/stop/wl_effort.py, .claude/hooks/stop/wl_effort_tune.py, .claude/rediacc_hooks/tests/test_wl_judge_facts.py, .claude/rediacc_hooks/tests/test_wl_judge_effort.py, .claude/rediacc_hooks/tests/test_wl_judge_local_batch.py, .claude/rediacc_hooks/tests/test_wl_judge_receipt_inflight.py
    Depends on: S2, S3.
    Needs: none
    Accept: `PYTHONPATH=.ci .ci/cache/toolchain/uv-tools/bin/pytest -q .claude/rediacc_hooks/tests/test_wl_judge_facts.py .claude/rediacc_hooks/tests/test_wl_judge_effort.py .claude/rediacc_hooks/tests/test_wl_judge_local_batch.py .claude/rediacc_hooks/tests/test_wl_judge_receipt_inflight.py` and `python3 .claude/hooks/stop/test-judge-schema.py` exit 0. The cases:
    - the stub-captured prompt holds `STORE FRESHNESS` and `CHANGES SINCE LAST STOP`, and holds neither `MISSING IDS` nor "by id";
    - `_judge_facts` returns no `missing_ids`, and `basis` no longer accepts `out-of-sync`;
    - a continue whose reason is "the message omits open items by id; restate the status table" is read as stop and queued. Control: a continue ordering a named file fix stands. Control: a continue ordering work on an open item stands;
    - the settle chain still applies `settle_by_effort` to `no-remaining`.

    The docstring at .claude/hooks/stop/wl_effort.py:5 and the `where` text at .claude/hooks/stop/wl_effort_tune.py:419 no longer name `out-of-sync`.
- [ ] R1 [writer] Retire the `out-of-sync` producer and its effort row after a recorded proposal, and reword `no-remaining` to the D6 contract with its opening clause unchanged (D6, D7 second half)
    Owns: .claude/hooks/stop/wl_checks.py, .claude/hooks/stop/worklist_messages.py, .claude/config/effort.json, .claude/rediacc_hooks/tests/test_wl_core_blocking.py, .claude/rediacc_hooks/tests/test_wl_remaining_bank.py
    Depends on: J1.
    Needs: none
    Accept: the proposal row for `out-of-sync` reads back through `worklist.py --effort-propose <me>` (listing mode), and the commit cites its id. Then:
    - `PYTHONPATH=.ci .ci/cache/toolchain/uv-tools/bin/pytest -q .claude/rediacc_hooks/tests/test_wl_core_blocking.py .claude/rediacc_hooks/tests/test_wl_remaining_bank.py .claude/rediacc_hooks/tests/test_wl_ci_queue_and_mail.py .claude/rediacc_hooks/tests/test_wl_agent_docs_and_focus.py .claude/rediacc_hooks/tests/test_wl_continuity_surface.py` exits 0;
    - the case at .claude/rediacc_hooks/tests/test_wl_core_blocking.py:173 is inverted: an omitted task id no longer blocks. Its control: a missing `## Remaining` heading on a changed item set still blocks with `no-remaining`, whose text lists no item;
    - `python3 .ci/scripts/quality/check_plan_record.py --effort-table` exits 0, and `out-of-sync` appears in neither `checks` nor `tuned`.
- [ ] D1 [writer] CLAUDE.md and the loop prompt describe the D6 message contract and the hook-rendered table, in place of "base the `## Remaining` section on that guide" and "naming every open task by id"
    Owns: CLAUDE.md, docs/agent-reference/loop-prompt.md
    Depends on: J1.
    Needs: none
    Accept: CLAUDE.md:64-65 and docs/agent-reference/loop-prompt.md:30 name `worklist.py --status <me>` and the D6 contract. `grep -n "every open task by id" CLAUDE.md docs/agent-reference/loop-prompt.md` prints nothing. CLAUDE.md:102-103 (what may appear under `## Remaining`) is unchanged.
- [ ] X1 [lead] Record in PLAN-stop-hook-retro-20261117.md that J1 replaces R20261117.1, keeping the box line byte-identical
    Owns: agent/plans/PLAN-stop-hook-retro-20261117.md
    Depends on: J1.
    Needs: none
    Accept: an indented `(corrected 2026-11-18 ...)` line under R20261117.1 names this plan's J1 and the removed MISSING IDS fact. `npm run check:ci-plan-boxes` exits 0 with that box's signature unchanged. The box closes through `worklist.py --plan-tick` with evidence citing J1's commit and the passing test_wl_judge_facts.py run.
- [ ] V1 [lead] One gate pass on the finished tree: hook integrity, every stop-hook suite, the effort table and the plan citations
    Owns: agent/plans/PLAN-stop-hook-store-status.md
    Depends on: R1, D1, X1.
    Needs: none
    Accept: these all exit 0:
    - `npm run check:ci-hook-integrity`;
    - `for t in .claude/hooks/stop/test-*.py; do python3 "$t" || exit 1; done`;
    - `PYTHONPATH=.ci .ci/cache/toolchain/uv-tools/bin/pytest -q .claude/rediacc_hooks/tests`;
    - `python3 .ci/scripts/quality/check_plan_record.py --effort-table`;
    - `npm run check:ci-plan-citations`;
    - `npm run check:ci-worklist-env-registry`.

    `grep -rn "MISSING IDS" .claude/hooks/stop/*.py` prints nothing.
- [ ] M1 [live] A real lead session on this checkout, over 20 judged stops after V1: no message carries a status table, and no judge continue rests on omitted ids
    Depends on: V1.
    Needs: none
    Accept: the tick evidence holds:
    - one systemMessage with the rendered table and its change summary;
    - one passed stop whose message names no id, with every open item fresh or live-leased;
    - one `wl-stale` block naming a planted stale item, cleared the next stop by its `--update`;
    - a count over the judge log of those 20 stops showing zero continues that match the status-table shape at .claude/hooks/stop/wl_effort_tune.py:400.
