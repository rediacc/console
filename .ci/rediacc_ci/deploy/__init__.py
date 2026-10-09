"""Python ports of `.ci/scripts/deploy/*.sh`, box W7P5-a.

WHY THIS SUBPACKAGE EXISTS. `deploy/` held 27 bash scripts and zero Python before this box (`agent/plans/PLAN-tooling-transformation.md` line 607). These are workflow `run:` targets, not gates: nothing here carries a `---- gate ----` header, and `scripts/gate-bind.ts` does not read this package. The acceptance this box works to is a shadow-gate ledger
(`.ci/shadow/*.observations.jsonl`)
asserting `equivalence holds` at K=5 against the bash twin, exactly as
`.ci/rediacc_ci/quality/*` did for the 78 quality-gate ports, using the same `scripts/lib/shadow-gate.ts` comparator, an `--old`/`--new` pair rather than a registered `--pair` id.

WORKFLOW CUTOVER IS DONE. `.github/workflows/**` runs each path in this package as `PYTHONPATH=.ci python3 -m rediacc_ci.deploy.<name>`; the bash twins under `.ci/scripts/deploy/` are deleted (W7P4-W, then PLAN-retire-bash-oracles), except `upload-media-to-r2.sh`, an exec shim kept for the gitignored growth pipeline and `packages/www/scripts/publish-tutorial-video-to-r2.ts`, which `upload_media_to_r2` is the twin of. No manifest.ts entry follows from a module living here: these are `run:` targets, never
gates.

TWO MODULES HERE ARE NOT PORTS OF A `.ci/scripts/deploy/*.sh`. `write_once_guard` is the sentinel-aware write guard that used to be a bash function inside `upload-to-r2.sh`; it was ported behind goldens frozen from the bash (operator ruling D5, 2026-10-08) and `upload_to_r2` calls it. `write_once_guard_check` is the registered gate `test:write-once-guard` (formerly `.ci/scripts/test/test-write-once-guard.sh`), whose subject is that guard; it is filed here by what it tests, because a `tests/` home would put a non-pytest program under a pytest root. Its gate registration is in `scripts/ci-runner/manifest.ts` and `.github/workflows/ci-quality.yml`.

Deliberately no re-exports, same reasoning as `rediacc_ci/__init__.py`: a consumer should import exactly the module it needs.
"""

__all__: list[str] = []
