# PLAN: scan() liveness oracle, the harness's own running-subagent roster
Status: compacted
First-Seen: 2026-09-20
Owner: 8f55d4f0
Full-Text-Blob: 86b1b24713fdabbf33a7fe99552b46c994ae94b1
Record-Sig: cb8e4f43

## Why
`.claude/hooks/stop/wl_report.py`'s `scan()` function decided agent completion from transcript mtime alone, which measures writing not aliveness. Long Bash calls block writes for 5+ minutes, causing premature capture of mid-flight reports. Critically, `capture()` returns `None` when an id is already indexed, so the half-answer permanently shadows the real report when it finally
arrives—the only artifact that ever exists. This happened twice 2026-09-07 (W1 P5(a) keystone and two 600+ second blocking calls) and the lost reports survived only in task notifications, which don't survive compaction.

## Outcome
Completed 2026-09-07. Liveness oracle added to read harness's running task list from sidecars as independent aliveness signal. Implemented: `running_agent_ids()` function, `SCAN_LIVE_MIN` env var (30s default), oracle wired into `scan()` to skip live agents before mtime check, case 13b test, two planted-defect proofs. CI-gated at `test-worklist-hooks.sh`: 131 tests passing (6 new).
Running agents no longer captured mid-flight; blind cases report verbatim.

## Lessons
- A defect in an invariant can only be falsified by an independent statement of it—the original suite couldn't catch mtime-based liveness because it had no way to express 'alive' except through mtime. Case 13b succeeds by asserting the two oracles disagree.
- Fail-open design protects self-heal: roster can only add skip reasons, never force capture. An unreadable sidecar or missing oracle degrades to mtime (unchanged), not to false negatives.
- Premature index entry permanently shadows later reports via `capture()`'s early return—fixing the symptom (the [SILENT] label) was misdirection. Root cause was the premature capture itself.
- The 30-minute sidecar freshness bound trades directly against starvation: converts 'any tool >5min' to 'any turn >30min'. Observed defects were 661s and 606s; the window doesn't eliminate the class.
- CI with wiped TMPDIR is unfixed by construction (blind case). Loud reporting is correct, but blindness must not be mistaken for coverage.

## Boxes
- [x] 1. Add `running_agent_ids(start) -> (ids, evidence)` to `wl_report.py`. Glob
    (record) sig=a3c08add done=f4d02cc2e
- [x] 2. Add `SCAN_LIVE_MIN` beside `SCAN_IDLE_MIN`, default 30, citing
    (record) sig=7e041871 done=f4d02cc2e
- [x] 3. Wire it into `scan()`: compute once above the loop, and skip on
    (record) sig=66f279eb done=f4d02cc2e
- [x] 4. Report the oracle's state in the `--scan` CLI, one bounded line, blindness
    (record) sig=26be2ba4 done=f4d02cc2e
- [x] 5. Add case 13b to `test-report-inbox.sh`.
    (record) sig=c3ba6973 done=f4d02cc2e
- [x] 6. Planted-defect proof both directions: revert box 3, 13b goes red while 12b and
    (record) sig=769becb0 done=f4d02cc2e
- [x] 7. Live run against a real running sub-agent.
    (record) sig=cd510b2d done=f4d02cc2e

## Record
Record-Kind: compacted
Prior-Status: done
Compacted-By: d778be9d
Compacted-At: 2026-09-20T18:07:13Z
Boxes: 7 attested, 0 open, 0 abandoned
Epics: e87fa3ce
Touched: .claude/hooks/stop/wl_report.py, .claude/hooks/stop/wl_store.py, .claude/hooks/stop/wl_liveness.py
Gates: check:ci-pytest
Why-Source: model
Read-History: `git show 86b1b24713fdabbf33a7fe99552b46c994ae94b1` recovers the text; `git log --find-object=86b1b24713fdabbf33a7fe99552b46c994ae94b1 --all` names the commit

## History
- 2026-09-20T18:07:13Z compacted by d778be9d from `done` (record-sig cb8e4f43)
