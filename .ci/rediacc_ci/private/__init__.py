"""Python ports of `.ci/scripts/private/*.sh`, box W7P6.

WHY THIS SUBPACKAGE EXISTS. `private/` holds the handful of scripts that drive
the `private/renet` Go submodule from the console side: one registered gate
(`check:ci-renet`, `run-renet.sh`) and two root-only test runners that CI calls
under `sudo`. None of them had a Python twin before this wave, and the three
are grouped by the directory their twins live in, the same rule every other
subpackage in this campaign follows.

NO `---- gate ----` HEADER ON ANYTHING HERE, INCLUDING `run_renet`. That header
is what `scripts/gate-bind.ts` reads to build the gate estate, and `run-renet.sh`
already carries it. A second file claiming `id: check:ci-renet` would give one
gate id two owners and the parity meta-gates would be right to complain. The
bash twin stays the LIVE registered gate; the module beside it is a
verified-equivalent alternative and nothing invokes it yet.

WHAT "VERIFIED-EQUIVALENT" MEANS HERE. Each module has a differential under
`.ci/rediacc_ci/tests/` that runs BOTH subjects on the same fixture in the same
run and compares exit code, stdout, stderr and the recorded argv of every
external command, plus a K=5 shadow-gate ledger
(`.ci/shadow/w7p6-<slug>.observations.jsonl`) recorded through
`scripts/lib/shadow-gate.ts`. The differentials never invoke a real `go`, `sudo`
or `mount`: every one of those is a recording fake on a scratch PATH, because
the real ones need root, a bpffs and a Go toolchain, and a test that quietly
skipped when they were missing would be certifying nothing.

CUTOVER IS A SEPARATE, LATER BOX. `package.json:251` still spells
`"check:ci-renet": ".ci/scripts/private/run-renet.sh quality"`, and
`.github/workflows/ct-tests.yml:1718/1746/1752` still invoke all three bash
twins. Repointing any of those, and the `scripts/ci-runner/manifest.ts` `leaves`
that follow from it, is a driver-only step gated on the ledgers this box
produces. It is not done here.

Deliberately no re-exports, same reasoning as `rediacc_ci/__init__.py`: a
consumer should import exactly the module it needs.
"""

__all__: list[str] = []
