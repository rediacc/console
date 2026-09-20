# Extension-shaped matchers: the W7 P5 precondition
Status: compacted
Full-Text-Blob: 3408a63e57259f441d86892ee614934adcdc4a3c
Record-Sig: b1e089e8

## Why
W7 P5 will delete 521 bash files. Tools that identify gates by the `.sh` extension will silently stop matching those gates — no error, just silent acceptance when nothing matches. This plan is the precondition to detecting and fixing those silent matching failures before the deletion happens, ensuring every matcher that must see the ported Python equivalent is widened first.

## Outcome
Commits 1 (detector) and 2 (extraction) landed by 2026-09-09. Commit 3 (widen `FAMILIES` to include `check_*.py`, `test_gate_*.py`, `guards/block_*.py`) remains not started as of 2026-09-17 after 26 independent re-checks. Five matchers investigated: one fixed with control, two refuted (must NOT be widened), two ported. The plan gates W7P5-c (bash deletion), which is itself deferred
by the operator pending ledger completeness, so this plan's own blockage is transitive and not currently active.

## Lessons
- Silent matching failures — tools that exit 0 when nothing matches — are harder to diagnose than loud failures. This plan discovered the hazard through measurement, not theory.
- Measurement bases move without notice: a tokenizer rewrite and directory relocation both landed 2026-09-09, invalidating every count from 2026-09-08. Re-derive rather than reuse prior measurements.
- Per-family floor constraints are structural, not cosmetic. A floor of 1 still prevents a gate from silently dying when a single-file family shrinks.
- Commit sequencing is load-bearing when deletion follows: extraction must land before the original is deleted, or the scope becomes ambiguous retroactively.
- Precondition proxies can drift from the real metric. This plan tracked `w7p5a-*.jsonl` but progress moved to `w7p6-*.jsonl` under unrelated naming; 26 re-checks never caught it.

## Boxes
(this plan carried no checkbox tasks)

## Record
Record-Kind: compacted
Prior-Status: executing
Compacted-By: d778be9d
Compacted-At: 2026-09-20T17:55:25Z
Boxes: 0 attested, 0 open, 0 abandoned
Epics: e87fa3ce
Touched: scripts/lib/gate-header.ts, .ci/rediacc_ci/quality/toolchain_pins.py, scripts/gates/check-shape-duplication.ts, .ci/scripts/quality/check_npmrc.py, scripts/lib/command-path-checker.ts, .ci/rediacc_ci/quality/workflows.py, .ci/scripts/quality/check-workflows.sh, scripts/gates/check-ci-parity.ts, .ci/rediacc_ci/quality/pool_writer_safety.py, .ci/rediacc_ci/quality/gate_id_convention.py, .ci/scripts/security/shfmt.sh, .ci/rediacc_ci/tests/test_battery.py, .claude/rediacc_hooks/guards/warn_remote_drift.py, .claude/rediacc_hooks/shellscan.py, .ci/rediacc_ci/tests/gates/harness.py
Gates: check:ci-gates-lock, check:ci-shape-duplication
Why-Source: model
Read-History: `git show 3408a63e57259f441d86892ee614934adcdc4a3c` recovers the text; `git log --find-object=3408a63e57259f441d86892ee614934adcdc4a3c --all` names the commit

## History
- 2026-09-20T17:55:25Z compacted by d778be9d from `executing` (record-sig b1e089e8)
