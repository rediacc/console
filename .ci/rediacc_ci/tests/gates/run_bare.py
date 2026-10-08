"""Run a ported gate-test module with nothing but the standard library.

    PYTHONPATH=.ci python3 -m rediacc_ci.tests.gates.run_bare rediacc_ci.tests.gates.test_gate_run_sh

WHY IT EXISTS. The `Entry Point (run.sh)` job runs on the bare `ubuntu-slim` runner, where there is a `python3` and no pytest, and the bash twin it ran (`test-run-sh.sh`) is gone. The ported module needs only `harness.Harness`, which is standard library, and its tests all take the single argument `gate`; the pytest `gate` fixture in `conftest.py` is the one pytest-shaped thing, and this module reproduces it in a loop.

WHAT IS KEPT FROM THE FIXTURE, because a bare runner that dropped either refusal would be a quieter pytest:

  * a test whose `gate.no()` tally holds a failure that no `tally_finish` raised is a failure, not a pass;
  * a test that exited green with zero recorded controls is a failure ("exited 0 but made no assertions").

Two refusals pytest never needed, because collection gives them for free there:

  * a module with no `test_*` function at all is a failure, so an import that found nothing cannot report green;
  * a test taking any argument other than `gate` and `tmp_path` is a failure, because this runner provides only `gate` and `tmp_path` (a fresh `tempfile.TemporaryDirectory()` as a `pathlib.Path`, removed after the test), and skipping any other argument would run a different test than the one written.

A failed assertion ends that test only. Any other exception is a defect in the test or the runner and propagates with its traceback, which exits 1.

Exit status: 0 when every test passed, 1 on any failure or refusal, 2 on a bad command line.
"""

from __future__ import annotations

import importlib
import inspect
import os
import pathlib
import sys
import tempfile
import traceback
from typing import TYPE_CHECKING

from rediacc_ci.tests.gates import harness

if (
    TYPE_CHECKING
):  # annotation-only, so the runner still imports nothing beyond the standard library at run time
    from collections.abc import Callable
    from types import FunctionType, ModuleType


def collect(module: ModuleType) -> list[tuple[str, FunctionType]]:
    """The module's own `test_*` functions, in definition order."""
    found: list[tuple[str, FunctionType]] = [
        (name, value)
        for name, value in vars(module).items()
        if name.startswith("test_")
        and inspect.isfunction(value)
        and value.__module__ == module.__name__
    ]
    found.sort(key=lambda pair: pair[1].__code__.co_firstlineno)
    return found


def refusal(function: Callable[..., object]) -> str | None:
    """Why this runner cannot run `function`, or None."""
    parameters = list(inspect.signature(function).parameters)
    if parameters not in (["gate"], ["gate", "tmp_path"]):
        return "takes %r; the bare runner provides only `gate` and `tmp_path`" % (parameters,)
    return None


def run_one(module_name: str, name: str, function: Callable[..., object]) -> str | None:
    """Run one test against a fresh Harness. None on a pass, else the failure text."""
    handle = harness.Harness(module_name, name, ledger=os.environ.get(harness.LEDGER_ENV))
    wants_tmp = "tmp_path" in inspect.signature(function).parameters
    try:
        if wants_tmp:
            with tempfile.TemporaryDirectory() as scratch:
                function(handle, pathlib.Path(scratch))
        else:
            function(handle)
    except AssertionError as exc:
        return "".join(traceback.format_exception(exc)).rstrip("\n")
    if handle.tally_fails:
        return (
            "%s\n%s recorded a failure with gate.no() and returned without calling "
            "gate.tally_finish(), so nothing raised on it." % (handle.tally_verdict(name), name)
        )
    if not handle.passes:
        return (
            "%s exited green without recording a single control (exited 0 but made no "
            "assertions)." % name
        )
    return None


def run_module(module_name: str) -> int:
    module = importlib.import_module(module_name)
    tests = collect(module)
    if not tests:
        print(
            "run_bare: %s defines no test_* function; nothing was proved" % module_name,
            file=sys.stderr,
        )
        return 1
    failed = 0
    for name, function in tests:
        reason = refusal(function)
        failure = "refused: %s" % reason if reason else run_one(module_name, name, function)
        if failure is None:
            print("ok   %s" % name)
            continue
        failed += 1
        print("FAIL %s\n%s" % (name, failure), file=sys.stderr)
    print("run_bare: %s: %d test(s), %d failed" % (module_name, len(tests), failed))
    return 1 if failed else 0


def main(argv: list[str]) -> int:
    if len(argv) != 1 or argv[0] in ("-h", "--help"):
        print(__doc__)
        return 2
    return run_module(argv[0])


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
