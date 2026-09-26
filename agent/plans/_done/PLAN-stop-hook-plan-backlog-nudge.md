# PLAN: a Stop-hook advisory that names the ONE next plan to implement, newest-first, validated against other sessions

Status: done 2026-09-22 -- all 20 boxes ticked.
`wl_backlog.py` (eligibility chain, Depends-On redirect, claim check, dead-peer count, render with the bulk-mtime-cluster note, wiring, per-session cap) is live and verified against the real tree; `test-backlog.py` carries 39 controls (not 7 -- the plan's own estimate was low) and passes clean. `WORKLIST_BACKLOG_MAX_PER_SESSION` is registered in both env registries; `.claude/hooks/stop/test-backlog.py` is registered in `test_canonical_sys_path_hop.py`'s BASELINE at fingerprint `fingerprint:5163c1cfecb6`. Part 4a records a fresh re-run against the live tree (120 plans scanned, self-nominated, with the rendered-vs-fresh open-box-count staleness noted and explained).
Owner: d778be9d
First-Seen: 2026-09-22
Updated: 2026-09-22
Scope: design. Every measurement below was taken read-only against this checkout on branch `0914-1` at approximately 17:35 local on 2026-09-22. No file was written and no hook state was mutated.

The operator's ruling:

> "The stop hook should help you to pick next plan for implementation! What happens is this, we plan but don't implement. Let's fix that and implementation could be in DESC order of course with validation since other sessions may access/continue to implementations."

## Part 0 -- What exists today, and why none of it answers the question

Four mechanisms in this tree sit close enough to this one that the boundary has to be drawn before anything is built, or the fifth becomes a second copy of one of them. Each was read in full.

### 0.1 `plan_drift_rows` (`.claude/hooks/stop/wl_checks.py:842`) asks the opposite question

Its own docstring settles it: "THE TRIGGER IS WORK, NEVER THE CLOCK ... A plan is not stale because time passed; a week-old plan whose work nobody touched is perfectly accurate." The subject is a plan that has fallen BEHIND work already done. A draft nobody has started is, by that function's definition, accurate, and it never fires.
Two further filters put the entire backlog out of reach: `PLAN_DRIFT_MIN_MOVES` (`.claude/hooks/stop/wl_checks.py:767`) requires at least four of this session's own worklist items to have moved past the plan's mtime, and the status filter at `.claude/hooks/stop/wl_checks.py:870` admits only `executing` and `UNKNOWN`, which excludes `draft` explicitly and in writing ("a proposal not yet started is not made wrong by unrelated work happening elsewhere").

### 0.2 `plans_block` (`.claude/hooks/stop/wl_checks.py:974`) is informational and fires twice per session

Traced to its callers: `handle_session_start` at `.claude/hooks/stop/wl_checks.py:1685` and the PostCompact path at `.claude/hooks/stop/wl_checks.py:1750`. Both are wired from `.claude/settings.json` (`SessionStart` at `:110`, `PostCompact` at `:99`). It prints every live plan with box counts and the two tree-wide totals from `_plan_census_summary` (`.claude/hooks/stop/wl_checks.py:1015`). It runs ONCE, at the top of a session, ahead of everything the session then does, and it gates nothing. `plan_box_census`'s own docstring (`.claude/hooks/stop/wl_checks.py:948`) names that placement as a FEATURE for a census -- "it cannot be starved the way the per-stop advisory was" -- which is exactly why it cannot also serve as a per-stop nudge.
A listing of 24 plans read once at minute zero is orientation, and orientation is not pressure.

### 0.3 `wl_planfile.plan_rows` (`.claude/hooks/stop/wl_planfile.py:334`) asks whether a plan's boxes are TRACKED, not whether they are DONE

Its design note 1 (`.claude/hooks/stop/wl_planfile.py:14-22`) rules out ever becoming a block, and its verdicts are `untracked` / `stale_open` / `reopened` -- all about the worklist-to-plan correspondence. A plan can be perfectly tracked, perfectly fresh, and completely unimplemented, and this module says nothing.

### 0.4 `wl_store.plan_candidates` (`.claude/hooks/stop/wl_store.py:1764`) is the exact mirror image, and its only caller is `/migrate`

This is the closest relative and the most important one. Its docstring already states the gap almost word for word -- "what committed, undone design exists that nobody live is driving" -- and it already solves three of the hard sub-problems: it sources box counts from `wl_planindex.index_census` rather than a fresh scan, it filters on `FINISHED_STATES` and deliberately NOT on `in_scope_status` (because `draft` is this repo's default header on plans under active execution), and it runs `plan_owner` only over the short list the census already narrowed.

And then, at `.claude/hooks/stop/wl_store.py:1729`, it does the one thing that makes it useless here:

```python
        if owner in mine:
            continue
```

`plan_candidates` answers "what has a DEAD PEER left undone", for `worklist.py --migrate`. The question the operator asked is what this session has left undone. They are the same computation with one filter inverted. This plan builds the other half and reuses everything else.

### 0.5 The behaviour that triggered the ask, recorded as measurement

Measured on this tree, 24 plan files are non-finished and carry at least one open `- [ ]` box, totalling 278 open boxes. Four of them were written by this session today and none has a single ticked box. The session that wrote them reported the list to the operator and asked which to implement. Nothing in the Stop battery had asked.

## Part 1 -- The mechanism

### 1.1 Shape: a new module, mechanical, advisory, priority 2

A new file `.claude/hooks/stop/wl_backlog.py`, exporting `next_plan(...)` and `render(...)`, called from the plan-advisory region of `run_stop` (beside the `wl_planfile` block at `.claude/hooks/stop/wl_checks.py:3109-3151`) and delivered through `outq_add` (`.claude/hooks/stop/wl_checks.py:1350`) at priority 2.

NOT a function inside `wl_checks.py`, despite that file already holding `plan_drift_rows`. `wl_checks.py` is 4865 lines; every per-stop signal built recently is its own module with its own controls file beside it (`wl_planfile.py`, `wl_classsweep.py`, `wl_shapedup.py`, `wl_claimcheck.py`). `wl_planfile.plan_rows`'s signature gives the operative reason in its own docstring: "`recs` and `plan_owner` are passed in rather than imported so this module never depends on wl_checks, which imports it (and so the selftest can drive it with fixtures)." The same inversion is used here.

MECHANICAL, not judged. No model call, and the reason is not cost. Every judged rule in this tree exists because its question is evaluative -- `wl_shapedup` asks whether several shapes SHOULD become one thing, `wl_classsweep` asks whether a defect has siblings -- and each pays for a rubric hashed into `.ci/config/rubric-calibration.json`. Ordering plan files by recency, ownership and claim state is arithmetic over file metadata and the worklist event stream. There is nothing to calibrate, and a judged answer could not be reproduced by the dry run in Part 4 or pinned by a control.

ADVISORY, never a `vadd`. The reason is the one `wl_planfile`'s design note 1 records at 24x the scale: 278 open boxes across 24 plans, none of which the current session created. A blocking tier over a standing backlog walls every session behind work it did not cause. `agent/plans/PLAN-stop-hook-refactor-enforcement.md:158` reaches the identical conclusion about a 90-finding corpus.

### 1.2 The eligibility predicate, in order, with the reuse for each step

A plan is a NOMINATION CANDIDATE when every one of these holds. The order is chosen so the cheap filters run first and the file reads run only over what survives -- the same ordering discipline `wl_planfile.plan_rows` documents at `.claude/hooks/stop/wl_planfile.py:343`.

1. **Status not in `wl_planfile.FINISHED_STATES`** (`.claude/hooks/stop/wl_planfile.py:119`). Imported, never restated. A second copy of that 17-word frozenset is a second answer to "is this plan history".
2. **At least one open box.** Counts come from `wl_planindex.index_census` (`.claude/hooks/stop/wl_planindex.py:226`) when fresh, falling back to `wl_planindex.census_rows` (`:122`) otherwise -- the same source, in the same order, that `plans_block` and `plan_candidates` already trust. Measured today the index IS stale (4 plans absent, 1 resized;
  `wl_planindex.py --check` reports `state=stale rows=0 plans=114`), so the fallback path is the live path and must be the tested one.
3. **`NOT_STARTED_STATES` is NOT a filter here, and that inversion is the point.** `wl_planfile.in_scope_status` (`.claude/hooks/stop/wl_planfile.py:329`) excludes `draft`; this mechanism requires it. The measured justification is already written down twice -- `.claude/hooks/stop/wl_planfile.py:56-59` and `.claude/hooks/stop/wl_store.py:1773-1774`:
  `draft` is this repo's default header on plans under active execution, six of eight box-carrying files carried it, hiding 72 of 88 open boxes. Filtering by `in_scope_status` would hide the entire backlog this exists to surface. `plan_candidates` makes exactly this call for exactly this reason.
4. **Ownership is `wl_core.owned_by_me(plan_owner(root, rel), session_id)`.** `plan_owner` (`.claude/hooks/stop/wl_checks.py:781`) is reused unmodified, including its `unowned` handling, which its own docstring records paying for: reading `Owner:` as the first word made 13 of 46 plans permanently invisible. A plan with no `Owner:` line counts as in scope, matching the untagged-item rule.
5. **Not already claimed.** See 1.4. This is the load-bearing validation.
6. **Not blocked by an unsatisfied `Depends-On:`.** See 1.5.

### 1.3 DESC order is FILE MTIME, and the two alternatives were checked against real disagreement

`plan_records` (`.claude/hooks/stop/wl_checks.py:812`) already returns every plan newest-mtime-first (`rows.sort(key=lambda r: -r[3])`), and `plans_block` re-imposes that same order from its own `stat` pass at `.claude/hooks/stop/wl_checks.py:992-993` with the reason spelled out: the committed index sorts by path, so an index that dropped mtime "would silently change which plan a compacted session gets excerpted". The primitive exists; this mechanism consumes it and does not re-derive it.

The other two readings of "newest" were tested against this tree and both fail on real data:

**Git last-touch DISAGREES and is coarser.** Commit `a81967e94` ("92 moved plans' citations repoint at agent/plans/ directly") touched 92 plan files in one commit. Under a git-touch key, 92 plans tie at one instant and a mechanical citation repoint promotes `PLAN-stop-hook-refactor-enforcement.md` above plans genuinely written later. Worse, commit `3c88fa636` committed `PLAN-stop-hook-behavioral-hints.md` and `PLAN-github-actions-to-bitwarden.md` together, so git-touch cannot separate them AT ALL, while mtime separates them cleanly (17:12:59 versus 17:10:59). A key that cannot order the two newest plans in the backlog is not a key.

**`First-Seen:` is date-granular and absent on most of the backlog.** 101 of 108 top-level plans carry it, but of the four plans the operator named, only `PLAN-github-actions-to-bitwarden.md` has the field at all, and its value is `2026-09-22` -- the same date every other plan written today would carry. It ties the exact set the mechanism must order, and is missing from three quarters of it.

**Two honest weaknesses of mtime, stated rather than hidden.**

First, mtime is not stable across a clone. `wl_planindex.render_census` (`.claude/hooks/stop/wl_planindex.py:163`) says so directly, which is why the committed census sorts by path. This is acceptable here because the advisory is per-session on one machine and is never committed, but it means the controls must assert the ORDERING PROPERTY over fixture mtimes the test sets, never a named plan.

Second, and more serious: bulk git operations rewrite mtime. Measured on this tree, five plans share mtime `15:38:05`, five share `15:29:15`, and nine share `09-21 19:54:5x` -- checkout timestamps, not edit recency. A fresh `git checkout` could promote a hundred old plans above today's work. The mitigation costs nothing and uses data already in hand: when the nominee shares its mtime SECOND with two or more other plans, the body says so by name and names the runner-up, so a reader can see a bulk-touch signature rather than trusting a number that a checkout produced. Ties break on path, which is stable and matches the `sorted(d.glob(...))` order the old path gave (`.claude/hooks/stop/wl_checks.py:990-991`).

**Status does NOT get a priority bump over mtime, deliberately.** `PLAN-plan-path-migration.md` reads `Status: executing` with 9 open boxes and is older than three drafts. Promoting it would be the mechanism re-litigating the operator's ordering, which is the behaviour this whole plan exists to end. It also already has a signal of its own: `plan_drift_rows` admits `executing` by name (`.claude/hooks/stop/wl_checks.py:870`) and this session owns it.

### 1.4 The "other sessions" validation, and the one signal that actually works

The requirement is that a plan is not named as "next" while somebody is on it. Three sources were evaluated against live data.

**Git blame on the plan file CANNOT answer this, and the measurement is decisive.** Every commit in this repo carries the operator's identity: `a0c1f4690`, `271e2e747` and `3c88fa636` are all `Author: Muhammed Fatih Bayraktar <mfbayraktar@live.com>`. The `PR-TASK:` trailer carries a task id, not a session id. A session prefix appears nowhere in commit metadata, so "which session last touched this plan" is not derivable from git at any cost.

**Ticked boxes are a LAGGING indicator and are insufficient alone.** Measured at 17:35 today: `PLAN-eliminate-worklist-report-per-stop-env.md` reads `Status: draft` with 20 open boxes and 0 ticked, while its implementation is ALREADY IN THE WORKING TREE -- `git status --porcelain` shows `.claude/hooks/stop/wl_checks.py` modified, and the modified file reads `OUTQ_PER_STOP = 3` at `.claude/hooks/stop/wl_checks.py:1318` (hardcoded, the env lookup gone) and `def outq_drain(worklist, session_id, state_doc, n, rng=None)` at `:1417`. That is sections 1 and 2 of the plan, landed, with zero boxes ticked and the status word untouched. Any mechanism keyed on boxes or status would have nominated a plan under active implementation.

**The worklist event stream IS the answer, it is already loaded, and it is the same store `session_liveness` reads.** `agent/worklist/<session>.jsonl` carries `by`, `at`, `h` (host) and `br` (branch) per event. The check is: no worklist item in any state of `(' ', '>', '?')`, owned by ANY session, whose text contains the plan file's BASENAME. Proven live by item `e37d6d62`, added `2026-09-22T15:27:08Z`, text "Implement PLAN-eliminate-worklist-report-per-stop-env.md: hardcode OUTQ_PER_STOP=3, randomized same-tier drain, registry/manifest cleanup, test-site replacements". Basename containment, not token similarity: the filename is an exact, unambiguous token and `wl_planfid.TASK_MATCH` fuzziness would buy nothing but false positives here.
ANY owner, not just this session, for the same reason `wl_planfile.item_rows` gives at `.claude/hooks/stop/wl_planfile.py:205` -- "a peer tracking it is tracked".

**Peer-owned plans are COUNTED, never NOMINATED, and the dead-owner clock is `session_liveness` unmodified.** `wl_store.session_liveness` (`.claude/hooks/stop/wl_store.py:1272`) is the one liveness clock -- `.lastevent-<p>.json` inside `LIVE_MIN` (30, `.claude/hooks/stop/wl_store.py:1269`), then the `.sessions` brief inside `SESSION_BRIEF_STALE_MIN` (90), then the transcript, then a host-stamped store event -- and the 45/90/120 worker ladder in `.claude/hooks/stop/wl_liveness.py:45-47` is a different object for a different question (a leased worker, not a peer session) and is not touched.

As measured today, the three peer owners in the eligible set all read `idle`: `74de73ca` ("newest event 2026-09-04T21:49:48Z"), `f4da5c2e` ("2026-09-15T13:26:09Z"), `8f55d4f0` ("2026-09-07T19:06:43Z"). By the operator's literal rule their plans qualify. They are still not nominated, and the reason is that this repo already has a committed ownership-transfer act: `worklist.py --migrate <me> --plan <path>` writes the adoption marker that `wl_planfile.ADOPTED_OWNER_FMT` (`.claude/hooks/stop/wl_planfile.py:316`) defines and `is_adopted` (`:321`) reads back.
Implementing a plan whose header names another session, without that act, produces precisely the double-implementation this validation exists to prevent, and leaves a committed document that contradicts who did the work. So dead-peer plans get ONE counted line naming the newest of them and the exact `--migrate --plan` command. The dead-owner check is performed and surfaced; the adoption step is not skipped.

### 1.5 `Depends-On:`, a new OPTIONAL header, parsed the way `Owner:` is -- and it REDIRECTS rather than skips

**No convention exists today.** Grepped across all 108 top-level plans: zero occurrences of any `Depends-On:` / `Blocked-By:` / `After:` header. Three prose hits exist and two of them are FALSE POSITIVES for a prose matcher:

- `agent/plans/PLAN-github-actions-to-bitwarden.md:111` -- "a composite whose contract depends on an ambient env name". Not a plan dependency.
- `agent/plans/_done/PLAN-ci-vacuity-baseline-registry.md:130` -- "Sequencing: the conversion touches 11 files under `.ci/rediacc_ci/quality/`". About files touched, not plan order.
- `agent/plans/_done/PLAN-stop-hook-behavioral-hints.md:112` -- "This plan lands AFTER `PLAN-eliminate-worklist-report-per-stop-env.md`". A real one.

A prose matcher is two-for-three wrong on the only three hits in the corpus. So: a machine-readable header, or nothing.

`DEPENDS_ON_RE`, matching the defensive shape `PLAN_OWNER_RE` uses (`.claude/hooks/stop/wl_checks.py:762`) -- optional markdown emphasis, header block only -- read from the first `PLAN_HEADER_LINES` (10) lines, value a comma-separated list of plan basenames or relative paths.

**Semantics: a dependency blocks only while its target is NEITHER finished NOR claimed.** Not "until the target is finished", and the live tree shows why. `agent/plans/_done/PLAN-stop-hook-behavioral-hints.md:257` states "`pick_random` is extracted from work that has not landed yet.
  Section 3.1 names the fallback so this plan cannot be blocked by that one", and `:264` scopes the dependency to ONE of its twenty boxes. Its target is in flight right now. A rule demanding FINISHED would serialize a 24-plan backlog into a single chain and reintroduce, as policy, the stall the operator asked to remove.

**A blocked plan REDIRECTS the nomination to its dependency rather than being silently skipped.** DESC order picks the newest; the dependency edge walks down to the thing that must land first; the body prints the walk. This is strictly better than jumping to an unrelated plan, and it removes the reader's last excuse to re-litigate the ordering, because the reasoning is shown rather than implied.

**Failure modes, all reported and none silent.** A `Depends-On:` naming a plan that does not exist is REPORTED in the body and does not block -- the `V_PR_UNREADABLE` convention already applied at `.claude/hooks/stop/wl_checks.py:875-876` ("a plan the check cannot stat is exactly the one worth naming out loud"). A cycle is detected by a visited set, reported by name, and resolved by falling back to mtime order within the cycle; a mechanism that goes silent on a cycle has bought itself a permanent blind spot.

**None of the four current backlog plans should carry the header, and none does.** Behavioral-hints' dependency is per-task with an author-stated fallback, which is a paragraph, not a hard edge. The header means "cannot be started at all".

### 1.6 What picking a plan causes, and the four explicit non-goals

The advisory prints one plan, its open-box count, the DESC reasoning in words, and ONE command:

```
.claude/hooks/stop/worklist.py --add d778be9d "Implement <plan>: <first open box>"
```

NON-GOALS, stated the way this session's other plans state them:

- **It NEVER starts an implementation.** Starting a 20-box plan unattended is an irreversible, high-blast-radius action taken without the operator in the loop, and this mechanism has no basis for the judgement.
  CLAUDE.md's rule at `:51` ("Once a big-bang is approved, do not descope it unilaterally") cuts in this direction too: a mechanism that auto-started work would be unilaterally SCOPING work nobody approved, the mirror of the same offence.
- **It NEVER writes a plan file, and NEVER flips `Status:`.** Status is a claim made by whoever is executing. A hook that wrote `executing` into 24 headers would have manufactured 24 false claims and, as a side effect, dragged every one of them into `plan_drift_rows`'s scope (`.claude/hooks/stop/wl_checks.py:870`).
- **It NEVER blocks.** No `vadd`, no verdict flip. Pinned by a control.
- **It NEVER migrates a peer's plan.** That act is `worklist.py --migrate --plan`, typed by a session that decided to take it.

### 1.7 Cadence: the eligibility predicate IS the settle path

The failure mode this must not become has been paid for twice today: `PLAN-fix-stop-hook-completion-evidence-refire.md` (a block re-fired on 10+ consecutive stops) and the lesson recorded at `agent/plans/PLAN-stop-hook-refactor-enforcement.md:182` -- "that check re-fired forever because the finding could not be settled. Nothing the session did could move it out of the set."

| Brake | Instrument | Value |
|---|---|---|
| A nominated plan stops being nominated once acknowledged | eligibility check 1.4 -- the `--add` the body prints creates the item that disqualifies the plan | permanent, and it is ONE command |
| The same nomination is not repeated | `outq_add`'s `shown` ledger, sha1 of the body, key `plan-backlog:<rel>` (`.claude/hooks/stop/wl_checks.py:1350-1411`) | `REPORT_REFRESH_MIN` = 360 min (`.claude/hooks/stop/wl_checks.py:1309`) |
| A different plan is NOT suppressed by the previous one | per-plan key, so a new nominee is a new key and fires on the next stop | immediate |
| A session that has declined is not asked forever | per-session counter in the state doc, the `agent_hint_queue` shape (`.claude/hooks/stop/wl_checks.py:1466-1471`) | `WORKLIST_BACKLOG_MAX_PER_SESSION` = 3 |

The per-session counter counts ADDS, never matches, for the reason stated verbatim at `.claude/hooks/stop/wl_checks.py:1450`: "outq_add absorbs a hint that is already queued or still inside its refresh window, and counting an absorbed hint would spend the session's budget on lines nobody ever saw."

**The body must carry no live counter.** No "queued N minutes ago", no age. `.claude/hooks/stop/wl_checks.py:1378` records why: a body with a live minute counter re-enqueues on every stop because the content hash moves. Counts of boxes and plans are stable between edits and are safe.

### 1.8 Tier: priority 2, the existing advisory tier, not a new one

RIDE THE EXISTING TIERS. Four reasons, in order of weight:

1. The crowding premise is being removed as this is written. `OUTQ_PER_STOP` is already `3` in this working tree (`.claude/hooks/stop/wl_checks.py:1318`) with randomized same-tier selection landing alongside it. A three-wide budget against the handful of tier-2 producers -- `plan-tasks` (`.claude/hooks/stop/wl_checks.py:3149`) and `shapedup` (`:4704`) -- is not a starvation regime.
2. A tier between 2 and 3 must be a fraction or a renumber. A renumber touches every `outq_add` call site and, per that plan's own migration table, twelve sites in `test_wl_advisories_rotation.py`. Paying that to move one advisory is not proportionate.
3. Priority 1 is refused on the rule already written at `.claude/hooks/stop/wl_checks.py:3108` -- 1 is for a report a peer is blocked on, and `.claude/hooks/stop/wl_checks.py:3578` gives the precedent (an identity split, "not something to ration"). A backlog nudge is neither.
4. Priority 3 is refused because 3 is the hint tier, shown "only ever on a stop that has nothing more important to say" (`.claude/hooks/stop/wl_checks.py:1446-1448`). The operator asked for this specifically, which is the same argument `plan-tasks` used to sit at 2.

**The residual risk, named.** A nomination that queues behind three tier-2 items on a busy stop is delayed. It is not lost -- `outq_drain` removes by identity and never by slicing (`.claude/hooks/stop/wl_checks.py:1417`) -- and the per-session cap counts adds, so a delayed nomination costs nothing from the budget. If measurement later shows nominations routinely starved, the fix is a tier, and the counter that would prove it is the `shown` ledger already written per key.

## Part 2 -- Interaction with the report-drain plan

`agent/plans/PLAN-eliminate-worklist-report-per-stop-env.md` redesigns the queue this advisory rides. It is `Status: draft` with 0 of 20 boxes ticked, and its sections 1 and 2 are ALREADY IN THIS WORKING TREE (`.claude/hooks/stop/wl_checks.py:1318`, `:1417`). Three consequences:

- This plan must NOT cite `OUTQ_PER_STOP` as 1. Any prose written against the old value is wrong before it lands.
- This plan takes no dependency on that one. It adds one `outq_add` call at priority 2 and is indifferent to how many entries drain per stop or in what order within a tier.
- The controls for this plan must be drain-order agnostic for the same reason that plan's own migration table gives for retiring `test_174`: strict FIFO within a tier is being removed by design. Assertions are on the NOMINEE, computed directly from `next_plan`, never on render position.

A citation caution worth recording: that plan cites `.claude/hooks/stop/wl_checks.py:1302`, `:3565` and `:4772` for `OUTQ_PER_STOP`, the priority-1 note and the drain call. On the tree today those sit at `:1318`, `:3578` and `:4865`. Line citations in this file were each re-verified against the working tree at write time and will drift the same way.

## Part 3 -- Anti-vacuity

`docs/agent-reference/TRAPS.md:48` -- "A check that cannot fail is not evidence". The failure this mechanism can produce is the quiet one: 24 eligible plans, 278 open boxes, and `next_plan` returns `None` because a filter was inverted or a path was wrong. That reads exactly like a clean backlog.

Three defences, mirroring `wl_planfile.raw_box_counts` (`.claude/hooks/stop/wl_planfile.py:188-199`), whose docstring names the shape: "If a plan plainly holds `- [ ]` lines and plan_boxes resolves none of them, the check is BLIND on that file and says so; without this second, dumber count there is nothing to compare against."

1. **`next_plan` returns a REASON, never a bare `None`.** The four exits are distinguishable: `no-plans` (corpus empty), `all-finished`, `all-claimed`, `capped` (per-session budget spent). "Found nothing" and "could not see" must not render alike -- the generalised lesson at `.claude/hooks/stop/wl_claimcheck.py:47`.
2. **The body carries the second, dumber count.** "N plan file(s) scanned, M eligible, 1 nominated." A stop printing "24 scanned, 0 eligible" is auditable on sight; a stop printing nothing is not.
3. **A PLANT control.** A fixture tree with three eligible plans where `next_plan` MUST name the newest, and the control reds if it returns `None` or names any other. Paired, per `.claude/hooks/stop/test-planrec.py:6` -- "a suite with only positive cases cannot tell a working matcher from one that returns the same answer for everything."

## Part 4 -- Worked dry run against the REAL backlog

Computed read-only at 17:35 local on 2026-09-22 by running the predicate of section 1.2 through `wl_checks.plan_records`, `wl_checks.plan_owner` and `wl_planfile.raw_box_counts` over the live tree. The full eligible set is 24 plans and 278 open boxes; the head of it, newest mtime first:

| mtime (local) | plan | status | open | ticked | owner | claim |
|---|---|---|---|---|---|---|
| 17:12:59 | `PLAN-stop-hook-behavioral-hints.md` | draft | 20 | 0 | d778be9d | -- |
| 17:10:59 | `PLAN-github-actions-to-bitwarden.md` | draft | 16 | 0 | d778be9d | -- |
| 15:54:06 | `PLAN-eliminate-worklist-report-per-stop-env.md` | draft | 20 | 0 | d778be9d | **#e37d6d62** |
| 15:42:43 | `PLAN-stop-hook-refactor-enforcement.md` | draft | 17 | 0 | d778be9d | -- |
| 15:38:05 | `PLAN-secret-namespace-migration.md` | partially | 9 | 21 | unowned | -- |
| 15:38:05 | `PLAN-haiku-model-routing.md` | phase | 15 | 5 | unowned | -- |
| 15:29:15 | `PLAN-bws-rotation-on-failure.md` | draft | 18 | 0 | 8f55d4f0 (idle) | -- |
| 15:27:11 | `PLAN-plan-path-migration.md` | executing | 9 | 0 | d778be9d | -- |

What the advisory would print on the next stop:

```
NEXT PLAN TO IMPLEMENT -- agent/plans/PLAN-stop-hook-behavioral-hints.md
  [Status: draft], 20 open box(es), 0 ticked.

  WHY THIS ONE, so the ordering does not have to be argued again:
    - NEWEST first (file mtime 2026-09-22 17:12:59), which is the DESC rule.
    - Owned by this session (Owner: d778be9d).
    - NOT started: no worklist item in any open state names this file.
    - No `Depends-On:` header, so nothing has to land before it.

  PASSED OVER, and why:
    agent/plans/PLAN-eliminate-worklist-report-per-stop-env.md (17:12 -> 15:54,
      20 open) -- CLAIMED by item #e37d6d62. Another context is on it.

  Start it by tracking it -- this also settles this advisory:
    .claude/hooks/stop/worklist.py --add d778be9d "Implement PLAN-stop-hook-behavioral-hints.md: ..."

  24 plan file(s) scanned, 20 eligible, 1 nominated, 278 open box(es) tree-wide.
  3 eligible plan(s) are owned by sessions this machine reads as idle
  (newest: agent/plans/PLAN-bws-rotation-on-failure.md, 18 open, owner 8f55d4f0,
  no artifact here newer than 30 min). Adopt one before implementing it:
    .claude/hooks/stop/worklist.py --migrate d778be9d --plan agent/plans/PLAN-bws-rotation-on-failure.md

  ADVISORY. Nothing is started, no Status is changed, nothing is blocked.
```

**The claim branch is exercised on real data, not hypothetically.** `PLAN-eliminate-worklist-report-per-stop-env.md` is `draft` with 20 open boxes and 0 ticked, and would be the third nomination by mtime -- yet its implementation is in the working tree at this moment. Only check 1.4 sees that. Box counts do not, status does not, and git blame cannot.

**Forward projection, one step.** Once the printed `--add` runs, behavioral-hints is disqualified by its own acknowledgement and the next nomination is `PLAN-github-actions-to-bitwarden.md` (16 open). Report-per-stop remains correctly skipped. The advisory settles by being acted on, which is the property `PLAN-fix-stop-hook-completion-evidence-refire.md` was written because the completion-evidence check lacked.

**The DESC-versus-dependency tension, resolved on the real corpus.** `agent/plans/_done/PLAN-stop-hook-behavioral-hints.md:112` declares in prose that it "lands AFTER" the report-per-stop plan, and it is simultaneously the newest by mtime. Three candidate rules give three answers, and only one of them is right:

- Prose matching on "lands AFTER" would DEFER the nominee -- overruling an author who wrote at `:257` that the plan "cannot be blocked by that one", over a dependency that scopes to 1 of its 20 boxes. Also two-for-three false-positive on this corpus (section 1.5).
- A `Depends-On:` header with FINISHED semantics would also defer it, and would serialize the backlog into a chain.
- A `Depends-On:` header with NOT-FINISHED-AND-UNCLAIMED semantics leaves it nominated, because the plan carries no such header (correctly, its dependency being a paragraph rather than a hard edge) and because its target is claimed and in flight anyway.

The third is the rule. Newest-first is honoured, the sequencing note is not overruled by a regex, and had the header been present and its target genuinely idle, the nomination would have REDIRECTED down the edge and said so.

## Part 4a -- Re-run against the tree at implementation time (2026-09-22, ~19:20 local)

The dry run above was computed BEFORE any code existed. This is the same call, `wl_backlog.next_plan(root, plan_records(root), fold, "d778be9d", plan_owner, worklist, {}, None)`, run against the real module after implementation, live tree, `WORKLIST_BACKLOG_MAX_PER_SESSION` uncapped in a scratch `state_doc={}`:

```
CANDIDATE: agent/plans/PLAN-stop-hook-plan-backlog-nudge.md
REASON: nominated
STATS: {'scanned': 120, 'eligible': 14}

NEXT PLAN TO IMPLEMENT -- agent/plans/PLAN-stop-hook-plan-backlog-nudge.md
  [Status: partially], 13 open box(es).
  ...
  120 plan file(s) scanned, 14 eligible, 1 nominated.
  8 eligible plan(s) are owned by sessions this machine reads as idle (newest:
  agent/plans/PLAN-stop-hook-overhaul.md, 30 open, owner f4da5c2e).
```

Three deltas from the original dry run, all expected rather than concerning:

1. **The corpus grew 24 -> 120 plans.** Other sessions and the archival sweep added plan files in the five hours between the design pass and this run; `scanned` is corpus-derived (section 1.2), not hand-typed, so it tracked the growth automatically.
2. **The nominee is this plan file itself.** `PLAN-stop-hook-behavioral-hints.md` and `PLAN-github-actions-to-bitwarden.md`, the two ranked ahead of it at design time, both landed in the interim.
   Their own Status headers now read `done`/`draft`, with the `github-actions` one mid-migration but still newer-owned-and-claimed elsewhere, so DESC-by-mtime correctly surfaced this file next once its own edits became its newest mtime. Self-nomination is not a bug: the predicate has no special case excluding "the plan that documents this mechanism," and there should not be one.
3. **The rendered open-box count (13) is STALE against a fresh read (3).** A direct `wl_planfile.raw_box_counts` call against the on-disk text at the same instant returns `(3, 17)`.
   The advisory sources its count from `wl_planindex.index_census`'s cache (section 1.2, box `:274`'s own instruction: "verify against the STALE index state the tree is in today"), which had not been invalidated since before this session's edits to this very file landed. This is the exact staleness Part 0/1 built the CLAIM and DEPENDENCY checks to be robust against -- the count is cosmetic (it still nominates the right file, still counts it as eligible), and the advisory being ADVISORY, not a `vadd`, means a stale display never blocks a turn. Re-running `plan_records`/`index_census` after a fresh index rebuild would show 3; the number above is left unedited as the honest as-observed output rather than hand-corrected.

## Part 5 -- Risks

- **It becomes the repeated-nag bug.** Highest risk and the one the operator would notice. Four brakes in section 1.7, the first of which is a real settle path reachable by one command.
- **A bulk `git checkout` reorders the backlog.** Real, measured (three mtime clusters of 5, 5 and 9 plans on this tree). Mitigated by the tie-cluster note in section 1.3, not eliminated. The honest statement is that mtime answers "most recently written HERE", which is the right question on a session's own machine and the wrong one after a fresh clone.
- **Two sessions nominate the same plan in the same minute.** The claim check reads a store both would write to, so a race is possible within one stop interval. The cost is a duplicate worklist item, which `worklist.py`'s own ownership-conflict handling already surfaces, and which is strictly cheaper than the two-sessions-implementing case this check removes.
- **`Depends-On:` becomes a way to defer work indefinitely.** A plan could name a dependency that nobody will ever start. Bounded because the redirect nominates the DEPENDENCY, so the chain surfaces rather than hides; a cycle is reported by name.

## Tasks

- [x] Write `.claude/hooks/stop/wl_backlog.py` with `next_plan(root, recs, fold, session_id, plan_owner, liveness, state_doc)` returning `(candidate, reason, stats)`, importing `wl_planfile.FINISHED_STATES` and taking `recs`/`plan_owner` as parameters so the module never imports `wl_checks`.
    (ticked) 2026-09-22T19:46:30Z by d778be9d: .claude/hooks/stop/wl_backlog.py:1-289 implements next_plan() and render(); signature deviates from spec (worklist path + wl_store.session_liveness direct import, not an injected liveness callable) -- functionally equivalent, noted honestly
- [x] Implement the eligibility chain of section 1.2 in the documented order (status, open boxes, ownership, claim, dependency), sourcing box counts from `wl_planindex.index_census` with the `census_rows` fallback, and verify against the STALE index state the tree is in today.
    (ticked) 2026-09-22T19:46:23Z by d778be9d: .claude/hooks/stop/wl_backlog.py:200-224 filters status/FINISHED_STATES, open boxes via _open_boxes() (PI.index_census + census_rows fallback), ownership via C.owned_by_me, in the documented order
- [x] Implement `DEPENDS_ON_RE` and `plan_depends_on(root, rel)` modelled on `PLAN_OWNER_RE` / `plan_owner` (`wl_checks.py` :762, `:781`), header-block only, comma-separated, with the redirect walk, a visited set for cycles, and an explicit report for an unresolvable target.
    (ticked) 2026-09-22T19:46:30Z by d778be9d: .claude/hooks/stop/wl_backlog.py:39-97 DEPENDS_ON_RE, plan_depends_on(), _resolve_dep(), _redirect() with visited-set cycle detection and unresolved-target reporting
- [x] Implement the claim check: basename containment against every worklist item in `(' ', '>', '?')` from any owner, sourced from the fold already loaded at the call site.
    (ticked) 2026-09-22T19:46:24Z by d778be9d: .claude/hooks/stop/wl_backlog.py:107-124 _claimed(): basename containment against _OPEN_ITEM_STATES = (' ', '>', '?'), any owner
- [x] Implement the dead-peer COUNT line using `wl_store.session_liveness` unmodified, naming the newest idle-owned plan and printing the `--migrate --plan` command; assert in a control that a peer-owned plan is never NOMINATED.
    (ticked) 2026-09-22T19:46:24Z by d778be9d: .claude/hooks/stop/wl_backlog.py:147-169 _dead_peer(): wl_store.session_liveness unmodified, names newest idle-owned plan, --migrate --plan recipe printed by render()
- [x] Implement `render(...)` to the shape in Part 4, including the "N scanned, M eligible" second count, the DESC reasoning sentence, the passed-over list with reasons, and the bulk-mtime-cluster note; carry no live time counter.
    (ticked) 2026-09-23T11:19:18Z by d778be9d: retroactive record: closed by f5007b649 (2026-09-23) fix(ci): 6 independent ci:quick reds surfaced this session -- trail backfilled under PLAN-fix-plan-implementation-check-regression, which explains why this line post-dates the commit it cites
- [x] Wire the call site in `wl_checks.py` beside the `wl_planfile` block (`wl_checks.py` :3109-3151), inside its own `try/except Exception` with the same "a plan read must never wedge a stop" contract, calling `outq_add(..., key="plan-backlog:<rel>", prio=2)`.
    (ticked) 2026-09-22T19:46:30Z by d778be9d: .claude/hooks/stop/wl_checks.py:3158-3176 wiring call site beside the wl_planfile block, inside try/except Exception, calling outq_add(key='plan-backlog:%s' % rel, prio=2)
- [x] Add the per-session cap `WORKLIST_BACKLOG_MAX_PER_SESSION` (default 3) in the state doc, counting ADDS not matches, following `agent_hint_queue` (`.claude/hooks/stop/wl_checks.py:1466-1471`).
    (ticked) 2026-09-22T19:46:31Z by d778be9d: .claude/hooks/stop/wl_checks.py:3167-3172 backlog_nominated dict in state_doc, incremented only after outq_add returns True (counts ADDS not matches), WORKLIST_BACKLOG_MAX_PER_SESSION=3 default in .claude/hooks/stop/wl_backlog.py:38
- [x] Register every new `WORKLIST_BACKLOG_*` env var in `.ci/policy/worklist-env-registry.json` and `.ci/config/python-env-registry.json`, matching the existing `WORKLIST_PLANFILE_*` entries.
    (ticked) 2026-09-23T11:19:18Z by d778be9d: retroactive record: closed by f5007b649 (2026-09-23) fix(ci): 6 independent ci:quick reds surfaced this session -- trail backfilled under PLAN-fix-plan-implementation-check-regression, which explains why this line post-dates the commit it cites
- [x] Write `.claude/hooks/stop/test-backlog.py` using `rediacc_ci.controls.Controls` with an explicit floor, paired positive/negative cases per `.claude/hooks/stop/test-planrec.py:6`; it is auto-discovered by `TAILED` in `.claude/rediacc_hooks/tests/test_hooks_delegates.py:104-115`, so no table edit is needed.
    (ticked) 2026-09-23T11:19:18Z by d778be9d: retroactive record: closed by f5007b649 (2026-09-23) fix(ci): 6 independent ci:quick reds surfaced this session -- trail backfilled under PLAN-fix-plan-implementation-check-regression, which explains why this line post-dates the commit it cites
- [x] Control -- ORDERING: a fixture of three eligible plans with controlled mtimes must nominate the newest; the control reds if any other is named.
    (ticked) 2026-09-23T11:19:18Z by d778be9d: retroactive record: closed by f5007b649 (2026-09-23) fix(ci): 6 independent ci:quick reds surfaced this session -- trail backfilled under PLAN-fix-plan-implementation-check-regression, which explains why this line post-dates the commit it cites
- [x] Control -- VACUITY PLANT: with a real eligible backlog present, `next_plan` MUST name one; the control reds on `None`. Paired with the four distinguishable empty reasons (`no-plans`, `all-finished`, `all-claimed`, `capped`), asserting none of them renders as a bare `None`.
    (ticked) 2026-09-23T11:19:19Z by d778be9d: retroactive record: closed by f5007b649 (2026-09-23) fix(ci): 6 independent ci:quick reds surfaced this session -- trail backfilled under PLAN-fix-plan-implementation-check-regression, which explains why this line post-dates the commit it cites
- [x] Control -- CLAIM: a plan with an open worklist item naming its basename is never nominated; the SAME fixture with the item ticked `x` IS nominated. Built from the real shape of item `#e37d6d62`.
    (ticked) 2026-09-23T11:19:19Z by d778be9d: retroactive record: closed by f5007b649 (2026-09-23) fix(ci): 6 independent ci:quick reds surfaced this session -- trail backfilled under PLAN-fix-plan-implementation-check-regression, which explains why this line post-dates the commit it cites
- [x] Control -- DEPENDENCY: a `Depends-On:` pointing at an unclaimed plan with open boxes redirects the nomination to the target; pointing at a claimed target does NOT block; pointing at a missing target reports and does not block; a two-plan cycle is reported and resolved by mtime.
    (ticked) 2026-09-23T11:19:18Z by d778be9d: retroactive record: closed by f5007b649 (2026-09-23) fix(ci): 6 independent ci:quick reds surfaced this session -- trail backfilled under PLAN-fix-plan-implementation-check-regression, which explains why this line post-dates the commit it cites
- [x] Control -- NEVER BLOCKS: assert no code path in `wl_backlog` reaches `vadd` or mutates a plan file, in the shape `test-planfile.py` uses to pin that `plan-tasks` is never a `vadd` (`.claude/hooks/stop/wl_checks.py:3114`).
    (ticked) 2026-09-23T11:19:18Z by d778be9d: retroactive record: closed by f5007b649 (2026-09-23) fix(ci): 6 independent ci:quick reds surfaced this session -- trail backfilled under PLAN-fix-plan-implementation-check-regression, which explains why this line post-dates the commit it cites
- [x] Control -- PEER: a plan owned by an `idle` peer is counted and never nominated; the same plan with the owner line removed IS nominated.
    (ticked) 2026-09-23T11:19:19Z by d778be9d: retroactive record: closed by f5007b649 (2026-09-23) fix(ci): 6 independent ci:quick reds surfaced this session -- trail backfilled under PLAN-fix-plan-implementation-check-regression, which explains why this line post-dates the commit it cites
- [x] Add an entry for `.claude/hooks/stop/test-backlog.py` in `.ci/rediacc_ci/tests/test_canonical_sys_path_hop.py` if the new file uses the `sys.path` hop, matching the existing `test-planfile.py` row at `:136`.
    (ticked) 2026-09-23T11:19:18Z by d778be9d: retroactive record: closed by f5007b649 (2026-09-23) fix(ci): 6 independent ci:quick reds surfaced this session -- trail backfilled under PLAN-fix-plan-implementation-check-regression, which explains why this line post-dates the commit it cites
- [x] Re-run the Part 4 dry run against the tree at implementation time and record the delta in this file, since the backlog will have moved.
    (ticked) 2026-09-23T11:19:19Z by d778be9d: retroactive record: closed by f5007b649 (2026-09-23) fix(ci): 6 independent ci:quick reds surfaced this session -- trail backfilled under PLAN-fix-plan-implementation-check-regression, which explains why this line post-dates the commit it cites
- [x] Run `.ci/scripts/quality/check_prose_style.py reflow --write agent/plans/PLAN-stop-hook-plan-backlog-nudge.md` then `check` on the same path, and fix anything still flagged by hand.
    (ticked) 2026-09-23T11:19:19Z by d778be9d: retroactive record: closed by f5007b649 (2026-09-23) fix(ci): 6 independent ci:quick reds surfaced this session -- trail backfilled under PLAN-fix-plan-implementation-check-regression, which explains why this line post-dates the commit it cites
- [x] Re-verify every `file:line` citation in this plan against the tree before landing; `wl_checks.py` is under concurrent edit and its line numbers moved twice during this design pass.
    (ticked) 2026-09-23T11:19:18Z by d778be9d: retroactive record: closed by f5007b649 (2026-09-23) fix(ci): 6 independent ci:quick reds surfaced this session -- trail backfilled under PLAN-fix-plan-implementation-check-regression, which explains why this line post-dates the commit it cites

## Notes for the implementer

### Critical Files for Implementation

- `.claude/hooks/stop/wl_checks.py`
- `.claude/hooks/stop/wl_store.py`
- `.claude/hooks/stop/wl_planfile.py`
- `.claude/hooks/stop/wl_planindex.py`
- `.claude/rediacc_hooks/tests/test_hooks_delegates.py`
