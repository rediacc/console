# PLAN: Stop-hook retro, 2026-09-25 (band late, lead session d778be9d)

Status: ready
Depends-On: no-dep -- cites no other plan
First-Seen: 2026-09-25
Owner: d778be9d (adopted from retro ae06fedae89115ef2 20260925)
Updated: 2026-09-25

**Scope.** This retro covers lead transcript bytes 236722957 to 238604947. That runs from 2026-09-24T19:38:07Z to 2026-09-25T13:32:09Z. The session was active until 20:59Z, then waited for the operator's AskUserQuestion answer, which came at 13:30:52Z.

The blocklog has 8 blocked stops in this window, at 19:39:31, 19:43:53, 19:45:03, 19:47:31, 19:50:04, 19:52:22, 20:13:14 and 20:16:38:
- **Leading key:** open-items led 3, judge 3, plan-adopted 1 and agent-state 1.
- **Named only:** queue-slot 3, roster-unleased 1, roster-dead 1 and ladder-investigate 1.
- **Judge flags:** 3 continue, 3 sweep demands and 2 proof demands.

Other rows in the window:
- 1 hint proposal (19:44:47Z, roster-cap).
- 0 admissions.
- 2 refused `--tick` calls (#df2d733a at 19:47:39Z, #4f167b47 at 19:50:47Z).
- 9 non-blocking CAP-SATURATED WAIT stops (offsets 237673369, 237729185, 237848837, 237879097, 238106538, 238135203, 238157964, 238190773, 238227886).

**Line numbers** refer to the working tree at about 15:35Z on 2026-09-25. `wl_roster.py`, `wl_judge.py`, `wl_classsweep.py` and `wl_proofcheck.py` are still uncommitted, so every citation also names a function to re-anchor on.

**Held, and not re-proposed:**
- **R20260924.16 held.** The 19:39:31 open item was the phantom post-compact retro, closed at 19:39:50 (offset 236825328). Writer A's fix was ticked at 20:14:53 (238015915).
- **R20260924.7 held.** Retro writer B's interim "waiting on my background test run" at 20:40:04 (238187654) did not block.
- **The cap-saturated stand-down held.** Nine stops passed without a block while 4 of 4 slots were live.
- **R20260924.5 held.** Each queue-slot block named exactly 1 item for 1 free slot.
- **R20260924.21 held.** The #4f167b47 refusal cost 1 retry (237293810), and the retry with `:556` was accepted.
- **Legitimate blocks.** These blocks were right and are not frictions:
  - the 19:39:31 unleased writer, a716b17b, spawned without a lease;
  - the 20:13:14 roster-dead on #2a94fc77, whose worker finished at 20:12:33;
  - the 20:13:14 90-minute ladder on item 10, whose output had been quiet for 256m;
  - the stale STATE.md at 20:13:14.
- **Out of scope.** The session's own work-loop cron prompt named three workers that no longer existed. It fired 5 times (237686929, 237870994, 238127107, 238149048, 238202000) and cost 5 turns. It is a scheduled task, not a Stop-hook block, so the lead should recreate it with a generic prompt.

## Ranking by cost to the session

| Rank | Point | Count in this window | Turns lost | Already fixed by? |
|---|---|---|---|---|
| 1 | #1: the judge's fix-set carries a live writer's Bash-made edits | 2 judge blocks (19:47:31, 19:50:04), plus 1 sweep and 1 proof still owed on disk | 2 turns, 2 sweeps, 1 of them a 177-file proof demand | **R20260924.1 did not hold.** It subtracts only Edit/Write paths, and only while the writer is live |
| 2 | #2: discharge misses two answered demands | 2 demands still owed on disk (the baseline sweep and the locale proof); both re-fire at the next unsaturated fix stop | 0 so far, at least 1 predicted | **R20260924.18 gaps:** a broader `find` glob, and a structural proof by another tool |
| 3 | #3: queue-slot and lease expiry treat work blocked on another writer as startable | 1 block led (19:45:03). 2 of 3 queue-slot namings were overridden because of a blocker (#bea10927 at 19:39:31, #ecb07ba6 at 20:13:14) | 1 turn, plus 2 overrides | No. R20260924.5 orders by age only |
| 4 | #4: plan-adopted ignores box ids in item text | 1 block (19:52:22): 7 of 9 boxes shown as untracked while 4 items named them | 1 turn, 12 worklist calls | No |
| 5 | #5: a stopped writer holds a slot in the spawn guard only | 3 spawn refusals (19:40:09, 19:44:30, 19:52:58) against 2 "slot free" claims (19:39:31, 19:52:22) | about 3 turns, plus 8 calls to fix it | **R20260924.6 did not hold.** Fixed in-session by #b9d4dcb2, not yet committed |
| 6 | #6: a refused queue lease leaves an orphan item, which then gets duplicated | 1 block (20:16:38) | 1 turn | No |

---

## 1. The judge's fix-set carries a live writer's Bash-made edits (R20260924.1 did not hold)

**What happened.**
- **19:47:31 (236979728):** the judge demanded:
  - a sweep of "stub shadow driver pattern ... across .ci/rediacc_ci/core/ and .claude/oracles/";
  - a proof for a "bulk update across 177 files: ... oracle library, hook logic, config baselines".
- **19:50:04 (237038138):** the judge demanded a sweep of "Baseline configuration files becoming stale ...".
- **Neither was the lead's work.** Every commit in the fix range (cafcd9696 to 20fc068c5) together touches 152 unique files, and none of them is under `.claude/oracles` or a `*baseline*.json`. `git log -- .claude/oracles` shows no deletion commit.
- **Those paths were A3's uncommitted edits.** A3 is agent aee082fbda5047b70, whose transcript ends at 19:49:23:
  - `sed -i '/^TWIN = "/d'` over the guards, at 18:16:01;
  - a Python rewrite of `scripts/data/enumeration-vacuity-baseline.json`, at 18:40:48;
  - a Python rewrite of `.ci/config/prose-style-baseline.json`, at 18:41:43;
  - `git rm -r --cached .claude/oracles; rm -rf .claude/oracles`, at 18:43:26.
- **A3 was live at 19:47:31.** The lead's own reply at 19:47:46 (237028607) lists "A3" under Running.
- **The answers found nothing.** The lead's sweeps at 19:47:38 (237023567) and 19:50:12 (237081143) found 0 copies. The file lists show that neither class was the lead's to sweep.

**Root cause.**
- **Edit tools only.** `wl_roster.edit_paths` (`.claude/hooks/stop/wl_roster.py:781`) reads only `EDIT_TOOLS` = Edit/Write/MultiEdit/NotebookEdit (`:44`). A3 made 330 Bash calls against 78 Edits, and every edit named above went through Bash.
- **Finished writers are not subtracted.** `live_writer_paths` (`:808`) states "A FINISHED writer's edits are not subtracted, since they have landed". Uncommitted edits that the lead has not verified have not landed. A3 finished at 19:49:23, and the lead verified it at 19:57:55 (237644533).
- **The whole tree answers for a tick.** A tick-based unit's fix-set is the whole dirty tree (`wl_reggate.fixset_files`, `.claude/hooks/stop/wl_reggate.py:373`, status arm). The judge therefore picks a "class" from any file in the tree.

**Fix.**
1. **Bash writes count.** `edit_paths` also collects each writer's Bash-made writes:
   - the redirect targets from `shellscan.write_targets` (`.claude/rediacc_hooks/shellscan.py:1201`);
   - the path operands of `rm`, `git rm`, `git mv`, `mv`, `cp`, `sed -i`, `tee`, `truncate` and `install`;
   - the repo-path string literals inside a Python heredoc that opens a file for writing (`open(...,'w')`, `write_text`, `unlink`).

   Paths are joined to any `cd` in the same command. A directory operand covers every dirty file under it.
2. **Writer paths stay out until the tick.** A writer's paths stay subtracted while any item leased to it is not ticked.
3. **A tick answers for its own writers.** A tick-based unit's fix-set becomes the paths of that item's lease workers intersected with the dirty tree, under provenance `item-writers`. It falls back to the current `status-minus-live-writers` only when the item never had a worker lease.

## 2. Discharge misses two answered demands (R20260924.18 gaps)

**What happened.** The markers on disk still owe two answered demands (`/tmp/claude-worklist/.judge/classsweep-0a598f50c372.json`, `proofcheck-0a598f50c372.json`).

- **Baseline sweep.**
  - Demanded: `find .ci/config .ci/rediacc_ci -name '*-baseline.json' -type f`.
  - The lead ran `find .ci/config .ci/rediacc_ci scripts/data -name '*baseline*.json' -type f` at 19:50:12 (237081143), which is a superset of both the glob and the paths.
  - Replayed against the current code: `search_pattern` gives `'*-baseline.json'`, the pattern-in-command test is False and `near_literal` is False.
- **Locale proof.**
  - Owed: "Automatic translation key regeneration ... 16 locales", scope `packages/cli/src/i18n/locales/`.
  - At 19:44:02 (236903370) the lead diffed every `locales/*/cli.json` key by key against `HEAD~11` and printed "unexpected 0".
  - `_runs_proof_on` gives False, because it accepts only `shape[-_]cluster[-_]diff`.
- **The judge's next action was not a proof for JSON.** It said "run shape_cluster_diff on packages/cli/src/i18n/locales". `shape_cluster_diff` shapes lines, not keys (`.ci/scripts/quality/shape_cluster_diff.py`, SHAPES). The lead's key diff was the stronger proof.
- **For contrast, a demand that did discharge.** The CLI-handoff sweep, answered at 19:44:02, now passes `near_literal` (True in the replay). That part of R.18 holds.

**Root cause.**
- `near_literal` (`wl_classsweep.py:427`) requires one of the demand's own pattern alternatives as a substring. A broader `find -name` glob never contains the narrower one.
- `PROOF_TOOL_RE` (`wl_proofcheck.py:147`) names one tool, and that tool has no JSON shapes.

**Fix.**
- **Glob cover.** A `find` demand is discharged when the lead's `find -name|-iname` glob matches a sample of the demand's glob (each `*` or `?` replaced by `x`, then `fnmatch`) and the two share a path operand (`shares_path`, `:404`).
- **JSON mode.** `shape_cluster_diff` gains a JSON mode: for `.json` files it diffs the key-path sets (added, removed, and value-type changed) against `--rev`. The tool the judge orders is then the right proof for locale files, and `PROOF_TOOL_RE` stays narrow.

## 3. Queue-slot and lease expiry treat work blocked on another writer as startable

**What happened.**
- **19:39:31 (236801211):** queue-slot said "start #bea10927". The lead started another item because "A3 is editing those golden files" (236817060).
- **19:45:03 (236957436):** open-items blocked on the same #bea10927. Its queue lease had expired at 19:42Z while it still waited on A3. The lead renewed it with the note "blocked on A3" (236971520).
- **20:13:14 (237943695):** queue-slot named #ecb07ba6, the biome/TS7 wave. The lead did not start it because the wave "would edit package.json and biome.json while their wiring is still uncommitted" (237966414).
- **The third naming is covered.** #11fbc2a2 at 19:52:22 was overridden for priority, which the existing HOLD_FOR handles.

**Root cause.**
- `queue_start` (`wl_roster.py:612`) takes the K oldest `worker:queue` items with no waiting check. BLOCKED_BY is honoured only for state `' '` (`wl_roster.py:567`, `wl_store.py:1287`).
- An expired `[>]` queue lease fails closed into an open item (`wl_store.classify_items`, about line 1318) even when its blockers are open.
- Neither block message names `BLOCKED_BY:#<id>` as the remedy.

**Fix.**
- `queue_start` skips a queued item whose `LH.waiting_on` is non-empty and names the next one.
- An expired queue lease on such an item reads as `waiting`, not open.
- `V_QUEUE_SLOT` and the expired-lease line both carry: "waiting on another item? `--update <id> 'BLOCKED_BY:#<blocker>'`".

## 4. plan-adopted ignores box ids in item text

**What happened.**
- At 19:51:08 (237305780) the lead tracked R20260924.16 to .23 as 4 items: "R20260924.16+17 ...", "R20260924.18+19 ...", "R20260924.22 ..." and "R20260924.20+21+23 ...".
- At 19:52:22 (237346990) plan-adopted blocked with "9 box(es) are open and 7 of them have no live worklist item".
- The lead re-added 8 per-box items (237370552) and ticked the 4 grouped ones as superseded (237395261).

**Root cause.**
- `wl_planfile.match_item` (`.claude/hooks/stop/wl_planfile.py:248`) matches only by token containment at `TASK_MATCH`.
- An item that covers two or three boxes falls below 0.7 against each one.
- The box's own id, `**R20260924.16**`, is never used as a key.

**Fix.**
- Match on the id first: a box whose leading bold id appears in an item's text matches that item.
- `<prefix>.<a>+<b>[+<c>]` and `<prefix>.<a>-<b>` expand to each id they name.
- Token containment stays as the fallback.

## 5. A stopped writer holds a slot in the spawn guard only (R20260924.6 did not hold)

**What happened.**
- The babysitter a149262d8b6a1601f was TaskStop-ped at about 19:1xZ.
- Spawns were refused at 19:40:09 (236839404), 19:44:30 (236934739) and 19:52:58 (237385878), each listing it as a live writer.
- In the same window the Stop hook said "1 slot(s) free" at 19:39:31 and 19:52:22.
- The lead filed #b9d4dcb2 and the 19:44:47 hint. It then fixed the guard: `wl_roster.py:892-895` makes `transcript_waiting` count only when the agent's transcript moved after the event. The fix has a test at `test_wl_roster.py:941` and was ticked at 19:57:14 (237575152).

**What survives.** The fix is uncommitted: `git diff --stat` shows `wl_roster.py` +11 and `test_wl_roster.py` +34. The Stop roster (`roster()`, `:488`) and the spawn guard (`live_estimate`) are still two estimators, and nothing checks that they agree.

**Fix.**
- Commit #b9d4dcb2.
- Add a parity test: for the killed-agent, shell-waiter and fresh-spawn fixtures, `roster()`'s writers equal `live_writers_estimate`'s ids.

## 6. A refused queue lease leaves an orphan item, which then gets duplicated

**What happened.**
- At 20:14:53 (238015915) `--add` created #91224636. Its `--lease worker:queue` was refused: "worker:queue is only for writer work the cap forbids starting ..." (238020140).
- The refusal named no id, so the lead added the finding again at 20:15:41 as #48bc48b4 (238059776).
- open-items blocked on the orphan at 20:16:38 (238084407), and the lead ticked it as a duplicate (238100617).

**Root cause.**
- The refusal (`.claude/hooks/stop/worklist.py:1140`) does not name the item or say what state it is left in.
- `--add` never mentions an owned open item it nearly duplicates.

**Fix.**
- The refusal ends with "#<id> stays OPEN (not leased)".
- `--add` prints "similar open item: #<id>" when `wl_planfile.match_item` at `TASK_MATCH` finds an owned open item. This is a warning, not a refusal.

## Decisions (default applies unless the operator says otherwise)

1. **A finished writer's uncommitted edits stay out of the lead's fix-set until its item is ticked.**
   - DEFAULT: yes. `test_r1_inverse_a_finished_writers_edit_is_still_in_the_fixset` is rewritten to "a finished writer whose item is TICKED is in the fix-set".
   - WHY: at 19:50:04 A3 had finished 41s earlier, and its baseline edits were unverified and uncommitted.
   - HOW: the lease history (`worker:<id>` on the item) is the join key.
2. **Extracting Bash writes errs toward subtracting.**
   - DEFAULT: yes, with a directory operand covering its subtree.
   - WHY: a missed subtraction costs a blocked turn, while an extra one only defers the question to the writer's own tick, where it is asked on `item-writers`.
   - HOW: an adversarial test keeps a lead-only file in the same directory as one the writer edited.
3. **Proof for JSON.**
   - DEFAULT: add a JSON key-path mode to `shape_cluster_diff`, not a wider `PROOF_TOOL_RE`.
   - WHY: this keeps "one proof tool, run on the scope" and makes the ordered command correct.
   - HOW: `--json-keys` is chosen automatically for `.json` paths.
4. **Queue blockers.**
   - DEFAULT: explicit `BLOCKED_BY` only, with no inference from prose such as "sequenced after" or "blocked on".
   - WHY: a heuristic that skips a queued item hides work.
   - HOW: the block text names the remedy.
5. **Near-duplicate `--add`.**
   - DEFAULT: warn, never refuse.
   - WHY: the generous matcher has false positives, and a refused `--add` loses a finding.

## Sequencing

1. **R20260925.9 first.** It needs no code, and it clears the markers before the next unsaturated fix stop re-asks them.
2. **R20260925.1, .2 and .8 go to one writer.** All three touch `wl_roster.py`. Items .2 and .1 also touch `wl_reggate.py` and `wl_judge.py`.
3. **R20260925.5 goes after that writer, or to the same one.** It also touches `wl_roster.py`, plus `wl_store.py` and `worklist_messages.py`.
4. **Two independent writers can run in parallel:**
   - R20260925.3 and .4 (`wl_classsweep.py`, `shape_cluster_diff.py`);
   - R20260925.6 and .7 (`wl_planfile.py`, `worklist.py`).
5. **R20260925.10 last.** It runs alongside the still-open R20260924.15.

## Tasks

- [ ] **R20260925.1** `wl_roster.edit_paths` also collects each writer's Bash-made writes:
  - redirect targets from `shellscan.write_targets`;
  - operands of `rm`, `git rm`, `git mv`, `mv`, `cp`, `sed -i`, `tee`, `truncate` and `install`;
  - repo-path literals in a Python heredoc that writes or unlinks.

  Paths are cd-joined, and a directory operand covers its subtree. Replay A3's commands at 18:16:01, 18:40:48, 18:41:43 and 18:43:26 as fixtures: all four are subtracted, and a lead-only file in the same directory still draws the questions. Test: .claude/rediacc_hooks/tests/test_wl_judge_fixset_scope.py.
- [ ] **R20260925.2** A writer's paths stay subtracted while any item leased to it is un-ticked. A tick-based unit's fix-set is its lease workers' paths intersected with the dirty tree (provenance `item-writers`, text in `M.FIXSET_PROVENANCE`). Rewrite `test_r1_inverse_*` per Decision 1. Test: .claude/rediacc_hooks/tests/test_wl_judge_fixset_scope.py.
- [x] **R20260925.3** Sweep discharge accepts a covering `find` glob with a shared path operand. The fixture is the 19:50:04 marker against the 19:50:12 command. The inverse is a narrower glob, or a glob with no shared path, which stays owed. Test: .claude/rediacc_hooks/tests/test_wl_judge_fixset_scope.py.
  Done 2026-09-25: wl_classsweep.py:460 glob_covers, wired at :543; test_wl_judge_fixset_scope.py 29 passed (worklist #8e860847).
- [x] **R20260925.4** `shape_cluster_diff` gets a JSON key-path mode for `.json` files, with added, removed and type-changed keys per file, and exit 1 when a key is removed. A `shape_cluster_diff` run on `packages/cli/src/i18n/locales` discharges the locale proof demand. Test: .ci/rediacc_ci/tests/test_quality_shape_cluster_diff.py and .claude/rediacc_hooks/tests/test_wl_judge_fixset_scope.py.
  Done 2026-09-25: shape_cluster_diff.py:125 json_key_diff; test_quality_shape_cluster_diff.py 11 passed, --selftest 21 controls (worklist #1c96c876).
- [ ] **R20260925.5** `queue_start` skips queued items with open `BLOCKED_BY` blockers. An expired queue lease on such an item reads as `waiting`. `V_QUEUE_SLOT` and the expired-lease line name `BLOCKED_BY:#<id>`. Test: .claude/rediacc_hooks/tests/test_wl_roster.py and .claude/rediacc_hooks/tests/test_wl_leases.py.
- [ ] **R20260925.6** `wl_planfile.match_item` matches on the box id first, including the `+` and `-` shorthand. The fixture is the 4 grouped items of 19:51:08 against R20260924.16 to .23, where 0 of 8 may come out untracked. Test: .claude/hooks/stop/test-planfile.py.
- [ ] **R20260925.7** The `worker:queue` refusal names "#<id> stays OPEN (not leased)", and `--add` warns "similar open item: #<id>" on an owned near-duplicate. The fixture is the #91224636 and #48bc48b4 texts. Test: .claude/rediacc_hooks/tests/test_wl_leases.py.
- [ ] **R20260925.8** Commit #b9d4dcb2 (`wl_roster.py:890-898`, `test_wl_roster.py:941`). Add a parity test showing that `roster()` writers equal the `live_writers_estimate` ids for the killed-agent, waiter and fresh-spawn fixtures. Test: .claude/rediacc_hooks/tests/test_wl_roster.py.
- [x] **R20260925.9** With no code change, discharge the on-disk markers through the existing path:
  - run verbatim `find .ci/config .ci/rediacc_ci -name '*-baseline.json' -type f`;
  - run `.ci/scripts/quality/shape_cluster_diff.py --rev <A3 base sha> .ci/config .claude/rediacc_hooks .ci/rediacc_ci/core` for A3's commit before it lands;
  - confirm that `classsweep-0a598f50c372.json` and `proofcheck-0a598f50c372.json` no longer carry the baseline sweep or the 177-file proof.

  The locale proof clears with R20260925.4. Test: the marker files' contents, quoted in the tick.
  Done 2026-09-25: the sweep marker holds owed:null and a different demand; the proof demand expired past its 120-minute TTL (load_outstanding() is None); every owed command ran verbatim (worklist #fb1747dc).
- [ ] **R20260925.10** After R20260925.1 to .8 land, re-count this retro's six frictions on the next session's `.blocklog`, alongside R20260924.15, and record the counts in this plan. Test: .claude/hooks/context/test-context-bands.py (retro window) plus the blocklog rows cited.

### Critical Files for Implementation
- /home/developer/console/.claude/hooks/stop/wl_roster.py
- /home/developer/console/.claude/hooks/stop/wl_reggate.py
- /home/developer/console/.claude/hooks/stop/wl_classsweep.py
- /home/developer/console/.ci/scripts/quality/shape_cluster_diff.py
- /home/developer/console/.claude/hooks/stop/wl_planfile.py
