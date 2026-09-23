# PLAN: stop-hook I7 evidence check scans the whole item history, not the closing tick's own note
Status: done
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

- [x] Change `wl_reggate.mine_tick_ids(lines, session_id)` to
    (ticked) 2026-09-22T19:55:38Z by d778be9d: wl_reggate.py:226-230 (commit e0fe455f7): mine_tick_ids(items, session_id) now reads rec['state']/rec.get('owner') directly off fold records, matches box text verbatim; verified live by reading the source today
      `mine_tick_ids(items, session_id)`, reading `rec["state"]`/`rec["owner"]` directly off
      each record instead of re-parsing `C.ITEM.match(rec["line"])`.
- [x] Change `wl_reggate.fix_signals(root, lines, session_id, state)` to accept `fold.items`
    (ticked) 2026-09-22T19:55:41Z by d778be9d: wl_reggate.py:355-428 (commit e0fe455f7): fix_signals(root, items, session_id, state) accepts fold.items and returns (tid, line, evidence_text) triples where evidence_text = rec.get('lastnote') or line; docstring at wl_reggate.py:372 describes the new shape
      (or an explicit second `items` param alongside `lines` if a narrower diff is
      preferred), and have it return, per new tick, an evidence text derived from
      `rec.get("lastnote") or rec["line"]`. Update the docstring's "ticks stays (id, line)
      pairs" note (`.claude/hooks/stop/wl_reggate.py:426`) to describe the new shape.
- [x] Update the `.claude/hooks/stop/wl_checks.py:2385` call site to unpack the new tuple shape.
    (ticked) 2026-09-22T19:55:45Z by d778be9d: wl_checks.py:2424 unpacks reg_signals, reg_ids, reg_new_ticks, reg_head, reg_banked = wl_reggate.fix_signals(...); every reg_new_ticks consumer (2427,2431,2434-2435,2469,2990,4359-4360,4569) unpacks the (t,_ln,_ev)/(_tid,_line,ev) triple shape; verified via grep
- [x] Update `.claude/hooks/stop/wl_checks.py:2949` to call `completion_evidence(root, evidence_text)` and to
    (ticked) 2026-09-22T19:55:48Z by d778be9d: wl_checks.py:2990: ev_ticks = [ev[:150] for _tid, _line, ev in reg_new_ticks if not completion_evidence(root, ev)] -- checks evidence_text (ev) not the full line, and displays the scoped evidence text's own prefix instead of the item's original description
      build `ev_ticks` from `S.brief_text(rec, cap=150)` (or equivalent) rather than
      `line[:150]`.
- [x] Confirm `tick_touches_code` (`.claude/hooks/stop/wl_reggate.py:412-417`) still receives the full `line`
    (ticked) 2026-09-22T19:55:51Z by d778be9d: wl_reggate.py:415 (fix_signals): if not tick_touches_code(line) -- still passed the full rendered line, unchanged; confirmed by reading the source
      (unchanged) -- it answers a different question (does the fix touch code) and must keep
      scanning the whole rendered text.
- [x] Add a regression fixture reproducing the exact poisoning shape: an item with several
    (ticked) 2026-09-22T19:55:55Z by d778be9d: test_wl_regression_gate.py:420-495, test_96_a_ticks_evidence_is_its_closing_note_not_the_whole_accumulated_history: reproduces the exact poisoning shape via raw JSONL lease events with worker-id-shaped hex notes (af61cd805486b8e9f etc.) followed by a closing state event with a real sha; ran green: pytest -k test_96 -> 1 passed
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
- [x] Add/extend a direct-call control in `.claude/hooks/stop/test-completion-evidence.py`
    (ticked) 2026-09-22T19:56:03Z by d778be9d: Direct-call control landed as part of test_96 (test_wl_regression_gate.py:482-495) rather than a separate file: checks.completion_evidence(str(wl.proj), rec['line']) asserted False (polluted blob) and checks.completion_evidence(str(wl.proj), evidence_text) asserted True (isolated closing note), both direct calls against the real function; ran green
      (or a new sibling file) proving `completion_evidence` behaves correctly when given an
      isolated note vs. a polluted multi-KB blob, mirroring the MUST_PASS/MUST_FAIL shape
      already used there.
- [x] Run `.claude/hooks/stop/test-completion-evidence.py`,
    (ticked) 2026-09-22T20:03:35Z by d778be9d: test-completion-evidence.py: exit 0 (4 pass/4 fail controls green). test-reggate-ledger.py: exit 0 (19 controls green). test_wl_regression_gate.py: pytest -q -> 15 passed (incl. test_96). check:ci-pytest full run: 17468 passed, 42 failed, 6 errors in 633.63s -- zero of the 48 failing/erroring tests are under .claude/rediacc_hooks/tests/ (616 hook test functions counted, all green); every failure is in unrelated .ci/rediacc_ci/tests/ (editorconfig, build_json/npm, dockerx, gate-lanes, env-manifest) pre-existing and untouched by this fix. No regression in the hook suite this plan targets.
      `.claude/hooks/stop/test-reggate-ledger.py`, and
      `.claude/rediacc_hooks/tests/test_wl_regression_gate.py` directly; then run
      `check:ci-pytest` (collects all of the above via
      `.claude/rediacc_hooks/tests/test_hooks_delegates.py`'s `TAILED`/delegate list) to
      confirm no regression in the wider hook suite.
- [x] Manually re-run the stop hook (or `wl_reggate.fix_signals` + `completion_evidence`)
    (ticked) 2026-09-22T19:59:32Z by d778be9d: Live-verified directly against agent/worklist/d778be9d.jsonl + /tmp/claude-worklist/home_developer_console.reggate-d778be9d: item 4954f598's rec['line'] (6150 chars) still fails completion_evidence (control, pins the bug), rec['lastnote'] passes; tick_id 5fe666f72866 is present in the live marker's seen_ticks (117 entries), confirming it self-healed and persisted on a prior stop
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
