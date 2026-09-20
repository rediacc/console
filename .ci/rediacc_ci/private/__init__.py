"""Python ports of `.ci/scripts/private/*.sh`, box W7P6.

WHY THIS SUBPACKAGE EXISTS. `private/` holds the handful of scripts that drive the `private/renet` Go submodule from the console side: one registered gate (`check:ci-renet`, `run-renet.sh`) and two root-only test runners that CI calls under `sudo`. None of them had a Python twin before this wave, and the three are grouped by the directory their twins live in, the same rule every
other subpackage in this campaign follows.

NO `---- gate ----` HEADER ON ANYTHING HERE, INCLUDING `run_renet`. That header is what `scripts/gate-bind.ts` reads to build the gate estate, and `run-renet.sh` already carries it. A second file claiming `id: check:ci-renet` would give one gate id two owners and the parity meta-gates would be right to complain. The header's `run:` now names this module, so the binder emits the
module form while the ownership stays where it was.

WHAT "VERIFIED-EQUIVALENT" MEANS HERE. Each module has a differential under `.ci/rediacc_ci/tests/` that runs BOTH subjects on the same fixture in the same run and compares exit code, stdout, stderr and the recorded argv of every
external command, plus a K=5 shadow-gate ledger
(`.ci/shadow/w7p6-<slug>.observations.jsonl`) recorded through `scripts/lib/shadow-gate.ts`. The differentials never invoke a real `go`, `sudo` or `mount`: every one of those is a recording fake on a scratch PATH, because the real ones need root, a bpffs and a Go toolchain, and a test that quietly skipped when they were missing would be certifying nothing.

CUTOVER LANDED IN W7P4-W FOR TWO OF THE THREE. `check:ci-renet` and `check:ci-account-server` now run `python3 -m rediacc_ci.private.run_renet` / `...run_account` from `package.json`, from their gate headers and from the workflows, with `scripts/ci-runner/manifest.ts` `leaves` following, on the `w7p4b-run-renet` and `w7p4b-run-account` ledgers. `compose_healthcheck_smoke_test` went
with them on `w7p4b-compose-healthcheck-smoke-test`. The remaining root-only runners still invoke their bash twins from `.github/workflows/ct-tests.yml`.

Deliberately no re-exports, same reasoning as `rediacc_ci/__init__.py`: a consumer should import exactly the module it needs.
"""

__all__: list[str] = []
