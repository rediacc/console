#!/usr/bin/env python3
"""Entry point for the ported profiler-coverage gate. Logic is in the package.

Contract section 5d puts a gate's entry point where `scripts/gate-bind.ts` can see it; the logic lives in `rediacc_ci.quality.profiler_coverage`, which pytest and the port's own `--selftest` import directly.

CUT OVER FROM BASH 2026-09-08 (W7 P4 batch 8a, the broad tree-scanning nine). See DRIVEN, below.

WHY AN ENTRY POINT AT ALL: `check_npmrc.py` states both measured reasons. A port cannot be run by path (nothing puts `.ci` on `sys.path`, hence the insert below), and `python3 -m rediacc_ci.quality.profiler_coverage` works but is the wrong registration because `check:ci-parity`'s tokenizer cannot read `-m` and resolves the leaves to `[python3]`.

THE HEADER BELOW IS THE TWIN'S, FIELD FOR FIELD, extracted from `.ci/scripts/quality/check-profiler-coverage.sh` by an awk range over its `---- gate ----` block, de-commented, and diffed as an ordered list of whole lines against the block in this docstring. The twin carried exactly FOUR fields in this order: `kind`, `test`, `blocker`, `needs`. No `step:`, no `emit:`, no `id:`, no
`run:`, no `lane:`, no `selftest:`, no `why:`.

`kind: test` IS THE LOAD-BEARING ONE, and its `blocker:` runs to 560 bytes, naming the seam-free real-tree case at `test-profiler-coverage.sh:584`, the 121-job parse, and the five anti-vacuity refusals the 22 fixture cases cover. Carried byte for byte. Grepped every file under `.github/workflows/` for `check-profiler-coverage.sh`: ZERO hits, which is what `kind: test` predicts.

NO `selftest:` IS CORRECT, carried exactly as found.

NO `id:` IS CORRECT HERE: `derivedId` (`gate-header.ts:260`) maps this basename to `check:ci-profiler-coverage`, which is the manifest id.

THE RESOLVED NEED SET DOES NOT MOVE, verified by calling `bind()` on both files. Both infer `[]` and both resolve to the empty set `needs: none` declares.

PINNED BY PATH IN TWO RUN-IN-PLACE ROWS, so both take the ENTRY POINT arm if they are ever repointed:

  - `.ci/scripts/test/gates/test-profiler-coverage.sh:31` (`GATE=`, then runs it)
  - `.ci/rediacc_ci/tests/gates/test_gate_profiler_coverage.py:63` (`GATE_REL`)

`.ci/rediacc_ci/tests/test_quality_profiler_coverage.py:34` is the DIFFERENTIAL and must keep naming the twin. Three further hits are prose only and pin nothing: `test-policy-path.sh:18`, `test-emit-advisory.sh:97` and `test_gate_emit_advisory.py:11` all name this gate in comments about libraries it sources, and
`.ci/rediacc_ci/tests/goldens/allowlist/corpus/profiler-coverage-allowlist.list:2` carries the path in a golden's own comment header.

BECAUSE THIS GATE IS `kind: test`, the run-in-place rows decide which side CI executes: while `test-profiler-coverage.sh:31` still names the `.sh`, CI executes the TWIN. Repointing is the driver's call and is called out in the report.

DRIVEN, on this tree, both streams captured SEPARATELY, `CI=true` on both:

    .ci/scripts/quality/check-profiler-coverage.sh   -> exit 0
    .ci/scripts/quality/check_profiler_coverage.py   -> exit 0
    stdout: BYTE-IDENTICAL, EMPTY on both sides
    stderr: BYTE-IDENTICAL, 147 bytes, sha256 ee6269d080293050...

No normalisation was applied and none was needed; the twin was run TWICE against an unchanged tree and is byte-stable against itself on both streams.

DRIVEN RED AS WELL, through the twin's own `PROFILER_COVERAGE_ALLOWLIST` seam, which the port reads under the same name. The fixture is a copy of `.ci/policy/.profiler-coverage-allowlist` with ONE BLANK LINE inserted above its last entry. That is the whole plant, and it is the exact shape the file's own header describes: a blank line resets the tracked BLOCKER, so the entry beneath
it is suddenly a suppression with no stated reason.

THE CONTROL WAS PROVED BEFORE THE PLANT RAN: an UNMODIFIED copy of the allowlist, read through the same override, exits 0 on the twin. So the red below is attributable to the inserted line and not to the override path.

    both sides -> exit 1, stdout BYTE-IDENTICAL (311 bytes,
    sha256 94f172c533269bee...), stderr BYTE-IDENTICAL (191 bytes,
    sha256 908d7172249d5c30...)

A PORT GAP WAS FOUND DOING THIS AND FIXED IN `profiler_coverage.py`, and it is the one that would have mattered most in CI. On the first red run the two sides had the same exit code and the same words in a DIFFERENT STREAM and a DIFFERENT FORM: the twin put

    ::error::Allowlist <file>: entry watchdog-monitor.yml:monitor is missing a
    '# BLOCKER: <reason>' comment above it

on STDOUT, and the port put `✗ Allowlist ...` on STDERR. The twin reaches that line through `blocker-validator.sh:229`, which calls `ci_error` (`emit-advisory.sh:136`), and `ci_error` switches to the GitHub Actions
annotation form when `CI=true` -- which is precisely how CI runs this gate. The
port had settled on one of the two renderings, so under CI it kept the red and lost the annotation that surfaces the finding in the Actions UI. The module now carries the same `ci_error` helper `go_deps.py:220` and `swallowed_failures.py:525` carry, applied to the head line only: the continuation line is a plain `echo` on both sides and the gate's own two "this is a hole in the
invariant" lines are plain `log_error` to stderr, three renderings in one failure and only the head moves stream.

Re-driven after the fix, both sides are byte-identical on both streams, and the GREEN run was re-driven afterwards to confirm the fix did not move it.

THE REAL TREE WAS NEVER WRITTEN TO for this gate; the allowlist is untouched.

INVARIANT 5 IS INTACT: `.ci/scripts/quality/check-profiler-coverage.sh` is NOT deleted here. It stays on disk as the differential twin; deletion is W7 P5's job.

---- gate ---- kind: test test: .ci/scripts/test/gates/test-profiler-coverage.sh blocker: BLOCKER: test-profiler-coverage.sh:584 runs the gate seam-free against the real tree inside run-all.sh (ci-quality.yml quality-security, "Quality-gate unit tests") -- real .github/workflows, real .profiler-coverage-allowlist, real .github/actions/profiler/action.yml, real floors -- so the full
121-job parse and both relations execute every CI run; the 22 fixture cases around it prove every fire direction, including the anti-vacuity refusals (empty dir, missing dir, zero jobs, three floors, missing action.yml) that a real-tree-only case can never exercise needs: none ---- end gate ----
"""

import sys

import _cipath  # noqa: F401
from rediacc_ci.quality import profiler_coverage

if __name__ == "__main__":
    raise SystemExit(profiler_coverage.main(sys.argv[1:]))
