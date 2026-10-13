"""rediacc_ci -- the Python home of this repository's CI machinery.

WHAT THIS BECOMES. The tooling transformation moves the CI programs off bash and into one importable package. Phase 2 of W1 fills it in; the modules already arbitrated in docs/ci-overhaul/08-driver-contract.md are:

  rediacc_ci.core.env      env-file loading, taken over from .ci/lib/local-common.sh
  rediacc_ci.core.output   the one place a gate formats a verdict
  rediacc_ci.gates         the gate registry and its ``---- gate ----`` headers

WHY THE PACKAGE EXISTS ALREADY, EMPTY. Two things had to be true before any of that could be written, and neither is about code:

  1. A PACKAGE MANAGER. pytest, uv, uvx, pip and pipx were all absent on the
     host these gates run on (measured 2026-09-06). .ci/bootstrap.sh is the
     answer, and this package is what it exists to make testable.
  2. A PACKAGE THE VACUITY FIXTURE CAN SEE.
     .ci/rediacc_ci/tests/gates/test_gate_gate_anti_vacuity.py runs every registered gate
     inside a fixture tree built by copying a SHORT list of directories. Until
     ``.ci/rediacc_ci`` joined that list, any gate importing this package would
     have failed inside the fixture with ModuleNotFoundError -- a red that names
     neither the gate nor the real problem, on a harness whose entire job is
     telling a real failure from an absent input.

WHERE IT SITS ON sys.path. The package directory is ``.ci/rediacc_ci``, so the importable name is ``rediacc_ci`` with ``.ci`` on the path. A consumer adds the repo's ``.ci`` directory to ``sys.path`` -- the same shape .ci/rediacc_ci/tests/gates/test_gate_gate_anti_vacuity.py already uses to import ``check_fetch_retry`` out of ``.ci/scripts/quality``.

Deliberately no re-exports: an ``__init__`` that imports its submodules turns every consumer into a consumer of all of them, and this one is imported by a fixture whose point is that most of the tree is absent.
"""

import os as _os


def _pin_pythonpath() -> None:
    """Make every relative `PYTHONPATH` entry absolute, once, against the directory this process started in.

    Every workflow starts a module as `PYTHONPATH=.ci python3 -m rediacc_ci.<x>`, and a child process inherits that relative `.ci`. A module that changes directory and then starts a sibling with `sys.executable -m rediacc_ci.<y>` hands the child a path that now points nowhere: build_cli_executables did exactly that after `os.chdir(packages/cli)`, and every CLI build leg failed with "No module named 'rediacc_ci'" (console run 38350834911). Pinning the entries here, at the first import of the package and before any module can have changed directory, closes it for every such spawn instead of one call site. An empty entry means the current directory to Python and is pinned too.
    """
    raw = _os.environ.get("PYTHONPATH")
    if raw is None:
        return
    here = _os.getcwd()
    pinned = _os.pathsep.join(
        entry if _os.path.isabs(entry) else _os.path.normpath(_os.path.join(here, entry))
        for entry in raw.split(_os.pathsep)
    )
    if pinned != raw:
        _os.environ["PYTHONPATH"] = pinned


_pin_pythonpath()

__all__: list[str] = []
