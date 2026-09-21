"""The `gate` fixture, and the refusal that makes a green here mean something.

THE RULE, LIFTED VERBATIM FROM THE BATTERY RUNNER. `.ci/rediacc_ci/battery.py` scores a bash gate test that exits 0 without emitting a single `PASS:` line as a FAILURE, not a pass -- "exited 0 but made no assertions". That refusal is the only thing standing between a gate test whose body stopped executing and a battery that simply got faster. pytest has no equivalent: a test
function whose body is `pass` is a passing test, and a test whose fixture silently returned early looks identical to one that asserted forty things.

So the fixture counts, and its teardown refuses a test that recorded nothing.

IT REFUSES ONLY ON A TEST THAT OTHERWISE PASSED, and that ordering is deliberate. A test that already failed has a real diagnostic; raising a second, vaguer error on top of it in teardown replaces the message a reader needs with one they do not. The outcome is read from the `call`-phase report, which pytest has already produced by the time a function-scoped fixture is torn down.
"""

import os

import pytest

from rediacc_ci.tests.gates import harness

_OUTCOME = pytest.StashKey[str]()


@pytest.hookimpl(wrapper=True)
def pytest_runtest_makereport(item, call):  # noqa: ARG001
    report = yield
    if report.when == "call":
        item.stash[_OUTCOME] = report.outcome
    return report


@pytest.fixture
def gate(request):
    """One `Harness` per test, torn down with the anti-vacuity refusal.

    `request.node.module.__name__` is the dotted module path, which is what the ledger keys on and therefore what `test_twin_parity.py` groups by.
    """
    handle = harness.Harness(
        request.node.module.__name__,
        request.node.name,
        ledger=os.environ.get(harness.LEDGER_ENV),
    )
    yield handle
    # "failed" as the default when no report was stashed: an item that never reached its call phase is not evidence of anything, and defaulting to "passed" would let a collection-time abort satisfy the check below.
    if request.node.stash.get(_OUTCOME, "failed") != "passed":
        return
    if not handle.passes:
        raise harness.GateAssertionError(
            "%s exited green without recording a single control. A test that asserts "
            "nothing reads exactly like one that asserts everything, which is the "
            "shape the battery refuses on the bash side ('exited 0 but made no "
            "assertions'). Call gate.log_pass() or gate.ok() for each thing proved."
            % request.node.name
        )
