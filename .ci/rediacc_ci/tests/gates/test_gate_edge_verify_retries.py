"""Port of `.ci/scripts/test/gates/test-edge-verify-retries.sh`, retired in W7 P5.

Assert the edge smoke test cannot be failed by ONE unlucky sample.

WHY THIS EXISTS, AND WHY IT IS A PR GATE. On 2026-08-08 release run 31234422166 deployed edge successfully and then failed `edge.rediacc.com footer does not render v1.2.19` -- while edge was ALREADY serving v1.2.19. The assertion sampled an eventually-consistent CDN exactly once, moments after the deploy, and lost the race. The failure cascaded: `Tag & GitHub Release` was skipped,
so a good release shipped with NO git tag and NO GitHub Release.

`verify-edge-endpoints.sh` runs ONLY from cd-v2.yml, which is dispatch-only and main-only. So the DEPLOY it verifies genuinely cannot be exercised on a PR -- and that was the reasoning that nearly left this unguarded. The reasoning was wrong. The defect was never "edge served the wrong version"; it was "the assertion samples once". That is a property of a shell script, and a shell
script can be driven against a FAKE curl on any PR, with no deploy at all.

WHAT IT ASSERTS
  1. RETRIES     a surface that is stale then correct is ACCEPTED (the incident).
  2. STILL FAILS a surface that is ALWAYS wrong is REJECTED -- the retry must not
                 have become "eventually pass no matter what".
  3. NO BARE     no assertion still reads a network surface exactly once.

CONTROL-FIRST: assertion 1 is re-run against a copy with the retry stripped, and MUST fail there. If the planted defect passes, this gate declares ITSELF broken.

THE TWIN IS A FLAT SCRIPT with no `test_*()` functions, so the port chooses the split: one pytest test per numbered assertion above, plus the control. Every `log_pass` line in the twin survives, one per test, which is what `test_twin_parity.py` counts.
"""

import pathlib
import re

from rediacc_ci import paths
from rediacc_ci.tests.gates import harness

TARGET = paths.from_root(".ci", "scripts", "deploy", "verify-edge-endpoints.sh")

# The floor is 9, the number actually wrapped, NOT a token 4. A floor set below the real count is a ratchet that permits silent regression: someone unwraps four
# assertions and the gate still reports green. Raise this when more are wrapped;
# never lower it to make a red go away.
MIN_RETRYING_CALL_SITES = 9

# `fetch_retry() {` .. the closing `}` at column 0. Extraction BY ANCHOR, so a
# rename or a rewrite breaks THIS test loudly instead of leaving it exercising a stale copy pasted in here.
FN_RE = re.compile(r"^fetch_retry\(\) \{.*?^\}", re.MULTILINE | re.DOTALL)


def fetch_retry_source() -> str:
    match = FN_RE.search(TARGET.read_text(encoding="utf-8"))
    return match.group(0) if match else ""


def run_case(fn_source: str, fails: int, retries: int, state: pathlib.Path) -> bool:
    """True when `fetch_retry` ACCEPTS a predicate that fails `fails` times first.

    The predicate counts its own invocations in a file, so "how many samples did it take" is a property of the fixture rather than of the shell's memory.
    """
    state.write_text("0\n", encoding="utf-8")
    program = (
        "set -eu\n" + fn_source + "\n"
        '_p() {\n  n=$(cat "$STATE"); n=$((n + 1)); echo "$n" >"$STATE"\n'
        '  [ "$n" -gt "$FAILS" ]\n}\n'
        "fetch_retry probe _p\n"
    )
    result = harness.run(
        ["bash", "-c", program],
        env={
            "EDGE_RETRIES": str(retries),
            "EDGE_RETRY_SLEEP": "0",
            "STATE": str(state),
            "FAILS": str(fails),
        },
    )
    return result.rc == 0


def test_the_extractor_matches_the_twins_awk(gate):
    """CONTROL FOR THE PORT ITSELF. The twin extracts the function with an awk
    RANGE (`/^fetch_retry\\(\\) \\{/,/^\\}/`); this file uses a Python regex. A
    port that swaps the reader without comparing it against the original has replaced a tested extractor with an untested one, and every case below would then be exercising whatever the new one happened to grab."""
    awk = harness.run(["awk", r"/^fetch_retry\(\) \{/,/^\}/", str(TARGET)])
    gate.assert_exit(0, awk, "the twin's awk still runs")
    gate.assert_eq(
        fetch_retry_source() + "\n", awk.out, "the Python extractor agrees with the awk one"
    )
    gate.assert_contains(awk.out, "fetch_retry() {", "and it really extracted the function")
    gate.log_pass("the ported extractor is byte-identical to the twin's awk range")


def test_the_retry_engine_is_extractable(gate):
    gate.log_test("edge smoke test survives one unlucky sample")
    if not TARGET.is_file():
        gate.log_fail("verify-edge-endpoints.sh not found at %s" % TARGET)
    source = fetch_retry_source()
    gate.assert_eq(
        source.count("fetch_retry() {"), 1, "fetch_retry() is extractable from the real script"
    )
    gate.log_pass("fetch_retry() extracted from the real script by anchor")


def test_stale_then_correct_is_accepted(gate, tmp_path):
    # The predicate fails twice, then succeeds: exactly the shape of a CDN that has not finished propagating.
    if not run_case(fetch_retry_source(), 2, 6, tmp_path / "state"):
        gate.log_fail(
            "a stale-then-correct surface was rejected; one unlucky sample can "
            "still fail a good release"
        )
    gate.log_pass("a surface that is stale twice then correct is ACCEPTED (the 1.2.19 incident)")


def test_always_wrong_is_still_rejected(gate, tmp_path):
    if run_case(fetch_retry_source(), 99, 3, tmp_path / "state"):
        gate.log_fail(
            "a surface that NEVER agrees was accepted -- the retry has become "
            "'pass eventually', which is worse than no check"
        )
    gate.log_pass(
        "a surface that never agrees is still REJECTED (retry did not become a rubber stamp)"
    )


def test_no_assertion_reads_the_network_exactly_once(gate):
    # Every bare `curl` that feeds an assertion must sit inside a predicate that fetch_retry drives. Counting is the cheap, robust form: the script had TWELVE single-sample reads and zero retries when this incident happened.
    retrying = TARGET.read_text(encoding="utf-8").count('fetch_retry "')
    if retrying < MIN_RETRYING_CALL_SITES:
        gate.log_fail(
            "only %d assertion(s) retry; the rest can still be failed by one sample" % retrying
        )
    gate.log_pass(
        "the load-bearing assertions are driven through fetch_retry (%d call sites)" % retrying
    )


def test_control_stripping_the_retry_makes_the_stale_case_fail(gate, tmp_path):
    # Collapse the loop to a single attempt. If the stale-then-correct case still passes against that, this gate is not measuring what it claims.
    #
    # ONE substitution, and it must be effective. The first version of this control also tried `EDGE_RETRIES:-6 -> :-1`, which matched NOTHING: the extraction
    # starts at `fetch_retry() {` and the default assignment lives ABOVE the
    # function, so it was never in scope. The control still fired -- via the second
    # substitution alone -- which is exactly the shape that hides a dead check.
    source = fetch_retry_source()
    mutant = source.replace('"$attempt" -ge "$EDGE_RETRIES"', "true")
    if mutant == source:
        gate.log_fail(
            "CONTROL could not plant its defect (fetch_retry's shape changed); "
            "update the mutant here"
        )
    if run_case(mutant, 2, 6, tmp_path / "state"):
        gate.log_fail(
            "CONTROL DID NOT FIRE: a single-attempt fetch_retry still accepted a "
            "stale-then-correct surface, so this gate cannot detect the defect it exists for"
        )
    gate.log_pass(
        "CONTROL fired: with the retry stripped, the stale-then-correct case fails "
        "as it did in production"
    )
