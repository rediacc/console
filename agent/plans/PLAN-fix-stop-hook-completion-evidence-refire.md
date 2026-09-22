# PLAN: stop-hook I7 evidence check scans the whole item history, not the closing tick's own note
Status: draft
First-Seen: 2026-09-22
Owner: d778be9d

## Why

The Stop hook has fired an identical "COMPLETION WITHOUT EVIDENCE" block for item `4954f598` (`agent/worklist/d778be9d.jsonl`) on at least 10 consecutive stops, regardless of what the session did in between. The tick that closed it does carry a real, resolving sha (`430b54ede`, in its own closing note) -- the check is wrong, not the session.

## Root cause (confirmed by direct execution against the live repo, not a fixture)

**Bug A -- wrong scope.** `wl_store._fold_events` (`.claude/hooks/stop/wl_store.py:923-953`, `kind == "state"`/`"lease"`) appends every lease/state note onto `rec["text"]` forever. Item `4954f598` accumulated ~40 lease notes into a 6,084-char blob. `_render_line` (`.claude/hooks/stop/wl_store.py:802-810`) renders that whole blob as `rec["line"]`; `Fold.lines()`
(`.claude/hooks/stop/wl_store.py:1010-1011`) hands it to `wl_reggate.fix_signals` (`.claude/hooks/stop/wl_reggate.py:364-427`), which passes it unmodified to `completion_evidence(root, line)` at `.claude/hooks/stop/wl_checks.py:2949`.

`completion_evidence`'s SHA-candidate scan (`.claude/hooks/stop/wl_checks.py:455-463`) checks only the 5 longest hex-shaped tokens in the text (by design, to dodge a different, previously-fixed poisoning case -- see the "Found live 2026-08-23" comment at `.claude/hooks/stop/wl_checks.py:452-454`). The accumulated blob also contains ~20 worker-id tokens (17-20 hex chars, e.g.
`af61cd805486b8e9f`) that are longer than the real 9-char commit sha `430b54ede` that closed the item. "Longest first" burns the whole 5-candidate budget on worker ids that are not git objects, and the real sha never gets tried:

```
top5 candidates: af61cd805486b8e9f, a6f203ba2d1dad4df, a3eb1f38776140810,
                 a2e744ce62808099b, aef4695176ce25a76   (all worker ids, none resolve)
completion_evidence(root, rec["line"])     -> False   (the bug)
completion_evidence(root, rec["lastnote"]) -> True    (rec["lastnote"] ==
    "430b54ede committed: check-go-deps.sh/release-age.sh/age-check.sh all deleted,
     112 pytest passing, all named gates green")
```

Verified live against `/home/developer/console/agent/worklist/d778be9d.jsonl`, `wl_reggate.fix_signals()` output for this exact tick, and the live marker at `/tmp/claude-worklist/home_developer_console.reggate-d778be9d`.

**Bug B (design, not a defect, but the reason it does not self-heal) -- no persistence on a blocked stop.** `run_stop` (`.claude/hooks/stop/wl_checks.py:2179`) gathers every static violation and, when any exist, exits at `if violations and not pause:` (`.claude/hooks/stop/wl_checks.py:4087`, via `C.emit()`->`sys.exit(0)`) before reaching the reggate settle/persist code
(`.claude/hooks/stop/wl_checks.py:4268` onward; writes `reg_state["fixsets"]`/`seen_ticks` at `:4438`/`:4496`). This is intentional and already documented: `.claude/rediacc_hooks/tests/test_wl_regression_gate.py:248` -- "The new tick line carries a real short sha as evidence, else I7 blocks before the reggate settle is ever reached." So a tick whose evidence is real but
undetectable by Bug A stays stuck: its tid never enters `seen_ticks`, so `fix_signals` rediscovers it as "new" every stop and recomputes the same failing check. Confirmed live: the marker has 97 correctly-persisted `seen_ticks` and 132 settled `fixsets` -- persistence works everywhere else; only this tick's tid (`5fe666f72866`) sits permanently outside that set because it has no
way to clear I7. No marker-path/session-id mismatch turned up (the marker path is already keyed on the truncated 8-char id, matching `me8`); the prior "marker never persists" theory is refuted by this file's own contents.

**The displayed message is also wrong, independent of Bug A.** `ev_ticks = [line[:150] for _tid, line in reg_new_ticks if not completion_evidence(root, line)]` (`.claude/hooks/stop/wl_checks.py:2949`) truncates the first 150 chars of the 6,084-char blob -- always the item's original `add`-event description, never the closing note roughly 6,000 chars later. The message names "the
line" as where the evidence belongs, but the reader is shown a slice that structurally cannot carry it.

## Fix shape (small, surgical -- confirmed sufficient, not forced)

1. `wl_reggate.mine_tick_ids` / `fix_signals` (`.claude/hooks/stop/wl_reggate.py:220-230`, `364-427`): iterate `fold.items` (full records) instead of `fold.lines()` (rendered strings only). Keep `_tick_id(rec["line"])` unchanged -- preserves the v10 upgrade-guard identity (tick_id must stay a hash of the full rendered line, per the module's own TICK_FLOOD comment).
   Add a per-tick evidence text = `rec.get("lastnote") or rec["line"]` (fallback covers markdown-origin items, which have no structured note and keep scanning the full line). Return it alongside the existing `(tid, line)` pair -- e.g. `(tid, line, evidence_text)`.
2. `.claude/hooks/stop/wl_checks.py:2949`: check `completion_evidence(root, evidence_text)`, not `completion_evidence(root, line)`.
   Display `wl_store.brief_text(rec, cap=150)` (existing helper at `.claude/hooks/stop/wl_store.py:813-827`, already built for "basetext + LATEST note" display elsewhere in this codebase) instead of `line[:150]`, so the shown snippet is the closing note, identifiable and evidence-bearing, not the original description's head.
3. `V_COMPLETION_TICKS` (`.claude/hooks/stop/worklist_messages.py:175`) wording stays otherwise correct ("put the evidence IN THE LINE") -- it becomes true once (2) ships.
   No copy change required beyond that, unless the displayed snippet's shape (brief_text's "base ... LATEST: note") needs a one-word tweak to read naturally; judge during implementation.
4. No change needed to `_tick_id`, `TICK_FLOOD` absorption, `tick_touches_code` (`.claude/hooks/stop/wl_reggate.py:257-265`, still scans the full line -- a different question, whether the fix touches code, not evidence), or the violations-block-before-reggate-settle ordering (`.claude/hooks/stop/wl_checks.py:4087` vs `:4268`) -- that ordering is deliberate (test_90 above).
   Once (1)/(2) land, a correctly-evaluated tick simply stops appearing in `ev_ticks`, so the very next clean stop flows through to the settle path and persists `seen_ticks` normally. No separate persistence fix is required.

Not addressed by this plan, flagged for a future one: I7 (`.claude/hooks/stop/wl_checks.py:2958-2971`) carries no defer/REBUT escape hatch, unlike nearly every other check in this hook. A future evidence-shape false negative slipping past (1)/(2) would still have no way to unstick short of a code fix. Worth a follow-up plan, not blocking this one.

## Tasks

- [ ] Change `wl_reggate.mine_tick_ids(lines, session_id)` to
      `mine_tick_ids(items, session_id)`, reading `rec["state"]`/`rec["owner"]` directly off
      each record instead of re-parsing `C.ITEM.match(rec["line"])`.
- [ ] Change `wl_reggate.fix_signals(root, lines, session_id, state)` to accept `fold.items`
      (or an explicit second `items` param alongside `lines` if a narrower diff is
      preferred), and have it return, per new tick, an evidence text derived from
      `rec.get("lastnote") or rec["line"]`. Update the docstring's "ticks stays (id, line)
      pairs" note (`.claude/hooks/stop/wl_reggate.py:426`) to describe the new shape.
- [ ] Update the `.claude/hooks/stop/wl_checks.py:2385` call site to unpack the new tuple shape.
- [ ] Update `.claude/hooks/stop/wl_checks.py:2949` to call `completion_evidence(root, evidence_text)` and to
      build `ev_ticks` from `S.brief_text(rec, cap=150)` (or equivalent) rather than
      `line[:150]`.
- [ ] Confirm `tick_touches_code` (`.claude/hooks/stop/wl_reggate.py:412-417`) still receives the full `line`
      (unchanged) -- it answers a different question (does the fix touch code) and must keep
      scanning the whole rendered text.
- [ ] Add a regression fixture reproducing the exact poisoning shape: an item with several
      `lease` events carrying long (17-20 char) hex worker-id-shaped notes, followed by a
      closing `state s="x"` event whose note carries a short, genuinely resolving sha.
      Recommended home: a new case in
      `.claude/rediacc_hooks/tests/test_wl_regression_gate.py` (alongside
      `test_90_ticks_are_the_uncommitted_tree_signal`, which already documents the "I7
      blocks before reggate settle" invariant this fix must not break), built by appending
      raw JSONL events to the fixture's worklist (not `wl.add_item`, which only writes a
      single markdown line and does not reproduce the accumulation). Assert:
        - CONTROL: on the unfixed code, `completion_evidence(root, rec["line"])` is False
          (pins the bug so the fixture cannot silently stop testing anything).
        - Post-fix: the stop allows (or at least does not block on "completion"), proving
          the real sha in the closing note is recognized.
- [ ] Add/extend a direct-call control in `.claude/hooks/stop/test-completion-evidence.py`
      (or a new sibling file) proving `completion_evidence` behaves correctly when given an
      isolated note vs. a polluted multi-KB blob, mirroring the MUST_PASS/MUST_FAIL shape
      already used there.
- [ ] Run `.claude/hooks/stop/test-completion-evidence.py`,
      `.claude/hooks/stop/test-reggate-ledger.py`, and
      `.claude/rediacc_hooks/tests/test_wl_regression_gate.py` directly; then run
      `check:ci-pytest` (collects all of the above via
      `.claude/rediacc_hooks/tests/test_hooks_delegates.py`'s `TAILED`/delegate list) to
      confirm no regression in the wider hook suite.
- [ ] Manually re-run the stop hook (or `wl_reggate.fix_signals` + `completion_evidence`)
      against the live `agent/worklist/d778be9d.jsonl` + the live
      `/tmp/claude-worklist/home_developer_console.reggate-d778be9d` marker and confirm item
      `4954f598` no longer appears in `ev_ticks`.

## Acceptance criteria

- The fixture in `test_wl_regression_gate.py` reproduces the bug red-then-green: fails
  against unfixed code (accumulated-blob scan misses the real sha), passes after the fix (isolated closing-note scan finds it).
- No regression in `.claude/hooks/stop/test-completion-evidence.py`,
  `.claude/hooks/stop/test-reggate-ledger.py`, the full `.claude/rediacc_hooks/tests/test_wl_regression_gate.py` module, and `check:ci-pytest` overall.
- Live check: item `4954f598` stops appearing in `ev_ticks` on the next real stop against the
  current worklist/marker state, and the reggate marker's `seen_ticks` picks up its tid on that same (now-clean) stop.
- The displayed violation text, when this class of check fires for a genuinely unevidenced
  tick, shows the tick's own note (via `brief_text`), not the item's original description.

## Notes for the implementer

This is a two-function, roughly 15-20 line diff (`.claude/hooks/stop/wl_reggate.py` + `.claude/hooks/stop/wl_checks.py`), not a redesign. The "violations block before reggate settle" ordering (`.claude/hooks/stop/wl_checks.py:4087` vs `:4268`) stays untouched -- it is deliberate and pinned by `test_90` in the ported v5 suite.
