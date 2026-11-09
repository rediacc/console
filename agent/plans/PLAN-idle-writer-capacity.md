# PLAN: the Stop hook names ready `[writer]` boxes when writer slots sit free

Status: approved -- operator rulings ASKED 2026-11-09 via AskUserQuestion: (R1) build both the ceiling fix and an IDLE CAPACITY block; (R2) the block names the ready boxes and the spawn command, no auto-spawn; (R3) only boxes explicitly tagged `[writer]` count as writer-ready; (R4) per-box Depends-on when stated: a box with its own `Depends on:` line is judged by that line, a plan-level edge gates only the boxes that state none, no schema change
Depends-On: no-dep -- the turbo picker, the roster, the box parser and the plan graph it reads all exist; this plan changes how they are combined
Owner: d778be9d
First-Seen: 2026-11-09
Updated: 2026-11-09
Priority: P1 -- writer slots sat idle for hours on 2026-11-09 while four writer-ready boxes waited, and the operator had to ask by hand
Concurrency: parallel -- the files are the turbo ceiling in plan_gate.py, one new Stop-hook module, one arm in wl_checks.py, one message and one effort key; no other live plan owns them
Live-Proof: none -- Stop-hook tooling only: `surfaces.owns_surfaces` over this Owns list returns no surface, so no live receipt is owed; ruling #11c34df3 (the operator request behind the surface map, closed with its answers)
Owns: agent/plans/PLAN-idle-writer-capacity.md, agent/plans/QUEUE.md, .claude/rediacc_hooks/plan_gate.py, .claude/hooks/stop/wl_boxready.py, .claude/hooks/stop/wl_plandeps.py, .claude/hooks/stop/wl_checks.py, .claude/hooks/stop/worklist_messages.py, .claude/config/effort.json, .claude/rediacc_hooks/tests/test_wl_boxready.py, .claude/rediacc_hooks/tests/test_plan_gate_ceiling.py, .claude/rediacc_hooks/tests/test_wl_plandeps_box_edges.py

## Context

On 2026-11-09 the Stop hook printed "no queued plan is eligible for a free writer slot" for hours while PLAN-enterprise-isolation.md had `[writer]` boxes (S2, C1, C2, K2) a writer could take, with 17 of 25 writer slots free. Four causes, read from the code:

1. The turbo ceiling. `next_turbo` in .claude/rediacc_hooks/plan_gate.py counts every in-set plan with an open box against `plan_concurrency` (5). The branch's in-set plans had only live, operator or post-merge boxes left, so the free slots came to `5 - 5 = 0`, and `pr_scope_line` in .claude/hooks/stop/wl_checks.py printed `PR_SCOPE_TURBO_NONE`.
2. The startable test. `writer_startable` knows the `Lead:` and `Operator:` first words and the `lead-only` and `operator-only` words, and none of the bracket tags plans use: `[live]`, `[operator window]`, `[hostinger rollout]`, `[fleet]`, `[live, post-merge]`. `wl_planenforce.after_merge` exists, and the ceiling never asks it.
3. The plan-level edge. A plan's `Depends-On:` blocks the dependent plan whole (`Graph.roots_with_tasks` and `item_deps` in .claude/hooks/stop/wl_plandeps.py, and `pr_plan_set` in plan_gate.py), even for a box whose own `Depends on:` line is resolved. And a prerequisite whose remaining boxes are all live work holds a dependent's code boxes, although no line of that live work is code they build on: the enterprise plan waited on PLAN-product-domain-rename.md, whose nine open boxes are all `[live]`, and on PLAN-website-routing-and-mail.md#M3, a live mail check.
4. No check fires on "free writer slots and ready writer boxes". The cap-saturated wait (`wl_roster.cap_saturated_wait`) covers only the full-cap case.

## Design

**D1 The box tag grammar, one home.** .claude/hooks/stop/wl_boxready.py owns the tag read: the first bracketed tag after a box's id (`S2 [writer] ...`, `V1 [live] ...`), split into lowercase words. A box is writer-tagged when a word is `writer`. It is non-writer when a word is one of `live`, `operator`, `lead`, `hostinger`, `fleet`, `ops`, `drill`, `deadline`, `bench`, `local` and none is `writer`. It is post-merge when a word is `post-merge` or its own `Depends on:` clause names a merge (`wl_planenforce.AFTER_MERGE`). plan_gate.py imports this grammar rather than keeping a second one.

**D2 The ceiling counts writer work (I1).** `writer_startable` is False for a box that is non-writer or post-merge, besides the lead and operator markers it already knows. An untagged box stays startable, so an older plan with code boxes and no tags still counts and is still picked. `next_turbo` counts an in-set plan against `plan_concurrency` only when `writer_startable` holds for its text; a plan whose open boxes are all live, operator or post-merge holds no slot.

**D3 Per-box Depends-on (I4, ruling R4).** wl_plandeps.py reads a box's own `Depends on:` clause (box line and continuation lines, up to the first `.`, `;` or `(`): `none`, same-plan box ids (`S2`), ranges (`SC5-SC9`), and plan or task tokens (`PLAN-x.md`, `PLAN-x.md#T3`); a merge phrase is D1's post-merge, not a ref. `Graph.box_blockers(rel, block)` returns the unresolved refs. A box that states a line is judged by that line alone, strictly: a same-plan id or a task token needs its box ticked with evidence (`task_verdict`), a plan token needs the plan finished, and an id that resolves to nothing blocks. A box that states none is judged by the plan-level edges, and the caller may pass a predicate that clears a LIVE plan-level edge. `item_deps` lets a linked item through when its box states a line and every ref resolves; otherwise its verdict is unchanged.

**D4 The ready set (I2, ruling R3).** `wl_boxready.ready_boxes` walks the `## Promoted` entries of agent/plans/QUEUE.md (or the live PR's plan set with turbo off) and keeps an open box when all of these hold: the box is writer-tagged and not post-merge; the plan is not held and has no `Writers: none` header; `box_blockers` is empty, where a plan-level edge is cleared for a writer box when the prerequisite's remaining open boxes, or the one box a task edge names, are all non-writer or post-merge (a writer box builds on the prerequisite's code, and code is writer work; an untagged open box of the prerequisite still holds it, failing closed); no open, deferred or leased worklist item of any owner names the plan and the box (its sig or id), since such a box is somebody's work already and the open-item checks cover it; and its `Owns:` line overlaps neither the Owns of a box in flight (a leased item naming it) nor the header Owns of another plan a live writer serves, nor a box already chosen. Signatures come from `wl_planrec.open_boxes`. The read is cached per plan path, mtime and size for the life of the process.

**D5 The IDLE CAPACITY block (I3, rulings R1 and R2).** A new arm in wl_checks.py after TURBO NEXT, under the key `idle-capacity`, fires when the loop governs, the roster is readable, free writer slots (`writer_cap` minus live writers) are at least one, and the ready set holds at least one box. It stands down in the babysit and merge phases, and like TURBO NEXT it rides the advisory queue when a bug, a red CI or the merge offer outranks it. The plans TURBO NEXT named this stop are left out and each takes one free slot, so one pick never silences the other idle slots. A subject latch (the listed `PLAN#sig` set, 30 minutes) keeps an unchanged list from holding every stop. It names each box as `PLAN-x.md#<sig>  <raw box line>`, then one `/writers-now <plan>` line per plan, and how to take a box off the list (track it as an item). It never spawns. `.claude/config/effort.json` registers the key (block at `smart`, advise from `low`), and TURBO_KEEPS keeps it under the PR-loop profile.

## Boxes

- [ ] I1 [writer] The ceiling: `writer_startable` recognises the D1 tags and post-merge boxes, and `next_turbo` counts only in-set plans with a writer-startable, pre-merge open box. Accept: `PYTHONPATH=.claude .ci/cache/toolchain/uv-tools/bin/pytest -q .claude/rediacc_hooks/tests/test_plan_gate_ceiling.py .claude/rediacc_hooks/tests/test_plan_gate.py` rc 0, the 2026-11-09 fixture (5 in-set plans with live-only boxes, `plan_concurrency: 5`, a Promoted plan with an untagged code box) red before the change and a non-empty pick after.
- [ ] I2 [writer] .claude/hooks/stop/wl_boxready.py: the D1 grammar and `ready_boxes` per D4. Accept: `PYTHONPATH=.claude .ci/cache/toolchain/uv-tools/bin/pytest -q .claude/rediacc_hooks/tests/test_wl_boxready.py` rc 0, with controls for each exclusion (untagged, live, post-merge, held, tracked, Owns overlap, unresolved own line, live-only prerequisite cleared, untagged prerequisite box holding).
- [ ] I3 [writer] The IDLE CAPACITY arm and message per D5, the effort key and the TURBO_KEEPS entry. Accept: test_wl_boxready.py's arm tests rc 0 (fires on N ≥ 1 ready and ≥ 1 free slot, silent on 0 of either, silent in a phase, a TURBO NEXT pick taking its slot and its boxes without silencing the rest), and the effort-table rule `python3 .ci/scripts/quality/check_plan_record.py --effort-table` rc 0.
- [ ] I4 [writer] Per-box Depends-on in wl_plandeps.py per D3, with `item_deps` honouring a resolved own line. Accept: `PYTHONPATH=.claude .ci/cache/toolchain/uv-tools/bin/pytest -q .claude/rediacc_hooks/tests/test_wl_plandeps_box_edges.py` rc 0 and `python3 .claude/hooks/stop/test-plandeps.py` rc 0.
- [ ] I5 [writer] A real run: the ceiling and the IDLE block computed by the real functions against the current tree and roster, with the output quoted here. Accept: the output, read with the live writers' Owns in force.

## Real run (2026-11-09T09:43Z, the main checkout, session d778be9d)

The real functions over the current tree, the worklist store and `wl_planconc.live_plans` (the writer count there is the plan holders' count, a lower bound of the roster's), read with /tmp/idlecap/realrun.py:

```
in-set plans: 12; writer_startable True for backup-program, cloudflare-proxy, proxy-cd-six-targets, backup-restore-path; False for sandbox-tenant-separation and gpu-device-grants (live-only) and the six finished ones
next_turbo picks: []   (4 startable in-set plans + 1 live plan = plan_concurrency 5)
ready_boxes: 11 ready, 8 skipped (0.15 s)
  skipped as tracked: enterprise S2 #623937fa, C1, C2 #827e8676, K2 #872e789f; repo-docker-storage-prune R7, production-key-only N5, detached-jobs J18
  skipped as waiting: free-license F2 on PLAN-production-key-only.md (its N5 [writer] box is open)
IDLE CAPACITY: 24 free writer slot(s) of 25, and 11 ready `[writer]` box(es):
  PLAN-backup-restore-path.md#094664ee R7; PLAN-enterprise-isolation.md #b2fa5c1a S3, #bf97a640 S4, #17a0e356 A1, #2636f3ec G1, #8dc87613 L1; this plan's I1-I5
  /writers-now PLAN-backup-restore-path.md, /writers-now PLAN-enterprise-isolation.md, /writers-now PLAN-idle-writer-capacity.md
```

An earlier run the same hour, before PLAN-backup-restore-path.md joined the PR's set, showed the ceiling fix alone: four startable in-set plans counted where six had, and `next_turbo` named PLAN-backup-restore-path.md, which the old ceiling (`5 - 6`) never could. Enterprise S3 and S4 are named while S2 is in flight because neither states a `Depends on:` line; under ruling R4 the plan says so on the box (`Depends on: S2.`) when the order matters, and the same holds for backup-restore-path R7, whose text cites R4 and R5 without a line.
