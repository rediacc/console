"""rediacc_ci -- the Python home of this repository's CI machinery.

WHAT THIS BECOMES. The tooling transformation moves the CI programs off bash and into one importable package. Phase 2 of W1 fills it in; the modules already arbitrated in docs/ci-overhaul/08-driver-contract.md are:

  rediacc_ci.core.env      env-file loading, taken over from .ci/lib/local-common.sh
  rediacc_ci.core.output   the one place a gate formats a verdict
  rediacc_ci.gates         the gate registry and its ``---- gate ----`` headers
  rediacc_ci.battery       the gate-test battery runner, which replaced
                           .ci/scripts/test/run-all.sh and outlived it

WHY THE PACKAGE EXISTS ALREADY, EMPTY. Two things had to be true before any of that could be written, and neither is about code:

  1. A PACKAGE MANAGER. pytest, uv, uvx, pip and pipx were all absent on the
     host these gates run on (measured 2026-09-06). .ci/bootstrap.sh is the
     answer, and this package is what it exists to make testable.
  2. A PACKAGE THE VACUITY FIXTURE CAN SEE.
     .ci/scripts/test/gates/test-gate-anti-vacuity.sh runs every registered gate
     inside a fixture tree built by copying a SHORT list of directories. Until
     ``.ci/rediacc_ci`` joined that list, any gate importing this package would
     have failed inside the fixture with ModuleNotFoundError -- a red that names
     neither the gate nor the real problem, on a harness whose entire job is
     telling a real failure from an absent input.

WHERE IT SITS ON sys.path. The package directory is ``.ci/rediacc_ci``, so the importable name is ``rediacc_ci`` with ``.ci`` on the path. A consumer adds the repo's ``.ci`` directory to ``sys.path`` -- the same shape .ci/scripts/test/gates/test-gate-anti-vacuity.sh already uses to import ``check_fetch_retry`` out of ``.ci/scripts/quality``.

Deliberately no re-exports: an ``__init__`` that imports its submodules turns every consumer into a consumer of all of them, and this one is imported by a fixture whose point is that most of the tree is absent.
"""

__all__: list[str] = []
