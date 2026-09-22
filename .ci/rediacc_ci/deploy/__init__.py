"""Python ports of `.ci/scripts/deploy/*.sh`, box W7P5-a.

WHY THIS SUBPACKAGE EXISTS. `deploy/` held 27 bash scripts and zero Python before this box (`agent/plans/PLAN-tooling-transformation.md` line 607). These are workflow `run:` targets, not gates: nothing here carries a `---- gate ----` header, and `scripts/gate-bind.ts` does not read this package. The acceptance this box works to is a shadow-gate ledger
(`.ci/shadow/*.observations.jsonl`)
asserting `equivalence holds` at K=5 against the bash twin, exactly as
`.ci/rediacc_ci/quality/*` did for the 78 quality-gate ports, using the same `scripts/lib/shadow-gate.ts` comparator, an `--old`/`--new` pair rather than a registered `--pair` id.

WORKFLOW CUTOVER IS A LATER BOX. `.github/workflows/**` still invokes the bash twin (`run: .ci/scripts/deploy/<name>.sh`) for every path in this package. Flipping a call site to `python3 -m rediacc_ci.deploy.<name>` is W7P4-W, gated on the ledger this box produces; it is not done here, and no manifest.ts entry follows from a module living here (these are `run:` targets, never
gates).

ONE MODULE HERE IS NOT A PORT OF A `.ci/scripts/deploy/*.sh`, and it sits here on purpose. `write_once_guard_check` (W7P6) ports `.ci/scripts/test/test-write-once-guard.sh`, the registered gate `test:write-once-guard`, whose entire SUBJECT is `write_once_guard()` inside `.ci/scripts/deploy/upload-to-r2.sh`. It is filed by what it tests rather than by where its twin's file lives,
because a `tests/` home would put a non-pytest program under a pytest root and a new subpackage for one module would hide the connection to the thing it guards. Unlike its neighbours it IS a gate, and its twin is wired at `.github/workflows/ci-quality.yml:387` and `scripts/ci-runner/manifest.ts:4853`; the cutover is not done here either.

Deliberately no re-exports, same reasoning as `rediacc_ci/__init__.py`: a consumer should import exactly the module it needs.
"""

__all__: list[str] = []
