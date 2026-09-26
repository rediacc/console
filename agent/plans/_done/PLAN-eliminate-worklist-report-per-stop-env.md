# PLAN: eliminate WORKLIST_REPORT_PER_STOP, hardcode the drain to 3 with randomized same-priority selection
Status: done
First-Seen: 2026-09-22
Owner: d778be9d
Updated: 2026-09-22

## 1. The drain-count change

`OUTQ_PER_STOP` (`.claude/hooks/stop/wl_checks.py:1302`) becomes a plain constant `3`, no `os.environ.get`. No other site reads this env var indirectly.

## 2. The randomization mechanism inside `outq_drain`

Group `q["items"]` by `prio`, iterate priority tiers in ascending numeric order (lower = more urgent, unchanged), and within each tier randomly select up to the remaining budget. `outq_drain` gains an `rng` parameter, defaulting `None` -> the module-level `random`. Only `outq_drain` gains the parameter; `outq_add` is untouched. Every call site of `outq_drain` was checked:
`.claude/hooks/stop/wl_checks.py line 4772 (blob 5a8904da5ad64d44df6a7e6095da16a81a681eff)` (real call, no `rng`), `.claude/hooks/stop/test-planfile.py:420-436` (in-process, needs attention -- see task list). No other callers exist anywhere in the tree.

The `is_settled`/`reg-settled:` merge logic later in the function reads `q["items"]` directly, not `take`'s order, so it is unaffected by the tier-internal shuffle.

## 3. Determinism for tests

No `random.`/`secrets.` usage exists anywhere in `.claude/hooks/stop/` or `.claude/rediacc_hooks/` today -- this is genuinely new territory, no house convention to match.

For subprocess-driven tests, there is no way to reach a child process's `random` state. New unit-level tests call `wl_checks.outq_drain` directly, in-process, matching the pattern `.claude/hooks/stop/test-planfile.py:420-436` and `test_wl_report_queue.py`'s own `test_180c` already use.

## 4. Registry / manifest edits

- `.ci/policy/worklist-env-registry.json:633-638` -- delete the whole `WORKLIST_REPORT_PER_STOP` block.
  Confirmed via the gate's own AST scanner (`worklist_env_registry.py:scan_python`): it counts only `os.environ.get(...)`/`getenv(...)` reads and `os.environ[...]` reads; `fix.env["WORKLIST_REPORT_PER_STOP"] = "N"` in test files is a write (excluded), and `wlfix.py`'s `RESET_KNOBS` tuple is a bare string in a tuple (also excluded).
  `.claude/hooks/stop/wl_checks.py:1302` is the only read site in the tracked corpus.
  This deletion must land in the same commit as the code change.
- `.ci/config/env-manifest.json:915` -- delete the line `"WORKLIST_REPORT_PER_STOP",` from the `harness` shard array. Hand-maintained for removals per its own header.
- `.ci/config/python-env-registry.json:1523` -- `SHRINK-ONLY, AND GENERATED -- do not hand-edit`. After the code edit, run `python3 .ci/scripts/quality/check_python_env_registry.py --write-baseline`. A pure shrink, no `--allow-new` needed.
- `scripts/data/doc-registry.md:1860` -- generated region. Row `| \`WORKLIST_REPORT_PER_STOP\` | harness | - |` disappears once the manifest's harness array drops the name. Run `npx tsx scripts/gen/gen-docs.ts --write` after the manifest edit.
- `.ci/policy/README.md:407-408` -- drop `WORKLIST_REPORT_PER_STOP` from the "three names in this tree today" sentence naming names wrongly derivable as flags. (The "133 names... 181 read sites" figures nearby are dated historical measurements, not gate-enforced -- leave them.)

## 5. Comment/docstring accuracy fixes (no behavior change, but the claim goes false once `OUTQ_PER_STOP` is a fixed 3)

| File:Line | Current text | Fix |
|---|---|---|
| `.claude/hooks/stop/wl_checks.py:1434` | "OUTQ_PER_STOP is 1" | "OUTQ_PER_STOP is 3" |
| `.claude/hooks/stop/wl_checks.py:3071` | "OUTQ_PER_STOP=1, plus outq_add's content signature" | "OUTQ_PER_STOP=3, plus outq_add's content signature" |
| `.claude/hooks/stop/wl_checks.py:3565` | "OUTQ_PER_STOP defaults to 1 and outq_drain is highest-priority-first" | "OUTQ_PER_STOP is 3 and outq_drain is highest-priority-first" |
| `.claude/hooks/stop/wl_planfile.py:25` | "`OUTQ_PER_STOP` is 1, so at most one advisory section reaches any stop at all" | "`OUTQ_PER_STOP` is 3, so at most three advisory sections reach any stop at all" |
| `.claude/rediacc_hooks/tests/test_wl_advisories_rotation.py:315` | describes a 1-wide drain forcing the hint to lose its slot | update to describe the fixed 3-wide budget and that widening is no longer a knob |

## 6. Message wording

`worklist_messages.py`'s `N_OUTQ_MORE` (~line 1338) and `N_OUTQ_BLOCKED` (~line 1346) both currently tell the reader to raise the env var.
Both need new wording once it no longer exists -- reference the fixed 3-per-stop budget and the fact that a session sees more sections over subsequent stops, with no knob to widen. House prose style applies: no second person, no first person, the work stays the subject.

## 7. Per-test-file table

Empirically verified: forcing `WORKLIST_REPORT_PER_STOP=3` on every subprocess call across all 13 files with literal-grep hits (264 tests) produced 9 failures. Two (`test_165`, `test_167` in `test_wl_triage_and_plans.py`) reproduce identically on the unmodified tree with no env override at all -- confirmed pre-existing and unrelated (a path-shape mismatch already on this branch,
since fixed by 1d3fdf2e9/a81967e94 this same session). Do not treat those two as part of this plan's fallout. The remaining 7 are genuine casualties of the fixed-3 world:

| File | Current value(s) | What it asserts | Replacement |
|---|---|---|---|
| `test_wl_report_queue.py` (test_173) | unset (default 1) | exactly 1 of 4 same-tier sections releases, tail says "3 more" | Numbers only -- `outq_seen(got.out) == 3`, `"(1 more report section(s) queued"`. Count-based, robust to which 3 of 4 randomization picks. |
| `test_wl_report_queue.py` (test_173_control, `="4"`) | widen to release all 4 at once, proves the cap is real | Replace with "the leftover releases on the very next stop and nothing remains queued": `wl.run(); wl.newturn(); wl.say("done for now"); got = wl.run(); assert outq_seen(got.out) == 1; assert "more report section(s) queued" not in got.out`. No env var. |
| `test_wl_report_queue.py` (test_174, `outq_fill`/`outq_order` using `="0"` then `="1"`) | strict FIFO drain order within a tier | Retire. Strict FIFO within a tier is the behavior being removed by design. Replace with the two new randomization-invariant tests (section 8). `outq_fill`/`outq_order` helpers become dead code, delete them. |
| `test_wl_report_queue.py` (test_174_control, changed content "goes to the back") | reuses `outq_fill`/`outq_order` | The mechanism (`outq_add` bumping `seq` on change) is still real, worth one direct non-subprocess assertion (call `outq_add` twice with the same key, assert `seq` increases). The drain-order consequence this test used to observe is gone by design. |
| `test_wl_report_queue.py` (test_175, `="0"` then `="1"`) | priority-0 CI note beats an older priority-2 advisory for the single slot | Assert render position, not exclusion. Plant the priority-2 advisory first (lower seq), then priority-0 (higher seq) -- both fit under budget 3, fully deterministic. Assert `got.out.index("retry allowlist") < got.out.index("nothing open for this session")`. |
| `test_wl_report_queue.py` (test_176, `="1"`) | a one-shot losing contention is delayed, never dropped (PLANTED DEFECT regression) | Move to unit level: 3 priority-0 filler entries (deterministically saturate a 3-wide budget) + 1 sticky priority-1 entry. First `outq_drain(n=3)` excludes it, `remaining == 1`; second call includes it, `remaining == 0`. See section 9's exact code. `test_176_control` (uncontended leg) is unaffected. |
| `test_wl_advisories_rotation.py` (12 sites at `="4"`, all except 209H/209H_control/209K) | widen so the agent hint (prio 3) gets a slot | Every fixture queues at most 2 concurrent items; fixed budget 3 already covers it. Delete the env-var line at each site, nothing else changes. |
| `test_wl_advisories_rotation.py` (209K, `="6"` on the CONTROL leg only) | FIRE leg proves the hint is outranked and stays queued; CONTROL widens to 6 to prove it was queued, not lost | Empirically confirmed: fixture queues 5 items (4 prio-2 + 1 prio-3 hint); at budget 3, the FIRE assertions hold with no env line at all. Replace the CONTROL's widening with `wl.newturn(); wl.say(HINT_SAY); got2 = wl.run()` (no widening needed, budget 3 >= the 2 remaining items). |
| `test_wl_advisories_rotation.py` (204/205/206, `="6"`) | two-key rotation / foreign checklist advisories not overwritten | Each fixture queues 1-2 concurrent items. Delete the env line at all sites. |
| `.claude/rediacc_hooks/tests/test_wl_background_waits.py:415` (`="6"`) | 2-item shape | Delete. |
| `.claude/rediacc_hooks/tests/test_wl_checklists.py:371` (`drained_setup`, `="6"`) | queue-not-violation shape | Delete -- item count is <=2, confirmed passing under forced 3. Update the docstring's "OUTQ_PER_STOP is 1 by default" claim too. |
| `test_wl_checklists.py` test_201 (does not set the env var) | poll fast-path forfeits (non-empty output) when a live checklist's stat changed | Genuine indirect casualty. Pad the fixture with `wl.brief_other("cafe1234")` + a stale peer transcript + an orphaned item so >=4 items compete at stop 1; under budget 3, at least 1 always survives into stop 2 regardless of which 3 randomization releases. Robust to randomization by construction. |
| `.claude/rediacc_hooks/tests/test_wl_ci_queue_and_mail.py:208` (`="9"`) | 2 concurrent items (peers section + request note) | Delete. |
| `.claude/rediacc_hooks/tests/test_wl_poll_and_waiting.py line 104 (blob 644924843f5ffc42817d1799bd39ea26b5e5980d)` (`="9"`) | 2-class-2-sections shape | Delete. |
| `.claude/rediacc_hooks/tests/test_wl_migrate.py:279,289` (`="6"`) | handoff-candidates report, 1-2 items typical | Delete both, pass `wl.run()` with no `extra_env`. |
| `.claude/rediacc_hooks/tests/test_wl_state_document.py:209,223,239,260` (`="9"`) | peer-visibility notes, 1-2 items | Delete all 4. |
| `.claude/rediacc_hooks/tests/test_wl_cadence.py:827,840` (`="9"`) | deferral audit note / ask-refusals ledger note, 2 items | Delete both. |
| `.claude/rediacc_hooks/tests/test_wl_guide_and_deferrals.py:559` (`="9"`) | audit note + unconfigured-email one-shot, 2 items | Delete. |
| `.claude/rediacc_hooks/tests/test_wl_requests.py line 132 (blob 422d64cd5040817dbb92254e51c66c1558a9de8e)` (`="9"`) | two class-2 sections | Delete. |
| `.claude/rediacc_hooks/tests/test_wl_identity.py:181` (in the `knobs` tuple) | checks the fixture scrub leaves no `WORKLIST_*` ambient leakage; names `WORKLIST_REPORT_PER_STOP` as one checked knob | Remove `"WORKLIST_REPORT_PER_STOP",` from the `knobs` tuple -- it is no longer a real knob, and leaving the string checks nothing. |
| `.claude/rediacc_hooks/tests/wlfix.py:51` (`RESET_KNOBS` tuple) | reset between fixture cases | Remove the `"WORKLIST_REPORT_PER_STOP",` entry -- inert for every other knob. |

## 8. The two new randomization-invariant tests (add to `test_wl_report_queue.py`, in-process, no subprocess)

```python
import random


def test_181_priority_order_across_tiers_is_never_violated_by_the_random_tie_break():
    """However the same-priority lottery lands, a priority-3 item is never released while a priority-1 item still waits. 200 seeds, driven directly against outq_drain."""
    checks = wlfix.import_wl("wl_checks")
    saved_save = checks.S.save_state
    checks.S.save_state = lambda *_a, **_kw: None
    try:
        for seed in range(200):
            qdoc = {"outq": {"items": [], "shown": {}, "seq": 0}}
            for i in range(5):
                checks.outq_add("wl", "sess", qdoc, "hi-%d" % i, "high %d" % i, 1)
            for i in range(5):
                checks.outq_add("wl", "sess", qdoc, "lo-%d" % i, "low %d" % i, 3)
            texts, _left = checks.outq_drain("wl", "sess", qdoc, 3, rng=random.Random(seed))
            assert all("high" in t for t in texts), (
                "seed %d: a priority-3 item was released while a priority-1 item "
                "still waited: %r" % (seed, texts)
            )
    finally:
        checks.S.save_state = saved_save


def test_181_control_same_tier_selection_is_genuinely_randomized_not_a_fixed_order():
    """The other half: with more same-tier items than the budget, different seeds must produce at least two DIFFERENT releases."""
    checks = wlfix.import_wl("wl_checks")
    saved_save = checks.S.save_state
    checks.S.save_state = lambda *_a, **_kw: None
    try:
        seen = set()
        for seed in range(50):
            qdoc = {"outq": {"items": [], "shown": {}, "seq": 0}}
            for i in range(6):
                checks.outq_add("wl", "sess", qdoc, "item-%d" % i, "text %d" % i, 2)
            texts, _left = checks.outq_drain("wl", "sess", qdoc, 3, rng=random.Random(seed))
            seen.add(tuple(sorted(texts)))
        assert len(seen) > 1, (
            "50 different seeds produced the same 3-of-6 release every time: %r" % seen
        )
    finally:
        checks.S.save_state = saved_save
```

## 9. `test_176`'s replacement (unit-level, exact code)

```python
def test_176_a_one_shot_that_loses_its_slot_is_never_dropped_only_delayed():
    """UNIT-LEVEL: the claim is a property of the QUEUE, not of the CI/request pipeline.
    PLANTED DEFECT, 2026-07-31: outq_drain's per-entry removal was replaced with
    `q["items"][:] = []`. Leg 2 would fail: the one-shot gone for good instead of
    surviving the first drain that had no room for it.
    """
    checks = wlfix.import_wl("wl_checks")
    saved_save = checks.S.save_state
    checks.S.save_state = lambda *_a, **_kw: None
    try:
        qdoc = {"outq": {"items": [], "shown": {}, "seq": 0}}
        for i in range(3):
            checks.outq_add("wl", "sess", qdoc, "ci-fact-%d" % i, "ci fact %d" % i, 0)
        checks.outq_add(
            "wl", "sess", qdoc, "req-escalated", "Requests ESCALATED: #cccc3333", 1, sticky=True
        )
        texts, remaining = checks.outq_drain("wl", "sess", qdoc, 3)
        assert all("ESCALATED" not in t for t in texts), (
            "leg 1: the one-shot won a slot it should have lost: %r" % texts
        )
        assert remaining == 1, "leg 1: the one-shot was not left queued: %r" % remaining

        texts2, remaining2 = checks.outq_drain("wl", "sess", qdoc, 3)
        assert any("ESCALATED" in t for t in texts2), (
            "leg 2: the one-shot was DROPPED, not delayed: %r" % texts2
        )
        assert remaining2 == 0, remaining2
    finally:
        checks.S.save_state = saved_save
```

## Part 3 -- Risk enumeration

- Randomization masking a real ordering regression. A future sort-key bug that only misorders within a tier (not across tiers) would be invisible to `test_181`'s tier-order check and could slip past `test_181_control`'s set-based check too, since a bug that scrambles order without changing the SET selected is not caught by it.
  Mitigated but not eliminated -- the plan proves tier order holds and that entropy exists, not which distribution is used.
- `.claude/hooks/stop/test-planfile.py:420-436`'s seeded call is a single hardcoded seed. If a future edit to `outq_add`/`outq_drain` changes iteration order such that seed picks the wrong item again, the test goes red for an unrelated reason. The implementer should verify the seed choice once (try seeds 0..9, pick the first that lands on a `reg-settled:` entry), not assume any seed works.
- The `test_201` fix and 209K's redesign both rely on "at least one item survives to the next stop" as their evidence, deterministic given the padded item counts. Any future change that raises `OUTQ_PER_STOP` again would silently re-open the vacuity these tests were just rescued from -- worth a comment at the constant's definition pointing at these two tests.
- The empirical sweep covered only the 13 files matching a literal grep for `WORKLIST_REPORT_PER_STOP`. The implementing session should re-run the complete `.claude/rediacc_hooks/tests/` suite (not just the 13-file subset) as the closing verification step.
- `N_OUTQ_BLOCKED`'s new second argument is `OUTQ_PER_STOP`, not `pending_outq` twice. Checked: only the two call sites and the one ARITY entry reference it; no third consumer exists.

## Tasks

- [x] Change `OUTQ_PER_STOP` (.claude/hooks/stop/wl_checks.py:1302) to a plain constant `3`, no env read.
    (ticked) 2026-09-23T11:19:17Z by d778be9d: retroactive record: closed by f5007b649 (2026-09-23) fix(ci): 6 independent ci:quick reds surfaced this session -- trail backfilled under PLAN-fix-plan-implementation-check-regression, which explains why this line post-dates the commit it cites
- [x] Add an `rng` parameter to `outq_drain`, default None -> module-level `random`; group items by priority tier, randomize selection within each tier, preserve strict tier ordering across tiers.
    (ticked) 2026-09-23T11:19:17Z by d778be9d: retroactive record: closed by f5007b649 (2026-09-23) fix(ci): 6 independent ci:quick reds surfaced this session -- trail backfilled under PLAN-fix-plan-implementation-check-regression, which explains why this line post-dates the commit it cites
- [x] Update the call site at .claude/hooks/stop/wl_checks.py :4772 (no change needed if it keeps the default `rng=None`).
    (ticked) 2026-09-23T11:19:17Z by d778be9d: retroactive record: closed by f5007b649 (2026-09-23) fix(ci): 6 independent ci:quick reds surfaced this session -- trail backfilled under PLAN-fix-plan-implementation-check-regression, which explains why this line post-dates the commit it cites
- [x] Fix the 5 stale comments naming "OUTQ_PER_STOP is 1" (.claude/hooks/stop/wl_checks.py:1434, :3071, :3565; .claude/hooks/stop/wl_planfile.py:25; .claude/rediacc_hooks/tests/test_wl_advisories_rotation.py:315).
    (ticked) 2026-09-23T11:19:17Z by d778be9d: retroactive record: closed by f5007b649 (2026-09-23) fix(ci): 6 independent ci:quick reds surfaced this session -- trail backfilled under PLAN-fix-plan-implementation-check-regression, which explains why this line post-dates the commit it cites
- [x] Reword N_OUTQ_MORE and N_OUTQ_BLOCKED in worklist_messages.py to drop the env-var mention.
    (ticked) 2026-09-23T11:19:17Z by d778be9d: retroactive record: closed by f5007b649 (2026-09-23) fix(ci): 6 independent ci:quick reds surfaced this session -- trail backfilled under PLAN-fix-plan-implementation-check-regression, which explains why this line post-dates the commit it cites
- [x] Delete the WORKLIST_REPORT_PER_STOP block from .ci/policy/worklist-env-registry.json.
    (ticked) 2026-09-23T11:19:17Z by d778be9d: retroactive record: closed by f5007b649 (2026-09-23) fix(ci): 6 independent ci:quick reds surfaced this session -- trail backfilled under PLAN-fix-plan-implementation-check-regression, which explains why this line post-dates the commit it cites
- [x] Delete the WORKLIST_REPORT_PER_STOP line from .ci/config/env-manifest.json's harness shard.
    (ticked) 2026-09-23T11:19:17Z by d778be9d: retroactive record: closed by f5007b649 (2026-09-23) fix(ci): 6 independent ci:quick reds surfaced this session -- trail backfilled under PLAN-fix-plan-implementation-check-regression, which explains why this line post-dates the commit it cites
- [x] Run `python3 .ci/scripts/quality/check_python_env_registry.py --write-baseline` to drain python-env-registry.json.
    (ticked) 2026-09-23T11:19:17Z by d778be9d: retroactive record: closed by f5007b649 (2026-09-23) fix(ci): 6 independent ci:quick reds surfaced this session -- trail backfilled under PLAN-fix-plan-implementation-check-regression, which explains why this line post-dates the commit it cites
- [x] Run `npx tsx scripts/gen/gen-docs.ts --write` to drop the generated doc-registry.md row.
    (ticked) 2026-09-23T11:19:17Z by d778be9d: retroactive record: closed by f5007b649 (2026-09-23) fix(ci): 6 independent ci:quick reds surfaced this session -- trail backfilled under PLAN-fix-plan-implementation-check-regression, which explains why this line post-dates the commit it cites
- [x] Edit .ci/policy/README.md to drop WORKLIST_REPORT_PER_STOP from its "three names" sentence.
    (ticked) 2026-09-23T11:19:17Z by d778be9d: retroactive record: closed by f5007b649 (2026-09-23) fix(ci): 6 independent ci:quick reds surfaced this session -- trail backfilled under PLAN-fix-plan-implementation-check-regression, which explains why this line post-dates the commit it cites
- [x] Delete the env-var line at every "U"-classified test site in section 7's table (test_wl_report_queue.py test_173_control widening; the 12 test_wl_advisories_rotation.py sites; .claude/rediacc_hooks/tests/test_wl_background_waits.py:415; .claude/rediacc_hooks/tests/test_wl_checklists.py:371; .claude/rediacc_hooks/tests/test_wl_ci_queue_and_mail.py:208; .claude/rediacc_hooks/tests/test_wl_poll_and_waiting.py line 104 (blob 644924843f5ffc42817d1799bd39ea26b5e5980d); .claude/rediacc_hooks/tests/test_wl_migrate.py:279,289; .claude/rediacc_hooks/tests/test_wl_state_document.py:209,223,239,260; .claude/rediacc_hooks/tests/test_wl_cadence.py:827,840; .claude/rediacc_hooks/tests/test_wl_guide_and_deferrals.py:559; .claude/rediacc_hooks/tests/test_wl_requests.py line 132 (blob 422d64cd5040817dbb92254e51c66c1558a9de8e)).
    (ticked) 2026-09-23T11:19:17Z by d778be9d: retroactive record: closed by f5007b649 (2026-09-23) fix(ci): 6 independent ci:quick reds surfaced this session -- trail backfilled under PLAN-fix-plan-implementation-check-regression, which explains why this line post-dates the commit it cites
- [x] Redesign test_173 to assert counts instead of exact single-item drain.
    (ticked) 2026-09-23T11:19:17Z by d778be9d: retroactive record: closed by f5007b649 (2026-09-23) fix(ci): 6 independent ci:quick reds surfaced this session -- trail backfilled under PLAN-fix-plan-implementation-check-regression, which explains why this line post-dates the commit it cites
- [x] Retire outq_fill/outq_order and test_174/test_174_control per section 7; add the direct seq-bump assertion for changed-content re-enqueue.
    (ticked) 2026-09-23T11:19:17Z by d778be9d: retroactive record: closed by f5007b649 (2026-09-23) fix(ci): 6 independent ci:quick reds surfaced this session -- trail backfilled under PLAN-fix-plan-implementation-check-regression, which explains why this line post-dates the commit it cites
- [x] Redesign test_175 to assert render position instead of exclusion.
    (ticked) 2026-09-23T11:19:17Z by d778be9d: retroactive record: closed by f5007b649 (2026-09-23) fix(ci): 6 independent ci:quick reds surfaced this session -- trail backfilled under PLAN-fix-plan-implementation-check-regression, which explains why this line post-dates the commit it cites
- [x] Replace test_176 with the unit-level version in section 9.
    (ticked) 2026-09-23T11:19:17Z by d778be9d: retroactive record: closed by f5007b649 (2026-09-23) fix(ci): 6 independent ci:quick reds surfaced this session -- trail backfilled under PLAN-fix-plan-implementation-check-regression, which explains why this line post-dates the commit it cites
- [x] Redesign 209K's CONTROL leg to drop its widening.
    (ticked) 2026-09-23T11:19:17Z by d778be9d: retroactive record: closed by f5007b649 (2026-09-23) fix(ci): 6 independent ci:quick reds surfaced this session -- trail backfilled under PLAN-fix-plan-implementation-check-regression, which explains why this line post-dates the commit it cites
- [x] Pad test_201's fixture per section 7 so it stays robust under randomization.
    (ticked) 2026-09-23T11:19:17Z by d778be9d: retroactive record: closed by f5007b649 (2026-09-23) fix(ci): 6 independent ci:quick reds surfaced this session -- trail backfilled under PLAN-fix-plan-implementation-check-regression, which explains why this line post-dates the commit it cites
- [x] Remove WORKLIST_REPORT_PER_STOP from test_wl_identity.py's `knobs` tuple and wlfix.py's RESET_KNOBS tuple.
    (ticked) 2026-09-23T11:19:17Z by d778be9d: retroactive record: closed by f5007b649 (2026-09-23) fix(ci): 6 independent ci:quick reds surfaced this session -- trail backfilled under PLAN-fix-plan-implementation-check-regression, which explains why this line post-dates the commit it cites
- [x] Add the two new randomization-invariant tests from section 8 (test_181, test_181_control).
    (ticked) 2026-09-23T11:19:17Z by d778be9d: retroactive record: closed by f5007b649 (2026-09-23) fix(ci): 6 independent ci:quick reds surfaced this session -- trail backfilled under PLAN-fix-plan-implementation-check-regression, which explains why this line post-dates the commit it cites
- [x] Run the full .claude/rediacc_hooks/tests/ suite, not just the 13-file subset, as the closing verification step. Run twice:
    (ticked) 2026-09-23T11:19:17Z by d778be9d: retroactive record: closed by f5007b649 (2026-09-23) fix(ci): 6 independent ci:quick reds surfaced this session -- trail backfilled under PLAN-fix-plan-implementation-check-regression, which explains why this line post-dates the commit it cites
  7548 total, 7540 passed both runs; the 8 differential-test failures (block_unlinked_commit_author, block_unverified_push) are confirmed environmental/concurrency artifacts (private/renet submodule git identity; a shared bash-side-suite.sh fixture colliding under -n 8 parallelism), each spot-verified passing in isolation.
  One genuine casualty found beyond the plan's own table (test_163y_unread_sub_agent_reports_are_surfaced_on_an_ordinary_stop) and fixed the same way as test_201: padded with a fresh peer note so something survives the fixed-3 drain.

## Acceptance criteria

- `WORKLIST_REPORT_PER_STOP` no longer appears anywhere in the tracked tree (code, registry, manifest, generated docs).
- `test_181` and `test_181_control` both pass, proving tier order is never violated and same-tier selection is genuinely randomized.
- The full `.claude/rediacc_hooks/tests/` suite is green, not just the 13-file subset with the known bare env-var hits.
- `check:ci-worklist-env-registry` (or whatever gate reads `worklist-env-registry.json`) stays green with the entry removed.

## Notes for the implementer

`test_165`/`test_167` in `test_wl_triage_and_plans.py` are pre-existing failures unrelated to this plan (already fixed by 1d3fdf2e9/a81967e94 this same session) -- do not attribute them to this work.

### Critical Files for Implementation

- `.claude/hooks/stop/wl_checks.py` -- `OUTQ_PER_STOP:1302`, `outq_add:1334`, `outq_drain:1401`, call site `:4772`
- `.claude/hooks/stop/worklist_messages.py` -- `N_OUTQ_MORE:1338`, `N_OUTQ_BLOCKED:1346`
- `.claude/rediacc_hooks/tests/test_wl_report_queue.py`
- `.claude/rediacc_hooks/tests/test_wl_advisories_rotation.py`
- `.claude/rediacc_hooks/tests/wlfix.py` -- `RESET_KNOBS`
- `.ci/policy/worklist-env-registry.json`
- `.ci/config/env-manifest.json`
- `.ci/config/python-env-registry.json`
- `.claude/hooks/stop/test-planfile.py`
