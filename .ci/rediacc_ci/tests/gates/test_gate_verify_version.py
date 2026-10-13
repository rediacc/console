"""Port of `.ci/scripts/test/gates/test-verify-version.sh`, retired in W7 P5.

Tests for `verify_version()` in `rediacc_ci.testrun.install_methods` (written against the bash `verify_version()` of `test-install-methods.sh`, retired behind its golden, PLAN-retire-bash-oracles B3).

WHY THIS EXISTS. On 2026-08-07 release run 31154305287 published CLI binaries built as 1.2.16 under the label 1.2.17. Two guards passed silently, and underneath both sat this one primitive, whose whole body was

    echo "$output" | grep -q "$expected"

which reports success in three situations where nothing was verified: an EMPTY expectation (`grep -q ""` matches any line), EMPTY output (a binary that did not run, or whose output was discarded by `|| true`), and a SUBSTRING match, so 1.2.1 "verified" against a binary reporting 1.2.16. The dots are regex wildcards on top of that.

The rule being pinned: there is ALWAYS a version, or it fails. A caller that genuinely cannot determine one must SKIP visibly, never hand an empty string to this and take the pass.

THE SUBJECT IS CALLED IN PROCESS. The module's `verify_version` is a pure function, so every call is a plain call and no case can leave state behind for the next one. (The bash gate lifted the function out of the script by an anchored awk range and ran each call in its own `bash -c`.)
"""

from rediacc_ci.testrun import install_methods as port
from rediacc_ci.tests.gates import harness

# The EXACT pre-fix body, re-created. Not a mutation of the current one: a mutation drifts with the subject, and the point of this control is that the shape which shipped the incident really did admit both silent-pass classes.
OLD_BODY = """
old_verify() {
    local output="$1" expected="$2"
    if [[ "$expected" == "latest" ]]; then
        [[ -n "$output" ]] && grep -qE '^v?[0-9]+\\.[0-9]+\\.[0-9]+(-[a-zA-Z0-9.]+)?$' <<<"$output"
    else
        grep -q "$expected" <<<"$output"
    fi
}
"""


def vv(gate, output: str, expected: str) -> int:
    """0 when verify_version ACCEPTED, 1 when it refused. The retired gate's `vv`."""
    del gate
    return 0 if port.verify_version(output, expected) else 1


def old_verify(output: str, expected: str) -> int:
    """0 when the PRE-FIX body accepted. Same convention as `vv`."""
    script = OLD_BODY + '\nold_verify "$1" "$2" >/dev/null 2>&1 && echo 0 || echo 1\n'
    result = harness.run(["bash", "-c", script, "old-verify-port", output, expected])
    return int(result.out.strip() or "-1")


def test_real_versions_are_accepted(gate):
    gate.assert_eq(vv(gate, "rdc 1.2.17", "1.2.17"), 0, "an exact match must pass")
    gate.assert_eq(vv(gate, "v1.2.17", "1.2.17"), 0, "a v-prefixed output must pass")
    gate.assert_eq(vv(gate, "rdc 1.2.17", "v1.2.17"), 0, "a v-prefixed expectation must pass")
    gate.assert_eq(
        vv(gate, "rediacc rdc 1.2.17 (linux)", "1.2.17"),
        0,
        "the version may sit inside a longer line",
    )
    gate.log_pass("well-formed versions are accepted")


def test_missing_version_never_passes(gate):
    # The founding defect class: nothing was established, yet grep said yes.
    gate.assert_eq(vv(gate, "rdc 1.2.17", ""), 1, "an EMPTY expectation must never pass")
    gate.assert_eq(vv(gate, "", "1.2.17"), 1, "EMPTY output must never pass")
    gate.assert_eq(vv(gate, "", ""), 1, "both empty must never pass")
    gate.log_pass("a version that could not be established fails instead of passing")


def test_substring_matches_are_refused(gate):
    # This is how a patch release would "verify" against the wrong build.
    gate.assert_eq(vv(gate, "rdc 1.2.16", "1.2.1"), 1, "1.2.1 must NOT match 1.2.16")
    gate.assert_eq(vv(gate, "rdc 11.2.1", "1.2.1"), 1, "1.2.1 must NOT match 11.2.1")
    gate.assert_eq(vv(gate, "rdc 1x2y17", "1.2.17"), 1, "dots must not behave as regex wildcards")
    gate.assert_eq(vv(gate, "rdc 1.2.16", "1.2.17"), 1, "a genuinely wrong version must fail")
    gate.log_pass("substring and regex matches are refused")


def test_latest_still_requires_a_real_version(gate):
    gate.assert_eq(vv(gate, "1.2.17", "latest"), 0, "latest accepts a well-formed semver")
    gate.assert_eq(vv(gate, "1.2.17-rc.1", "latest"), 0, "latest accepts a prerelease")
    gate.assert_eq(vv(gate, "command not found", "latest"), 1, "latest must reject garbage")
    gate.assert_eq(vv(gate, "", "latest"), 1, "latest must reject empty output")
    gate.log_pass("latest means any REAL version, not any output")


def test_the_founding_defect_fires(gate):
    """The control on every case above: the OLD body must ACCEPT what the new one refuses. If it did not, these tests would be decorative and would have let the incident through unchanged."""
    gate.assert_eq(
        old_verify("rdc 1.2.17", ""),
        0,
        "the OLD body must accept an empty expectation, or this test proves nothing",
    )
    gate.assert_eq(
        old_verify("rdc 1.2.16", "1.2.1"),
        0,
        "the OLD body must accept 1.2.1 against 1.2.16, or this test proves nothing",
    )
    gate.log_pass("the old implementation really did admit both silent-pass classes")


def test_the_subject_is_the_modules_own_function(gate):
    """The cases above call `port.verify_version` directly; a rename or removal makes this module fail to import rather than pass over nothing."""
    gate.assert_eq(callable(port.verify_version), True, "verify_version must exist and be callable")
    gate.log_pass("verify_version() is present in rediacc_ci.testrun.install_methods")
