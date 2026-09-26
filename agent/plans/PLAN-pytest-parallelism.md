# PLAN: parallelise check:ci-pytest with pytest-xdist
Status: compacted
First-Seen: 2026-09-20
Owner: 8f55d4f0
Full-Text-Blob: 043547f131a60caa448fcd8d07cc8d832d7e2f1e
Record-Sig: d168df27

## Why
check:ci-pytest was a 675s bottleneck dominating the pre-push lane (45x the next gate). The suite was 90s from timeout crash, and the corpus grows ~200 tests per cycle. The gate was about to be force-retiered out of pre-push despite being correct.

## Outcome
DONE. 823.93s → 396s (2.08x speedup), exited 0, 8968 tests. Operator ruling stopped optimization there. Two defects fixed before `-n` was even turned on: (1) hook ordering — pytest_collection_modifyitems lacked @pytest.hookimpl(tryfirst=True) so xdist's hook won and the group derivation stayed inert; (2) session-scoped fixtures duplicate per WORKER (per-process), so `-n 8` alone
cost 1.64x slowdown before grouping fixed it. Landed in check_pytest.py with argv-based `-n <jobs> --dist loadgroup`, real TimeoutExpired verdict arm, and SEPARATE xdist_group values (hooks-guards, hooks-shellscan) — a single shared group would have pinned 72% of corpus to one worker, inverting the parallelism trap.

## Lessons
- Session-scoped fixtures in pytest are per-PROCESS, not per-test-session. Under xdist each worker is a process and rebuilds the full fixture cost (30k processes per worker in this case). No naive `-n` works without first declaring which tests share expensive fixtures.
- pytest hook ordering is load-bearing. An undecorated hook competes with pluggy's default ordering and loses. @pytest.hookimpl(tryfirst=True) is not cosmetic.
- A hypothesis about collection cost (1377 files × N workers) was refuted: 0.53s measured. The cost was not there. Do not trust overhead speculation — measure the real tree.
- Argv-based `-n` (not in addopts) is load-bearing BY DESIGN. It keeps direct pytest serial-by-default and only the CI gate parallelizes. A fork-bomb (`-n auto` in addopts + nested pytest) costs 576 processes on a 22-slot machine.
- Grouping granularity inverts the trap: one group serializes the group, separate groups cost per-worker setup. The 72-percent session-fixture case chose separate groups deliberately to avoid pinning that half the corpus to one core.

## Boxes
- [x] 1. **CLOSED BY OPERATOR RULING, not by completion, and that distinction is the point.** The three-run FLOOR and the `--durations` long pole were never taken, because the operator ruled STOP AT 2.08x before box 10's re-measure needed them; box 10 was satisfied instead by the tier oracle's own floor (367.9s over five samples), which is the same statistic taken by the instrument that judges it. Original text: the serial baseline is recorded (8945 tests, exit 0, stderr empty, ~617-660s
    (record) sig=50b9a829 done=1ae84c3e3
- [x] 2. Fix the imminent crash: catch `TimeoutExpired`, return a verdict, raise the
    (record) sig=ce053824 done=f4d02cc2e
- [x] 3. Declare the isolation the gate ALREADY needs: `reads: ['tree:repo']` on
    (record) sig=8b7d18d6 done=f4d02cc2e
- [x] 4. Pin and provision xdist: `PYTEST_XDIST_VERSION=3.8.0`, a `resolve_xdist` rung,
    (record) sig=1d4a0b97 done=1ae84c3e3
- [x] 5. Prove xdist works here at all: one hand run of `-n 2 --dist loadgroup`, and
    (record) sig=7f769165 done=1ae84c3e3
- [x] 6. Teach the gate to read the parallel header. WITHOUT this, `-n` makes
    (record) sig=16119952 done=1ae84c3e3
- [x] 7. Land the group derivation, still with no `-n`. Markers are inert without
    (record) sig=90f06a32 done=1ae84c3e3
- [x] 8. Turn it on: `-n`, `--dist loadgroup`, `weight: 8`.
    (record) sig=f9591a59 done=1ae84c3e3
- [x] 9. Add the four controls below, each with a planted-defect demonstration.
    (record) sig=20f5d32f done=1ae84c3e3
- [x] 10. Re-measure and retier on a quiesced tree.
    (record) sig=f8d3ccc3 done=1ae84c3e3

## Record
Record-Kind: compacted
Prior-Status: done
Compacted-By: d778be9d
Compacted-At: 2026-09-20T16:42:43Z
Boxes: 10 attested, 0 open, 0 abandoned
Epics: e87fa3ce
Touched: pyproject.toml, scripts/gates/check-gate-manifest.ts, .ci/rediacc_ci/check_pytest.py, scripts/ci-runner/run.ts, .ci/rediacc_ci/tests/gates/test_twin_parity.py, .ci/rediacc_ci/tests/test_core_ports.py, .ci/rediacc_ci/battery.py, scripts/ci-runner/pool.ts
Gates: check:ci-guard-mention-anchoring, check:ci-pytest, check:ci-trap-registry
Why-Source: model
Read-History: `git show 043547f131a60caa448fcd8d07cc8d832d7e2f1e` recovers the text; `git log --find-object=043547f131a60caa448fcd8d07cc8d832d7e2f1e --all` names the commit

## History
- 2026-09-20T16:42:43Z compacted by d778be9d from `done` (record-sig d168df27)
