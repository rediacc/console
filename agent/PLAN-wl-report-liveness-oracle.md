# PLAN: scan() liveness oracle, the harness's own running-subagent roster
Status: done Owner: 8f55d4f0 Updated: 2026-09-07

## Why

`.claude/hooks/stop/wl_report.py` `scan()` decides an agent has FINISHED from its transcript's mtime. Every anchor below was re-verified against the tree today:

| anchor | verified content |
|---|---|
| `.claude/hooks/stop/wl_report.py:69` | `SILENT_FLOOR = int(os.environ.get("WORKLIST_REPORT_SILENT_FLOOR", "200"))` |
| `.claude/hooks/stop/wl_report.py:75` | `SCAN_IDLE_MIN = float(os.environ.get("WORKLIST_REPORT_SCAN_IDLE_MIN", "5"))` |
| `.claude/hooks/stop/wl_report.py:415-417` | `for ev in read_index(store): if str(ev["id"]) == rid: return None` |
| `.claude/hooks/stop/wl_report.py:475` | `"silent": sends == 0 and len(body.strip()) < SILENT_FLOOR,` |
| `.claude/hooks/stop/wl_report.py:763` | `def scan(store, start, idle_min=None):` |
| `.claude/hooks/stop/wl_report.py:795` | `idle = (now.timestamp() - jsonl.stat().st_mtime) / 60.0` |
| `.claude/hooks/stop/wl_report.py:798-799` | `if idle < idle_min: continue  # still running: capturing now would record a half-answer` |
| `.claude/hooks/stop/wl_store.py:1563` | `LIVE_MIN = int(os.environ.get("WORKLIST_LIVE_MIN", "30"))` |

mtime measures whether an agent is WRITING, not whether it is ALIVE. An agent blocked in a single Bash call is silent by construction for the whole call.

**THE COST IS NOT A PREMATURE ROW, IT IS A LOST REPORT.** `capture()` returns `None` when the id is already indexed (`:415-417`, verified above). So a mid-flight row does not merely arrive early, it PERMANENTLY SHADOWS the real report: when the agent finishes and `SubagentStop` fires, the substantive body is dropped on the floor and the half-answer is the only artifact that ever
exists.

That happened twice on 2026-09-07 and the damage is on disk now. The durable record of the W1 P5(a) keystone is a 68-byte fragment reading "Now I have the full picture. Let me write the CLI."; its real report survives only in a task notification, which does not survive compaction. One agent was waiting on `check:ci-pytest` (661 s measured in this repo's own receipt), the other on
the full bash gate battery (606 s).

It is then escalated: `wl_checks.py` surfaces unread reports with a `[SILENT]` prefix and promotes one to an invariant violation at `UNREAD_INVARIANT_MIN`. The session is blocked over an agent that is working correctly, and told the agent said nothing.

## The oracle

The harness's running background task list, read from the `.lastevent-<prefix>.json` sidecars that `wl_checks.py` writes on every full stop.

**The join key is exact, and it is the one claim everything rests on.** Verified live: the sidecar carries `background_tasks[].id == "<agent-id>"` for a `type: "subagent"` entry, and the transcript `scan()` globs is `agent-<agent-id>.jsonl`. Byte-identical. No mapping and no heuristic: `jsonl.stem.removeprefix("agent-")` at `:791` already produces exactly the lookup key.

The roster does not over-protect. The live session has 136 subagent transcripts and the harness lists 2 as running; finished agents are dropped. A roster that never shrank would freeze `scan()` permanently.

`scan()` receives `start`, and `C.worklist_for(start)` lives in `wl_core`, the only sibling `wl_report.py` imports. So the stdlib-plus-`wl_core` invariant survives. **Do not import `wl_liveness`.**

**Rejected, with reasons.** Process-tree liveness: `.claude/hooks/stop/wl_liveness.py:14-18` already settled it from measurement, agent tasks have NO OS process. The `.meta.json` sidecar: read live, it carries `agentType`, `description`, `toolUseId`, `spawnDepth` and no terminal state; it records what an agent IS, never whether it is done.

**The fail-open shape, inherited not invented.** The roster may only ever add a reason to SKIP, never a reason to CAPTURE. An agent absent from every roster is decided by the mtime rule alone, exactly as today.

| situation | verdict | why self-heal survives |
|---|---|---|
| id in a FRESH roster (sidecar age <= `SCAN_LIVE_MIN`) | SKIP | the harness says it is running now |
| id only in a STALE roster | roster ignored, mtime decides, CAPTURE | a dead session's sidecar freezes with tasks still `running`; without the bound those ids would be protected forever and the self-heal would starve |
| id in NO roster | mtime decides, CAPTURE | the common case, unchanged |
| NO readable sidecar at all | BLIND, mtime decides, CAPTURE | skipping everything is fail-OFF, not fail-open |

The blind case is stated rather than hidden: when the oracle cannot see, the fix is not applied and the old defect is fully present. It reports its blindness in words rather than degrading silently.

## What is NOT being changed

- **`SCAN_IDLE_MIN` stays at 5 and the mtime check stays exactly as written.** It is a
correct, cheap pre-filter. It was never wrong about what it measured, only about what that measurement implies. The new check runs after it and only ever subtracts.
- **The `silent` semantics at `:475` are byte-identical.** Case 12b killed the cheap fix
and was right: a scan row can be legitimately silent when the transcript is unreadable. `silent` says what the agent SAID; liveness says whether it is DONE. Conflating them is the error already made once, by me, today.
- **Import set stays stdlib + `wl_core`.** No `sys.path` hop added.
- **`scan()`'s return arity stays `(added, pruned)`.**
- **`.claude/hooks/stop/` stays flat, no `__init__.py`.** That is W5 P7's job.

## Boxes

- [x] 1. Add `running_agent_ids(start) -> (ids, evidence)` to `wl_report.py`. Glob
      `wl.parent.glob(wl.stem + ".lastevent-*.json")`. Empty list returns a NAMED
      blindness string, never an innocent empty set. Per-sidecar try/except so one
      corrupt file cannot blind the whole oracle (the 12b lesson, one level up).
- [x] 2. Add `SCAN_LIVE_MIN` beside `SCAN_IDLE_MIN`, default 30, citing
      `.claude/hooks/stop/wl_store.py:1563` for why a freshness bound is required at all.
- [x] 3. Wire it into `scan()`: compute once above the loop, and skip on
      `agent_id in live_ids` BEFORE the `stat()` so a live agent costs one set lookup.
- [x] 4. Report the oracle's state in the `--scan` CLI, one bounded line, blindness
      verbatim when blind.
- [x] 5. Add case 13b to `test-report-inbox.sh`.
- [x] 6. Planted-defect proof both directions: revert box 3, 13b goes red while 12b and
      13 stay green; then break the join key, 13b goes red again. The second plant pins
      the exact claim rather than merely "something skips".
- [x] 7. Live run against a real running sub-agent.

## The test that would have caught this

**Case 13 would NOT have caught it, and that matters more than the fix.** Case 13 plants a fresh mtime and asserts a skip; its control backdates the same file and asserts a capture. Both arms vary exactly one thing, mtime, and both AGREE with the mtime oracle. It is a faithful test of the rule that was implemented and structurally blind to the rule being wrong. The defect lives in
the quadrant no fixture in the suite has ever built: STALE MTIME AND STILL ALIVE. A test can only falsify a rule it can state independently of that rule, and the suite had no way to express "alive" except mtime.

Case 13b supplies the independent statement, the harness roster, and asserts the two oracles DISAGREEING. Six assertions: a harness-running agent with a stale mtime is not indexed; its identical twin marked `completed` IS indexed (without which "lacks liveagent" is satisfied by a scan that saw nothing); exactly one of the two captured; a stale roster releases the hold; with no
roster the scan still self-heals; and it NAMES its blindness. A running `type: "shell"` entry sits in the same roster so the filter is proven to be on `type` as well as `status`.

## What could still go wrong

1. **The 30-minute window is a real hole.** A session that has not stopped in
`SCAN_LIVE_MIN` has a stale sidecar, so its running agents fall back to mtime. This converts "any tool call longer than 5 minutes" into "any TURN longer than 30", about a 6x reduction against the observed 661 s and 606 s failures. It does not eliminate the class, and shrinking it trades directly against box 2's starvation argument.
2. **The blind case is unfixed by construction.** In CI with a wiped TMPDIR this fix
does nothing. It is loud rather than silent, which is the correct choice, but it must not be mistaken for coverage.
3. **The `status` vocabulary is inferred, not enumerated.** Only `"running"` protects,
so an unknown value degrades to today's behaviour rather than to a new failure.
4. **The join key is a harness convention, not a contract.** Case 13b pins it, so a
change turns CI red instead of silently restoring the defect.
5. **A roster entry can outlive its agent inside the window**, delaying a capture by up
to 30 minutes. The failure mode is LATE capture, the direction this design is deliberately biased toward.

## Record

Triaged: worklist #9afb008e, TRIAGED BIG.

## Outcome

All seven boxes done and driven, 2026-09-07.

**Live behaviour changed in the right direction, observed on the real tree.** Before: `--scan` would have captured a running `gate-author` mid-flight (idle 8.1 min by mtime, listed RUNNING by the harness, absent from a 314-entry index). After:

    liveness oracle: 3 fresh sidecar(s), 0 stale, 0 unreadable, 2 running sub-agent(s);
      held back <agent-id-2> <agent-id>
    nothing to index

and `WORKLIST_REPORT_SCAN_LIVE_MIN=0` restores the pre-fix verdict exactly (`0 fresh, 3 stale, 0 running`), which is what makes the knob a real control lever rather than a decoration.

**Both plants fired, in an ISOLATED COPY of the hook directory** so no defect was ever planted in a hook the live session depends on:

- Plant 1, the liveness skip removed: `passed=128 failed=3`. Cases 12b and 13 stayed
GREEN throughout, which is the point -- they are structurally blind to this defect.
- Plant 2, the join key changed from `id` to `agent_type`: `passed=128 failed=3` again.
This is the plant that matters, because it pins the EXACT claim the design rests on rather than merely "something skips".
- Clean tree: `passed=131 failed=0`, up from 125 by exactly the six new assertions.

`.ci/scripts/test/gates/test-worklist-hooks.sh` reports `PASS[report-inbox]: passed=131 failed=0`, so the case is CI-gated the moment it exists; no new wiring was needed. `ruff check` and `ruff format --check` both clean.

## What the design got wrong, corrected in flight

`running_agent_ids` used `time.time()` and `time` was NOT among the module's imports -- the module keeps a deliberately minimal stdlib set. Caught before the first run rather than at a hook firing, and `import time` added.

`ruff` then refused `except Exception` (BLE001) on the worklist-path lookup. Narrowed to `(OSError, ValueError, TypeError, AttributeError)`, which is the same tuple the per-sidecar handler already uses, so the two now agree instead of differing by accident.

## The mistake this plan exists because of

I first tried to fix the SYMPTOM: gate `silent` on `source == "hook"`, so a scan row could never be labelled `[SILENT]`. `test-report-inbox.sh` case 12b refused it within one run: a scan row CAN be legitimately silent, because an unreadable transcript indexes with an empty body and must still be flagged. The suite was right and I was wrong; the change was reverted whole before
anything else was attempted. That refusal is what turned a label complaint into the real finding, which is that `capture()` drops the substantive report forever once a mid-flight row holds the id.
