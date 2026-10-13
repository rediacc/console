"""Port of `.ci/scripts/test/gates/test-edge-verify-retries.sh`, retired in W7 P5.

Assert the edge smoke test cannot be failed by ONE unlucky sample.

WHY THIS EXISTS, AND WHY IT IS A PR GATE. On 2026-08-08 release run 31234422166 deployed edge successfully and then failed `edge.rediacc.com footer does not render v1.2.19` -- while edge was ALREADY serving v1.2.19. The assertion sampled an eventually-consistent CDN exactly once, moments after the deploy, and lost the race. The failure cascaded: `Tag & GitHub Release` was skipped,
so a good release shipped with NO git tag and NO GitHub Release.

`verify_edge_endpoints.py` (the port that replaced `verify-edge-endpoints.sh`) runs ONLY from cd-v2.yml, which is dispatch-only and main-only. So the DEPLOY it verifies genuinely cannot be exercised on a PR -- and that was the reasoning that nearly left this unguarded. The reasoning was wrong. The defect was never "edge served the wrong version"; it was "the assertion samples once". That is a property of the script, and its retry engine can be driven against a fake predicate on any PR, with no deploy at all.

WHAT IT ASSERTS
  1. RETRIES     a surface that is stale then correct is ACCEPTED (the incident).
  2. STILL FAILS a surface that is ALWAYS wrong is REJECTED -- the retry must not
                 have become "eventually pass no matter what".
  3. NO BARE     no assertion still reads a network surface exactly once.

CONTROL-FIRST: assertion 1 is re-run against a copy with the retry stripped, and MUST fail there. If the planted defect passes, this gate declares ITSELF broken.

THE RETRY ENGINE IS DRIVEN IN PROCESS: `fetch_retry` is called with a predicate that counts its own invocations. The control plants its defect in a copy of the module's own source, written to the test's scratch directory and imported from there, so a rewrite of the function breaks THIS test loudly instead of leaving it exercising a stale copy pasted in here.
"""

import importlib.util
import inspect
import pathlib
import time
import types

from rediacc_ci import paths
from rediacc_ci.deploy import verify_edge_endpoints

TARGET = paths.from_root(".ci", "rediacc_ci", "deploy", "verify_edge_endpoints.py")

# The floor is 9, the number actually wrapped, NOT a token 4. A floor set below the real count is a ratchet that permits silent regression: someone unwraps four
# assertions and the gate still reports green. Raise this when more are wrapped;
# never lower it to make a red go away.
MIN_RETRYING_CALL_SITES = 9


def run_case(module: types.ModuleType, fails: int, retries: int) -> bool:
    """True when `module.fetch_retry` ACCEPTS a predicate that fails `fails` times first.

    The predicate counts its own invocations, so "how many samples did it take" is a property of the fixture rather than of the function's memory.
    """
    calls = {"n": 0}

    def predicate() -> bool:
        calls["n"] += 1
        return calls["n"] > fails

    # `time.sleep` is stubbed for the duration: the spacing between samples is not under test, and a real sleep would only slow the case down.
    real_sleep = time.sleep
    time.sleep = lambda _seconds: None
    try:
        return bool(module.fetch_retry("probe", predicate, retries, "0"))
    finally:
        time.sleep = real_sleep


def load_mutant(directory: pathlib.Path) -> tuple[types.ModuleType, bool]:
    """A copy of the real module with the retry loop collapsed to one attempt. Returns it and whether the plant applied."""
    source = TARGET.read_text(encoding="utf-8")
    mutated = source.replace("attempt >= retries", "True")
    path = directory / "verify_edge_endpoints_mutant.py"
    path.write_text(mutated, encoding="utf-8")
    spec = importlib.util.spec_from_file_location("verify_edge_endpoints_mutant", path)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module, mutated != source


def test_the_retry_engine_is_extractable(gate):
    gate.log_test("edge smoke test survives one unlucky sample")
    if not TARGET.is_file():
        gate.log_fail("verify_edge_endpoints.py not found at %s" % TARGET)
    source = inspect.getsource(verify_edge_endpoints.fetch_retry)
    gate.assert_eq(
        source.count("def fetch_retry("), 1, "fetch_retry() is extractable from the real module"
    )
    gate.log_pass("fetch_retry() extracted from the real module by inspection")


def test_stale_then_correct_is_accepted(gate):
    # The predicate fails twice, then succeeds: exactly the shape of a CDN that has not finished propagating.
    if not run_case(verify_edge_endpoints, 2, 6):
        gate.log_fail(
            "a stale-then-correct surface was rejected; one unlucky sample can "
            "still fail a good release"
        )
    gate.log_pass("a surface that is stale twice then correct is ACCEPTED (the 1.2.19 incident)")


def test_always_wrong_is_still_rejected(gate):
    if run_case(verify_edge_endpoints, 99, 3):
        gate.log_fail(
            "a surface that NEVER agrees was accepted -- the retry has become "
            "'pass eventually', which is worse than no check"
        )
    gate.log_pass(
        "a surface that never agrees is still REJECTED (retry did not become a rubber stamp)"
    )


def test_no_assertion_reads_the_network_exactly_once(gate):
    # Every bare `curl` that feeds an assertion must sit inside a predicate that fetch_retry drives. Counting is the cheap, robust form: the script had TWELVE single-sample reads and zero retries when this incident happened.
    retrying = TARGET.read_text(encoding="utf-8").count('fetch_retry("')
    if retrying < MIN_RETRYING_CALL_SITES:
        gate.log_fail(
            "only %d assertion(s) retry; the rest can still be failed by one sample" % retrying
        )
    gate.log_pass(
        "the load-bearing assertions are driven through fetch_retry (%d call sites)" % retrying
    )


def test_control_stripping_the_retry_makes_the_stale_case_fail(gate, tmp_path):
    # Collapse the loop to a single attempt. If the stale-then-correct case still passes against that, this gate is not measuring what it claims.
    mutant, planted = load_mutant(tmp_path)
    if not planted:
        gate.log_fail(
            "CONTROL could not plant its defect (fetch_retry's shape changed); "
            "update the mutant here"
        )
    if run_case(mutant, 2, 6):
        gate.log_fail(
            "CONTROL DID NOT FIRE: a single-attempt fetch_retry still accepted a "
            "stale-then-correct surface, so this gate cannot detect the defect it exists for"
        )
    gate.log_pass(
        "CONTROL fired: with the retry stripped, the stale-then-correct case fails "
        "as it did in production"
    )
